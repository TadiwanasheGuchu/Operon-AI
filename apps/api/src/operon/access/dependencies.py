"""Authentication and tenant-resolution dependencies used by every protected route."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select

from operon.access.context import Actor, AuthContext, RequestMeta, TenantContext
from operon.core.db import set_rls_context
from operon.core.deps import DatabaseDep, RedisDep, SessionDep, SettingsDep
from operon.core.errors import ApiError
from operon.core.request_context import get_request_id
from operon.modules.audit import service as audit
from operon.modules.identity.service import IdentityService
from operon.modules.organisations.models import Membership, Organisation
from operon.modules.permissions.models import Role
from operon.modules.permissions.service import permissions_for_role

TENANT_HEADER = "X-Operon-Organisation"
ORG_NOT_FOUND = ApiError(404, "organisation_not_found", "Organisation not found.")


def get_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=get_request_id(),
    )


MetaDep = Annotated[RequestMeta, Depends(get_meta)]


def get_identity(
    request: Request,
    session: SessionDep,
    db: DatabaseDep,
    settings: SettingsDep,
    redis: RedisDep,
    meta: MetaDep,
) -> IdentityService:
    state = request.app.state
    return IdentityService(
        session,
        db=db,
        settings=settings,
        redis=redis,
        passwords=state.passwords,
        secrets_box=state.secret_box,
        mailer=state.mailer,
        meta=meta,
    )


IdentityDep = Annotated[IdentityService, Depends(get_identity)]


async def get_optional_auth(
    request: Request, identity: IdentityDep, settings: SettingsDep
) -> AuthContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    auth = await identity.authenticate(token)
    if auth is not None:
        await set_rls_context(identity.s, user_id=auth.user_id)
    return auth


OptionalAuthDep = Annotated[AuthContext | None, Depends(get_optional_auth)]


async def require_auth(auth: OptionalAuthDep) -> AuthContext:
    if auth is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return auth


AuthDep = Annotated[AuthContext, Depends(require_auth)]


async def require_tenant(request: Request, auth: AuthDep, session: SessionDep) -> TenantContext:
    """Resolve the requested organisation from verified membership, never from client claims.

    A malformed, unknown or foreign organisation ID all produce the same 404, so the response
    never confirms that another organisation exists.
    """
    raw = request.headers.get(TENANT_HEADER)
    try:
        org_id = UUID(raw) if raw else None
    except ValueError:
        org_id = None
    if org_id is None:
        raise ORG_NOT_FOUND
    row = (
        await session.execute(
            select(Membership, Role, Organisation)
            .join(Role, Role.id == Membership.role_id)
            .join(Organisation, Organisation.id == Membership.organisation_id)
            .where(Membership.organisation_id == org_id, Membership.user_id == auth.user_id)
        )
    ).first()
    if row is None:
        raise ORG_NOT_FOUND
    membership, role, organisation = row
    await set_rls_context(session, organisation_id=org_id)
    if organisation.mfa_required and not auth.mfa_enabled:
        raise ApiError(
            403,
            "mfa_required",
            "This organisation requires two-factor authentication. Turn it on in "
            "your account security settings to continue.",
        )
    return TenantContext(
        organisation_id=org_id,
        user_id=auth.user_id,
        user_email=auth.email,
        membership_id=membership.id,
        role_key=role.key,
        permissions=await permissions_for_role(session, role.id),
    )


TenantDep = Annotated[TenantContext, Depends(require_tenant)]


def require_permission(permission: str) -> Callable[..., Awaitable[TenantContext]]:
    async def check(
        ctx: TenantDep, db: DatabaseDep, meta: MetaDep, request: Request
    ) -> TenantContext:
        if not ctx.has(permission):
            await audit.record_independent(
                db,
                actor=Actor.user(ctx.user_id, ctx.user_email),
                action="access.denied",
                outcome="denied",
                meta=meta,
                organisation_id=ctx.organisation_id,
                details={
                    "permission": permission,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise ApiError(
                403,
                "forbidden",
                "You don't have permission to do this.",
                {"permission": permission},
            )
        return ctx

    return check
