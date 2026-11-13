from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from operon.access.dependencies import TenantDep
from operon.core.deps import SessionDep
from operon.modules.notifications import service

router = APIRouter(tags=["notifications"])


class NotificationOut(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationPageOut(BaseModel):
    items: list[NotificationOut]
    unread_count: int


@router.get(
    "/notifications",
    response_model=NotificationPageOut,
    summary="Your notifications in the current organisation",
)
async def list_notifications(
    ctx: TenantDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    unread_only: bool = False,
) -> NotificationPageOut:
    page = await service.list_notifications(session, ctx, limit=limit, unread_only=unread_only)
    return NotificationPageOut(
        items=[NotificationOut.model_validate(n, from_attributes=True) for n in page.items],
        unread_count=page.unread_count,
    )


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: UUID, ctx: TenantDep, session: SessionDep) -> None:
    await service.mark_read(session, ctx, notification_id)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(ctx: TenantDep, session: SessionDep) -> None:
    await service.mark_all_read(session, ctx)
