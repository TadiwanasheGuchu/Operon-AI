"""Contract for GET /api/v1/dashboard/summary.

Mirrored by apps/web/src/features/dashboard/contract.ts.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from operon.modules.dashboard.layouts import SectionKey, Size

Provenance = Literal["live", "demo", "stale", "unavailable"]
Period = Literal["7d", "30d", "90d"]
Severity = Literal["critical", "high", "medium", "low"]


class Section[T](BaseModel):
    """One dashboard section. Never contains data without saying where it came from."""

    state: Literal["ready", "unavailable", "restricted"]
    provenance: Provenance
    as_of: datetime | None = None
    message: str | None = None
    available_in_phase: int | None = None
    data: T | None = None


class Indicator(BaseModel):
    key: str
    label: str
    value: int | None
    total: int | None = None
    previous_value: int | None = None
    increase_is: Literal["good", "bad", "neutral"] = "neutral"
    state: Literal["healthy", "attention", "critical", "neutral"] = "neutral"
    detail: str
    provenance: Provenance


class EvidenceItem(BaseModel):
    label: str
    value: str
    source: str | None = None


class Insight(BaseModel):
    id: str
    ref: str
    title: str
    category: Literal["inventory", "procurement", "finance", "operations"]
    severity: Severity
    status: Literal["open", "acknowledged", "actioned", "resolved", "dismissed"]
    detected_at: datetime
    owner: str | None
    source_system: str
    rule_id: str
    rule_version: int
    summary: str
    why_it_matters: str
    recommended_action: str
    assumptions: list[str]
    limitations: list[str]
    evidence: list[EvidenceItem]
    explanation_generated_by: Literal["model", "template"]
    explanation_model: str | None


class Approval(BaseModel):
    id: str
    ref: str
    title: str
    requester: str
    amount: float | None
    currency: str | None
    policy: str
    requested_at: datetime
    related_insight_ref: str | None


class ActivityEvent(BaseModel):
    id: str
    at: datetime
    actor_type: Literal["system", "user", "integration", "agent"]
    actor: str
    message: str
    ref: str | None


class IntegrationStatus(BaseModel):
    id: str
    name: str
    system: str
    status: Literal["healthy", "degraded", "disconnected", "paused"]
    last_sync_at: datetime | None
    detail: str


class WorkflowStatus(BaseModel):
    workflow: str
    running: int
    awaiting_approval: int
    failed_24h: int
    completed: int
    success_rate: float


class FillRatePoint(BaseModel):
    date: date
    value: float


class FillRate(BaseModel):
    target: float
    points: list[FillRatePoint]


class LocationRisk(BaseModel):
    location: str
    skus_at_risk: int
    skus_tracked: int


class IncidentCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int


class SetupStep(BaseModel):
    key: str
    title: str
    body: str
    done: bool
    available: bool
    href: str | None
    action_label: str | None


class RecentJoin(BaseModel):
    name: str
    role_name: str
    joined_at: datetime


class Team(BaseModel):
    members: int
    pending_invitations: int
    mfa_enabled: int
    recent_joins: list[RecentJoin]


class OrganisationRef(BaseModel):
    id: str
    name: str
    is_demo: bool


class Viewer(BaseModel):
    name: str
    role_key: str
    role_name: str


class LayoutSection(BaseModel):
    key: SectionKey
    size: Size


class LayoutOut(BaseModel):
    preset: str
    name: str
    is_default: bool
    sections: list[LayoutSection]


class DashboardSummary(BaseModel):
    organisation: OrganisationRef
    viewer: Viewer
    layout: LayoutOut
    period: Period
    generated_at: datetime
    indicators: list[Indicator]
    getting_started: Section[list[SetupStep]]
    insights: Section[list[Insight]]
    approvals: Section[list[Approval]]
    incidents: Section[IncidentCounts]
    fill_rate: Section[FillRate]
    inventory_risk: Section[list[LocationRisk]]
    workflows: Section[list[WorkflowStatus]]
    integrations: Section[list[IntegrationStatus]]
    activity: Section[list[ActivityEvent]]
    team: Section[Team]


class PresetOut(BaseModel):
    key: str
    name: str
    description: str


class LayoutSettingsOut(BaseModel):
    current: LayoutOut
    default_preset: str
    presets: list[PresetOut]


class UpdateLayoutRequest(BaseModel):
    preset: Literal["executive", "operations", "finance", "warehouse"] | None
