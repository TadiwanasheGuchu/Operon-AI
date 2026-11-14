"""Single sign-on (OIDC) per organisation, verified email domains, linked identities."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin


class SsoConnection(IdMixin, TimestampMixin, Base):
    __tablename__ = "sso_connections"
    __table_args__ = (
        UniqueConstraint("organisation_id", name="uq_sso_connections_organisation_id"),
        UniqueConstraint("organisation_id", "id", name="uq_sso_connections_org_id"),
        CheckConstraint(
            "default_role_key IN ('operations_manager', 'approver', 'analyst', 'viewer')",
            name="default_role_valid",
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    issuer: Mapped[str] = mapped_column(String(300))
    client_id: Mapped[str] = mapped_column(String(300))
    # AES-GCM encrypted, bound to the connection id (core.crypto.SecretBox).
    client_secret_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=False)
    # When on, members whose email is in a verified domain must sign in with SSO.
    enforce: Mapped[bool] = mapped_column(default=False)
    # Create memberships for people from verified domains on their first SSO sign-in.
    jit_provisioning: Mapped[bool] = mapped_column(default=True)
    default_role_key: Mapped[str] = mapped_column(String(40), default="viewer")


class SsoDomain(Base):
    """An email domain an organisation has proved it controls (DNS TXT). Globally unique."""

    __tablename__ = "sso_domains"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["sso_connections.organisation_id", "sso_connections.id"],
            ondelete="CASCADE",
            name="fk_sso_domains_connection_same_org",
        ),
        CheckConstraint("domain = lower(domain)", name="domain_lowercase"),
    )

    domain: Mapped[str] = mapped_column(String(253), primary_key=True)
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[UUID] = mapped_column()
    verification_token: Mapped[str] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserIdentity(IdMixin, Base):
    """A user's identity at an organisation's identity provider (issuer + subject)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("connection_id", "subject", name="uq_user_identities_connection_subject"),
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["sso_connections.organisation_id", "sso_connections.id"],
            ondelete="CASCADE",
            name="fk_user_identities_connection_same_org",
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[UUID] = mapped_column()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    subject: Mapped[str] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
