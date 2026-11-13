"""Run one sync of one connection. Called by the Temporal activity or the inline dispatcher."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from operon.core.config import Settings
from operon.core.crypto import SecretBox
from operon.core.db import Database, set_rls_context
from operon.core.logging import get_logger
from operon.core.net import UnsafeUrlError, validate_outbound_url
from operon.modules.integrations import credentials
from operon.modules.integrations.connectors.base import (
    SNAPSHOT_ENTITIES,
    SYNC_ORDER,
    WINDOWED_ENTITIES,
    AuthError,
    ConfigError,
    ConnectorContext,
    ConnectorError,
    Entity,
)
from operon.modules.integrations.connectors.registry import REMOTE_CONNECTORS
from operon.modules.integrations.models import Connection, InboundEvent, SyncJob
from operon.modules.notifications.service import notify
from operon.modules.operations.store import EntityStats, Store
from operon.modules.organisations.models import Membership
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.models import RolePermission

log = get_logger(__name__)

HttpFactory = Callable[[], httpx.AsyncClient]
# Called after new operational data lands (organisation id, "sync" | "upload"), e.g. detection.
DataChangedHook = Callable[[UUID, str], Awaitable[object]]
INITIAL_SALES_DAYS = 90
SALES_RESYNC_DAYS = 3  # re-read recent days to catch late edits and cancellations
MAX_RECORDS_PER_ENTITY = 250_000


@dataclass(frozen=True)
class SyncOutcome:
    status: str  # "succeeded" | "failed" | "skipped"
    job_id: UUID | None
    stats: dict[str, Any]
    error: str | None = None
    retryable: bool = False


@dataclass
class SyncRuntime:
    db: Database
    settings: Settings
    box: SecretBox
    http_factory: HttpFactory
    on_data_changed: list[DataChangedHook] = field(default_factory=list)

    async def data_changed(self, organisation_id: UUID, trigger: str) -> None:
        for hook in self.on_data_changed:
            try:
                await hook(organisation_id, trigger)
            except Exception:
                log.exception("data_changed_hook_failed", organisation_id=str(organisation_id))


def default_http_factory(settings: Settings) -> HttpFactory:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=settings.integration_http_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "Operon-Integrations/1.0"},
        )

    return factory


async def managers_of(session: AsyncSession, organisation_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(Membership.user_id)
        .join(RolePermission, RolePermission.role_id == Membership.role_id)
        .where(
            Membership.organisation_id == organisation_id,
            RolePermission.permission_key == Perm.INTEGRATIONS_MANAGE,
        )
    )
    return list(rows.all())


async def build_connector(
    rt: SyncRuntime, session: AsyncSession, conn: Connection, http: httpx.AsyncClient
) -> Any:
    connector_cls = REMOTE_CONNECTORS.get(conn.connector)
    if connector_cls is None:
        raise ConfigError("This connection type doesn't sync from a remote system.")
    config = connector_cls.config_model.model_validate(conn.config)
    if hasattr(config, "url"):
        try:
            config.url = await validate_outbound_url(
                config.url, allow_private=rt.settings.allow_private_integration_hosts
            )
        except UnsafeUrlError as exc:
            raise ConfigError(str(exc)) from exc
    secrets = connector_cls.secrets_model.model_validate(
        await credentials.load(session, rt.box, conn.id)
    )
    return connector_cls(ConnectorContext(config=config, secrets=secrets, http=http))


async def run_sync(
    rt: SyncRuntime,
    *,
    organisation_id: UUID,
    connection_id: UUID,
    trigger: str,
    workflow_id: str | None = None,
) -> SyncOutcome:
    # A session-level advisory lock on its own connection keeps syncs of one connection serial.
    async with rt.db.engine.connect() as lock_conn:
        got = (
            await lock_conn.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": f"sync:{connection_id}"}
            )
        ).scalar()
        if not got:
            return SyncOutcome("skipped", None, {}, "A sync is already running.")
        try:
            return await _run(rt, organisation_id, connection_id, trigger, workflow_id)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"sync:{connection_id}"}
            )
            await lock_conn.commit()


async def _run(
    rt: SyncRuntime, org: UUID, connection_id: UUID, trigger: str, workflow_id: str | None
) -> SyncOutcome:
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        conn = await s.get(Connection, connection_id)
        if conn is None or conn.organisation_id != org:
            return SyncOutcome("skipped", None, {}, "Connection not found.")
        if conn.status == "paused":
            return SyncOutcome("skipped", None, {}, "Connection is paused.")
        job = SyncJob(
            organisation_id=org,
            connection_id=connection_id,
            trigger=trigger,
            status="running",
            workflow_id=workflow_id,
        )
        s.add(job)
        previous_status = conn.status
        conn.status = "syncing"
        conn.last_sync_at = datetime.now(UTC)
        await s.flush()
        job_id = job.id
        sync_state = dict(conn.sync_state or {})

    stats: dict[str, Any] = {}
    try:
        async with rt.http_factory() as http:
            async with rt.db.sessionmaker() as s, s.begin():
                await set_rls_context(s, organisation_id=org)
                conn = await s.get(Connection, connection_id)
                assert conn is not None
                connector = await build_connector(rt, s, conn, http)
            check = await connector.check()
            for entity in SYNC_ORDER:
                if entity not in check.capabilities:
                    continue
                stats[entity], cursor = await _sync_entity(
                    rt, org, connection_id, connector, entity, sync_state
                )
                if cursor is not None:
                    sync_state[entity] = cursor
    except ConnectorError as exc:
        log.warning(
            "sync_failed",
            connection_id=str(connection_id),
            error=exc.user_message,
            detail=exc.detail,
            kind=type(exc).__name__,
        )
        await _finish(rt, org, connection_id, job_id, previous_status, stats, exc)
        return SyncOutcome("failed", job_id, stats, exc.user_message, exc.retryable)
    except Exception as exc:
        log.exception("sync_crashed", connection_id=str(connection_id))
        err = ConnectorError("The sync stopped unexpectedly. Operon will retry.", detail=repr(exc))
        err.retryable = True
        await _finish(rt, org, connection_id, job_id, previous_status, stats, err)
        return SyncOutcome("failed", job_id, stats, err.user_message, True)

    await _finish(rt, org, connection_id, job_id, previous_status, stats, None)
    return SyncOutcome("succeeded", job_id, stats)


async def _sync_entity(
    rt: SyncRuntime,
    org: UUID,
    connection_id: UUID,
    connector: Any,
    entity: Entity,
    state: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    started = datetime.now(UTC)
    since = None
    sales_from: date | None = None
    if entity in WINDOWED_ENTITIES:
        days = SALES_RESYNC_DAYS if state.get(entity) else INITIAL_SALES_DAYS
        sales_from = (started - timedelta(days=days)).date()
    elif entity not in SNAPSHOT_ENTITIES and state.get(entity):
        # Small overlap so records edited during the previous sync aren't missed.
        since = datetime.fromisoformat(state[entity]) - timedelta(minutes=5)

    records: list[Any] = []
    async for page in connector.fetch(entity, since=since, sales_from=sales_from):
        records.extend(page)
        if len(records) > MAX_RECORDS_PER_ENTITY:
            raise ConfigError(f"Too many {entity.replace('_', ' ')} to sync in one run.")

    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        store = Store(s, org, connection_id)
        result: EntityStats
        if entity == "locations":
            result = await store.locations(records)
        elif entity == "suppliers":
            result = await store.suppliers(records)
        elif entity == "products":
            result = await store.products(records)
        elif entity == "supplier_products":
            result = await store.supplier_products(records)
        elif entity == "stock":
            result = await store.stock_snapshot(records)
        elif entity == "sales":
            assert sales_from is not None
            result = await store.sales_window(records, sales_from)
        else:
            result = await store.purchase_orders(records)
        # The cursor advances in the same transaction as the data it describes.
        new_state = {**state, entity: started.isoformat()}
        await s.execute(
            update(Connection).where(Connection.id == connection_id).values(sync_state=new_state)
        )
    return result.as_dict(), started.isoformat()


async def _finish(
    rt: SyncRuntime,
    org: UUID,
    connection_id: UUID,
    job_id: UUID,
    previous_status: str,
    stats: dict[str, Any],
    error: ConnectorError | None,
) -> None:
    now = datetime.now(UTC)
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        conn = await s.get(Connection, connection_id)
        job = await s.get(SyncJob, job_id)
        if conn is None or job is None:
            return
        job.finished_at = now
        job.stats = stats
        if error is None:
            job.status = "succeeded"
            conn.status = "active"
            conn.last_success_at = now
            conn.last_error = None
            await s.execute(
                update(InboundEvent)
                .where(
                    InboundEvent.connection_id == connection_id,
                    InboundEvent.status == "pending",
                    InboundEvent.received_at <= job.started_at,
                )
                .values(status="processed", processed_at=now)
            )
            if previous_status in ("degraded", "action_required"):
                await notify(
                    s,
                    organisation_id=org,
                    user_ids=await managers_of(s, org),
                    kind="integration",
                    title=f"{conn.name} is syncing again",
                    body="The connection recovered and data is up to date.",
                    link=f"/integrations/{connection_id}",
                )
            return
        job.status = "failed"
        job.error = error.user_message[:500]
        conn.status = (
            "action_required" if isinstance(error, (AuthError, ConfigError)) else "degraded"
        )
        conn.last_error = error.user_message[:500]
        # Notify on the transition only, not on every failed retry.
        if previous_status not in ("degraded", "action_required"):
            await notify(
                s,
                organisation_id=org,
                user_ids=await managers_of(s, org),
                kind="integration",
                title=f"{conn.name} needs attention"
                if conn.status == "action_required"
                else f"{conn.name} sync failed",
                body=error.user_message[:500],
                link=f"/integrations/{connection_id}",
            )
