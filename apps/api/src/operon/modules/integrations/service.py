"""Connections: create, test, configure, rotate credentials, disconnect; CSV uploads."""

import secrets as pysecrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.errors import ApiError
from operon.modules.audit import service as audit
from operon.modules.integrations import credentials, csv_import
from operon.modules.integrations.connectors.base import (
    ConnectionCheck,
    ConnectorContext,
    ConnectorError,
)
from operon.modules.integrations.connectors.registry import REMOTE_CONNECTORS
from operon.modules.integrations.models import Connection, InboundEvent, SyncJob
from operon.modules.integrations.schemas import (
    CatalogueEntry,
    CatalogueField,
    CreateConnectionRequest,
    UploadError,
    UploadResult,
)
from operon.modules.integrations.sync import SyncRuntime
from operon.modules.operations.models import Location, Product
from operon.modules.operations.store import EntityStats, Store

NOT_FOUND = ApiError(404, "not_found", "The requested resource was not found.")
CSV_PROVIDES = ["locations", "products", "supplier terms", "stock", "sales", "purchase orders"]
VERIFICATION = {
    "odoo": (
        False,
        "Built to Odoo's published external API (JSON-2 and JSON-RPC) and tested "
        "against a protocol-level test server. Not yet verified against a live Odoo.",
    ),
    "shopify": (
        False,
        "Built to Shopify's GraphQL Admin API (2025-10) and tested against a "
        "protocol-level test server. Not yet verified against a live store.",
    ),
    "csv": (True, "Fully supported."),
}
FIELD_HELP = {
    "url": "Your Odoo address, e.g. https://acme.odoo.com",
    "database": "The Odoo database name",
    "username": "Login of the Odoo user the API key belongs to",
    "api_version": "Leave on auto unless your administrator says otherwise",
    "api_key": "Odoo: Preferences → Account Security → New API key",
    "shop_domain": "e.g. acme.myshopify.com",
    "access_token": "Admin API access token of a custom app with read_products, "
    "read_inventory, read_locations and read_orders scopes",
    "webhook_secret": "The custom app's API secret key (optional, enables instant updates)",
}


def catalogue() -> list[CatalogueEntry]:
    entries = []
    for key, cls in REMOTE_CONNECTORS.items():
        fields = []
        for model, secret in ((cls.config_model, False), (cls.secrets_model, True)):
            for name, f in model.model_fields.items():
                choices = None
                if name == "api_version":
                    choices = ["auto", "json2", "jsonrpc"]
                fields.append(
                    CatalogueField(
                        name=name,
                        label=name.replace("_", " ").capitalize(),
                        secret=secret,
                        required=f.is_required(),
                        help=FIELD_HELP.get(name),
                        choices=choices,
                    )
                )
        provides = (
            [
                "locations",
                "suppliers",
                "products",
                "supplier terms",
                "stock",
                "sales",
                "purchase orders",
            ]
            if key == "odoo"
            else ["locations", "products", "stock", "sales"]
        )
        verified, note = VERIFICATION[key]
        entries.append(
            CatalogueEntry(
                key=key,
                name=cls.name,
                description=cls.description,
                provides=provides,
                fields=fields,
                supports_webhooks=cls.supports_webhooks,
                verified_live=verified,
                verification_note=note,
            )
        )
    verified, note = VERIFICATION["csv"]
    entries.append(
        CatalogueEntry(
            key="csv",
            name="CSV import",
            description=(
                "Upload spreadsheets exported from any system: locations, products, "
                "supplier terms, stock, sales and purchase orders."
            ),
            provides=CSV_PROVIDES,
            fields=[],
            supports_webhooks=False,
            verified_live=verified,
            verification_note=note,
        )
    )
    return entries


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(x) for x in first.get("loc", []))
    return f"{field}: {first.get('msg')}" if field else str(first.get("msg"))


async def check_remote(
    rt: SyncRuntime, connector: str, config: dict[str, Any], secrets: dict[str, Any]
) -> tuple[dict[str, Any], ConnectionCheck]:
    """Validate settings and talk to the system. Raises ApiError with a safe message."""
    from operon.core.net import UnsafeUrlError, validate_outbound_url

    cls = REMOTE_CONNECTORS[connector]
    try:
        cfg = cls.config_model.model_validate(config)
        sec = cls.secrets_model.model_validate(secrets)
    except ValidationError as exc:
        raise ApiError(422, "invalid_settings", _validation_message(exc)) from exc
    if hasattr(cfg, "url"):
        try:
            cfg.url = await validate_outbound_url(
                cfg.url, allow_private=rt.settings.allow_private_integration_hosts
            )
        except UnsafeUrlError as exc:
            raise ApiError(422, "unsafe_url", str(exc)) from exc
    try:
        async with rt.http_factory() as http:
            result = await cls(ConnectorContext(config=cfg, secrets=sec, http=http)).check()
    except ConnectorError as exc:
        raise ApiError(422, "connection_failed", exc.user_message) from exc
    return cfg.model_dump(mode="json"), result


async def get_connection(
    session: AsyncSession, ctx: TenantContext, connection_id: UUID
) -> Connection:
    conn = await session.get(Connection, connection_id)
    if conn is None or conn.organisation_id != ctx.organisation_id:
        raise NOT_FOUND
    return conn


async def create_connection(
    session: AsyncSession,
    ctx: TenantContext,
    rt: SyncRuntime,
    body: CreateConnectionRequest,
    meta: RequestMeta,
) -> tuple[Connection, str | None]:
    summary = None
    config: dict[str, Any] = {}
    if body.connector != "csv":
        config, check = await check_remote(rt, body.connector, body.config, body.secrets)
        summary = check.summary
    config["sync_interval_minutes"] = body.sync_interval_minutes
    conn = Connection(
        organisation_id=ctx.organisation_id,
        connector=body.connector,
        name=body.name.strip(),
        status="active",
        config=config,
        public_id=pysecrets.token_urlsafe(32),
        created_by=ctx.user_id,
        sync_state={},
    )
    session.add(conn)
    await session.flush()
    if body.connector != "csv":
        await credentials.store(
            session,
            rt.box,
            organisation_id=ctx.organisation_id,
            connection_id=conn.id,
            secrets=body.secrets,
        )
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="integration.connected",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="integration",
        target_id=conn.id,
        details={"connector": body.connector, "name": conn.name, "summary": summary},
    )
    return conn, summary


async def update_connection(
    session: AsyncSession,
    ctx: TenantContext,
    conn: Connection,
    *,
    name: str | None,
    interval: int | None,
    paused: bool | None,
    meta: RequestMeta,
) -> Connection:
    changes: dict[str, Any] = {}
    if name is not None and name.strip() != conn.name:
        changes["name"] = {"from": conn.name, "to": name.strip()}
        conn.name = name.strip()
    if interval is not None and interval != conn.config.get("sync_interval_minutes"):
        changes["sync_interval_minutes"] = {
            "from": conn.config.get("sync_interval_minutes"),
            "to": interval,
        }
        conn.config = {**conn.config, "sync_interval_minutes": interval}
    if paused is not None and paused != (conn.status == "paused"):
        changes["paused"] = paused
        conn.status = "paused" if paused else "active"
    if changes:
        await session.flush()
        await audit.record(
            session,
            actor=Actor.user(ctx.user_id, ctx.user_email),
            action="integration.updated",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="integration",
            target_id=conn.id,
            details=changes,
        )
    return conn


async def rotate_credentials(
    session: AsyncSession,
    ctx: TenantContext,
    rt: SyncRuntime,
    conn: Connection,
    secrets: dict[str, str],
    meta: RequestMeta,
) -> str:
    if conn.connector == "csv":
        raise ApiError(409, "no_credentials", "CSV imports don't use credentials.")
    config = {k: v for k, v in conn.config.items() if k != "sync_interval_minutes"}
    _, check = await check_remote(rt, conn.connector, config, secrets)
    await credentials.store(
        session, rt.box, organisation_id=ctx.organisation_id, connection_id=conn.id, secrets=secrets
    )
    # Status changes only when a sync proves the new credentials work (the route requests one).
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="integration.credentials_rotated",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="integration",
        target_id=conn.id,
        details={"fields": sorted(secrets)},
    )
    return check.summary


async def check_existing(
    session: AsyncSession, rt: SyncRuntime, conn: Connection
) -> ConnectionCheck:
    if conn.connector == "csv":
        return ConnectionCheck(summary="CSV import · no remote system", capabilities=())
    config = {k: v for k, v in conn.config.items() if k != "sync_interval_minutes"}
    _, check = await check_remote(
        rt, conn.connector, config, await credentials.load(session, rt.box, conn.id)
    )
    return check


async def disconnect(
    session: AsyncSession, ctx: TenantContext, conn: Connection, meta: RequestMeta
) -> None:
    """Remove the connection, its credentials and every record synced through it."""
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="integration.disconnected",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="integration",
        target_id=conn.id,
        details={"connector": conn.connector, "name": conn.name},
    )
    await session.delete(conn)
    await session.flush()


async def list_jobs(session: AsyncSession, conn: Connection, limit: int) -> list[SyncJob]:
    return list(
        (
            await session.scalars(
                select(SyncJob)
                .where(SyncJob.connection_id == conn.id)
                .order_by(SyncJob.started_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def list_events(session: AsyncSession, conn: Connection, limit: int) -> list[InboundEvent]:
    return list(
        (
            await session.scalars(
                select(InboundEvent)
                .where(InboundEvent.connection_id == conn.id)
                .order_by(InboundEvent.received_at.desc())
                .limit(limit)
            )
        ).all()
    )


@dataclass
class _Known:
    skus: set[str]
    locations: set[str]


async def upload_csv(
    session: AsyncSession,
    ctx: TenantContext,
    conn: Connection,
    kind: csv_import.Kind,
    content: bytes,
    filename: str,
    meta: RequestMeta,
) -> UploadResult:
    if conn.connector != "csv":
        raise ApiError(409, "not_csv", "Uploads are only for CSV import connections.")
    if conn.status == "paused":
        raise ApiError(409, "paused", "Resume this connection before importing.")
    skus = set(
        (
            await session.scalars(
                select(Product.external_id).where(Product.connection_id == conn.id)
            )
        ).all()
    )
    locations = set(
        (
            await session.scalars(
                select(Location.external_id).where(Location.connection_id == conn.id)
            )
        ).all()
    )
    parsed = csv_import.parse(kind, content, known_skus=skus, known_locations=locations)
    errors = [UploadError(row=e.row, column=e.column, message=e.message) for e in parsed.errors]
    if parsed.error_count:
        return UploadResult(
            kind=kind,
            accepted=False,
            rows=parsed.rows,
            written=0,
            error_count=parsed.error_count,
            errors=errors,
        )

    started = datetime.now(UTC)
    store = Store(session, ctx.organisation_id, conn.id)
    if parsed.records.get("suppliers"):
        await store.suppliers(parsed.records["suppliers"])
    records = parsed.records[kind]
    stats: EntityStats
    if kind == "locations":
        stats = await store.locations(records)
    elif kind == "products":
        stats = await store.products(records)
    elif kind == "supplier_terms":
        stats = await store.supplier_products(records)
    elif kind == "stock":
        stats = await store.stock_snapshot(records)
    elif kind == "sales":
        stats = await store.sales_upsert_days(records)
    else:
        stats = await store.purchase_orders(records)
    session.add(
        SyncJob(
            organisation_id=ctx.organisation_id,
            connection_id=conn.id,
            trigger="upload",
            status="succeeded",
            started_at=started,
            finished_at=datetime.now(UTC),
            stats={kind: {**stats.as_dict(), "file": filename[:120]}},
        )
    )
    conn.last_sync_at = conn.last_success_at = datetime.now(UTC)
    conn.status = "active"
    conn.last_error = None
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="integration.data_imported",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="integration",
        target_id=conn.id,
        details={"kind": kind, "rows": parsed.rows, "file": filename[:120]},
    )
    return UploadResult(
        kind=kind, accepted=True, rows=parsed.rows, written=stats.written, error_count=0, errors=[]
    )
