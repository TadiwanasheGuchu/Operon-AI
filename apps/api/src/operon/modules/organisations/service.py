"""Organisations, memberships and invitations."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.config import Settings
from operon.core.db import set_rls_context
from operon.core.email import EmailMessage, EmailSender
from operon.core.errors import ApiError
from operon.core.ids import uuid7
from operon.core.security import hash_token, new_token
from operon.modules.audit import service as audit
from operon.modules.identity.models import MfaFactor, User
from operon.modules.notifications.service import notify
from operon.modules.organisations.models import Invitation, Membership, Organisation
from operon.modules.permissions import service as roles_service
from operon.modules.permissions.catalogue import SystemRole
from operon.modules.permissions.models import Role

NOT_FOUND = ApiError(404, "not_found", "The requested resource was not found.")


def _now() -> datetime:
    return datetime.now(UTC)


# --- Organisations ------------------------------------------------------------------------------


async def create_organisation(
    session: AsyncSession, *, name: str, owner: User, meta: RequestMeta | None
) -> Organisation:
    """New organisation with system roles; the creator becomes its owner. One transaction."""
    org_id = uuid7()
    await set_rls_context(session, user_id=owner.id, organisation_id=org_id)
    org = Organisation(id=org_id, name=name.strip(), created_by=owner.id)
    session.add(org)
    await session.flush()
    roles = await roles_service.provision_system_roles(session, org_id)
    membership = Membership(
        organisation_id=org_id, user_id=owner.id, role_id=roles[SystemRole.OWNER].id
    )
    session.add(membership)
    await session.flush()
    actor = Actor.user(owner.id, owner.email)
    await audit.record(
        session,
        actor=actor,
        action="organisation.created",
        meta=meta,
        organisation_id=org_id,
        target_type="organisation",
        target_id=org_id,
        details={"name": org.name},
    )
    await audit.record(
        session,
        actor=actor,
        action="member.joined",
        meta=meta,
        organisation_id=org_id,
        target_type="membership",
        target_id=membership.id,
        details={"role": SystemRole.OWNER.value},
    )
    return org


@dataclass(frozen=True)
class MyOrganisation:
    id: UUID
    name: str
    role_key: str
    role_name: str
    mfa_required: bool
    is_demo: bool


async def list_my_organisations(session: AsyncSession, user_id: UUID) -> list[MyOrganisation]:
    await set_rls_context(session, user_id=user_id)
    rows = await session.execute(
        select(Organisation, Role)
        .join(Membership, Membership.organisation_id == Organisation.id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == user_id)
        .order_by(Organisation.name)
    )
    return [
        MyOrganisation(o.id, o.name, r.key, r.name, o.mfa_required, o.is_demo)
        for o, r in rows.all()
    ]


async def get_current(session: AsyncSession, ctx: TenantContext) -> Organisation:
    org = await session.get(Organisation, ctx.organisation_id)
    if org is None:
        raise NOT_FOUND
    return org


async def update_organisation(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    name: str | None,
    mfa_required: bool | None,
    actor_mfa_enabled: bool,
    meta: RequestMeta,
) -> Organisation:
    org = await get_current(session, ctx)
    changes: dict[str, object] = {}
    if name is not None and name.strip() != org.name:
        changes["name"] = {"from": org.name, "to": name.strip()}
        org.name = name.strip()
    if mfa_required is not None and mfa_required != org.mfa_required:
        if mfa_required and not actor_mfa_enabled:
            raise ApiError(
                409,
                "mfa_not_enabled",
                "Turn on two-factor authentication for your own account first, "
                "so this policy doesn't lock you out.",
            )
        changes["mfa_required"] = {"from": org.mfa_required, "to": mfa_required}
        org.mfa_required = mfa_required
    if changes:
        await session.flush()
        if changes.get("mfa_required") and org.mfa_required:
            await _notify_members_without_mfa(session, ctx, org.name)
        await audit.record(
            session,
            actor=Actor.user(ctx.user_id, ctx.user_email),
            action="organisation.updated",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="organisation",
            target_id=org.id,
            details=changes,
        )
    return org


async def _notify_members_without_mfa(
    session: AsyncSession, ctx: TenantContext, org_name: str
) -> None:
    confirmed = select(MfaFactor.user_id).where(MfaFactor.confirmed_at.is_not(None))
    user_ids = (
        await session.scalars(
            select(Membership.user_id).where(
                Membership.organisation_id == ctx.organisation_id,
                Membership.user_id.not_in(confirmed),
            )
        )
    ).all()
    await notify(
        session,
        organisation_id=ctx.organisation_id,
        user_ids=user_ids,
        kind="security",
        title=f"{org_name} now requires two-factor authentication",
        body="Turn it on for your account to keep access to this organisation.",
        link="/account/security",
    )


# --- Members ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberView:
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role_key: str
    role_name: str
    joined_at: datetime
    mfa_enabled: bool


async def list_members(session: AsyncSession, ctx: TenantContext) -> list[MemberView]:
    mfa = select(MfaFactor.user_id).where(MfaFactor.confirmed_at.is_not(None)).subquery()
    rows = await session.execute(
        select(Membership, User, Role, mfa.c.user_id)
        .join(User, User.id == Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .outerjoin(mfa, mfa.c.user_id == User.id)
        .where(Membership.organisation_id == ctx.organisation_id)
        .order_by(User.full_name)
    )
    return [
        MemberView(
            m.id, u.id, u.email, u.full_name, r.key, r.name, m.created_at, mfa_uid is not None
        )
        for m, u, r, mfa_uid in rows.all()
    ]


async def _member_with_role(
    session: AsyncSession, ctx: TenantContext, member_id: UUID
) -> tuple[Membership, Role, User]:
    row = (
        await session.execute(
            select(Membership, Role, User)
            .join(Role, Role.id == Membership.role_id)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id == member_id, Membership.organisation_id == ctx.organisation_id)
        )
    ).first()
    if row is None:
        raise NOT_FOUND
    return row[0], row[1], row[2]


async def _owner_count(session: AsyncSession, ctx: TenantContext) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.organisation_id == ctx.organisation_id, Role.key == SystemRole.OWNER)
        )
        or 0
    )


async def change_member_role(
    session: AsyncSession, ctx: TenantContext, member_id: UUID, role_key: str, meta: RequestMeta
) -> MemberView:
    member, current_role, user = await _member_with_role(session, ctx, member_id)
    if member.user_id == ctx.user_id:
        raise ApiError(
            409,
            "cannot_change_own_role",
            "You can't change your own role. Ask another administrator.",
        )
    new_role = await roles_service.role_by_key(session, ctx, role_key)
    if new_role is None:
        raise ApiError(422, "unknown_role", "That role doesn't exist in this organisation.")
    if not roles_service.can_assign(ctx.role_key, current_role.key) or not roles_service.can_assign(
        ctx.role_key, new_role.key
    ):
        raise ApiError(
            403,
            "role_not_assignable",
            "You can only manage members and roles at or below your own role.",
        )
    demoting_owner = current_role.key == SystemRole.OWNER and new_role.key != SystemRole.OWNER
    if demoting_owner and await _owner_count(session, ctx) <= 1:
        raise ApiError(409, "last_owner", "An organisation must keep at least one owner.")
    if new_role.id != member.role_id:
        member.role_id = new_role.id
        await session.flush()
        await audit.record(
            session,
            actor=Actor.user(ctx.user_id, ctx.user_email),
            action="member.role_changed",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="membership",
            target_id=member.id,
            details={"user": user.email, "from": current_role.key, "to": new_role.key},
        )
        org = await get_current(session, ctx)
        await notify(
            session,
            organisation_id=ctx.organisation_id,
            user_ids=[user.id],
            kind="security",
            title=f"Your role in {org.name} is now {new_role.name}",
            body=f"Changed by {ctx.user_email}. What you can see and do has changed.",
            link="/overview",
        )
    return MemberView(
        member.id,
        user.id,
        user.email,
        user.full_name,
        new_role.key,
        new_role.name,
        member.created_at,
        False,
    )


async def remove_member(
    session: AsyncSession, ctx: TenantContext, member_id: UUID, meta: RequestMeta
) -> None:
    member, role, user = await _member_with_role(session, ctx, member_id)
    if member.user_id == ctx.user_id:
        raise ApiError(
            409, "cannot_remove_self", "You can't remove yourself from the organisation."
        )
    if not roles_service.can_assign(ctx.role_key, role.key):
        raise ApiError(
            403, "role_not_assignable", "You can only remove members at or below your own role."
        )
    if role.key == SystemRole.OWNER and await _owner_count(session, ctx) <= 1:
        raise ApiError(409, "last_owner", "An organisation must keep at least one owner.")
    await session.delete(member)
    await session.flush()
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="member.removed",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="membership",
        target_id=member_id,
        details={"user": user.email, "role": role.key},
    )


# --- Invitations --------------------------------------------------------------------------------


@dataclass(frozen=True)
class InvitationView:
    id: UUID
    email: str
    role_key: str
    role_name: str
    invited_by: str | None
    created_at: datetime
    expires_at: datetime


async def list_invitations(session: AsyncSession, ctx: TenantContext) -> list[InvitationView]:
    inviter = User.__table__.alias("inviter")
    rows = await session.execute(
        select(Invitation, Role, inviter.c.full_name)
        .join(Role, Role.id == Invitation.role_id)
        .outerjoin(inviter, inviter.c.id == Invitation.invited_by)
        .where(
            Invitation.organisation_id == ctx.organisation_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .order_by(Invitation.created_at.desc())
    )
    return [
        InvitationView(i.id, i.email, r.key, r.name, name, i.created_at, i.expires_at)
        for i, r, name in rows.all()
    ]


async def create_invitation(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    email: str,
    role_key: str,
    inviter_name: str,
    settings: Settings,
    mailer: EmailSender,
    meta: RequestMeta,
) -> InvitationView:
    role = await roles_service.role_by_key(session, ctx, role_key)
    if role is None:
        raise ApiError(422, "unknown_role", "That role doesn't exist in this organisation.")
    if not roles_service.can_assign(ctx.role_key, role.key):
        raise ApiError(
            403, "role_not_assignable", "You can only invite people to roles at or below your own."
        )
    existing_member = await session.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organisation_id == ctx.organisation_id, User.email == email)
    )
    if existing_member:
        raise ApiError(409, "already_member", "This person is already a member.")
    open_invite = await session.scalar(
        select(Invitation.id).where(
            Invitation.organisation_id == ctx.organisation_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if open_invite:
        raise ApiError(
            409,
            "already_invited",
            "This person already has an open invitation. Revoke it to send a new one.",
        )
    token = new_token()
    now = _now()
    invitation = Invitation(
        organisation_id=ctx.organisation_id,
        email=email,
        role_id=role.id,
        token_hash=hash_token(token),
        invited_by=ctx.user_id,
        created_at=now,
        expires_at=now + timedelta(days=settings.invitation_days),
    )
    session.add(invitation)
    await session.flush()
    org = await get_current(session, ctx)
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="invitation.created",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="invitation",
        target_id=invitation.id,
        details={"email": email, "role": role.key},
    )
    await mailer.send(
        EmailMessage(
            to=email,
            subject=f"{inviter_name} invited you to {org.name} on Operon",
            text=(
                f"{inviter_name} invited you to join {org.name} on Operon as {role.name}.\n\n"
                f"Accept the invitation: {settings.web_base_url}/invite?token={token}\n\n"
                f"This link expires in {settings.invitation_days} days. If you weren't expecting "
                "it, you can ignore this email."
            ),
        )
    )
    return InvitationView(
        invitation.id,
        email,
        role.key,
        role.name,
        inviter_name,
        invitation.created_at,
        invitation.expires_at,
    )


async def revoke_invitation(
    session: AsyncSession, ctx: TenantContext, invitation_id: UUID, meta: RequestMeta
) -> None:
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organisation_id == ctx.organisation_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if invitation is None:
        raise NOT_FOUND
    invitation.revoked_at = _now()
    await session.flush()
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="invitation.revoked",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="invitation",
        target_id=invitation.id,
        details={"email": invitation.email},
    )


@dataclass(frozen=True)
class InvitationLookup:
    invitation: Invitation
    organisation_name: str
    role_name: str
    inviter_name: str | None
    status: str  # "open" | "expired" | "accepted" | "revoked"


async def lookup_invitation(session: AsyncSession, token: str) -> InvitationLookup:
    """Resolve a token to its invitation. Sets the RLS org context for the rest of the request."""
    row = (
        await session.execute(
            text("SELECT id, organisation_id FROM operon_invitation_by_token(:h)"),
            {"h": hash_token(token)},
        )
    ).first()
    if row is None:
        raise ApiError(404, "invitation_not_found", "This invitation link is not valid.")
    await set_rls_context(session, organisation_id=row.organisation_id)
    invitation = await session.get(Invitation, row.id)
    org = await session.get(Organisation, row.organisation_id)
    role = await session.get(Role, invitation.role_id) if invitation else None
    if invitation is None or org is None or role is None:
        raise ApiError(404, "invitation_not_found", "This invitation link is not valid.")
    inviter = await session.get(User, invitation.invited_by) if invitation.invited_by else None
    status = (
        "accepted"
        if invitation.accepted_at
        else "revoked"
        if invitation.revoked_at
        else "expired"
        if invitation.expires_at <= _now()
        else "open"
    )
    return InvitationLookup(
        invitation, org.name, role.name, inviter.full_name if inviter else None, status
    )


async def accept_invitation(
    session: AsyncSession, *, token: str, user: User, meta: RequestMeta
) -> UUID:
    """Join the organisation. The invitation must be open and addressed to this user's email."""
    found = await lookup_invitation(session, token)
    if found.status != "open":
        raise ApiError(
            410,
            f"invitation_{found.status}",
            {
                "expired": "This invitation has expired. Ask for a new one.",
                "accepted": "This invitation has already been used.",
                "revoked": "This invitation was withdrawn.",
            }[found.status],
        )
    invitation = found.invitation
    if invitation.email.lower() != user.email.lower():
        raise ApiError(
            403,
            "invitation_email_mismatch",
            "This invitation was sent to a different email address.",
        )
    await set_rls_context(session, user_id=user.id)
    already = await session.scalar(
        select(Membership.id).where(
            Membership.organisation_id == invitation.organisation_id, Membership.user_id == user.id
        )
    )
    if already:
        raise ApiError(409, "already_member", "You're already a member of this organisation.")
    membership = Membership(
        organisation_id=invitation.organisation_id,
        user_id=user.id,
        role_id=invitation.role_id,
        invited_by=invitation.invited_by,
    )
    session.add(membership)
    invitation.accepted_at = _now()
    await session.flush()
    role = await session.get(Role, invitation.role_id)
    if invitation.invited_by and invitation.invited_by != user.id:
        await notify(
            session,
            organisation_id=invitation.organisation_id,
            user_ids=[invitation.invited_by],
            kind="member",
            title=f"{user.full_name} joined {found.organisation_name}",
            body=f"{user.email} accepted your invitation as {found.role_name}.",
            link="/admin/members",
        )
    await audit.record(
        session,
        actor=Actor.user(user.id, user.email),
        action="invitation.accepted",
        meta=meta,
        organisation_id=invitation.organisation_id,
        target_type="membership",
        target_id=membership.id,
        details={"role": role.key if role else None},
    )
    return invitation.organisation_id


@dataclass(frozen=True)
class Person:
    user_id: UUID
    full_name: str
    email: str


async def people(
    session: AsyncSession, organisation_id: UUID, user_ids: set[UUID]
) -> dict[UUID, Person]:
    """Names of the given users, limited to members of the organisation."""
    ids = {u for u in user_ids if u is not None}
    if not ids:
        return {}
    rows = await session.execute(
        select(User.id, User.full_name, User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organisation_id == organisation_id, User.id.in_(ids))
    )
    return {uid: Person(uid, name, email) for uid, name, email in rows.all()}
