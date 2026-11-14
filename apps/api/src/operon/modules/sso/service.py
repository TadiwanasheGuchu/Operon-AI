"""Single sign-on with OpenID Connect, per organisation (Phase 7, ADR 0015).

Flow: authorization code with PKCE, state and nonce.
1. `/auth/sso/start` takes an email address and finds the organisation through a *verified* domain.
2. The browser goes to the identity provider; state, nonce and the PKCE verifier wait in Redis
   for ten minutes.
3. `/auth/sso/callback` exchanges the code, then verifies the ID token: signature (JWKS), issuer,
   audience, expiry, nonce, `email_verified`, and that the email is in one of the organisation's
   verified domains. The domain check stops an identity provider from signing in people outside
   the domains the organisation proved it controls.
4. The user is linked by (connection, subject), or by verified email on their first sign-in,
   created if just-in-time provisioning is on, and given a normal Operon session.
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import dns.asyncresolver
import dns.exception
import httpx
import jwt
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.config import Settings
from operon.core.crypto import SecretBox
from operon.core.db import set_rls_context
from operon.core.errors import ApiError
from operon.core.ids import uuid7
from operon.core.logging import get_logger
from operon.core.net import UnsafeUrlError, validate_outbound_url
from operon.modules.audit import service as audit
from operon.modules.identity.models import User
from operon.modules.organisations.models import Membership
from operon.modules.permissions.models import Role
from operon.modules.sso.models import SsoConnection, SsoDomain, UserIdentity

log = get_logger(__name__)

STATE_TTL = 600
DISCOVERY_TTL = 3600
TXT_PREFIX = "_operon-verification"
# Domains anyone can get an address at; claiming them would route strangers to one tenant.
PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "mail.com",
        "yandex.com",
        "zoho.com",
    }
)
ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]


def _secret_context(connection_id: UUID) -> str:
    return f"sso:{connection_id}"


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()


# --- administration ---------------------------------------------------------------------------


async def get_connection(s: AsyncSession, org: UUID) -> SsoConnection | None:
    conn: SsoConnection | None = await s.scalar(
        select(SsoConnection).where(SsoConnection.organisation_id == org)
    )
    return conn


async def domains(s: AsyncSession, org: UUID) -> list[SsoDomain]:
    return list(
        await s.scalars(
            select(SsoDomain).where(SsoDomain.organisation_id == org).order_by(SsoDomain.domain)
        )
    )


async def save_connection(
    s: AsyncSession,
    ctx: TenantContext,
    box: SecretBox,
    settings: Settings,
    http: httpx.AsyncClient,
    *,
    issuer: str,
    client_id: str,
    client_secret: str | None,
    enabled: bool,
    enforce: bool,
    jit_provisioning: bool,
    default_role_key: str,
    meta: RequestMeta,
) -> SsoConnection:
    try:
        issuer = await validate_outbound_url(
            issuer, allow_private=settings.allow_private_integration_hosts
        )
    except UnsafeUrlError as exc:
        raise ApiError(422, "invalid_issuer", str(exc)) from exc
    conn = await get_connection(s, ctx.organisation_id)
    created = conn is None
    if conn is None:
        if not client_secret:
            raise ApiError(422, "secret_required", "Enter the client secret.")
        conn = SsoConnection(
            id=uuid7(),
            organisation_id=ctx.organisation_id,
            issuer=issuer,
            client_id=client_id.strip(),
            client_secret_encrypted="",
        )
    if enabled:
        # Prove the issuer is a working OIDC provider before anyone is sent to it.
        await discover(http, issuer, refresh=True)
    if enforce and not enabled:
        raise ApiError(
            422, "enforce_requires_enabled", "Turn single sign-on on before requiring it."
        )
    if enforce and not any(d.verified_at for d in await domains(s, ctx.organisation_id)):
        raise ApiError(
            422, "enforce_requires_domain", "Verify at least one email domain before requiring SSO."
        )
    conn.issuer = issuer
    conn.client_id = client_id.strip()
    if client_secret:
        conn.client_secret_encrypted = box.encrypt(client_secret, context=_secret_context(conn.id))
    if created:
        s.add(conn)
    conn.enabled = enabled
    conn.enforce = enforce
    conn.jit_provisioning = jit_provisioning
    conn.default_role_key = default_role_key
    await audit.record(
        s,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="sso.configured",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="sso_connection",
        target_id=conn.id,
        details={
            "created": created,
            "issuer": issuer,
            "enabled": enabled,
            "enforce": enforce,
            "jit_provisioning": jit_provisioning,
            "default_role_key": default_role_key,
            "secret_changed": bool(client_secret),
        },
    )
    await s.flush()
    return conn


async def add_domain(
    s: AsyncSession, ctx: TenantContext, domain: str, meta: RequestMeta
) -> SsoDomain:
    domain = domain.strip().lower().rstrip(".")
    if domain in PUBLIC_EMAIL_DOMAINS:
        raise ApiError(
            422, "public_domain", "Public email domains can't be used for single sign-on."
        )
    conn = await get_connection(s, ctx.organisation_id)
    if conn is None:
        raise ApiError(409, "no_connection", "Set up the identity provider first.")
    existing = await s.scalar(text("SELECT 1 FROM operon_sso_for_domain(:d)"), {"d": domain})
    if existing:
        raise ApiError(
            409, "domain_taken", "Another organisation has already verified this domain."
        )
    row = await s.get(SsoDomain, domain)
    if row is not None:
        return row
    row = SsoDomain(
        domain=domain,
        organisation_id=ctx.organisation_id,
        connection_id=conn.id,
        verification_token=secrets.token_urlsafe(24),
    )
    s.add(row)
    try:
        await s.flush()
    except Exception as exc:  # unique across organisations, unverified claim elsewhere
        raise ApiError(
            409, "domain_taken", "This domain is being claimed by another organisation."
        ) from exc
    await audit.record(
        s,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="sso.domain_added",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="sso_domain",
        target_id=domain,
    )
    return row


async def lookup_txt(name: str) -> list[str]:
    try:
        answer = await dns.asyncresolver.resolve(name, "TXT", lifetime=5)
    except (dns.exception.DNSException, OSError):
        return []
    return [b"".join(r.strings).decode("utf-8", "replace") for r in answer]


async def verify_domain(
    s: AsyncSession, ctx: TenantContext, domain: str, meta: RequestMeta
) -> SsoDomain:
    row = await s.get(SsoDomain, domain.lower())
    if row is None or row.organisation_id != ctx.organisation_id:
        raise ApiError(404, "not_found", "Domain not found.")
    if row.verified_at is None:
        expected = f"operon-verification={row.verification_token}"
        records = await lookup_txt(f"{TXT_PREFIX}.{row.domain}")
        if expected not in records:
            raise ApiError(
                422,
                "not_verified",
                f"The TXT record wasn't found yet. Add {TXT_PREFIX}.{row.domain} with the value "
                f"{expected}. DNS changes can take a while to appear.",
            )
        row.verified_at = datetime.now(UTC)
        await audit.record(
            s,
            actor=Actor.user(ctx.user_id, ctx.user_email),
            action="sso.domain_verified",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="sso_domain",
            target_id=row.domain,
        )
    return row


async def remove_domain(
    s: AsyncSession, ctx: TenantContext, domain: str, meta: RequestMeta
) -> None:
    row = await s.get(SsoDomain, domain.lower())
    if row is None or row.organisation_id != ctx.organisation_id:
        raise ApiError(404, "not_found", "Domain not found.")
    conn = await get_connection(s, ctx.organisation_id)
    others = [
        d for d in await domains(s, ctx.organisation_id) if d.domain != row.domain and d.verified_at
    ]
    if conn is not None and conn.enforce and not others:
        raise ApiError(
            409, "last_enforced_domain", "Stop requiring SSO before removing its last domain."
        )
    await s.delete(row)
    await audit.record(
        s,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="sso.domain_removed",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="sso_domain",
        target_id=domain,
    )


# --- discovery ---------------------------------------------------------------------------------


async def discover(
    http: httpx.AsyncClient, issuer: str, *, redis: Redis | None = None, refresh: bool = False
) -> dict[str, Any]:
    key = f"oidc_discovery:{hashlib.sha256(issuer.encode()).hexdigest()}"
    if redis is not None and not refresh:
        cached = await redis.get(key)
        if cached:
            return dict(json.loads(cached))
    try:
        r = await http.get(f"{issuer}/.well-known/openid-configuration")
        r.raise_for_status()
        doc = dict(r.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise ApiError(
            422,
            "discovery_failed",
            "The identity provider's OpenID configuration couldn't be read.",
        ) from exc
    if doc.get("issuer", "").rstrip("/") != issuer.rstrip("/"):
        raise ApiError(422, "issuer_mismatch", "The provider reports a different issuer.")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not str(doc.get(field, "")).startswith("https://") and not str(
            doc.get(field, "")
        ).startswith(issuer):
            raise ApiError(422, "discovery_failed", f"The provider's {field} isn't usable.")
    if redis is not None:
        await redis.set(key, json.dumps(doc), ex=DISCOVERY_TTL)
    return doc


# --- sign-in -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    organisation_id: UUID
    connection_id: UUID
    enforce: bool


async def route_for_email(s: AsyncSession, email: str) -> Route | None:
    row = (
        await s.execute(
            text("SELECT organisation_id, connection_id, enforce FROM operon_sso_for_domain(:d)"),
            {"d": domain_of(email)},
        )
    ).first()
    return Route(row[0], row[1], bool(row[2])) if row else None


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


def _state_key(state: str) -> str:
    return f"sso_state:{hashlib.sha256(state.encode()).hexdigest()}"


async def start(
    s: AsyncSession,
    redis: Redis,
    http: httpx.AsyncClient,
    *,
    email: str,
    redirect_uri: str,
    binding: str,
) -> str:
    """`binding` is a random value also set as a cookie on the starting browser; the callback
    must present it, so a sign-in can't be completed in someone else's browser (login CSRF)."""
    route = await route_for_email(s, email)
    if route is None:
        raise ApiError(
            404, "sso_not_configured", "Single sign-on isn't set up for this email domain."
        )
    await set_rls_context(s, organisation_id=route.organisation_id)
    conn = await s.get(SsoConnection, route.connection_id)
    assert conn is not None
    doc = await discover(http, conn.issuer, redis=redis)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = _pkce()
    await redis.set(
        _state_key(state),
        json.dumps(
            {
                "org": str(route.organisation_id),
                "conn": str(conn.id),
                "nonce": nonce,
                "verifier": verifier,
                "redirect_uri": redirect_uri,
                "binding": hashlib.sha256(binding.encode()).hexdigest(),
            }
        ),
        ex=STATE_TTL,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": conn.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "login_hint": email,
        }
    )
    return f"{doc['authorization_endpoint']}?{query}"


@dataclass(frozen=True)
class SignedIn:
    user: User
    organisation_id: UUID
    created_user: bool
    joined: bool


SSO_FAILED = ApiError(401, "sso_failed", "Single sign-on didn't complete. Try again.")


async def complete(
    s: AsyncSession,
    redis: Redis,
    http: httpx.AsyncClient,
    box: SecretBox,
    *,
    code: str,
    state: str,
    binding: str | None,
    meta: RequestMeta,
) -> SignedIn:
    raw = await redis.getdel(_state_key(state))  # single use
    if not raw:
        raise ApiError(400, "sso_state_invalid", "This sign-in link expired. Start again.")
    st = json.loads(raw)
    presented = hashlib.sha256((binding or "").encode()).hexdigest()
    if not binding or not hmac.compare_digest(presented, st.get("binding", "")):
        raise ApiError(400, "sso_state_invalid", "This sign-in link expired. Start again.")
    org, conn_id = UUID(st["org"]), UUID(st["conn"])
    await set_rls_context(s, organisation_id=org)
    conn = await s.get(SsoConnection, conn_id)
    if conn is None or not conn.enabled:
        raise SSO_FAILED
    doc = await discover(http, conn.issuer, redis=redis)
    secret = box.decrypt(conn.client_secret_encrypted, context=_secret_context(conn.id))
    try:
        token_response = await http.post(
            doc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": st["redirect_uri"],
                "code_verifier": st["verifier"],
            },
            auth=(conn.client_id, secret),
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        id_token = str(token_response.json()["id_token"])
        jwks = (await http.get(doc["jwks_uri"])).json()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("sso_token_exchange_failed", organisation_id=str(org), error=type(exc).__name__)
        raise SSO_FAILED from exc
    claims = _verify_id_token(
        id_token, jwks, issuer=doc.get("issuer", conn.issuer), audience=conn.client_id
    )
    if claims.get("nonce") != st["nonce"]:
        raise SSO_FAILED
    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise ApiError(
            403, "email_not_verified", "Your identity provider didn't confirm your email."
        )
    verified = {d.domain for d in await domains(s, org) if d.verified_at}
    if domain_of(email) not in verified:
        raise ApiError(
            403, "domain_not_allowed", "Your email domain isn't verified for this organisation."
        )
    subject = str(claims["sub"])
    return await _link_and_join(s, conn, org, subject, email, claims, meta)


def _verify_id_token(
    token: str, jwks: dict[str, Any], *, issuer: str, audience: str
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        keys = {k.get("kid"): k for k in jwks.get("keys", [])}
        jwk = keys.get(header.get("kid")) or (next(iter(keys.values())) if len(keys) == 1 else None)
        if jwk is None or header.get("alg") not in ALGORITHMS:
            raise SSO_FAILED
        key = jwt.PyJWK(jwk).key
        return dict(
            jwt.decode(
                token,
                key=key,
                algorithms=ALGORITHMS,
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=60,
            )
        )
    except jwt.PyJWTError as exc:
        log.warning("sso_id_token_invalid", error=type(exc).__name__)
        raise SSO_FAILED from exc


async def _link_and_join(
    s: AsyncSession,
    conn: SsoConnection,
    org: UUID,
    subject: str,
    email: str,
    claims: dict[str, Any],
    meta: RequestMeta,
) -> SignedIn:
    now = datetime.now(UTC)
    identity = await s.scalar(
        select(UserIdentity).where(
            UserIdentity.connection_id == conn.id, UserIdentity.subject == subject
        )
    )
    created_user = joined = False
    if identity is not None:
        user = await s.get(User, identity.user_id)
        if user is None:
            raise SSO_FAILED
    else:
        user = await s.scalar(select(User).where(User.email == email))
        if user is None:
            if not conn.jit_provisioning:
                raise ApiError(403, "not_a_member", "Ask an administrator to invite you first.")
            name = str(claims.get("name") or email.split("@")[0])[:200]
            user = User(email=email, full_name=name, email_verified_at=now)
            s.add(user)
            await s.flush()
            created_user = True
        identity = UserIdentity(
            organisation_id=org, connection_id=conn.id, user_id=user.id, subject=subject
        )
        s.add(identity)
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account is disabled.")
    if user.email_verified_at is None:
        user.email_verified_at = now
    identity.last_login_at = now
    await set_rls_context(s, user_id=user.id, organisation_id=org)
    member = await s.scalar(
        select(Membership).where(Membership.organisation_id == org, Membership.user_id == user.id)
    )
    if member is None:
        if not conn.jit_provisioning:
            raise ApiError(403, "not_a_member", "Ask an administrator to invite you first.")
        role = await s.scalar(
            select(Role).where(Role.organisation_id == org, Role.key == conn.default_role_key)
        )
        if role is None:
            raise SSO_FAILED
        s.add(Membership(organisation_id=org, user_id=user.id, role_id=role.id))
        joined = True
        await audit.record(
            s,
            actor=Actor("user", user.id, f"{email} (single sign-on)"),
            action="member.joined",
            meta=meta,
            organisation_id=org,
            target_type="user",
            target_id=user.id,
            details={"via": "sso", "role": conn.default_role_key},
        )
    await s.flush()
    return SignedIn(user, org, created_user, joined)
