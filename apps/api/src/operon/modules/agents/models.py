"""Assistant conversations, agents, and the full record of every model run (plan §6, ADR 0014).

Every model loop, from an assistant answer or an agent run, is an `agent_executions` row with
append-only `agent_execution_steps`: each model turn, tool call (with its validated input and
truncated output), refusal, denial and limit. A run can be reconstructed from these alone.
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin


class Agent(IdMixin, TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_agents_org_id"),
        UniqueConstraint("organisation_id", "key", name="uq_agents_org_key"),
        CheckConstraint("key IN ('inventory_replenishment')", name="key_valid"),
        CheckConstraint("schedule IN ('off', 'daily')", name="schedule_valid"),
        # The agent acts for a named member: their permissions cap it, and they own its requests.
        ForeignKeyConstraint(
            ["organisation_id", "run_as_user_id"],
            ["organisation_members.organisation_id", "organisation_members.user_id"],
            name="fk_agents_run_as_is_member",
            ondelete="SET NULL (run_as_user_id)",
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(default=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    run_as_user_id: Mapped[UUID | None] = mapped_column()
    schedule: Mapped[str] = mapped_column(String(20), default="off")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentVersion(IdMixin, Base):
    """Immutable instructions and limits. Runs record the version they used."""

    __tablename__ = "agent_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "agent_id"],
            ["agents.organisation_id", "agents.id"],
            ondelete="CASCADE",
            name="fk_agent_versions_agent_same_org",
        ),
        UniqueConstraint("agent_id", "version", name="uq_agent_versions_agent_version"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    agent_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class AgentToolPermission(Base):
    """The agent's tool allowlist. A tool not listed here, or disabled, is never offered."""

    __tablename__ = "agent_tool_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "agent_id"],
            ["agents.organisation_id", "agents.id"],
            ondelete="CASCADE",
            name="fk_agent_tool_permissions_agent_same_org",
        ),
    )

    agent_id: Mapped[UUID] = mapped_column(primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    enabled: Mapped[bool] = mapped_column(default=False)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(IdMixin, TimestampMixin, Base):
    """An assistant conversation. Private to the member who started it."""

    __tablename__ = "assistant_conversations"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_assistant_conversations_org_id"),
        Index("ix_assistant_conversations_owner", "organisation_id", "user_id", "updated_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))


class ConversationMessage(IdMixin, Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "conversation_id"],
            ["assistant_conversations.organisation_id", "assistant_conversations.id"],
            ondelete="CASCADE",
            name="fk_assistant_messages_conversation_same_org",
        ),
        CheckConstraint("role IN ('user', 'assistant')", name="role_valid"),
        Index("ix_assistant_messages_conversation", "conversation_id", "created_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[UUID] = mapped_column()
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # [{"ref", "label", "href", "kind"}]: records the answer relied on, all returned by tools.
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Verification of the answer against tool outputs (numbers, references).
    checked: Mapped[bool] = mapped_column(default=True)
    problems: Mapped[list[str]] = mapped_column(JSONB, default=list)
    execution_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class AgentExecution(IdMixin, Base):
    __tablename__ = "agent_executions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_agent_executions_org_id"),
        CheckConstraint("kind IN ('assistant', 'agent')", name="kind_valid"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'limited', 'refused', 'failed')",
            name="status_valid",
        ),
        CheckConstraint("trigger IN ('chat', 'manual', 'schedule')", name="trigger_valid"),
        ForeignKeyConstraint(
            ["organisation_id", "agent_id"],
            ["agents.organisation_id", "agents.id"],
            ondelete="CASCADE",
            name="fk_agent_executions_agent_same_org",
        ),
        Index("ix_agent_executions_org_started", "organisation_id", "kind", "started_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    agent_id: Mapped[UUID | None] = mapped_column()
    agent_version: Mapped[int | None] = mapped_column(Integer)
    conversation_id: Mapped[UUID | None] = mapped_column()
    trigger: Mapped[str] = mapped_column(String(20))
    triggered_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(60))
    tools_offered: Mapped[list[str]] = mapped_column(JSONB, default=list)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(String(60))
    error: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentExecutionStep(IdMixin, Base):
    """Append-only log of one run."""

    __tablename__ = "agent_execution_steps"
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012 — SQLAlchemy declarative hook
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "execution_id"],
            ["agent_executions.organisation_id", "agent_executions.id"],
            ondelete="CASCADE",
            name="fk_agent_execution_steps_execution_same_org",
        ),
        CheckConstraint(
            "kind IN ('model_turn', 'tool_call', 'tool_denied', 'tool_error', 'limit', "
            "'refused', 'final', 'error')",
            name="kind_valid",
        ),
        Index("ix_agent_execution_steps_execution", "execution_id", "position"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    execution_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    tool_name: Mapped[str | None] = mapped_column(String(60))
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
