"""Append-only audit trail. The application role may INSERT and SELECT only (enforced by grants)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"
    # Never INSERT ... RETURNING: PostgreSQL applies the SELECT policy to returned rows, and
    # account-level events (NULL organisation) are intentionally write-only for the app role.
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'agent')", name="actor_type_valid"),
        Index("ix_audit_logs_org_occurred", "organisation_id", "occurred_at"),
        Index("ix_audit_logs_actor", "actor_user_id", "occurred_at"),
    )

    # NULL for account-level security events (login, password reset) that belong to no tenant.
    organisation_id: Mapped[UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(String(20))
    # No FK: the trail must outlive deleted users and organisations.
    actor_user_id: Mapped[UUID | None] = mapped_column()
    actor_label: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(INET)
