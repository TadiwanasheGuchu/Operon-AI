"""In-app notifications. Written in the same transaction as the event that causes them."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import TenantContext
from operon.core.errors import ApiError
from operon.modules.notifications.models import Notification


async def notify(
    session: AsyncSession,
    *,
    organisation_id: UUID,
    user_ids: Iterable[UUID],
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
) -> None:
    if link is not None and not (link.startswith("/") and not link.startswith("//")):
        raise ValueError("Notification links must be in-app paths.")
    for user_id in set(user_ids):
        session.add(
            Notification(
                organisation_id=organisation_id,
                user_id=user_id,
                kind=kind,
                title=title[:200],
                body=body[:500],
                link=link,
            )
        )
    await session.flush()


@dataclass(frozen=True)
class NotificationPage:
    items: list[Notification]
    unread_count: int


async def list_notifications(
    session: AsyncSession, ctx: TenantContext, *, limit: int, unread_only: bool
) -> NotificationPage:
    mine = (
        Notification.organisation_id == ctx.organisation_id,
        Notification.user_id == ctx.user_id,
    )
    stmt = select(Notification).where(*mine)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = list(
        (
            await session.scalars(
                stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
            )
        ).all()
    )
    unread = await session.scalar(
        select(func.count()).select_from(Notification).where(*mine, Notification.read_at.is_(None))
    )
    return NotificationPage(items, int(unread or 0))


async def mark_read(session: AsyncSession, ctx: TenantContext, notification_id: UUID) -> None:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.organisation_id == ctx.organisation_id,
            Notification.user_id == ctx.user_id,
        )
        .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
    )
    if not getattr(result, "rowcount", 0):
        raise ApiError(404, "not_found", "The requested resource was not found.")


async def mark_all_read(session: AsyncSession, ctx: TenantContext) -> None:
    await session.execute(
        update(Notification)
        .where(
            Notification.organisation_id == ctx.organisation_id,
            Notification.user_id == ctx.user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
