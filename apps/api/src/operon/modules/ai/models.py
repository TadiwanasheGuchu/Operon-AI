"""AI settings per organisation and a record of every model call (ADR 0006, ADR 0011)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin

PROVIDERS = ("anthropic", "openai")


class OrganisationAISettings(Base):
    """Whether this organisation lets Operon send evidence to a model provider, and how much.

    AI is off until an administrator turns it on: explanations then come from templates.
    """

    __tablename__ = "organisation_ai_settings"
    __table_args__ = (
        CheckConstraint("provider IN ('anthropic', 'openai')", name="provider_valid"),
        CheckConstraint("monthly_token_budget >= 0", name="budget_non_negative"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False)
    provider: Mapped[str] = mapped_column(String(20), default="anthropic")
    monthly_token_budget: Mapped[int] = mapped_column(Integer, default=200_000)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIGeneration(IdMixin, Base):
    """One attempt to generate text with a model: inputs summarised, outputs, cost, verdict.

    Every attempt is recorded, including ones the validator rejected and ones skipped because
    the budget was spent, so an explanation can always be traced to how it was produced.
    """

    __tablename__ = "ai_generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'rejected', 'refused', 'failed', 'skipped')",
            name="status_valid",
        ),
        Index("ix_ai_generations_org_created", "organisation_id", "created_at"),
        Index("ix_ai_generations_subject", "organisation_id", "subject_type", "subject_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    purpose: Mapped[str] = mapped_column(String(60))
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[UUID] = mapped_column()
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # The validated (or rejected) structured output; never the prompt, which holds tenant data
    # that already lives in the evidence tables.
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    problems: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
