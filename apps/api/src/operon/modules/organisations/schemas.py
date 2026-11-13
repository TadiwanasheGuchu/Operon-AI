from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from operon.modules.identity.schemas import Email, Name, Token

RoleKey = Annotated[str, StringConstraints(min_length=1, max_length=60)]


class CreateOrganisationRequest(BaseModel):
    name: Name


class UpdateOrganisationRequest(BaseModel):
    name: Name | None = None
    mfa_required: bool | None = None


class OrganisationOut(BaseModel):
    id: UUID
    name: str
    mfa_required: bool
    is_demo: bool
    created_at: datetime


class CurrentOrganisationOut(OrganisationOut):
    """The organisation plus the caller's own role and permissions in it.

    For the UI to hide actions the user can't take; the API enforces them regardless.
    """

    role_key: str
    permissions: list[str]


class MemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role_key: str
    role_name: str
    joined_at: datetime
    mfa_enabled: bool
    is_you: bool


class ChangeRoleRequest(BaseModel):
    role_key: RoleKey


class CreateInvitationRequest(BaseModel):
    email: Email
    role_key: RoleKey


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role_key: str
    role_name: str
    invited_by: str | None
    created_at: datetime
    expires_at: datetime


class InvitationLookupOut(BaseModel):
    organisation_name: str
    email: str
    role_name: str
    invited_by: str | None
    expires_at: datetime
    status: str


class AcceptInvitationRequest(BaseModel):
    token: Token


class AcceptInvitationResponse(BaseModel):
    organisation_id: UUID
