"""Purchase-request parameters and approval policy (plan §5.5). Pure code, no I/O.

The policy decides which approval stages a request needs from its value. It never depends on
AI output: a recommendation only pre-fills the request; people approve it.
"""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ApproverRole = Literal["owner", "administrator", "operations_manager", "approver"]


class StageRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    # The stage applies when the request's value is at least this (in the policy currency).
    min_value: Decimal = Field(ge=0, le=Decimal("1000000000"))
    approver_roles: list[ApproverRole] = Field(min_length=1)

    @field_validator("approver_roles")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class PurchaseRequestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field("GBP", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    stages: list[StageRule] = Field(
        default_factory=lambda: [
            StageRule(
                name="Operations approval",
                min_value=Decimal(0),
                approver_roles=["operations_manager", "approver", "administrator", "owner"],
            ),
            StageRule(
                name="Finance approval",
                min_value=Decimal(10000),
                approver_roles=["approver", "owner"],
            ),
        ],
        min_length=1,
        max_length=5,
    )
    approval_timeout_hours: int = Field(48, ge=1, le=720)
    max_attempts: int = Field(5, ge=1, le=10)

    @model_validator(mode="after")
    def _first_stage_always(self) -> "PurchaseRequestParams":
        # Every request needs at least one approval: an AI recommendation is never authorisation.
        if self.stages[0].min_value != 0:
            raise ValueError("The first approval stage must apply to every request (minimum 0).")
        values = [s.min_value for s in self.stages]
        if values != sorted(values):
            raise ValueError("Stages must be ordered by minimum value.")
        return self


class PlannedStage(BaseModel):
    stage: int
    name: str
    approver_roles: list[str]
    reason: str


def plan_stages(
    params: PurchaseRequestParams, value: Decimal | None, currency: str | None
) -> list[PlannedStage]:
    """Stages a request needs. Unknown value or a different currency → every stage (fail safe)."""
    comparable = value is not None and (currency or params.currency) == params.currency
    out: list[PlannedStage] = []
    for rule in params.stages:
        if rule.min_value == 0:
            reason = "Required for every purchase request."
        elif not comparable:
            reason = (
                "Required because the request's value couldn't be compared with the "
                f"{params.currency} {rule.min_value:,.2f} threshold."
            )
        elif value is not None and value >= rule.min_value:
            reason = f"Required for requests of {params.currency} {rule.min_value:,.2f} or more."
        else:
            continue
        out.append(
            PlannedStage(
                stage=len(out) + 1,
                name=rule.name,
                approver_roles=list(rule.approver_roles),
                reason=reason,
            )
        )
    return out


def defaults() -> dict[str, Any]:
    return PurchaseRequestParams().model_dump(mode="json")
