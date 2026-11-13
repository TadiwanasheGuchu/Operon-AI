"""Insights raised by detectors, the evidence behind them, and their history (plan §4.1–4.5)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin

SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
ACTIVE_STATUSES = ("open", "acknowledged", "actioned")
INSIGHT_STATUSES = (*ACTIVE_STATUSES, "resolved", "dismissed")


def _same_org_insight(table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", "insight_id"],
        ["ai_insights.organisation_id", "ai_insights.id"],
        ondelete="CASCADE",
        name=f"fk_{table}_insight_same_org",
    )


class DetectorConfig(Base):
    """Per-organisation switch and parameters for one detector rule."""

    __tablename__ = "detector_configs"

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    rule_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DetectionRun(IdMixin, Base):
    """One evaluation of an organisation's detectors, and what it changed."""

    __tablename__ = "detection_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('sync', 'upload', 'manual', 'schedule')", name="trigger_valid"
        ),
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status_valid"),
        Index("ix_detection_runs_org_started", "organisation_id", "started_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="running")
    as_of: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Per rule: evaluated, raised, updated, resolved, suppressed.
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))


class Insight(IdMixin, TimestampMixin, Base):
    """A condition a detector found, with the numbers, evidence and recommendation behind it.

    Numbers, severity and the recommended action are computed in code. A model may only
    rephrase them (`explanation`), and only after validation against the evidence.
    """

    __tablename__ = "ai_insights"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="severity_valid"),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'actioned', 'resolved', 'dismissed')",
            name="status_valid",
        ),
        CheckConstraint("confidence IN ('normal', 'low')", name="confidence_valid"),
        CheckConstraint(
            "explanation_source IN ('template', 'model')", name="explanation_source_valid"
        ),
        UniqueConstraint("organisation_id", "id", name="uq_ai_insights_org_id"),
        UniqueConstraint("organisation_id", "number", name="uq_ai_insights_org_number"),
        # At most one active insight per rule and subject: re-detection updates it.
        Index(
            "uq_ai_insights_active_subject",
            "organisation_id",
            "rule_id",
            "subject_key",
            unique=True,
            postgresql_where=text("status IN ('open', 'acknowledged', 'actioned')"),
        ),
        Index("ix_ai_insights_org_status", "organisation_id", "status", "severity"),
        ForeignKeyConstraint(
            ["organisation_id", "owner_user_id"],
            ["organisation_members.organisation_id", "organisation_members.user_id"],
            name="fk_ai_insights_owner_is_member",
            ondelete="SET NULL (owner_user_id)",
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(80))
    rule_version: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40))
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_key: Mapped[str] = mapped_column(String(200))
    subject_label: Mapped[str] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[str] = mapped_column(String(10), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="open")
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    # Computed values (as strings, exactly as shown in evidence) keyed by name.
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recommendation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # {"what_happened": str, "why_it_matters": str}
    explanation: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    explanation_source: Mapped[str] = mapped_column(String(20), default="template")
    explanation_generation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ai_generations.id", ondelete="SET NULL")
    )
    # A fresh explanation is needed (new insight, or its numbers changed).
    explanation_stale: Mapped[bool] = mapped_column(default=True)
    owner_user_id: Mapped[UUID | None] = mapped_column()
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(500))
    # A dismissal suppresses re-raising for the same subject until then, unless it worsens.
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def reference(self) -> str:
        return f"INS-{self.number:04d}"


class InsightEvidence(IdMixin, Base):
    """One fact behind an insight, traceable to the record (or setting) it came from."""

    __tablename__ = "insight_evidence"
    __table_args__ = (
        _same_org_insight("insight_evidence"),
        CheckConstraint(
            "source_type IN ('stock_level', 'sales_daily', 'purchase_order', "
            "'purchase_order_line', 'supplier_product', 'product', 'detector_config', "
            "'computed')",
            name="source_type_valid",
        ),
        Index("ix_insight_evidence_insight", "insight_id", "position"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    insight_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(200))
    # Display value exactly as users (and the explanation validator) see it.
    value: Mapped[str] = mapped_column(String(200))
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(30))
    source_type: Mapped[str] = mapped_column(String(40))
    # The Operon record id, plus the source system's own reference where there is one.
    source_id: Mapped[UUID | None] = mapped_column()
    source_ref: Mapped[str | None] = mapped_column(String(300))
    connection_id: Mapped[UUID | None] = mapped_column()
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How a computed value was derived, e.g. "z × σ × √L".
    formula: Mapped[str | None] = mapped_column(String(200))


class InsightEvent(IdMixin, Base):
    """Append-only history of an insight: detection, re-evaluation, people's decisions."""

    __tablename__ = "insight_events"
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        _same_org_insight("insight_events"),
        Index("ix_insight_events_insight", "insight_id", "created_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    insight_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(320))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
