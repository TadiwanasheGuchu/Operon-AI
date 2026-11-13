"""Workflow definitions, versions, executions, approvals and their timelines (plan §5.1).

A workflow is a template an organisation has configured (e.g. purchase requests). Its parameters
(approval thresholds, approver roles, timeouts) live in immutable versions; each execution pins
the version it started on, so editing settings never changes a request already in flight.
The approval policy is part of the version parameters, so there is no separate policies table.
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

EXECUTION_STATUSES = (
    "awaiting_approval",
    "approved",
    "executing",
    "completed",
    "rejected",
    "expired",
    "failed",
    "cancelled",
)
ACTIVE_EXECUTION = ("awaiting_approval", "approved", "executing")


class Workflow(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_workflows_org_id"),
        UniqueConstraint("organisation_id", "key", name="uq_workflows_org_key"),
        CheckConstraint("key IN ('purchase_request')", name="key_valid"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)


class WorkflowVersion(IdMixin, Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "workflow_id"],
            ["workflows.organisation_id", "workflows.id"],
            ondelete="CASCADE",
            name="fk_workflow_versions_workflow_same_org",
        ),
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
        UniqueConstraint("organisation_id", "id", name="uq_workflow_versions_org_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    workflow_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class WorkflowExecution(IdMixin, TimestampMixin, Base):
    """One run of a workflow, e.g. one purchase request (PR-0001)."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_approval', 'approved', 'executing', 'completed', 'rejected', "
            "'expired', 'failed', 'cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("organisation_id", "id", name="uq_workflow_executions_org_id"),
        UniqueConstraint("organisation_id", "number", name="uq_workflow_executions_org_number"),
        ForeignKeyConstraint(
            ["organisation_id", "workflow_id"],
            ["workflows.organisation_id", "workflows.id"],
            ondelete="CASCADE",
            name="fk_workflow_executions_workflow_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "version_id"],
            ["workflow_versions.organisation_id", "workflow_versions.id"],
            name="fk_workflow_executions_version_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "insight_id"],
            ["ai_insights.organisation_id", "ai_insights.id"],
            name="fk_workflow_executions_insight_same_org",
            ondelete="SET NULL (insight_id)",
        ),
        # One request in flight per insight: a second click can't order twice.
        Index(
            "uq_workflow_executions_active_insight",
            "organisation_id",
            "insight_id",
            unique=True,
            postgresql_where=text(
                "insight_id IS NOT NULL "
                "AND status IN ('awaiting_approval', 'approved', 'executing')"
            ),
        ),
        Index("ix_workflow_executions_org_status", "organisation_id", "status", "created_at"),
        Index(
            "ix_workflow_executions_wake",
            "next_wake_at",
            postgresql_where=text("next_wake_at IS NOT NULL"),
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)
    workflow_id: Mapped[UUID] = mapped_column()
    version_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(300))
    # Frozen at submission: product, location, supplier, quantity, price, value, target system.
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    insight_id: Mapped[UUID | None] = mapped_column()
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # External write: attempts, the external reference once created, the last error.
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))
    # When the execution next needs attention (approval deadline, retry backoff).
    next_wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engine_ref: Mapped[str | None] = mapped_column(String(200))

    @property
    def reference(self) -> str:
        return f"PR-{self.number:04d}"


class WorkflowApproval(IdMixin, Base):
    """One approval stage of an execution. Stages are decided in order."""

    __tablename__ = "workflow_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting', 'pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="status_valid",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "execution_id"],
            ["workflow_executions.organisation_id", "workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_workflow_approvals_execution_same_org",
        ),
        UniqueConstraint("execution_id", "stage", name="uq_workflow_approvals_execution_stage"),
        UniqueConstraint("organisation_id", "id", name="uq_workflow_approvals_org_id"),
        Index("ix_workflow_approvals_org_status", "organisation_id", "status"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    execution_id: Mapped[UUID] = mapped_column()
    stage: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    # Role keys allowed to decide this stage (they also need approvals.decide).
    approver_roles: Mapped[list[str]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class WorkflowExecutionEvent(IdMixin, Base):
    """Append-only execution timeline."""

    __tablename__ = "workflow_execution_events"
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "execution_id"],
            ["workflow_executions.organisation_id", "workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_workflow_execution_events_execution_same_org",
        ),
        Index("ix_workflow_execution_events_execution", "execution_id", "created_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    execution_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(320))
    message: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
