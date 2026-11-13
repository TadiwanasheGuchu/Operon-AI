"""Incidents: problems someone owns until they are resolved (plan §4.6).

Comments, assignments, status and severity changes are all rows in `incident_events`, an
append-only timeline. Comments are therefore immutable, like the rest of the record.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin

INCIDENT_STATUSES = ("open", "investigating", "resolved")


class Incident(IdMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="severity_valid"),
        CheckConstraint("status IN ('open', 'investigating', 'resolved')", name="status_valid"),
        CheckConstraint(
            "status <> 'resolved' OR resolution IS NOT NULL", name="resolution_required"
        ),
        UniqueConstraint("organisation_id", "id", name="uq_incidents_org_id"),
        UniqueConstraint("organisation_id", "number", name="uq_incidents_org_number"),
        ForeignKeyConstraint(
            ["organisation_id", "insight_id"],
            ["ai_insights.organisation_id", "ai_insights.id"],
            name="fk_incidents_insight_same_org",
            ondelete="SET NULL (insight_id)",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "assignee_user_id"],
            ["organisation_members.organisation_id", "organisation_members.user_id"],
            name="fk_incidents_assignee_is_member",
            ondelete="SET NULL (assignee_user_id)",
        ),
        # One unresolved incident per insight: escalating twice opens the existing one.
        Index(
            "uq_incidents_active_insight",
            "organisation_id",
            "insight_id",
            unique=True,
            postgresql_where=text("status <> 'resolved' AND insight_id IS NOT NULL"),
        ),
        Index("ix_incidents_org_status", "organisation_id", "status", "severity"),
        Index(
            "ix_incidents_due",
            "response_due_at",
            postgresql_where=text("status = 'open'"),
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="open")
    insight_id: Mapped[UUID | None] = mapped_column()
    assignee_user_id: Mapped[UUID | None] = mapped_column()
    reported_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Someone must start working on it (status → investigating) by this time, or it escalates.
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    last_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def reference(self) -> str:
        return f"INC-{self.number:04d}"


class IncidentEvent(IdMixin, Base):
    __tablename__ = "incident_events"
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "incident_id"],
            ["incidents.organisation_id", "incidents.id"],
            ondelete="CASCADE",
            name="fk_incident_events_incident_same_org",
        ),
        CheckConstraint(
            "kind IN ('created', 'comment', 'assigned', 'status_changed', 'severity_changed', "
            "'escalated', 'insight_linked')",
            name="kind_valid",
        ),
        Index("ix_incident_events_incident", "incident_id", "created_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    incident_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(320))
    body: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
