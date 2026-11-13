"""Audit trail: who did what, to what, when, from where, with what outcome."""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.db import Database, set_rls_context
from operon.core.errors import ApiError
from operon.core.logging import get_logger
from operon.modules.audit.models import AuditLog

log = get_logger(__name__)


async def record(
    session: AsyncSession,
    *,
    actor: Actor,
    action: str,
    meta: RequestMeta | None,
    organisation_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    """Write inside the caller's transaction: the event commits or rolls back with the change."""
    session.add(
        AuditLog(
            organisation_id=organisation_id,
            actor_type=actor.type,
            actor_user_id=actor.user_id,
            actor_label=actor.label,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            outcome=outcome,
            details=details or {},
            request_id=meta.request_id if meta else None,
            ip_address=meta.ip_address if meta else None,
        )
    )
    log.info("audit", action=action, outcome=outcome, organisation_id=str(organisation_id))


async def record_independent(db: Database, **kwargs: Any) -> None:
    """Write in a separate transaction, for failures whose request transaction rolls back."""
    org: UUID | None = kwargs.get("organisation_id")
    async with db.sessionmaker() as session, session.begin():
        if org is not None:
            await set_rls_context(session, organisation_id=org)
        await record(session, **kwargs)


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditLog]
    next_cursor: str | None


def _encode_cursor(entry: AuditLog) -> str:
    return base64.urlsafe_b64encode(f"{entry.occurred_at.isoformat()}|{entry.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        at, _, ident = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        return datetime.fromisoformat(at), UUID(ident)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(422, "invalid_cursor", "The pagination cursor is invalid.") from exc


async def list_events(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    limit: int,
    cursor: str | None,
    action: str | None,
    actor_user_id: UUID | None,
    outcome: str | None,
) -> AuditPage:
    stmt = select(AuditLog).where(AuditLog.organisation_id == ctx.organisation_id)
    if action:
        # Prefix match lets callers filter a family ("member." or "auth.").
        stmt = stmt.where(AuditLog.action.startswith(action, autoescape=True))
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if cursor:
        at, ident = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(AuditLog.occurred_at < at, and_(AuditLog.occurred_at == at, AuditLog.id < ident))
        )
    stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit + 1)
    rows = list((await session.scalars(stmt)).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    return AuditPage(items=items, next_cursor=_encode_cursor(items[-1]) if has_more else None)
