import secrets
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from operon.access.context import TenantContext
from operon.access.dependencies import IdentityDep, MetaDep, require_permission
from operon.core.crypto import SecretBox
from operon.core.deps import RedisDep, SessionDep, SettingsDep
from operon.core.errors import ApiError
from operon.core.logging import get_logger
from operon.modules.identity.api import _set_session_cookie
from operon.modules.permissions.catalogue import Perm
from operon.modules.sso import service
from operon.modules.sso.models import SsoConnection, SsoDomain

log = get_logger(__name__)
router = APIRouter(tags=["single sign-on"])

OrgRead = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_READ))]
OrgManage = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_MANAGE))]
CALLBACK_PATH = "/api/v1/auth/sso/callback"
BINDING_COOKIE = "operon_sso_binding"
BINDING_PATH = "/api/v1/auth/sso"


def _http(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient = request.app.state.sync_runtime.http_factory()
    return client


def _box(request: Request) -> SecretBox:
    box: SecretBox = request.app.state.secret_box
    return box


class DomainOut(BaseModel):
    domain: str
    verified: bool
    txt_name: str
    txt_value: str


class SsoOut(BaseModel):
    configured: bool
    issuer: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    enabled: bool = False
    enforce: bool = False
    jit_provisioning: bool = True
    default_role_key: str = "viewer"
    redirect_uri: str
    domains: list[DomainOut] = Field(default_factory=list)


class SsoUpdate(BaseModel):
    issuer: str = Field(min_length=8, max_length=300)
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str | None = Field(None, max_length=2000)
    enabled: bool
    enforce: bool = False
    jit_provisioning: bool = True
    default_role_key: Literal["operations_manager", "approver", "analyst", "viewer"] = "viewer"


class DomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=253, pattern=r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class StartIn(BaseModel):
    email: EmailStr


def _domain(d: SsoDomain) -> DomainOut:
    return DomainOut(
        domain=d.domain,
        verified=d.verified_at is not None,
        txt_name=f"{service.TXT_PREFIX}.{d.domain}",
        txt_value=f"operon-verification={d.verification_token}",
    )


async def _out(session: object, ctx: TenantContext, settings: object) -> SsoOut:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    redirect = f"{getattr(settings, 'web_base_url', '')}{CALLBACK_PATH}"
    conn: SsoConnection | None = await service.get_connection(session, ctx.organisation_id)
    if conn is None:
        return SsoOut(configured=False, redirect_uri=redirect)
    return SsoOut(
        configured=True,
        issuer=conn.issuer,
        client_id=conn.client_id,
        has_client_secret=bool(conn.client_secret_encrypted),
        enabled=conn.enabled,
        enforce=conn.enforce,
        jit_provisioning=conn.jit_provisioning,
        default_role_key=conn.default_role_key,
        redirect_uri=redirect,
        domains=[_domain(d) for d in await service.domains(session, ctx.organisation_id)],
    )


@router.get("/organisations/current/sso", response_model=SsoOut)
async def get_sso(ctx: OrgRead, session: SessionDep, settings: SettingsDep) -> SsoOut:
    return await _out(session, ctx, settings)


@router.put("/organisations/current/sso", response_model=SsoOut)
async def put_sso(
    body: SsoUpdate,
    ctx: OrgManage,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    meta: MetaDep,
) -> SsoOut:
    async with _http(request) as http:
        await service.save_connection(
            session,
            ctx,
            _box(request),
            settings,
            http,
            issuer=body.issuer,
            client_id=body.client_id,
            client_secret=body.client_secret,
            enabled=body.enabled,
            enforce=body.enforce,
            jit_provisioning=body.jit_provisioning,
            default_role_key=body.default_role_key,
            meta=meta,
        )
    return await _out(session, ctx, settings)


@router.post(
    "/organisations/current/sso/domains",
    response_model=DomainOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_domain(
    body: DomainIn, ctx: OrgManage, session: SessionDep, meta: MetaDep
) -> DomainOut:
    return _domain(await service.add_domain(session, ctx, body.domain, meta))


@router.post("/organisations/current/sso/domains/{domain}/verify", response_model=DomainOut)
async def verify_domain(
    domain: str, ctx: OrgManage, session: SessionDep, meta: MetaDep
) -> DomainOut:
    return _domain(await service.verify_domain(session, ctx, domain, meta))


@router.delete(
    "/organisations/current/sso/domains/{domain}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_domain(domain: str, ctx: OrgManage, session: SessionDep, meta: MetaDep) -> None:
    await service.remove_domain(session, ctx, domain, meta)


# --- sign-in (public) --------------------------------------------------------------------------


@router.post("/auth/sso/start")
async def start(
    body: StartIn,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    request: Request,
    response: Response,
) -> dict[str, str]:
    binding = secrets.token_urlsafe(32)
    async with _http(request) as http:
        url = await service.start(
            session,
            redis,
            http,
            email=str(body.email),
            redirect_uri=f"{settings.web_base_url}{CALLBACK_PATH}",
            binding=binding,
        )
    # Lax: sent on the identity provider's top-level redirect back, not on cross-site subrequests.
    response.set_cookie(
        BINDING_COOKIE,
        binding,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=BINDING_PATH,
        max_age=service.STATE_TTL,
    )
    return {"redirect_url": url}


@router.get("/auth/sso/callback", include_in_schema=False)
async def callback(
    request: Request,
    identity: IdentityDep,
    redis: RedisDep,
    settings: SettingsDep,
    meta: MetaDep,
    code: str = "",
    state: str = "",
    error: str = "",
) -> Response:
    web = settings.web_base_url
    if error or not code or not state:
        return RedirectResponse(f"{web}/login?sso_error={'denied' if error else 'invalid'}", 303)
    try:
        async with _http(request) as http:
            signed_in = await service.complete(
                identity.s,
                redis,
                http,
                _box(request),
                code=code,
                state=state,
                binding=request.cookies.get(BINDING_COOKIE),
                meta=meta,
            )
        issued = await identity.issue_sso_session(signed_in.user)
    except ApiError as exc:
        log.info("sso_sign_in_refused", code=exc.code)
        return RedirectResponse(f"{web}/login?sso_error={exc.code}", 303)
    response = RedirectResponse(f"{web}/overview?org={signed_in.organisation_id}", 303)
    _set_session_cookie(response, settings, issued)
    response.delete_cookie(BINDING_COOKIE, path=BINDING_PATH)
    return response
