from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from operon.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


def _normalise_email(value: str) -> str:
    return value.strip().lower()


Email = Annotated[EmailStr, AfterValidator(_normalise_email)]
NewPassword = Annotated[
    str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]
AnyPassword = Annotated[str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Token = Annotated[str, StringConstraints(min_length=20, max_length=200)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=20)]


class RegisterRequest(BaseModel):
    email: Email
    password: NewPassword
    full_name: Name
    organisation_name: Name | None = None
    invitation_token: Token | None = None


class LoginRequest(BaseModel):
    email: Email
    password: AnyPassword


class LoginResponse(BaseModel):
    status: str = Field(description='"authenticated" or "mfa_required"')


class MfaLoginRequest(BaseModel):
    code: Code


class EmailRequest(BaseModel):
    email: Email


class TokenRequest(BaseModel):
    token: Token


class ResetPasswordRequest(BaseModel):
    token: Token
    password: NewPassword


class ChangePasswordRequest(BaseModel):
    current_password: AnyPassword
    new_password: NewPassword


class AcceptedResponse(BaseModel):
    message: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    email_verified: bool
    mfa_enabled: bool
    created_at: datetime


class OrganisationSummary(BaseModel):
    id: UUID
    name: str
    role_key: str
    role_name: str
    mfa_required: bool
    is_demo: bool


class SessionResponse(BaseModel):
    """Current sign-in state. `user` is null when signed out (not an error)."""

    user: UserOut | None
    organisations: list[OrganisationSummary] = []


class UpdateProfileRequest(BaseModel):
    full_name: Name


class SessionOut(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    current: bool


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class CodeRequest(BaseModel):
    code: Code


class DisableMfaRequest(BaseModel):
    password: AnyPassword
    code: Code


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]
