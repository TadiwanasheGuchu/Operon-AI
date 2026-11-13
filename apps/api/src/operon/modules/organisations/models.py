"""Organisations (tenants), memberships and invitations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin


class Organisation(IdMixin, TimestampMixin, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))
    # Organisation policy: members must have MFA enabled to access the workspace.
    mfa_required: Mapped[bool] = mapped_column(default=False)
    # Demo organisations show fictional, labelled sample data. Set only by the seed-demo command,
    # never through the API: the application role has no INSERT/UPDATE privilege on this column
    # (ADR 0009). No Python default, so inserts omit it and the server default applies.
    is_demo: Mapped[bool] = mapped_column(server_default="false")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Membership(IdMixin, TimestampMixin, Base):
    __tablename__ = "organisation_members"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id"),
        # Composite FK: a membership can only reference a role of the same organisation.
        ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_organisation_members_role_same_org",
        ),
        Index("ix_organisation_members_user_id", "user_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[UUID] = mapped_column()
    invited_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Invitation(IdMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_invitations_role_same_org",
        ),
        # At most one open invitation per email per organisation.
        Index(
            "uq_invitations_open_per_email",
            "organisation_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT)
    role_id: Mapped[UUID] = mapped_column()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
