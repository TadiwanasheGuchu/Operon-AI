from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin


class Notification(IdMixin, Base):
    """In-app notification for one user in one organisation."""

    __tablename__ = "notifications"
    # Created for *other* users, whose rows the creator can't SELECT under RLS: never RETURNING.
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        CheckConstraint(
            "kind IN ('member', 'security', 'insight', 'approval', 'incident', 'integration', "
            "'workflow')",
            name="kind_valid",
        ),
        Index("ix_notifications_recipient", "organisation_id", "user_id", "created_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="")
    # In-app path only (validated to start with "/"), never an external URL.
    link: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
