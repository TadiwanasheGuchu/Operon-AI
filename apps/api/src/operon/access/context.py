"""Who is making the request, and in which organisation. Pure data: no module imports."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class RequestMeta:
    ip_address: str | None
    user_agent: str | None
    request_id: str | None


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    email: str
    full_name: str
    session_id: UUID
    mfa_enabled: bool


@dataclass(frozen=True)
class TenantContext:
    """Built only after the user's membership in the organisation has been verified."""

    organisation_id: UUID
    user_id: UUID
    user_email: str
    membership_id: UUID
    role_key: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass(frozen=True)
class Actor:
    type: str  # "user" | "system" | "agent"
    user_id: UUID | None
    label: str

    @classmethod
    def user(cls, user_id: UUID, email: str) -> "Actor":
        return cls("user", user_id, email)

    @classmethod
    def anonymous(cls, label: str) -> "Actor":
        return cls("user", None, label)
