from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
InsightStatus = Literal["open", "acknowledged", "actioned", "resolved", "dismissed"]


class PersonOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str


class SourceConnection(BaseModel):
    id: UUID
    name: str
    connector: str


class EvidenceOut(BaseModel):
    id: UUID
    key: str
    label: str
    value: str
    unit: str | None
    source_type: str
    source_id: UUID | None
    source_ref: str | None
    connection: SourceConnection | None
    observed_at: datetime | None
    formula: str | None
    # Synced records can be opened; computed and configured values show their formula instead.
    resolvable: bool


class InsightSummary(BaseModel):
    id: UUID
    reference: str
    rule_id: str
    rule_version: int
    category: str
    severity: Severity
    confidence: Literal["normal", "low"]
    status: InsightStatus
    title: str
    summary: str
    subject_label: str
    owner: PersonOut | None
    detected_at: datetime
    last_evaluated_at: datetime
    incident_id: UUID | None


class InsightListOut(BaseModel):
    items: list[InsightSummary]
    total: int
    limit: int
    offset: int
    active_by_severity: dict[str, int]


class ExplanationOut(BaseModel):
    what_happened: str
    why_it_matters: str
    source: Literal["template", "model"]
    provider: str | None
    model: str | None
    generated_at: datetime | None
    pending: bool


class InsightEventOut(BaseModel):
    id: UUID
    kind: str
    actor_label: str
    details: dict[str, Any]
    created_at: datetime


class InsightDetail(InsightSummary):
    metrics: dict[str, str]
    recommendation: dict[str, Any] | None
    recommended_action: str
    assumptions: list[str]
    limitations: list[str]
    explanation: ExplanationOut
    evidence: list[EvidenceOut]
    events: list[InsightEventOut]
    closed_at: datetime | None
    close_reason: str | None
    suppressed_until: datetime | None
    allowed_transitions: list[str]


class StatusChangeRequest(BaseModel):
    status: Literal["acknowledged", "actioned", "resolved", "dismissed", "open"]
    reason: str | None = Field(None, max_length=500)


class OwnerRequest(BaseModel):
    user_id: UUID | None


class DetectorParamOut(BaseModel):
    name: str
    description: str | None
    type: str
    default: Any
    value: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None


class DetectorOut(BaseModel):
    rule_id: str
    version: int
    name: str
    category: str
    description: str
    enabled: bool
    params: list[DetectorParamOut]
    updated_at: datetime | None


class DetectorUpdate(BaseModel):
    enabled: bool
    params: dict[str, Any] = Field(default_factory=dict)


class DetectionRunOut(BaseModel):
    id: UUID
    trigger: str
    status: str
    as_of: date
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None


class AISettingsOut(BaseModel):
    enabled: bool
    provider: Literal["anthropic", "openai"]
    provider_available: bool
    model: str | None
    monthly_token_budget: int
    tokens_used_this_month: int
    available_providers: list[str]
    data_shared: str


class AISettingsUpdate(BaseModel):
    enabled: bool
    provider: Literal["anthropic", "openai"]
    monthly_token_budget: int = Field(ge=0, le=50_000_000)
