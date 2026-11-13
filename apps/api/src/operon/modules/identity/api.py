from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from operon.access.dependencies import AuthDep, IdentityDep, OptionalAuthDep
from operon.core.config import Settings
from operon.core.deps import SettingsDep
from operon.core.errors import ApiError
from operon.modules.identity import schemas as s
from operon.modules.identity.service import IssuedSession, MfaChallenge
from operon.modules.organisations.service import list_my_organisations

router = APIRouter(tags=["auth"])

CHECK_EMAIL = s.AcceptedResponse(
    message="If the details are valid, we've sent an email with the next step."
)


def _set_session_cookie(response: Response, settings: Settings, issued: IssuedSession) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=settings.session_absolute_hours * 3600,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )


@router.get("/auth/session", response_model=s.SessionResponse, summary="Current sign-in state")
async def get_session(auth: OptionalAuthDep, identity: IdentityDep) -> s.SessionResponse:
    if auth is None:
        return s.SessionResponse(user=None)
    user = await identity.get_user(auth.user_id)
    orgs = await list_my_organisations(identity.s, auth.user_id)
    return s.SessionResponse(
        user=s.UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            email_verified=user.email_verified_at is not None,
            mfa_enabled=auth.mfa_enabled,
            created_at=user.created_at,
        ),
        organisations=[s.OrganisationSummary(**o.__dict__) for o in orgs],
    )


@router.post(
    "/auth/register", response_model=s.AcceptedResponse, status_code=status.HTTP_202_ACCEPTED
)
async def register(body: s.RegisterRequest, identity: IdentityDep) -> s.AcceptedResponse:
    await identity.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organisation_name=body.organisation_name,
        invitation_token=body.invitation_token,
    )
    return CHECK_EMAIL


@router.post("/auth/verify-email", response_model=s.AcceptedResponse)
async def verify_email(body: s.TokenRequest, identity: IdentityDep) -> s.AcceptedResponse:
    await identity.verify_email(body.token)
    return s.AcceptedResponse(message="Your email is confirmed. You can now sign in.")


@router.post(
    "/auth/verify-email/resend",
    response_model=s.AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resend_verification(body: s.EmailRequest, identity: IdentityDep) -> s.AcceptedResponse:
    await identity.resend_verification(body.email)
    return CHECK_EMAIL


@router.post("/auth/login", response_model=s.LoginResponse)
async def login(
    body: s.LoginRequest, response: Response, identity: IdentityDep, settings: SettingsDep
) -> s.LoginResponse:
    result = await identity.login(email=body.email, password=body.password)
    if isinstance(result, MfaChallenge):
        response.set_cookie(
            settings.mfa_cookie_name,
            result.token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/api/v1/auth/login",
            max_age=settings.mfa_challenge_minutes * 60,
        )
        return s.LoginResponse(status="mfa_required")
    _set_session_cookie(response, settings, result)
    return s.LoginResponse(status="authenticated")


@router.post("/auth/login/mfa", response_model=s.LoginResponse)
async def login_mfa(
    body: s.MfaLoginRequest,
    request: Request,
    response: Response,
    identity: IdentityDep,
    settings: SettingsDep,
) -> s.LoginResponse:
    challenge = request.cookies.get(settings.mfa_cookie_name)
    if not challenge:
        raise ApiError(
            401,
            "mfa_challenge_expired",
            "Your sign-in attempt expired. Enter your email and password again.",
        )
    issued = await identity.complete_mfa_login(challenge=challenge, code=body.code)
    response.delete_cookie(settings.mfa_cookie_name, path="/api/v1/auth/login")
    _set_session_cookie(response, settings, issued)
    return s.LoginResponse(status="authenticated")


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, auth: OptionalAuthDep, identity: IdentityDep, settings: SettingsDep
) -> Response:
    if auth is not None:
        await identity.logout(auth)
    _clear_session_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/auth/password/forgot", response_model=s.AcceptedResponse, status_code=status.HTTP_202_ACCEPTED
)
async def forgot_password(body: s.EmailRequest, identity: IdentityDep) -> s.AcceptedResponse:
    await identity.request_password_reset(body.email)
    return CHECK_EMAIL


@router.post("/auth/password/reset", response_model=s.AcceptedResponse)
async def reset_password(body: s.ResetPasswordRequest, identity: IdentityDep) -> s.AcceptedResponse:
    await identity.reset_password(token=body.token, new_password=body.password)
    return s.AcceptedResponse(message="Your password was changed. Sign in with your new password.")


@router.post("/auth/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: s.ChangePasswordRequest, auth: AuthDep, identity: IdentityDep
) -> None:
    await identity.change_password(auth, current=body.current_password, new=body.new_password)


@router.get("/auth/sessions", response_model=list[s.SessionOut])
async def list_sessions(auth: AuthDep, identity: IdentityDep) -> list[s.SessionOut]:
    return [
        s.SessionOut(
            id=x.id,
            created_at=x.created_at,
            last_seen_at=x.last_seen_at,
            expires_at=x.expires_at,
            ip_address=str(x.ip_address) if x.ip_address else None,
            user_agent=x.user_agent,
            current=x.id == auth.session_id,
        )
        for x in await identity.list_sessions(auth)
    ]


@router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: UUID, auth: AuthDep, identity: IdentityDep) -> None:
    await identity.revoke_session(auth, session_id)


@router.post("/auth/mfa/totp/setup", response_model=s.TotpSetupResponse)
async def totp_setup(auth: AuthDep, identity: IdentityDep) -> s.TotpSetupResponse:
    secret, uri = await identity.start_totp_setup(auth)
    return s.TotpSetupResponse(secret=secret, otpauth_uri=uri)


@router.post("/auth/mfa/totp/confirm", response_model=s.RecoveryCodesResponse)
async def totp_confirm(
    body: s.CodeRequest, auth: AuthDep, identity: IdentityDep
) -> s.RecoveryCodesResponse:
    return s.RecoveryCodesResponse(recovery_codes=await identity.confirm_totp(auth, body.code))


@router.post("/auth/mfa/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(body: s.DisableMfaRequest, auth: AuthDep, identity: IdentityDep) -> None:
    await identity.disable_totp(auth, password=body.password, code=body.code)


@router.post("/auth/mfa/recovery-codes", response_model=s.RecoveryCodesResponse)
async def regenerate_codes(
    body: s.CodeRequest, auth: AuthDep, identity: IdentityDep
) -> s.RecoveryCodesResponse:
    return s.RecoveryCodesResponse(
        recovery_codes=await identity.regenerate_recovery_codes(auth, body.code)
    )


@router.get("/users/me", response_model=s.UserOut, tags=["users"])
async def me(auth: AuthDep, identity: IdentityDep) -> s.UserOut:
    user = await identity.get_user(auth.user_id)
    return s.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        mfa_enabled=auth.mfa_enabled,
        created_at=user.created_at,
    )


@router.patch("/users/me", response_model=s.UserOut, tags=["users"])
async def update_me(
    body: s.UpdateProfileRequest, auth: AuthDep, identity: IdentityDep
) -> s.UserOut:
    user = await identity.update_profile(auth, full_name=body.full_name)
    return s.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        mfa_enabled=auth.mfa_enabled,
        created_at=user.created_at,
    )
