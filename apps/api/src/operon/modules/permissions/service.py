"""Role and permission queries, and system-role provisioning for new organisations."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import TenantContext
from operon.modules.permissions.catalogue import ROLE_RANK, SYSTEM_ROLES, SystemRole
from operon.modules.permissions.models import Permission, Role, RolePermission


async def provision_system_roles(session: AsyncSession, organisation_id: UUID) -> dict[str, Role]:
    """Create the system roles for a new organisation (RLS context must already be that org)."""
    roles: dict[str, Role] = {}
    for key, (name, description, _perms) in SYSTEM_ROLES.items():
        role = Role(
            organisation_id=organisation_id,
            key=key.value,
            name=name,
            description=description,
            is_system=True,
        )
        session.add(role)
        roles[key.value] = role
    await session.flush()
    for key, (_, _, perms) in SYSTEM_ROLES.items():
        for perm in sorted(perms):
            session.add(
                RolePermission(
                    organisation_id=organisation_id,
                    role_id=roles[key.value].id,
                    permission_key=perm.value,
                )
            )
    await session.flush()
    return roles


async def permissions_for_role(session: AsyncSession, role_id: UUID) -> frozenset[str]:
    rows = await session.scalars(
        select(RolePermission.permission_key).where(RolePermission.role_id == role_id)
    )
    return frozenset(rows.all())


async def role_by_key(session: AsyncSession, ctx: TenantContext, key: str) -> Role | None:
    return await session.scalar(
        select(Role).where(Role.organisation_id == ctx.organisation_id, Role.key == key)
    )


async def list_roles(session: AsyncSession, ctx: TenantContext) -> list[tuple[Role, list[str]]]:
    roles = list(
        (
            await session.scalars(select(Role).where(Role.organisation_id == ctx.organisation_id))
        ).all()
    )
    perms: dict[UUID, list[str]] = defaultdict(list)
    for rp in await session.scalars(
        select(RolePermission).where(RolePermission.organisation_id == ctx.organisation_id)
    ):
        perms[rp.role_id].append(rp.permission_key)
    roles.sort(key=lambda r: ROLE_RANK.get(r.key, len(ROLE_RANK)))
    return [(r, sorted(perms[r.id])) for r in roles]


async def list_permissions(session: AsyncSession) -> list[Permission]:
    return list((await session.scalars(select(Permission).order_by(Permission.key))).all())


def can_assign(actor_role: str, target_role: str) -> bool:
    """Nobody grants a role more privileged than their own; only owners grant ownership."""
    if target_role == SystemRole.OWNER:
        return actor_role == SystemRole.OWNER
    return ROLE_RANK.get(actor_role, 99) <= ROLE_RANK.get(target_role, 99)


async def members_with_permission(
    session: AsyncSession, organisation_id: UUID, permission: str
) -> list[UUID]:
    """User ids of the organisation's members whose role grants `permission`."""
    from operon.modules.organisations.models import Membership

    rows = await session.scalars(
        select(Membership.user_id)
        .join(RolePermission, RolePermission.role_id == Membership.role_id)
        .where(
            Membership.organisation_id == organisation_id,
            RolePermission.permission_key == permission,
        )
    )
    return list(rows.all())


async def member_has_permission(
    session: AsyncSession, organisation_id: UUID, user_id: UUID, permission: str
) -> bool:
    return user_id in await members_with_permission(session, organisation_id, permission)
