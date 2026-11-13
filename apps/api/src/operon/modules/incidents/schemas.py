from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from operon.modules.intelligence.schemas import PersonOut, Severity

IncidentStatus = Literal["open", "investigating", "resolved"]


class LinkedInsight(BaseModel):
    id: UUID
    reference: str
    title: str
    status: str
    severity: Severity


class IncidentSummary(BaseModel):
    id: UUID
    reference: str
    title: str
    severity: Severity
    status: IncidentStatus
    assignee: PersonOut | None
    insight: LinkedInsight | None
    response_due_at: datetime
    response_overdue: bool
    escalation_level: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class IncidentListOut(BaseModel):
    items: list[IncidentSummary]
    total: int
    limit: int
    offset: int
    unresolved_by_severity: dict[str, int]


class IncidentEventOut(BaseModel):
    id: UUID
    kind: str
    actor_label: str
    body: str | None
    details: dict[str, Any]
    created_at: datetime


class IncidentDetail(IncidentSummary):
    description: str
    resolution: str | None
    reported_by: PersonOut | None
    events: list[IncidentEventOut]
    allowed_transitions: list[str]


class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field("", max_length=10_000)
    severity: Severity
    assignee_user_id: UUID | None = None


class EscalateInsightRequest(BaseModel):
    assignee_user_id: UUID | None = None
    note: str = Field("", max_length=10_000)


class UpdateIncidentRequest(BaseModel):
    status: IncidentStatus | None = None
    severity: Severity | None = None
    # Omit to leave unchanged; null to unassign.
    assignee_user_id: UUID | None = Field(default=None)
    resolution: str | None = Field(None, max_length=10_000)


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)
