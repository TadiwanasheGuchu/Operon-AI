"""Insight queries and the decisions people make about insights (plan §4.5)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.errors import ApiError
from operon.modules.ai.models import AIGeneration
from operon.modules.audit import service as audit
from operon.modules.integrations.models import Connection
from operon.modules.intelligence.detectors.registry import DETECTORS
from operon.modules.intelligence.engine import insight_event, suppress_until
from operon.modules.intelligence.models import (
    ACTIVE_STATUSES,
    DetectionRun,
    DetectorConfig,
    Insight,
    InsightEvent,
    InsightEvidence,
)
from operon.modules.notifications.service import notify
from operon.modules.operations.models import (
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SalesDaily,
    StockLevel,
    Supplier,
    SupplierProduct,
)
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.service import member_has_permission

NOT_FOUND = ApiError(404, "not_found", "Insight not found.")

# Allowed status changes made by people. Detection itself may also resolve active insights.
TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "actioned", "resolved", "dismissed"},
    "acknowledged": {"actioned", "resolved", "dismissed"},
    "actioned": {"resolved", "dismissed"},
    "resolved": set(),
    "dismissed": {"open"},
}
SEVERITY_ORDER = case(
    {"critical": 0, "high": 1, "medium": 2, "low": 3}, value=Insight.severity, else_=4
)


@dataclass(frozen=True)
class InsightPage:
    items: list[Insight]
    total: int
    counts: dict[str, int]  # active insights by severity


async def list_insights(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    status: str,
    severity: str | None,
    category: str | None,
    owner: str | None,
    limit: int,
    offset: int,
) -> InsightPage:
    q = select(Insight).where(Insight.organisation_id == ctx.organisation_id)
    if status == "active":
        q = q.where(Insight.status.in_(ACTIVE_STATUSES))
    elif status == "closed":
        q = q.where(Insight.status.in_(("resolved", "dismissed")))
    elif status != "all":
        q = q.where(Insight.status == status)
    if severity:
        q = q.where(Insight.severity == severity)
    if category:
        q = q.where(Insight.category == category)
    if owner == "me":
        q = q.where(Insight.owner_user_id == ctx.user_id)
    elif owner == "none":
        q = q.where(Insight.owner_user_id.is_(None))
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    rows = await session.scalars(
        q.order_by(SEVERITY_ORDER, Insight.detected_at.desc(), Insight.number.desc())
        .limit(limit)
        .offset(offset)
    )
    counts: dict[str, int] = {
        sev: int(n)
        for sev, n in (
            await session.execute(
                select(Insight.severity, func.count())
                .where(
                    Insight.organisation_id == ctx.organisation_id,
                    Insight.status.in_(ACTIVE_STATUSES),
                )
                .group_by(Insight.severity)
            )
        ).all()
    }
    return InsightPage(list(rows.all()), int(total or 0), counts)


async def get_insight(session: AsyncSession, ctx: TenantContext, insight_id: UUID) -> Insight:
    insight = await session.get(Insight, insight_id)
    if insight is None or insight.organisation_id != ctx.organisation_id:
        raise NOT_FOUND
    return insight


async def evidence_of(session: AsyncSession, insight: Insight) -> list[InsightEvidence]:
    return list(
        await session.scalars(
            select(InsightEvidence)
            .where(
                InsightEvidence.organisation_id == insight.organisation_id,
                InsightEvidence.insight_id == insight.id,
            )
            .order_by(InsightEvidence.position)
        )
    )


async def events_of(session: AsyncSession, insight: Insight) -> list[InsightEvent]:
    return list(
        await session.scalars(
            select(InsightEvent)
            .where(
                InsightEvent.organisation_id == insight.organisation_id,
                InsightEvent.insight_id == insight.id,
            )
            .order_by(InsightEvent.created_at, InsightEvent.id)
        )
    )


async def generation_of(session: AsyncSession, insight: Insight) -> AIGeneration | None:
    if insight.explanation_generation_id is None:
        return None
    return await session.get(AIGeneration, insight.explanation_generation_id)


async def connections_by_id(session: AsyncSession, org: UUID, ids: set[UUID]) -> dict[UUID, Any]:
    if not ids:
        return {}
    rows = await session.scalars(
        select(Connection).where(Connection.organisation_id == org, Connection.id.in_(ids))
    )
    return {c.id: c for c in rows.all()}


async def change_status(
    session: AsyncSession,
    ctx: TenantContext,
    insight: Insight,
    *,
    to: str,
    reason: str | None,
    meta: RequestMeta,
) -> Insight:
    if to not in TRANSITIONS.get(insight.status, set()):
        raise ApiError(
            409,
            "invalid_transition",
            f"An insight that is {insight.status} can't be marked {to}.",
        )
    if to == "dismissed" and not (reason and reason.strip()):
        raise ApiError(422, "reason_required", "Say why this insight is being dismissed.")
    now = datetime.now(UTC)
    if to == "open":
        clash = await session.scalar(
            select(Insight.id).where(
                Insight.organisation_id == ctx.organisation_id,
                Insight.rule_id == insight.rule_id,
                Insight.subject_key == insight.subject_key,
                Insight.status.in_(ACTIVE_STATUSES),
            )
        )
        if clash is not None:
            raise ApiError(
                409,
                "already_active",
                "A newer insight for the same item is already open.",
                {"insight_id": str(clash)},
            )
        insight.closed_at = None
        insight.close_reason = None
        insight.suppressed_until = None
    elif to in ("resolved", "dismissed"):
        insight.closed_at = now
        insight.close_reason = (reason or "").strip()[:500] or None
        if to == "dismissed":
            insight.suppressed_until = suppress_until(now)
    before = insight.status
    insight.status = to
    session.add(
        insight_event(
            insight,
            to if to != "open" else "reopened",
            {"from": before, "reason": insight.close_reason},
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="insight.status_changed",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="insight",
        target_id=insight.id,
        details={"reference": insight.reference, "from": before, "to": to, "reason": reason},
    )
    return insight


async def assign_owner(
    session: AsyncSession,
    ctx: TenantContext,
    insight: Insight,
    owner_id: UUID | None,
    meta: RequestMeta,
) -> Insight:
    if owner_id is not None and not await member_has_permission(
        session, ctx.organisation_id, owner_id, Perm.INSIGHTS_READ
    ):
        raise ApiError(422, "invalid_owner", "The owner must be a member who can see insights.", {})
    before = insight.owner_user_id
    if before == owner_id:
        return insight
    insight.owner_user_id = owner_id
    session.add(
        insight_event(
            insight,
            "owner_changed",
            {"from": str(before) if before else None, "to": str(owner_id) if owner_id else None},
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="insight.owner_changed",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="insight",
        target_id=insight.id,
        details={
            "reference": insight.reference,
            "owner_user_id": str(owner_id) if owner_id else None,
        },
    )
    if owner_id is not None and owner_id != ctx.user_id:
        await notify(
            session,
            organisation_id=ctx.organisation_id,
            user_ids=[owner_id],
            kind="insight",
            title=f"You own {insight.reference}: {insight.title}"[:200],
            body=insight.summary[:500],
            link=f"/intelligence/{insight.id}",
        )
    return insight


async def request_explanation(session: AsyncSession, insight: Insight) -> None:
    """Mark for re-explanation; the caller runs it after commit."""
    if insight.status not in ACTIVE_STATUSES:
        raise ApiError(409, "closed", "Closed insights keep the explanation they had.")
    insight.explanation_stale = True


# --- detector configuration ---------------------------------------------------------------------


async def list_detectors(
    session: AsyncSession, ctx: TenantContext
) -> list[tuple[str, Any, DetectorConfig | None]]:
    rows = {
        c.rule_id: c
        for c in await session.scalars(
            select(DetectorConfig).where(DetectorConfig.organisation_id == ctx.organisation_id)
        )
    }
    return [(rule_id, det, rows.get(rule_id)) for rule_id, det in DETECTORS.items()]


async def update_detector(
    session: AsyncSession,
    ctx: TenantContext,
    rule_id: str,
    *,
    enabled: bool,
    params: dict[str, Any],
    meta: RequestMeta,
) -> DetectorConfig:
    det = DETECTORS.get(rule_id)
    if det is None:
        raise ApiError(404, "not_found", "Detector not found.")
    try:
        validated = det.params_model.model_validate(params)
    except ValidationError as exc:
        raise ApiError(
            422,
            "invalid_params",
            "Some settings are out of range.",
            {
                "errors": [
                    {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                    for e in exc.errors()
                ]
            },
        ) from exc
    cfg = await session.get(DetectorConfig, (ctx.organisation_id, rule_id))
    before = {"enabled": cfg.enabled, "params": cfg.params} if cfg else None
    if cfg is None:
        cfg = DetectorConfig(organisation_id=ctx.organisation_id, rule_id=rule_id)
        session.add(cfg)
    cfg.enabled = enabled
    cfg.params = validated.model_dump(mode="json")
    cfg.updated_by = ctx.user_id
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="detector.updated",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="detector",
        target_id=rule_id,
        details={"before": before, "after": {"enabled": enabled, "params": cfg.params}},
    )
    await session.flush()
    return cfg


async def recent_runs(session: AsyncSession, ctx: TenantContext, limit: int) -> list[DetectionRun]:
    return list(
        await session.scalars(
            select(DetectionRun)
            .where(DetectionRun.organisation_id == ctx.organisation_id)
            .order_by(DetectionRun.started_at.desc())
            .limit(limit)
        )
    )


# --- evidence sources ---------------------------------------------------------------------------

SOURCE_MODELS: dict[str, Any] = {
    "stock_level": StockLevel,
    "purchase_order": PurchaseOrder,
    "purchase_order_line": PurchaseOrderLine,
    "supplier_product": SupplierProduct,
    "product": Product,
    "sales_daily": Product,  # sales evidence points at the product whose sales were summed
}


async def resolve_source(
    session: AsyncSession, ctx: TenantContext, evidence: InsightEvidence
) -> dict[str, Any]:
    """The source record behind one evidence item, as it is in Operon now."""
    model = SOURCE_MODELS.get(evidence.source_type)
    if model is None or evidence.source_id is None:
        raise ApiError(404, "no_source", "This value is computed or configured, not synced.")
    row = await session.get(model, evidence.source_id)
    if row is None or row.organisation_id != ctx.organisation_id:
        raise ApiError(
            404,
            "source_gone",
            "The source record no longer exists in Operon (it may have "
            "been removed from the connected system).",
        )
    fields: dict[str, Any] = {}
    if isinstance(row, StockLevel):
        product = await session.get(Product, row.product_id)
        location = await session.get(Location, row.location_id)
        fields = {
            "product": product.name if product else None,
            "sku": product.sku if product else None,
            "location": location.name if location else None,
            "on_hand": str(row.on_hand),
            "reserved": str(row.reserved),
            "as_of": row.as_of.isoformat(),
        }
    elif isinstance(row, PurchaseOrder):
        supplier = await session.get(Supplier, row.supplier_id) if row.supplier_id else None
        fields = {
            "number": row.number,
            "status": row.status,
            "supplier": supplier.name if supplier else None,
            "ordered_at": row.ordered_at.isoformat() if row.ordered_at else None,
            "expected_at": row.expected_at.isoformat() if row.expected_at else None,
            "total": str(row.total) if row.total is not None else None,
            "currency": row.currency,
        }
    elif isinstance(row, PurchaseOrderLine):
        po = await session.get(PurchaseOrder, row.purchase_order_id)
        product = await session.get(Product, row.product_id) if row.product_id else None
        fields = {
            "purchase_order": po.number if po else None,
            "product": product.name if product else None,
            "quantity": str(row.quantity),
            "received_quantity": str(row.received_quantity),
            "unit_price": str(row.unit_price) if row.unit_price is not None else None,
            "expected_at": expected.isoformat()
            if (expected := row.expected_at or (po.expected_at if po else None))
            else None,
        }
    elif isinstance(row, SupplierProduct):
        supplier = await session.get(Supplier, row.supplier_id)
        product = await session.get(Product, row.product_id)
        fields = {
            "supplier": supplier.name if supplier else None,
            "product": product.name if product else None,
            "lead_time_days": row.lead_time_days,
            "min_quantity": str(row.min_quantity) if row.min_quantity is not None else None,
            "price": str(row.price) if row.price is not None else None,
            "currency": row.currency,
        }
    elif isinstance(row, Product):
        fields = {"product": row.name, "sku": row.sku, "uom": row.uom}
        if evidence.source_type == "sales_daily":
            recent = (
                await session.execute(
                    select(SalesDaily.day, func.sum(SalesDaily.quantity))
                    .where(
                        SalesDaily.organisation_id == ctx.organisation_id,
                        SalesDaily.product_id == row.id,
                    )
                    .group_by(SalesDaily.day)
                    .order_by(SalesDaily.day.desc())
                    .limit(90)
                )
            ).all()
            fields["daily_sales"] = [{"day": d.isoformat(), "quantity": str(q)} for d, q in recent]
    conn = await session.get(Connection, row.connection_id)
    return {
        "source_type": evidence.source_type,
        "source_id": str(row.id),
        "external_id": getattr(row, "external_id", None),
        "connection": (
            {"id": str(conn.id), "name": conn.name, "connector": conn.connector} if conn else None
        ),
        "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
        "fields": fields,
    }


def describe_recommendation(rec: dict[str, Any] | None) -> str:
    """One sentence for the code-computed recommended action."""
    if not rec:
        return "Review the evidence and decide on an action."
    if rec.get("action") == "create_purchase_request":
        supplier = rec.get("supplier_name")
        text = f"Raise a purchase request for {rec.get('quantity_display')}"
        text += f" from {supplier}" if supplier else " (choose a supplier)"
        if rec.get("estimated_value_display"):
            text += f", about {rec['estimated_value_display']}"
        return text + "."
    if rec.get("action") == "contact_supplier":
        who = rec.get("supplier_name") or "the supplier"
        return (
            f"Contact {who} to confirm a delivery date for {rec.get('purchase_order_number')}, "
            "and update the expected date in the source system."
        )
    return "Review the evidence and decide on an action."
