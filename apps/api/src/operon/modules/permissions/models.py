from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin


class Permission(Base):
    """Global catalogue (not tenant-owned)."""

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    description: Mapped[str] = mapped_column(String(300))


class Role(IdMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key"),
        # Target of composite FKs that keep role references inside one organisation.
        UniqueConstraint("organisation_id", "id", name="uq_roles_organisation_id_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    is_system: Mapped[bool] = mapped_column(default=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            ondelete="CASCADE",
            name="fk_role_permissions_role_same_org",
        ),
        Index("ix_role_permissions_organisation_id", "organisation_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    role_id: Mapped[UUID] = mapped_column(primary_key=True)
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True
    )
