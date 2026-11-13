from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from operon.access.context import TenantContext
from operon.access.dependencies import AuthDep, require_permission
from operon.core.deps import SessionDep
from operon.modules.permissions import service
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["roles"])


class RoleOut(BaseModel):
    id: UUID
    key: str
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    assignable_by_you: bool


class PermissionOut(BaseModel):
    key: str
    description: str


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    ctx: Annotated[TenantContext, Depends(require_permission(Perm.ROLES_READ))],
    session: SessionDep,
) -> list[RoleOut]:
    return [
        RoleOut(
            id=r.id,
            key=r.key,
            name=r.name,
            description=r.description,
            is_system=r.is_system,
            permissions=perms,
            assignable_by_you=service.can_assign(ctx.role_key, r.key),
        )
        for r, perms in await service.list_roles(session, ctx)
    ]


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(_: AuthDep, session: SessionDep) -> list[PermissionOut]:
    return [
        PermissionOut(key=p.key, description=p.description)
        for p in await service.list_permissions(session)
    ]
