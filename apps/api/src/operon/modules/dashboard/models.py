from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base


class DashboardLayout(Base):
    """A user's chosen overview layout in one organisation. Absent row = role default."""

    __tablename__ = "dashboard_layouts"
    __table_args__ = (
        CheckConstraint(
            "preset IN ('executive', 'operations', 'finance', 'warehouse')", name="preset_valid"
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preset: Mapped[str] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
