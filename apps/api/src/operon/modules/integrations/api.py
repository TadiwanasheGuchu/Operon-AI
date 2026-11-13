from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from operon.access.context import Actor, TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core.db import set_rls_context
from operon.core.deps import DatabaseDep, SessionDep, SettingsDep
from operon.core.errors import ApiError
from operon.modules.audit import service as audit
from operon.modules.integrations import credentials, csv_import, service
from operon.modules.integrations.connectors.registry import REMOTE_CONNECTORS
from operon.modules.integrations.connectors.shopify import ShopifyConnector
from operon.modules.integrations.dispatch import SyncDispatcher
from operon.modules.integrations.models import Connection, InboundEvent
from operon.modules.integrations.schemas import (
    CatalogueEntry,
    CheckOut,
    ConnectionOut,
    CreateConnectionRequest,
    EventOut,
    RotateCredentialsRequest,
    SyncJobOut,
    UpdateConnectionRequest,
    UploadResult,
)
from operon.modules.integrations.sync import SyncRuntime
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["integrations"])
webhooks = APIRouter(tags=["webhooks"])

IntRead = Annotated[TenantContext, Depends(require_permission(Perm.INTEGRATIONS_READ))]
IntManage = Annotated[TenantContext, Depends(require_permission(Perm.INTEGRATIONS_MANAGE))]
MAX_WEBHOOK_BYTES = 1024 * 1024


def _rt(request: Request) -> SyncRuntime:
    rt: SyncRuntime = request.app.state.sync_runtime
    return rt


def _dispatcher(request: Request) -> SyncDispatcher:
    d: SyncDispatcher = request.app.state.dispatcher
    return d


def _out(conn: Connection, request: Request, has_secret: bool = False) -> ConnectionOut:
    supports = (
        conn.connector in REMOTE_CONNECTORS and REMOTE_CONNECTORS[conn.connector].supports_webhooks
    )
    base = str(request.base_url).rstrip("/")
    return ConnectionOut(
        id=conn.id,
        connector=conn.connector,
        name=conn.name,
        status=conn.status,
        config={k: v for k, v in conn.config.items() if k != "sync_interval_minutes"},
        sync_interval_minutes=int(conn.config.get("sync_interval_minutes", 15)),
        last_sync_at=conn.last_sync_at,
        last_success_at=conn.last_success_at,
        last_error=conn.last_error,
        created_at=conn.created_at,
        webhook_url=f"{base}/api/v1/webhooks/{conn.public_id}" if supports else None,
        has_webhook_secret=has_secret,
    )


@router.get("/integrations/catalogue", response_model=list[CatalogueEntry])
async def catalogue(_: IntRead) -> list[CatalogueEntry]:
    return service.catalogue()


@router.get("/integrations", response_model=list[ConnectionOut])
async def list_connections(
    ctx: IntRead, session: SessionDep, request: Request
) -> list[ConnectionOut]:
    from sqlalchemy import select

    rows = await session.scalars(
        select(Connection)
        .where(Connection.organisation_id == ctx.organisation_id)
        .order_by(Connection.created_at)
    )
    return [_out(c, request) for c in rows.all()]


@router.post("/integrations", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    body: CreateConnectionRequest,
    ctx: IntManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ConnectionOut:
    conn, _ = await service.create_connection(session, ctx, _rt(request), body, meta)
    if conn.connector != "csv":
        dispatcher = _dispatcher(request)
        org, cid = ctx.organisation_id, conn.id
        minutes = int(conn.config.get("sync_interval_minutes", 15))
        # After commit: the worker must see the connection.
        background.add_task(dispatcher.ensure_schedule, org, cid, minutes, False)
        background.add_task(dispatcher.request_sync, org, cid, "initial")
    return _out(conn, request, bool(body.secrets.get("webhook_secret")))


@router.get("/integrations/{connection_id}", response_model=ConnectionOut)
async def get_connection(
    connection_id: UUID, ctx: IntRead, session: SessionDep, request: Request
) -> ConnectionOut:
    conn = await service.get_connection(session, ctx, connection_id)
    has_secret = False
    if conn.connector == "shopify":
        has_secret = bool(
            (await credentials.load(session, _rt(request).box, conn.id)).get("webhook_secret")
        )
    return _out(conn, request, has_secret)


@router.patch("/integrations/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: UUID,
    body: UpdateConnectionRequest,
    ctx: IntManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ConnectionOut:
    conn = await service.get_connection(session, ctx, connection_id)
    conn = await service.update_connection(
        session,
        ctx,
        conn,
        name=body.name,
        interval=body.sync_interval_minutes,
        paused=body.paused,
        meta=meta,
    )
    if conn.connector != "csv" and (
        body.sync_interval_minutes is not None or body.paused is not None
    ):
        background.add_task(
            _dispatcher(request).ensure_schedule,
            ctx.organisation_id,
            conn.id,
            int(conn.config.get("sync_interval_minutes", 15)),
            conn.status == "paused",
        )
    return _out(conn, request)


@router.put("/integrations/{connection_id}/credentials", response_model=CheckOut)
async def rotate_credentials(
    connection_id: UUID,
    body: RotateCredentialsRequest,
    ctx: IntManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> CheckOut:
    conn = await service.get_connection(session, ctx, connection_id)
    summary = await service.rotate_credentials(session, ctx, _rt(request), conn, body.secrets, meta)
    # A sync proves the new credentials; only that changes the connection's status.
    if conn.status != "paused":
        background.add_task(
            _dispatcher(request).request_sync, ctx.organisation_id, conn.id, "manual"
        )
    return CheckOut(ok=True, summary=summary, provides=[], message=None)


@router.post("/integrations/{connection_id}/test", response_model=CheckOut)
async def test_connection(
    connection_id: UUID, ctx: IntManage, session: SessionDep, request: Request
) -> CheckOut:
    conn = await service.get_connection(session, ctx, connection_id)
    try:
        check = await service.check_existing(session, _rt(request), conn)
    except ApiError as exc:
        return CheckOut(ok=False, summary=None, provides=[], message=exc.message)
    return CheckOut(ok=True, summary=check.summary, provides=list(check.capabilities), message=None)


@router.post("/integrations/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_now(
    connection_id: UUID,
    ctx: IntManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> dict[str, str]:
    conn = await service.get_connection(session, ctx, connection_id)
    if conn.connector == "csv":
        raise ApiError(409, "not_syncable", "CSV imports update when you upload a file.")
    if conn.status == "paused":
        raise ApiError(409, "paused", "Resume this connection before syncing.")
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="integration.sync_requested",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="integration",
        target_id=conn.id,
    )
    background.add_task(_dispatcher(request).request_sync, ctx.organisation_id, conn.id, "manual")
    return {"status": "requested"}


@router.delete("/integrations/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    connection_id: UUID,
    ctx: IntManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> None:
    conn = await service.get_connection(session, ctx, connection_id)
    remote = conn.connector != "csv"
    await service.disconnect(session, ctx, conn, meta)
    if remote:
        background.add_task(_dispatcher(request).remove_schedule, connection_id)


@router.get("/integrations/{connection_id}/sync-jobs", response_model=list[SyncJobOut])
async def sync_jobs(
    connection_id: UUID,
    ctx: IntRead,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncJobOut]:
    conn = await service.get_connection(session, ctx, connection_id)
    return [
        SyncJobOut.model_validate(j, from_attributes=True)
        for j in await service.list_jobs(session, conn, limit)
    ]


@router.get("/integrations/{connection_id}/events", response_model=list[EventOut])
async def events(
    connection_id: UUID,
    ctx: IntRead,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EventOut]:
    conn = await service.get_connection(session, ctx, connection_id)
    return [
        EventOut.model_validate(e, from_attributes=True)
        for e in await service.list_events(session, conn, limit)
    ]


@router.post("/integrations/{connection_id}/uploads", response_model=UploadResult)
async def upload(
    connection_id: UUID,
    ctx: IntManage,
    session: SessionDep,
    settings: SettingsDep,
    meta: MetaDep,
    request: Request,
    background: BackgroundTasks,
    kind: Annotated[csv_import.Kind, Form()],
    file: Annotated[UploadFile, File()],
) -> UploadResult:
    conn = await service.get_connection(session, ctx, connection_id)
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise ApiError(
            413,
            "file_too_large",
            f"Files are limited to {settings.max_upload_bytes // (1024 * 1024)} MB.",
        )
    result = await service.upload_csv(
        session, ctx, conn, kind, content, file.filename or "upload.csv", meta
    )
    # After commit: re-evaluate detectors against the new data.
    if result.accepted:
        background.add_task(_rt(request).data_changed, ctx.organisation_id, "upload")
    return result


@router.get("/integrations/csv-templates/{kind}", response_class=PlainTextResponse)
async def csv_template(
    kind: Literal["locations", "products", "supplier_terms", "stock", "sales", "purchase_orders"],
    _: IntRead,
) -> PlainTextResponse:
    return PlainTextResponse(
        csv_import.template(kind),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="operon-{kind}-template.csv"'},
    )


# --- webhooks (public, signature-verified) ------------------------------------------------------


@webhooks.post("/webhooks/{public_id}", summary="Inbound webhook from a connected system")
async def receive_webhook(
    public_id: str,
    request: Request,
    session: SessionDep,
    db: DatabaseDep,
    background: BackgroundTasks,
    meta: MetaDep,
) -> dict[str, str]:
    if not 20 <= len(public_id) <= 64:
        raise ApiError(404, "not_found", "Unknown webhook address.")
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise ApiError(413, "payload_too_large", "Payload too large.")
    row = (
        await session.execute(
            text("SELECT id, organisation_id FROM operon_connection_by_public_id(:p)"),
            {"p": public_id},
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Unknown webhook address.")
    await set_rls_context(session, organisation_id=row.organisation_id)
    conn = await session.get(Connection, row.id)
    # Shopify is the only connector with webhooks today; add verifiers here as others gain them.
    if conn is None or conn.connector != ShopifyConnector.key:
        raise ApiError(404, "not_found", "Unknown webhook address.")
    connector = ShopifyConnector
    secrets = connector.secrets_model.model_validate(
        await credentials.load(session, _rt(request).box, conn.id)
    )
    event = connector.verify_webhook(
        {k.lower(): v for k, v in request.headers.items()}, body, secrets
    )
    if event is None:
        await audit.record_independent(
            db,
            actor=Actor("system", None, "webhook"),
            action="integration.webhook_rejected",
            outcome="failure",
            meta=meta,
            organisation_id=conn.organisation_id,
            target_type="integration",
            target_id=conn.id,
            details={"reason": "invalid or missing signature"},
        )
        raise ApiError(401, "invalid_signature", "Signature verification failed.")
    relevant = connector.is_relevant(event.topic)
    inserted = (
        await session.execute(
            insert(InboundEvent)
            .values(
                organisation_id=conn.organisation_id,
                connection_id=conn.id,
                source_event_id=event.source_event_id,
                topic=event.topic,
                status="pending" if relevant else "ignored",
            )
            .on_conflict_do_nothing(index_elements=["connection_id", "source_event_id"])
            .returning(InboundEvent.id)
        )
    ).first()
    if inserted is None:
        return {"status": "duplicate"}
    if not relevant or conn.status == "paused":
        return {"status": "ignored"}
    background.add_task(_dispatcher(request).request_sync, conn.organisation_id, conn.id, "webhook")
    return {"status": "accepted"}
