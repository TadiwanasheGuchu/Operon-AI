"""`procurement.po_overdue.v1` — open purchase orders whose expected receipt date has passed."""

from collections import defaultdict
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.modules.intelligence.detectors.base import (
    DetectionContext,
    Evidence,
    Finding,
    day,
    money,
    units,
)
from operon.modules.operations.models import Product, PurchaseOrder, PurchaseOrderLine, Supplier


class PoOverdueParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grace_days: int = Field(
        1, ge=0, le=30, description="Days after the expected date before an order counts as late."
    )
    medium_after_days: int = Field(3, ge=1, le=365, description="Days late that make it medium.")
    high_after_days: int = Field(7, ge=1, le=365, description="Days late that make it high.")
    critical_after_days: int = Field(
        21, ge=1, le=365, description="Days late that make it critical."
    )

    @model_validator(mode="after")
    def _ordered(self) -> "PoOverdueParams":
        if not self.medium_after_days <= self.high_after_days <= self.critical_after_days:
            raise ValueError("Severity thresholds must increase: medium ≤ high ≤ critical.")
        return self


def severity_for(days_late: int, p: PoOverdueParams) -> str:
    if days_late >= p.critical_after_days:
        return "critical"
    if days_late >= p.high_after_days:
        return "high"
    if days_late >= p.medium_after_days:
        return "medium"
    return "low"


class PurchaseOrderOverdueDetector:
    rule_id: ClassVar[str] = "procurement.po_overdue"
    version: ClassVar[int] = 1
    category: ClassVar[str] = "procurement"
    name: ClassVar[str] = "Overdue purchase orders"
    description: ClassVar[str] = (
        "Open purchase orders with quantity still to receive after the expected date has passed."
    )
    params_model: ClassVar[type[BaseModel]] = PoOverdueParams

    async def evaluate(
        self, session: AsyncSession, ctx: DetectionContext, params: Any
    ) -> list[Finding]:
        p: PoOverdueParams = params
        org, today = ctx.organisation_id, ctx.today
        rows = (
            await session.execute(
                select(PurchaseOrderLine, PurchaseOrder, Product, Supplier)
                .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
                .outerjoin(Product, Product.id == PurchaseOrderLine.product_id)
                .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
                .where(
                    PurchaseOrderLine.organisation_id == org,
                    PurchaseOrder.status == "open",
                    PurchaseOrderLine.quantity > PurchaseOrderLine.received_quantity,
                )
                .order_by(PurchaseOrder.number, PurchaseOrderLine.external_id)
            )
        ).all()
        by_po: dict[UUID, list[Any]] = defaultdict(list)
        for row in rows:
            by_po[row[1].id].append(row)

        findings: list[Finding] = []
        for po_rows in by_po.values():
            po: PurchaseOrder = po_rows[0][1]
            supplier: Supplier | None = po_rows[0][3]
            late = []
            for line, _, product, _ in po_rows:
                expected = line.expected_at or po.expected_at
                if expected is None:
                    continue
                days_late = (today - expected.date()).days
                if days_late > p.grace_days:
                    late.append((line, product, expected, days_late))
            if not late:
                continue
            worst = max(d for *_, d in late)
            earliest = min(e for _, _, e, _ in late)
            sev = severity_for(worst, p)
            supplier_name = supplier.name if supplier else "an unknown supplier"
            outstanding_value = sum(
                (
                    (ln.quantity - ln.received_quantity) * ln.unit_price
                    for ln, _, _, _ in late
                    if ln.unit_price is not None
                ),
                Decimal(0),
            )
            evidence: list[Evidence] = [
                Evidence(
                    key="purchase_order",
                    label="Purchase order",
                    value=f"{po.number} from {supplier_name}",
                    source_type="purchase_order",
                    source_id=po.id,
                    source_ref=po.external_id,
                    connection_id=po.connection_id,
                ),
                Evidence(
                    key="expected_date",
                    label="Expected receipt",
                    value=day(earliest),
                    source_type="purchase_order",
                    source_id=po.id,
                    connection_id=po.connection_id,
                ),
                Evidence(
                    key="days_late",
                    label="Days late",
                    value=f"{worst} days",
                    numeric=Decimal(worst),
                    unit="days",
                    source_type="computed",
                    formula=f"{day(today)} − expected receipt date",
                ),
            ]
            for line, product, expected, _ in late:
                remaining = line.quantity - line.received_quantity
                name = (product.sku or product.name) if product else "Unlinked item"
                evidence.append(
                    Evidence(
                        key="outstanding_line",
                        label=f"Not yet received: {name}",
                        value=f"{units(remaining, product.uom if product else None)} "
                        f"of {units(line.quantity, product.uom if product else None)}",
                        numeric=remaining,
                        source_type="purchase_order_line",
                        source_id=line.id,
                        source_ref=f"{po.number} / line {line.external_id}",
                        connection_id=line.connection_id,
                        observed_at=expected,
                    )
                )
            metrics = {
                "number": po.number,
                "supplier": supplier_name,
                "expected_date": day(earliest),
                "days_late": f"{worst} days",
                "lines_late": str(len(late)),
            }
            recommendation: dict[str, Any] = {
                "action": "contact_supplier",
                "purchase_order_id": str(po.id),
                "purchase_order_number": po.number,
                "supplier_id": str(supplier.id) if supplier else None,
                "supplier_name": supplier.name if supplier else None,
            }
            if outstanding_value > 0:
                metrics["outstanding_value"] = money(outstanding_value, po.currency)
                evidence.append(
                    Evidence(
                        key="outstanding_value",
                        label="Value not yet received",
                        value=metrics["outstanding_value"],
                        numeric=outstanding_value,
                        source_type="computed",
                        formula="Σ (ordered − received) × unit price",
                    )
                )
            limitations = []
            if any((ln.expected_at or po.expected_at) is None for ln, _, _, _ in po_rows):
                limitations.append("Some lines on this order have no expected date.")
            findings.append(
                Finding(
                    subject_type="purchase_order",
                    subject_key=f"po:{po.id}",
                    subject_label=f"{po.number} ({supplier_name})",
                    severity=sev,
                    title=f"Purchase order {po.number} from {supplier_name} is {worst} days late",
                    summary=(
                        f"Expected by {day(earliest)}; {len(late)} line(s) not yet fully received."
                    ),
                    evidence=evidence,
                    metrics=metrics,
                    recommendation=recommendation,
                    assumptions=[
                        "Receipts recorded in the source system are up to date as of the last sync."
                    ],
                    limitations=limitations,
                    explanation={
                        "what_happened": (
                            f"Purchase order {po.number} from {supplier_name} was expected by "
                            f"{day(earliest)} and is now {worst} days late, with {len(late)} "
                            "line(s) not fully received."
                        ),
                        "why_it_matters": (
                            "Stock planned on this order isn't available yet, which can "
                            "delay customer orders and production that depend on it. "
                            "Confirming a new delivery date with the supplier keeps plans "
                            "realistic."
                        ),
                    },
                )
            )
        return findings


__all__ = ["PoOverdueParams", "PurchaseOrderOverdueDetector", "severity_for"]
