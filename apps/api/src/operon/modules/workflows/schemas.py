from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from operon.modules.intelligence.schemas import PersonOut

ExecutionStatus = Literal[
    "awaiting_approval",
    "approved",
    "executing",
    "completed",
    "rejected",
    "expired",
    "failed",
    "cancelled",
]


class ApprovalOut(BaseModel):
    id: UUID
    stage: int
    name: str
    approver_roles: list[str]
    approver_role_names: list[str]
    reason: str
    status: Literal["waiting", "pending", "approved", "rejected", "expired", "cancelled"]
    due_at: datetime | None
    escalated_at: datetime | None
    decided_by: PersonOut | None
    decided_at: datetime | None
    comment: str | None
    # For the current user: null if they may decide, otherwise why not.
    blocked_reason: str | None


class ExecutionSummary(BaseModel):
    id: UUID
    reference: str
    title: str
    status: ExecutionStatus
    requested_by: PersonOut | None
    supplier_name: str | None
    value_display: str | None
    insight_id: UUID | None
    insight_reference: str | None
    current_stage: str | None
    target: Literal["odoo", "record_only"]
    external_reference: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ExecutionListOut(BaseModel):
    items: list[ExecutionSummary]
    total: int
    limit: int
    offset: int
    by_status: dict[str, int]


class ExecutionEventOut(BaseModel):
    id: UUID
    kind: str
    actor_label: str
    message: str
    details: dict[str, Any]
    created_at: datetime


class ExecutionDetail(ExecutionSummary):
    input: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    attempts: int
    policy_version: int
    approvals: list[ApprovalOut]
    events: list[ExecutionEventOut]
    can_cancel: bool
    can_retry: bool


class SubmitRequest(BaseModel):
    insight_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)
    note: str = Field("", max_length=2000)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field("", max_length=2000)


class CancelRequest(BaseModel):
    reason: str = Field("", max_length=500)


class InboxItem(BaseModel):
    approval: ApprovalOut
    execution: ExecutionSummary


class WorkflowVersionOut(BaseModel):
    version: int
    params: dict[str, Any]
    created_at: datetime
    created_by: PersonOut | None


class WorkflowConfigOut(BaseModel):
    key: str
    name: str
    enabled: bool
    current_version: int
    params: dict[str, Any]
    versions: list[WorkflowVersionOut]
    role_names: dict[str, str]


class WorkflowConfigUpdate(BaseModel):
    enabled: bool
    params: dict[str, Any]
