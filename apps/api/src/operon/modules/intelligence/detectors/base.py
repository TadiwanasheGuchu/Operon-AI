"""Detector contract (plan §4.2).

A detector is a versioned, deterministic rule. It reads canonical operational data for one
organisation and returns findings. Each finding carries every number it relies on as evidence
traceable to a source record, a code-computed recommendation, and a template explanation.
Detectors never call a model and never write; the engine owns persistence.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Evidence:
    key: str
    label: str
    value: str
    source_type: str
    numeric: Decimal | None = None
    unit: str | None = None
    source_id: UUID | None = None
    source_ref: str | None = None
    connection_id: UUID | None = None
    observed_at: datetime | None = None
    formula: str | None = None


@dataclass
class Finding:
    subject_type: str
    subject_key: str
    subject_label: str
    severity: str
    title: str
    summary: str
    evidence: list[Evidence]
    explanation: dict[str, str]  # template: {"what_happened", "why_it_matters"}
    metrics: dict[str, str] = field(default_factory=dict)
    recommendation: dict[str, Any] | None = None
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    confidence: str = "normal"


@dataclass(frozen=True)
class DetectionContext:
    organisation_id: UUID
    today: date
    now: datetime


class Detector(Protocol):
    rule_id: ClassVar[str]
    version: ClassVar[int]
    category: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]

    async def evaluate(
        self, session: AsyncSession, ctx: DetectionContext, params: Any
    ) -> list[Finding]: ...


# --- formatting: one place decides how numbers are shown, so evidence and text agree ----------


def q(value: Decimal, places: int = 1) -> Decimal:
    exp = Decimal(1).scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def num(value: Decimal | int, places: int = 1) -> str:
    """Thousands separators; at most `places` decimals; no trailing zeros."""
    d = q(Decimal(value), places)
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,.{places}f}".rstrip("0").rstrip(".")


def units(value: Decimal | int, uom: str | None = None, places: int = 1) -> str:
    return f"{num(value, places)} {uom or 'units'}"


def money(value: Decimal, currency: str | None) -> str:
    amount = f"{q(value, 2):,.2f}"
    return f"{currency} {amount}" if currency else amount


def day(value: date | datetime) -> str:
    return (value.date() if isinstance(value, datetime) else value).isoformat()
