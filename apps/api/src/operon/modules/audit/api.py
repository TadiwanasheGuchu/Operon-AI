from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from operon.access.context import TenantContext
from operon.access.dependencies import require_permission
from operon.core.deps import SessionDep
from operon.modules.audit import service
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["audit"])


class AuditEventOut(BaseModel):
    id: UUID
    occurred_at: datetime
    actor_type: str
    actor_user_id: UUID | None
    actor_label: str
    action: str
    target_type: str | None
    target_id: str | None
    outcome: str
    details: dict[str, Any]
    request_id: str | None


class AuditPageOut(BaseModel):
    items: list[AuditEventOut]
    next_cursor: str | None


@router.get("/audit", response_model=AuditPageOut)
async def list_audit(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.AUDIT_READ))],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_user_id: UUID | None = None,
    outcome: Annotated[str | None, Query(pattern="^(success|failure|denied)$")] = None,
) -> AuditPageOut:
    page = await service.list_events(
        session,
        ctx,
        limit=limit,
        cursor=cursor,
        action=action,
        actor_user_id=actor_user_id,
        outcome=outcome,
    )
    return AuditPageOut(
        items=[AuditEventOut.model_validate(e, from_attributes=True) for e in page.items],
        next_cursor=page.next_cursor,
    )
