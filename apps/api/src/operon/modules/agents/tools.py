"""Typed tools for the assistant and agents (plan §6.1-6.2, ADR 0014).

There is no free-form query tool. Each tool:
- has a Pydantic input model (validated before it runs; invalid input becomes a tool error);
- requires a permission, checked against whoever the run acts for (the asking member, or the
  agent's run-as member), so a model can only see what that person could see;
- is read-only unless `writes` is set. Only `draft_purchase_request` writes, and it creates a
  purchase request that still needs human approval (Phase 5). The assistant is never offered it.

Tool outputs are data. They contain text from connected systems (product names, notes) that may
include instructions; the system prompts say so, and nothing a tool returns can widen what the
model is allowed to do.
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from operon.access.context import TenantContext
from operon.core.db import Database, set_rls_context
from operon.core.errors import ApiError
from operon.modules.incidents import service as incidents
from operon.modules.intelligence import service as intelligence
from operon.modules.intelligence.models import SEVERITY_RANK, Insight
from operon.modules.operations.models import (
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SalesDaily,
    StockLevel,
    Supplier,
)
from operon.modules.permissions.catalogue import Perm
from operon.modules.workflows import service as workflows


@dataclass(frozen=True)
class Citation:
    ref: str
    label: str
    kind: str
    href: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "label": self.label, "kind": self.kind, "href": self.href}


@dataclass
class ToolOutput:
    data: Any
    citations: list[Citation] = field(default_factory=list)


@dataclass
class ToolContext:
    db: Database
    actor: TenantContext  # permissions already capped for agents
    execution_id: UUID
    agent_name: str | None = None
    # Per-run policy and counters (drafts made, minimum severity, quantity bounds).
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def organisation_id(self) -> UUID:
        return self.actor.organisation_id


Handler = Callable[[ToolContext, Any], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: str
    handler: Handler
    writes: bool = False

    def schema(self) -> dict[str, Any]:
        s = self.input_model.model_json_schema()
        s.pop("title", None)
        return s


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _session(ctx: ToolContext) -> Any:
    return ctx.db.sessionmaker()


def _day(d: datetime | date | None) -> str | None:
    if d is None:
        return None
    return (d.date() if isinstance(d, datetime) else d).isoformat()


def _num(d: Decimal | None) -> str | None:
    if d is None:
        return None
    n = d.normalize()
    return format(n, "f")


# --- insights -------------------------------------------------------------------------------


class ListInsightsIn(_In):
    status: Literal["active", "closed", "all"] = Field("active", description="Which insights.")
    severity: Literal["low", "medium", "high", "critical"] | None = None
    category: Literal["inventory", "procurement"] | None = None
    limit: int = Field(10, ge=1, le=25)


async def list_insights(ctx: ToolContext, inp: ListInsightsIn) -> ToolOutput:
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        page = await intelligence.list_insights(
            s,
            ctx.actor,
            status=inp.status,
            severity=inp.severity,
            category=inp.category,
            owner=None,
            limit=inp.limit,
            offset=0,
        )
        items = [
            {
                "reference": i.reference,
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "category": i.category,
                "subject": i.subject_label,
                "summary": i.summary,
                "detected": _day(i.detected_at),
                "confidence": i.confidence,
            }
            for i in page.items
        ]
        cites = [
            Citation(i.reference, i.title, "insight", f"/intelligence/{i.id}") for i in page.items
        ]
    return ToolOutput(
        {"total_matching": page.total, "active_by_severity": page.counts, "insights": items}, cites
    )


class GetInsightIn(_In):
    reference: str = Field(pattern=r"^INS-\d{1,8}$", description="For example INS-0003.")


async def _insight_by_ref(s: Any, org: UUID, ref: str) -> Insight:
    insight: Insight | None = await s.scalar(
        select(Insight).where(Insight.organisation_id == org, Insight.number == int(ref[4:]))
    )
    if insight is None:
        raise ApiError(404, "not_found", f"There is no insight {ref}.")
    return insight


async def get_insight(ctx: ToolContext, inp: GetInsightIn) -> ToolOutput:
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        i = await _insight_by_ref(s, ctx.organisation_id, inp.reference)
        evidence = await intelligence.evidence_of(s, i)
        rec = i.recommendation or {}
        data = {
            "reference": i.reference,
            "title": i.title,
            "severity": i.severity,
            "status": i.status,
            "confidence": i.confidence,
            "subject": i.subject_label,
            "summary": i.summary,
            "what_happened": (i.explanation or {}).get("what_happened"),
            "why_it_matters": (i.explanation or {}).get("why_it_matters"),
            "recommended_action": intelligence.describe_recommendation(i.recommendation),
            "recommendation": {
                "action": rec.get("action"),
                "quantity": rec.get("quantity"),
                "quantity_display": rec.get("quantity_display"),
                "supplier": rec.get("supplier_name"),
                "estimated_value": rec.get("estimated_value_display"),
            }
            if rec
            else None,
            "evidence": [{"label": e.label, "value": e.value} for e in evidence],
            "assumptions": i.assumptions,
            "limitations": i.limitations,
        }
        cite = Citation(i.reference, i.title, "insight", f"/intelligence/{i.id}")
    return ToolOutput(data, [cite])


# --- stock and purchase orders ----------------------------------------------------------------


class SearchStockIn(_In):
    query: str = Field(min_length=2, max_length=100, description="SKU or part of a product name.")
    limit: int = Field(10, ge=1, le=25)


async def search_stock(ctx: ToolContext, inp: SearchStockIn) -> ToolOutput:
    pattern = "%" + inp.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    since = datetime.now(UTC).date() - timedelta(days=28)
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        products = list(
            await s.scalars(
                select(Product)
                .where(
                    Product.organisation_id == ctx.organisation_id,
                    or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)),
                )
                .order_by(Product.sku)
                .limit(inp.limit)
            )
        )
        out = []
        cites = []
        for p in products:
            levels = (
                await s.execute(
                    select(StockLevel, Location)
                    .join(Location, Location.id == StockLevel.location_id)
                    .where(StockLevel.product_id == p.id)
                    .order_by(Location.name)
                )
            ).all()
            sold = await s.scalar(
                select(func.coalesce(func.sum(SalesDaily.quantity), 0)).where(
                    SalesDaily.product_id == p.id, SalesDaily.day >= since
                )
            )
            out.append(
                {
                    "sku": p.sku,
                    "product": p.name,
                    "unit": p.uom,
                    "sold_last_28_days": _num(Decimal(sold or 0)),
                    "stock": [
                        {
                            "location": loc.name,
                            "on_hand": _num(sl.on_hand),
                            "reserved": _num(sl.reserved),
                            "as_of": sl.as_of.isoformat(),
                        }
                        for sl, loc in levels
                    ],
                }
            )
            cites.append(Citation(p.sku or p.name, p.name, "product"))
    return ToolOutput({"products": out}, cites)


class ListPurchaseOrdersIn(_In):
    status: Literal["open", "all"] = "open"
    overdue_only: bool = False
    supplier: str | None = Field(None, max_length=100)
    limit: int = Field(10, ge=1, le=25)


async def list_purchase_orders(ctx: ToolContext, inp: ListPurchaseOrdersIn) -> ToolOutput:
    today = datetime.now(UTC).date()
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        q = (
            select(PurchaseOrder, Supplier)
            .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .where(PurchaseOrder.organisation_id == ctx.organisation_id)
        )
        if inp.status == "open":
            q = q.where(PurchaseOrder.status == "open")
        if inp.overdue_only:
            q = q.where(PurchaseOrder.expected_at < datetime.now(UTC))
        if inp.supplier:
            q = q.where(Supplier.name.ilike(f"%{inp.supplier.replace('%', '')}%"))
        rows = (
            await s.execute(q.order_by(PurchaseOrder.expected_at.nulls_last()).limit(inp.limit))
        ).all()
        out, cites = [], []
        for po, sup in rows:
            lines = (
                await s.execute(
                    select(PurchaseOrderLine, Product)
                    .outerjoin(Product, Product.id == PurchaseOrderLine.product_id)
                    .where(PurchaseOrderLine.purchase_order_id == po.id)
                )
            ).all()
            out.append(
                {
                    "number": po.number,
                    "supplier": sup.name if sup else None,
                    "status": po.status,
                    "expected": _day(po.expected_at),
                    "days_late": (today - po.expected_at.date()).days
                    if po.expected_at and po.status == "open" and po.expected_at.date() < today
                    else 0,
                    "lines": [
                        {
                            "sku": prod.sku if prod else None,
                            "ordered": _num(line.quantity),
                            "received": _num(line.received_quantity),
                        }
                        for line, prod in lines
                    ],
                }
            )
            cites.append(Citation(po.number, f"Purchase order {po.number}", "purchase_order"))
    return ToolOutput({"purchase_orders": out}, cites)


# --- incidents and purchase requests -------------------------------------------------------


class ListIncidentsIn(_In):
    status: Literal["unresolved", "all"] = "unresolved"
    limit: int = Field(10, ge=1, le=25)


async def list_incidents(ctx: ToolContext, inp: ListIncidentsIn) -> ToolOutput:
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        page = await incidents.list_incidents(
            s, ctx.actor, status=inp.status, severity=None, assignee=None, limit=inp.limit, offset=0
        )
        out = [
            {
                "reference": i.reference,
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "opened": _day(i.created_at),
                "response_overdue": i.status == "open" and i.response_due_at <= datetime.now(UTC),
            }
            for i in page.items
        ]
        cites = [
            Citation(i.reference, i.title, "incident", f"/incidents/{i.id}") for i in page.items
        ]
    return ToolOutput({"total_matching": page.total, "incidents": out}, cites)


class ListPurchaseRequestsIn(_In):
    status: Literal["active", "finished", "all"] = "active"
    limit: int = Field(10, ge=1, le=25)


async def list_purchase_requests(ctx: ToolContext, inp: ListPurchaseRequestsIn) -> ToolOutput:
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        page = await workflows.list_executions(
            s, ctx.actor, status=inp.status, mine=False, limit=inp.limit, offset=0
        )
        out = [
            {
                "reference": e.reference,
                "title": e.title,
                "status": e.status,
                "value": e.input.get("value_display"),
                "supplier": e.input.get("supplier_name"),
                "raised_from": e.input.get("insight_reference"),
                "created": _day(e.created_at),
            }
            for e in page.items
        ]
        cites = [
            Citation(e.reference, e.title, "purchase_request", f"/workflows/{e.id}")
            for e in page.items
        ]
    return ToolOutput({"total_matching": page.total, "purchase_requests": out}, cites)


# --- the one write tool ----------------------------------------------------------------------


class DraftPurchaseRequestIn(_In):
    insight_reference: str = Field(pattern=r"^INS-\d{1,8}$")
    quantity: int = Field(ge=1, le=1_000_000)
    rationale: str = Field(min_length=10, max_length=500, description="Why, citing the evidence.")


QUANTITY_BAND = (Decimal("0.5"), Decimal("1.5"))


async def draft_purchase_request(ctx: ToolContext, inp: DraftPurchaseRequestIn) -> ToolOutput:
    """Create a purchase request for human approval. Guarded in code, not by the prompt."""
    drafted: int = ctx.state.get("drafted", 0)
    max_drafts: int = ctx.state.get("max_drafts", 0)
    if drafted >= max_drafts:
        raise ApiError(409, "draft_limit", f"This run may draft at most {max_drafts} request(s).")
    async with ctx.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=ctx.organisation_id, user_id=ctx.actor.user_id)
        insight = await _insight_by_ref(s, ctx.organisation_id, inp.insight_reference)
        if insight.rule_id != "inventory.stockout_risk":
            raise ApiError(409, "not_orderable", "Only stockout-risk insights can be ordered.")
        min_sev = ctx.state.get("min_severity", "high")
        if SEVERITY_RANK[insight.severity] < SEVERITY_RANK[min_sev]:
            raise ApiError(
                409,
                "below_threshold",
                f"{insight.reference} is {insight.severity}; this agent drafts only for "
                f"{min_sev} or above.",
            )
        recommended = (insight.recommendation or {}).get("quantity")
        if recommended:
            low = max(1, math.ceil(Decimal(recommended) * QUANTITY_BAND[0]))
            high = math.floor(Decimal(recommended) * QUANTITY_BAND[1])
            if not low <= inp.quantity <= high:
                raise ApiError(
                    422,
                    "quantity_out_of_bounds",
                    f"Quantity must be between {low} and {high} (50%-150% of the recommended "
                    f"{recommended}).",
                )
        e = await workflows.submit_from_insight(
            s,
            ctx.actor,
            insight_id=insight.id,
            quantity=inp.quantity,
            note=inp.rationale,
            meta=None,
            origin={
                "type": "agent",
                "agent": ctx.agent_name,
                "execution_id": str(ctx.execution_id),
            },
        )
        ref, eid, title = e.reference, e.id, e.title
    ctx.state["drafted"] = drafted + 1
    return ToolOutput(
        {
            "created": ref,
            "status": "awaiting_approval",
            "note": "A person must approve this before anything is ordered.",
        },
        [Citation(ref, title, "purchase_request", f"/workflows/{eid}")],
    )


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "list_insights",
            "List insights (problems Operon's rules detected), most severe first.",
            ListInsightsIn,
            Perm.INSIGHTS_READ,
            list_insights,
        ),
        Tool(
            "get_insight",
            "Get one insight with its evidence, recommendation, assumptions and limitations.",
            GetInsightIn,
            Perm.INSIGHTS_READ,
            get_insight,
        ),
        Tool(
            "search_stock",
            "Find products by SKU or name: stock on hand per location and units sold in the "
            "last 28 days.",
            SearchStockIn,
            Perm.INSIGHTS_READ,
            search_stock,
        ),
        Tool(
            "list_purchase_orders",
            "List purchase orders from connected systems, optionally only overdue ones.",
            ListPurchaseOrdersIn,
            Perm.INSIGHTS_READ,
            list_purchase_orders,
        ),
        Tool(
            "list_incidents",
            "List incidents (problems someone owns until resolved).",
            ListIncidentsIn,
            Perm.INCIDENTS_READ,
            list_incidents,
        ),
        Tool(
            "list_purchase_requests",
            "List purchase requests and their approval status.",
            ListPurchaseRequestsIn,
            Perm.WORKFLOWS_READ,
            list_purchase_requests,
        ),
        Tool(
            "draft_purchase_request",
            "Draft a purchase request from a stockout-risk insight. It is sent for human "
            "approval; nothing is ordered until a person approves it.",
            DraftPurchaseRequestIn,
            Perm.WORKFLOWS_REQUEST,
            draft_purchase_request,
            writes=True,
        ),
    ]
}

READ_TOOLS = [name for name, t in TOOLS.items() if not t.writes]


def permitted(names: list[str], actor: TenantContext) -> list[Tool]:
    return [TOOLS[n] for n in names if n in TOOLS and actor.has(TOOLS[n].permission)]
