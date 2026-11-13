"""DEMO DATA — fictional operational data for organisations flagged ``is_demo`` (ADR 0009).

Only ``service.build_summary`` calls this, and only when the organisation row says it is a demo.
Every section it produces carries provenance "demo". Names, suppliers and SKUs are invented;
the stockout numbers follow inventory.stockout_risk.v1 (docs/product/mvp-implementation-plan.md
§2) so the demo can be checked for correctness. Timestamps are relative to ``now``.
"""

import random
from datetime import datetime, timedelta

from operon.modules.dashboard.schemas import (
    ActivityEvent,
    Approval,
    EvidenceItem,
    FillRate,
    FillRatePoint,
    IncidentCounts,
    Indicator,
    Insight,
    IntegrationStatus,
    LocationRisk,
    Period,
    WorkflowStatus,
)

PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}
_PREVIOUS = {
    "open_insights": {"7d": 4, "30d": 5, "90d": 3},
    "active_incidents": {"7d": 2, "30d": 4, "90d": 6},
    "pending_approvals": {"7d": 3, "30d": 2, "90d": 5},
    "workflows_in_progress": {"7d": 9, "30d": 11, "90d": 8},
}


def _day(now: datetime, days: int) -> str:
    return f"{(now + timedelta(days=days)).day} {(now + timedelta(days=days)):%b}"


def indicators(period: Period) -> list[Indicator]:
    def ind(
        key: str,
        label: str,
        value: int,
        increase_is: str,
        state: str,
        detail: str,
        total: int | None = None,
    ) -> Indicator:
        return Indicator(
            key=key,
            label=label,
            value=value,
            total=total,
            previous_value=_PREVIOUS.get(key, {}).get(period),
            increase_is=increase_is,
            state=state,
            detail=detail,
            provenance="demo",
        )

    return [
        ind("open_insights", "Open insights", 7, "bad", "critical", "1 critical · 2 high"),
        ind("active_incidents", "Active incidents", 3, "bad", "attention", "Oldest open 2 d"),
        ind(
            "pending_approvals",
            "Pending approvals",
            4,
            "neutral",
            "attention",
            "£26,810 awaiting decision",
        ),
        ind(
            "workflows_in_progress",
            "Workflows in progress",
            12,
            "neutral",
            "neutral",
            "1 failed in last 24 h",
        ),
        ind(
            "integrations",
            "Integrations healthy",
            1,
            "good",
            "attention",
            "Shopify needs reconnection",
            total=2,
        ),
    ]


def fill_rate(period: Period, now: datetime) -> FillRate:
    rng = random.Random(2041)  # noqa: S311 — deterministic demo series, not security
    points = []
    for i in range(90):
        days_ago = 89 - i
        pressure = (7 - days_ago) * 0.32 if days_ago < 7 else 0
        value = 97.8 + (rng.random() - 0.5) * 1.1 - pressure
        points.append(
            FillRatePoint(date=(now - timedelta(days=days_ago)).date(), value=round(value, 1))
        )
    return FillRate(target=97, points=points[90 - PERIOD_DAYS[period] :])


def inventory_risk() -> list[LocationRisk]:
    return [
        LocationRisk(location="Leeds DC", skus_at_risk=14, skus_tracked=2140),
        LocationRisk(location="Felixstowe port store", skus_at_risk=9, skus_tracked=1120),
        LocationRisk(location="Bristol DC", skus_at_risk=6, skus_tracked=1860),
        LocationRisk(location="Glasgow cross-dock", skus_at_risk=3, skus_tracked=640),
    ]


def incidents() -> IncidentCounts:
    return IncidentCounts(critical=1, high=1, medium=1, low=0)


def workflows() -> list[WorkflowStatus]:
    return [
        WorkflowStatus(
            workflow="Purchase request approval",
            running=5,
            awaiting_approval=4,
            failed_24h=0,
            completed=38,
            success_rate=97.4,
        ),
        WorkflowStatus(
            workflow="Supplier delivery follow-up",
            running=4,
            awaiting_approval=0,
            failed_24h=1,
            completed=61,
            success_rate=95.1,
        ),
        WorkflowStatus(
            workflow="Inter-site stock transfer",
            running=3,
            awaiting_approval=0,
            failed_24h=0,
            completed=22,
            success_rate=100,
        ),
    ]


def insights(now: datetime) -> list[Insight]:
    m = timedelta(minutes=1)
    return [
        Insight(
            id="demo_ins_2041",
            ref="INS-2041",
            title="Stockout risk: nitrile gloves, size L at Leeds DC",
            category="inventory",
            severity="critical",
            status="open",
            detected_at=now - 6 * m,
            owner="Operations team",
            source_system="Odoo · Shopify",
            rule_id="inventory.stockout_risk",
            rule_version=1,
            summary=(
                f"HV-GLV-220 will run out around {_day(now, 6)}, 8 days before the next "
                "scheduled delivery."
            ),
            why_it_matters=(
                "On-hand stock covers 6.7 days of demand, but replenishment takes "
                "9 days. Without action, open customer orders for this SKU cannot "
                "be fulfilled from Leeds DC."
            ),
            recommended_action=(
                "Raise a purchase request for 2,000 units from Brightline Safety "
                "Supplies (£9,700). Requests above £5,000 need Finance Manager "
                "approval."
            ),
            assumptions=[
                "Demand over the next 9 days matches the 28-day average of 186 units per day.",
                "Brightline's 9-day lead time holds for a new order.",
            ],
            limitations=[
                f"PO-10482 (2,000 units, due {_day(now, 14)}) is excluded because it arrives "
                "after the lead-time window. Expediting it may be an alternative; Odoo has no "
                "supplier confirmation for an earlier date.",
            ],
            evidence=[
                EvidenceItem(
                    label="On hand, Leeds DC", value="1,240 units", source="Odoo · stock levels"
                ),
                EvidenceItem(
                    label="Average daily demand (28 d)",
                    value="186 units (σ 41)",
                    source="Shopify + Odoo sales",
                ),
                EvidenceItem(
                    label="Supplier lead time",
                    value="9 days",
                    source="Odoo · Brightline Safety Supplies",
                ),
                EvidenceItem(
                    label="Inbound within lead time",
                    value="0 units",
                    source="Odoo · purchase orders",
                ),
                EvidenceItem(
                    label="Safety stock (95% service level)",
                    value="203 units",
                    source="1.65 × 41 × √9",
                ),
                EvidenceItem(label="Reorder point", value="1,877 units", source="186 × 9 + 203"),
                EvidenceItem(label="Days of cover", value="6.7 days", source="1,240 ÷ 186"),
                EvidenceItem(
                    label="Recommended order",
                    value="2,000 units · £9,700",
                    source="Reorder point + 7-day review − on hand, rounded to pack of 100",
                ),
            ],
            explanation_generated_by="model",
            explanation_model="demo-model",
        ),
        Insight(
            id="demo_ins_2038",
            ref="INS-2038",
            title="Supplier delivery overdue: PO-10391 corrugated cartons",
            category="procurement",
            severity="high",
            status="acknowledged",
            detected_at=now - 26 * 60 * m,
            owner="Procurement team",
            source_system="Odoo",
            rule_id="procurement.po_overdue",
            rule_version=1,
            summary="Kestrel Packaging has not delivered PO-10391, which was due 3 business days ago.",
            why_it_matters=(
                "Cartons from this order are scheduled for 3 outbound waves at "
                "Bristol DC. Kestrel has 4 open orders worth £18,240."
            ),
            recommended_action=(
                "Confirm a delivery date with Kestrel Packaging, or source from "
                "the approved alternate supplier."
            ),
            assumptions=["Odoo receipt records are up to date for Bristol DC."],
            limitations=[
                "Carrier tracking data is not connected, so in-transit status is unknown."
            ],
            evidence=[
                EvidenceItem(
                    label="Expected receipt", value="3 business days ago", source="Odoo · PO-10391"
                ),
                EvidenceItem(
                    label="Supplier on-time rate (90 d)",
                    value="78% vs 94% average",
                    source="Odoo · receipts",
                ),
                EvidenceItem(
                    label="Open orders with supplier",
                    value="4 · £18,240",
                    source="Odoo · purchase orders",
                ),
            ],
            explanation_generated_by="template",
            explanation_model=None,
        ),
        Insight(
            id="demo_ins_2035",
            ref="INS-2035",
            title="Demand shift: hi-vis vests at Bristol DC",
            category="inventory",
            severity="medium",
            status="open",
            detected_at=now - 5 * 60 * m,
            owner=None,
            source_system="Shopify",
            rule_id="inventory.demand_shift",
            rule_version=1,
            summary="7-day demand for HV-VST-104 is 2.4× its 28-day average.",
            why_it_matters="If the shift persists, stock reaches the reorder point in 11 days instead of 26.",
            recommended_action="Review the reorder point for HV-VST-104 and confirm whether the increase is seasonal.",
            assumptions=["The spike is not caused by a single bulk order."],
            limitations=["Fewer than 14 days at the new level; treat as low confidence."],
            evidence=[
                EvidenceItem(
                    label="Demand, last 7 days", value="61 units / day", source="Shopify · orders"
                ),
                EvidenceItem(
                    label="Demand, 28-day average",
                    value="25 units / day",
                    source="Shopify · orders",
                ),
                EvidenceItem(
                    label="On hand, Bristol DC", value="1,610 units", source="Odoo · stock levels"
                ),
            ],
            explanation_generated_by="model",
            explanation_model="demo-model",
        ),
    ]


def approvals(now: datetime) -> list[Approval]:
    h = timedelta(hours=1)
    return [
        Approval(
            id="demo_apr_3305",
            ref="PR-3305",
            title="Pallet wrap film, 23 μm",
            requester="Daniel Reyes",
            amount=6480,
            currency="GBP",
            policy="Above £5,000 · Finance Manager",
            requested_at=now - 5 * h,
            related_insight_ref=None,
        ),
        Approval(
            id="demo_apr_3302",
            ref="PR-3302",
            title="Forklift battery replacement, Leeds DC",
            requester="Priya Nair",
            amount=14900,
            currency="GBP",
            policy="Above £10,000 · Operations Director",
            requested_at=now - 26 * h,
            related_insight_ref=None,
        ),
        Approval(
            id="demo_apr_3299",
            ref="PR-3299",
            title="Cartons 600×400 from alternate supplier",
            requester="Tom Achebe",
            amount=3120,
            currency="GBP",
            policy="New supplier · Procurement Manager",
            requested_at=now - 3 * h,
            related_insight_ref="INS-2038",
        ),
        Approval(
            id="demo_apr_0412",
            ref="TR-0412",
            title="Stock transfer Bristol DC → Leeds DC",
            requester="Amara Okafor",
            amount=2310,
            currency="GBP",
            policy="Transfers above 500 units · Warehouse Manager",
            requested_at=now - timedelta(minutes=45),
            related_insight_ref=None,
        ),
    ]


def activity(now: datetime) -> list[ActivityEvent]:
    m = timedelta(minutes=1)
    rows = [
        (
            4,
            "integration",
            "Odoo",
            "Synchronised 1,284 stock records for Leeds DC and Bristol DC",
            None,
        ),
        (6, "system", "Detection", "Raised stockout risk for HV-GLV-220", "INS-2041"),
        (38, "user", "Priya Nair", "Approved purchase request (£2,140)", "PR-3296"),
        (45, "user", "Amara Okafor", "Requested stock transfer Bristol DC → Leeds DC", "TR-0412"),
        (
            72,
            "integration",
            "Shopify",
            "Sync completed with a warning: access token expires in 3 days",
            None,
        ),
        (180, "user", "Tom Achebe", "Escalated overdue delivery to an incident", "INC-0117"),
        (
            420,
            "system",
            "Workflows",
            "Purchase order PO-10488 created in Odoo after approval",
            "PR-3290",
        ),
    ]
    return [
        ActivityEvent(
            id=f"demo_ev_{i}",
            at=now - mins * m,
            actor_type=t,
            actor=a,
            message=msg,
            ref=ref,
        )
        for i, (mins, t, a, msg, ref) in enumerate(rows)
    ]


def integrations(now: datetime) -> list[IntegrationStatus]:
    return [
        IntegrationStatus(
            id="demo_int_odoo",
            name="Odoo",
            system="Inventory and purchasing",
            status="healthy",
            last_sync_at=now - timedelta(minutes=4),
            detail="Products, stock, purchase orders, suppliers",
        ),
        IntegrationStatus(
            id="demo_int_shopify",
            name="Shopify",
            system="Sales channel",
            status="degraded",
            last_sync_at=now - timedelta(minutes=72),
            detail="Access token expires in 3 days. Reconnect to keep orders flowing.",
        ),
    ]
