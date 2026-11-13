"""Platform-level tables that belong to no single domain module."""

from typing import Any

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin


class SystemEvent(IdMixin, TimestampMixin, Base):
    """Platform-wide operational events (deployments, migrations, maintenance).

    Not tenant-scoped: never store organisation data here. Tenant activity goes to audit_logs.
    """

    __tablename__ = "system_events"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')", name="severity_valid"
        ),
    )

    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(String(1000))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
