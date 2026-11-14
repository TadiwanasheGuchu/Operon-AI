"""Data retention policy per organisation (Phase 7)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base

# Bounds: audit history is never kept less than a year; operational logs at least a week.
RETENTION_BOUNDS = {
    "audit_days": (365, 3650),
    "conversation_days": (7, 3650),
    "run_log_days": (30, 3650),
    "sync_job_days": (7, 3650),
}


class RetentionPolicy(Base):
    __tablename__ = "data_retention_policies"
    __table_args__ = tuple(
        CheckConstraint(f"{col} BETWEEN {lo} AND {hi}", name=f"{col}_range")
        for col, (lo, hi) in RETENTION_BOUNDS.items()
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    audit_days: Mapped[int] = mapped_column(Integer, default=730)
    conversation_days: Mapped[int] = mapped_column(Integer, default=90)
    run_log_days: Mapped[int] = mapped_column(Integer, default=180)
    sync_job_days: Mapped[int] = mapped_column(Integer, default=90)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
