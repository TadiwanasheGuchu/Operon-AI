"""`inventory.stockout_risk.v1` — stock that may run out before replenishment can arrive (plan §2).

The calculation (`compute`) is a pure function over Decimals so it can be golden-tested; the
detector loads inputs from canonical tables and turns results into evidence.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.modules.intelligence.detectors.base import (
    DetectionContext,
    Evidence,
    Finding,
    day,
    money,
    num,
    q,
    units,
)
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

Z_SCORES: dict[str, Decimal] = {
    "0.90": Decimal("1.28"),
    "0.95": Decimal("1.65"),
    "0.975": Decimal("1.96"),
    "0.99": Decimal("2.33"),
}


class StockoutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_level: Literal["0.90", "0.95", "0.975", "0.99"] = Field(
        "0.95", description="Target probability of not running out during the lead time."
    )
    sales_window_days: int = Field(
        28, ge=7, le=90, description="Days of sales history used to estimate demand."
    )
    review_period_days: int = Field(
        7, ge=1, le=90, description="Days of demand an order should cover beyond the lead time."
    )
    default_lead_time_days: int = Field(
        14, ge=1, le=365, description="Lead time used when no supplier terms are on record."
    )
    min_history_days: int = Field(
        14, ge=1, le=90, description="Below this much sales history, insights are low confidence."
    )


# --- pure calculation -------------------------------------------------------------------------


@dataclass(frozen=True)
class StockoutInputs:
    on_hand: Decimal
    daily_sales: list[Decimal]  # one value per day in the window, zeros included
    inbound_within_lead: Decimal
    lead_time_days: int
    service_level: str = "0.95"
    review_period_days: int = 7
    min_order_quantity: Decimal | None = None


@dataclass(frozen=True)
class StockoutResult:
    demand_per_day: Decimal
    demand_std_dev: Decimal
    z: Decimal
    safety_stock: Decimal
    reorder_point: Decimal
    position: Decimal  # on_hand + inbound within lead time
    projected: Decimal  # position − demand during lead time
    triggered: bool
    severity: str | None
    days_of_cover: Decimal | None
    recommended_quantity: int


def compute(inp: StockoutInputs) -> StockoutResult:
    n = len(inp.daily_sales)
    d = sum(inp.daily_sales, Decimal(0)) / n if n else Decimal(0)
    if n > 1:
        variance = sum(((x - d) ** 2 for x in inp.daily_sales), Decimal(0)) / (n - 1)
        sigma = variance.sqrt()
    else:
        sigma = Decimal(0)
    lead = Decimal(inp.lead_time_days)
    z = Z_SCORES[inp.service_level]
    ss = z * sigma * lead.sqrt()
    rop = d * lead + ss
    position = inp.on_hand + inp.inbound_within_lead
    projected = position - d * lead
    # Raise once stock will reach the reorder point before the next review (periodic review):
    # at or below the reorder point is high/critical; within one review period of it is medium.
    # No demand, no risk: a zero reorder point would flag every empty, unsold item.
    triggered = d > 0 and position <= rop + d * Decimal(inp.review_period_days)
    severity = None
    if triggered:
        severity = "critical" if projected <= 0 else "high" if projected < ss else "medium"
    cover = (inp.on_hand / d) if d > 0 else None
    qty = 0
    if triggered:
        need = rop + d * Decimal(inp.review_period_days) - position
        qty = max(math.ceil(need), 1)
        if inp.min_order_quantity is not None:
            qty = max(qty, math.ceil(inp.min_order_quantity))
    return StockoutResult(
        d, sigma, z, ss, rop, position, projected, triggered, severity, cover, qty
    )


# --- data loading -----------------------------------------------------------------------------


@dataclass
class _Terms:
    supplier_product: SupplierProduct
    supplier: Supplier


@dataclass
class _Group:
    product: Product
    location: Location | None  # None: evaluated across all locations
    stock: list[tuple[StockLevel, Location]] = field(default_factory=list)


class StockoutRiskDetector:
    rule_id: ClassVar[str] = "inventory.stockout_risk"
    version: ClassVar[int] = 1
    category: ClassVar[str] = "inventory"
    name: ClassVar[str] = "Stockout risk"
    description: ClassVar[str] = (
        "Stock plus inbound purchase orders at or below the reorder point "
        "(average demand × lead time + safety stock)."
    )
    params_model: ClassVar[type[BaseModel]] = StockoutParams

    async def evaluate(
        self, session: AsyncSession, ctx: DetectionContext, params: Any
    ) -> list[Finding]:
        p: StockoutParams = params
        org, today = ctx.organisation_id, ctx.today
        window_start = today - timedelta(days=p.sales_window_days)

        stock_rows = (
            await session.execute(
                select(StockLevel, Product, Location)
                .join(Product, Product.id == StockLevel.product_id)
                .join(Location, Location.id == StockLevel.location_id)
                .where(StockLevel.organisation_id == org, Product.active.is_(True))
                .order_by(Product.id, Location.name)
            )
        ).all()
        if not stock_rows:
            return []
        product_ids = {sl.product_id for sl, _, _ in stock_rows}

        first_sale: dict[UUID, date] = {
            pid: first
            for pid, first in (
                await session.execute(
                    select(SalesDaily.product_id, func.min(SalesDaily.day))
                    .where(
                        SalesDaily.organisation_id == org,
                        SalesDaily.product_id.in_(product_ids),
                    )
                    .group_by(SalesDaily.product_id)
                )
            ).all()
        }
        sales: dict[UUID, list[tuple[UUID | None, date, Decimal]]] = defaultdict(list)
        for pid, loc, d, qty in (
            await session.execute(
                select(
                    SalesDaily.product_id,
                    SalesDaily.location_id,
                    SalesDaily.day,
                    SalesDaily.quantity,
                ).where(
                    SalesDaily.organisation_id == org,
                    SalesDaily.product_id.in_(product_ids),
                    SalesDaily.day >= window_start,
                    SalesDaily.day < today,
                )
            )
        ).all():
            sales[pid].append((loc, d, qty))

        lines: dict[UUID, list[tuple[PurchaseOrderLine, PurchaseOrder]]] = defaultdict(list)
        for line, po in (
            await session.execute(
                select(PurchaseOrderLine, PurchaseOrder)
                .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
                .where(
                    PurchaseOrderLine.organisation_id == org,
                    PurchaseOrderLine.product_id.in_(product_ids),
                    PurchaseOrder.status == "open",
                    PurchaseOrderLine.quantity > PurchaseOrderLine.received_quantity,
                )
            )
        ).all():
            assert line.product_id is not None
            lines[line.product_id].append((line, po))

        terms: dict[UUID, list[_Terms]] = defaultdict(list)
        for sp, sup in (
            await session.execute(
                select(SupplierProduct, Supplier)
                .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
                .where(
                    SupplierProduct.organisation_id == org,
                    SupplierProduct.product_id.in_(product_ids),
                    Supplier.active.is_(True),
                )
            )
        ).all():
            terms[sp.product_id].append(_Terms(sp, sup))

        # Most recent PO per product (any status but cancelled) → preferred supplier and price.
        recent: dict[UUID, tuple[PurchaseOrderLine, PurchaseOrder]] = {}
        for line, po in (
            await session.execute(
                select(PurchaseOrderLine, PurchaseOrder)
                .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
                .where(
                    PurchaseOrderLine.organisation_id == org,
                    PurchaseOrderLine.product_id.in_(product_ids),
                    PurchaseOrder.status != "cancelled",
                    or_(PurchaseOrder.ordered_at.is_not(None), PurchaseOrder.status == "open"),
                )
                .order_by(PurchaseOrder.ordered_at.desc().nulls_last())
            )
        ).all():
            assert line.product_id is not None
            recent.setdefault(line.product_id, (line, po))

        stock_locations: dict[UUID, set[UUID]] = defaultdict(set)
        for sl, _, _ in stock_rows:
            stock_locations[sl.product_id].add(sl.location_id)
        findings: list[Finding] = []
        for g in self._groups(stock_rows, sales):
            f = self._evaluate_group(
                g,
                p,
                ctx,
                sales.get(g.product.id, []),
                first_sale.get(g.product.id),
                lines.get(g.product.id, []),
                terms.get(g.product.id, []),
                recent.get(g.product.id),
                multi_location=len(stock_locations[g.product.id]) > 1,
            )
            if f is not None:
                findings.append(f)
        return findings

    @staticmethod
    def _groups(
        stock_rows: Any, sales: dict[UUID, list[tuple[UUID | None, date, Decimal]]]
    ) -> list[_Group]:
        """Per location when every sale knows its location; otherwise across locations."""
        by_product: dict[UUID, list[tuple[StockLevel, Product, Location]]] = defaultdict(list)
        for sl, prod, loc in stock_rows:
            by_product[prod.id].append((sl, prod, loc))
        groups: list[_Group] = []
        for pid, rows in by_product.items():
            product = rows[0][1]
            located = all(loc is not None for loc, _, _ in sales.get(pid, []))
            if located and len(rows) > 1:
                for sl, _, loc in rows:
                    groups.append(_Group(product, loc, [(sl, loc)]))
            elif len(rows) == 1:
                groups.append(_Group(product, rows[0][2], [(rows[0][0], rows[0][2])]))
            else:
                groups.append(_Group(product, None, [(sl, loc) for sl, _, loc in rows]))
        return groups

    def _evaluate_group(
        self,
        g: _Group,
        p: StockoutParams,
        ctx: DetectionContext,
        product_sales: list[tuple[UUID | None, date, Decimal]],
        first_sale: date | None,
        po_lines: list[tuple[PurchaseOrderLine, PurchaseOrder]],
        product_terms: list[_Terms],
        last_po: tuple[PurchaseOrderLine, PurchaseOrder] | None,
        *,
        multi_location: bool,
    ) -> Finding | None:
        if first_sale is None:
            return None  # never sold: demand is unknown, nothing to project
        today = ctx.today
        product, uom = g.product, g.product.uom
        limitations: list[str] = []
        assumptions: list[str] = []

        # Demand: one value per day from the window start (or first sale) to yesterday.
        start = max(today - timedelta(days=p.sales_window_days), first_sale)
        per_day: dict[date, Decimal] = defaultdict(Decimal)
        single_location = g.location is not None and multi_location
        for sale_loc, d, qty in product_sales:
            if single_location and sale_loc != g.location.id:  # type: ignore[union-attr]
                continue
            if d >= start:
                per_day[d] += qty
        n_days = (today - start).days
        if n_days <= 0:
            return None
        daily = [per_day.get(start + timedelta(days=i), Decimal(0)) for i in range(n_days)]
        total_sold = sum(daily, Decimal(0))
        confidence = "normal"
        if n_days < p.min_history_days:
            confidence = "low"
            limitations.append(
                f"Only {n_days} days of sales history (fewer than {p.min_history_days}); "
                "demand estimates may be unreliable."
            )

        # Supplier terms: the supplier of the most recent purchase order, else the fastest.
        chosen: _Terms | None = None
        if last_po is not None and last_po[1].supplier_id is not None:
            chosen = next(
                (t for t in product_terms if t.supplier.id == last_po[1].supplier_id), None
            )
        if chosen is None and product_terms:
            chosen = min(
                product_terms,
                key=lambda t: (
                    t.supplier_product.lead_time_days is None,
                    t.supplier_product.lead_time_days or 0,
                    t.supplier_product.price or Decimal(0),
                ),
            )
        if chosen is not None and chosen.supplier_product.lead_time_days:
            lead = chosen.supplier_product.lead_time_days
            if len(product_terms) > 1:
                assumptions.append(
                    f"Used {chosen.supplier.name}'s terms; other suppliers also offer this item."
                )
        else:
            lead = p.default_lead_time_days
            limitations.append(
                f"No supplier lead time on record; used the configured default of {lead} days."
            )

        # Inbound: open purchase-order quantity expected within the lead time.
        horizon = today + timedelta(days=lead)
        inbound = Decimal(0)
        inbound_ev: list[Evidence] = []
        overdue_units = Decimal(0)
        undated: list[str] = []
        for line, po in po_lines:
            if g.location is not None and po.location_id not in (None, g.location.id):
                continue
            remaining = line.quantity - line.received_quantity
            expected = line.expected_at or po.expected_at
            if expected is None:
                undated.append(po.number)
                continue
            if expected.date() > horizon:
                continue
            inbound += remaining
            if expected.date() < today:
                overdue_units += remaining
            if g.location is not None and po.location_id is None and multi_location:
                assumptions.append(
                    f"Purchase order {po.number} has no destination; counted as arriving here."
                )
            inbound_ev.append(
                Evidence(
                    key="inbound_line",
                    label=f"Purchase order {po.number}",
                    value=f"{units(remaining, uom)} expected {day(expected)}",
                    numeric=remaining,
                    unit=uom or "units",
                    source_type="purchase_order_line",
                    source_id=line.id,
                    source_ref=f"{po.number} / line {line.external_id}",
                    connection_id=line.connection_id,
                )
            )
        if undated:
            limitations.append(
                "Not counted as inbound because they have no expected date: "
                + ", ".join(sorted(set(undated))[:5])
                + "."
            )
        if overdue_units > 0:
            assumptions.append(
                f"Includes {units(overdue_units, uom)} on purchase orders that are already late."
            )

        on_hand = sum((sl.on_hand for sl, _ in g.stock), Decimal(0))
        moq = chosen.supplier_product.min_quantity if chosen else None
        r = compute(
            StockoutInputs(
                on_hand=on_hand,
                daily_sales=daily,
                inbound_within_lead=inbound,
                lead_time_days=lead,
                service_level=p.service_level,
                review_period_days=p.review_period_days,
                min_order_quantity=moq,
            )
        )
        if not r.triggered:
            return None
        assert r.severity is not None

        where = g.location.name if g.location else "all locations"
        label = f"{product.sku or product.name} at {where}"
        sl_pct = num(Decimal(p.service_level) * 100, 1)
        stockout_date = (
            today + timedelta(days=max(0, math.floor(r.days_of_cover)))
            if r.days_of_cover is not None
            else None
        )
        m = {
            "on_hand": units(on_hand, uom),
            "avg_daily_demand": units(r.demand_per_day, uom),
            "demand_std_dev": units(r.demand_std_dev, uom),
            "lead_time": f"{lead} days",
            "service_level": f"{sl_pct}% (z = {r.z})",
            "safety_stock": units(r.safety_stock, uom),
            "reorder_point": units(r.reorder_point, uom),
            "inbound": units(inbound, uom),
            "projected_position": units(r.projected, uom),
            "days_of_cover": f"{num(r.days_of_cover)} days" if r.days_of_cover is not None else "",
            "stockout_date": day(stockout_date) if stockout_date else "",
            "recommended_quantity": units(r.recommended_quantity, uom, 0),
        }

        evidence: list[Evidence] = []
        for sl, loc in g.stock:
            evidence.append(
                Evidence(
                    key="on_hand",
                    label=f"On hand at {loc.name}",
                    value=units(sl.on_hand, uom),
                    numeric=sl.on_hand,
                    unit=uom or "units",
                    source_type="stock_level",
                    source_id=sl.id,
                    source_ref=f"{product.sku or product.external_id} @ {loc.code or loc.name}",
                    connection_id=sl.connection_id,
                    observed_at=sl.as_of,
                )
            )
        evidence.append(
            Evidence(
                key="avg_daily_demand",
                label=f"Average daily sales ({n_days} days to {day(today - timedelta(days=1))})",
                value=m["avg_daily_demand"],
                numeric=q(r.demand_per_day, 4),
                unit=f"{uom or 'units'}/day",
                source_type="sales_daily",
                source_id=product.id,
                source_ref=f"{units(total_sold, uom)} sold over {n_days} days",
                connection_id=product.connection_id,
                formula="units sold ÷ days",
            )
        )
        evidence.append(
            Evidence(
                key="demand_std_dev",
                label="Day-to-day variation in sales (standard deviation)",
                value=m["demand_std_dev"],
                numeric=q(r.demand_std_dev, 4),
                source_type="sales_daily",
                source_id=product.id,
                connection_id=product.connection_id,
                formula="sample standard deviation of daily sales",
            )
        )
        if chosen is not None and chosen.supplier_product.lead_time_days:
            evidence.append(
                Evidence(
                    key="lead_time",
                    label=f"Lead time from {chosen.supplier.name}",
                    value=m["lead_time"],
                    numeric=Decimal(lead),
                    unit="days",
                    source_type="supplier_product",
                    source_id=chosen.supplier_product.id,
                    source_ref=chosen.supplier_product.external_id,
                    connection_id=chosen.supplier_product.connection_id,
                )
            )
        else:
            evidence.append(
                Evidence(
                    key="lead_time",
                    label="Lead time (configured default)",
                    value=m["lead_time"],
                    numeric=Decimal(lead),
                    unit="days",
                    source_type="detector_config",
                    source_ref="default_lead_time_days",
                )
            )
        evidence += [
            Evidence(
                key="service_level",
                label="Service level target",
                value=m["service_level"],
                numeric=Decimal(p.service_level),
                source_type="detector_config",
                source_ref="service_level",
            ),
            Evidence(
                key="safety_stock",
                label="Safety stock",
                value=m["safety_stock"],
                numeric=q(r.safety_stock, 4),
                source_type="computed",
                formula="z × standard deviation × √lead time",
            ),
            Evidence(
                key="reorder_point",
                label="Reorder point",
                value=m["reorder_point"],
                numeric=q(r.reorder_point, 4),
                source_type="computed",
                formula="average daily sales × lead time + safety stock",
            ),
            Evidence(
                key="inbound",
                label=f"Inbound by {day(horizon)} (open purchase orders)",
                value=m["inbound"],
                numeric=inbound,
                source_type="computed",
                formula="sum of open purchase-order lines expected within the lead time",
            ),
            *inbound_ev,
            Evidence(
                key="projected_position",
                label="Projected stock when an order placed today could arrive",
                value=m["projected_position"],
                numeric=q(r.projected, 4),
                source_type="computed",
                formula="on hand + inbound − average daily sales × lead time",
            ),
        ]
        if r.days_of_cover is not None:
            evidence.append(
                Evidence(
                    key="days_of_cover",
                    label="Days of cover at current sales",
                    value=m["days_of_cover"],
                    numeric=q(r.days_of_cover, 4),
                    unit="days",
                    source_type="computed",
                    formula="on hand ÷ average daily sales",
                )
            )
        if stockout_date is not None:
            evidence.append(
                Evidence(
                    key="stockout_date",
                    label="Projected stockout date with no new stock",
                    value=m["stockout_date"],
                    source_type="computed",
                    formula="today + whole days of cover",
                )
            )

        recommendation: dict[str, Any] = {
            "action": "create_purchase_request",
            "product_id": str(product.id),
            "location_id": str(g.location.id) if g.location else None,
            "quantity": r.recommended_quantity,
            "quantity_display": m["recommended_quantity"],
            "basis": "reorder point + average daily sales × review period − on hand − inbound"
            + (", raised to the supplier's minimum order" if moq else ""),
            "supplier_id": str(chosen.supplier.id) if chosen else None,
            "supplier_name": chosen.supplier.name if chosen else None,
        }
        evidence.append(
            Evidence(
                key="recommended_quantity",
                label="Recommended order quantity",
                value=m["recommended_quantity"],
                numeric=Decimal(r.recommended_quantity),
                source_type="computed",
                formula=recommendation["basis"],
            )
        )
        if moq:
            evidence.append(
                Evidence(
                    key="min_order_quantity",
                    label="Supplier minimum order",
                    value=units(moq, uom),
                    numeric=moq,
                    source_type="supplier_product",
                    source_id=chosen.supplier_product.id if chosen else None,
                    connection_id=chosen.supplier_product.connection_id if chosen else None,
                )
            )
        price, currency, price_ev = _price(chosen, last_po)
        if price is not None:
            value = price * r.recommended_quantity
            recommendation |= {
                "unit_price": str(q(price, 4)),
                "currency": currency,
                "estimated_value": str(q(value, 2)),
                "estimated_value_display": money(value, currency),
            }
            evidence.append(price_ev)  # type: ignore[arg-type]
            evidence.append(
                Evidence(
                    key="estimated_value",
                    label="Estimated order value",
                    value=money(value, currency),
                    numeric=q(value, 2),
                    source_type="computed",
                    formula="recommended quantity × unit price",
                )
            )
        else:
            limitations.append("No price on record for this item; order value not estimated.")
        if chosen is None:
            limitations.append("No supplier is linked to this item; choose one when ordering.")

        title = {
            "critical": f"{product.name} may run out at {where} before an order can arrive",
            "high": f"{product.name} at {where} will dip into safety stock",
            "medium": f"{product.name} at {where} will reach its reorder point within "
            f"{p.review_period_days} days",
        }[r.severity]
        summary = (
            f"{m['on_hand']} on hand and {m['inbound']} inbound against a reorder point of "
            f"{m['reorder_point']}. Recommended order: {m['recommended_quantity']}."
        )
        return Finding(
            subject_type="product_location",
            subject_key=f"{product.id}:{g.location.id if g.location else '*'}",
            subject_label=label,
            severity=r.severity,
            confidence=confidence,
            title=title,
            summary=summary,
            evidence=evidence,
            metrics={k: v for k, v in m.items() if v},
            recommendation=recommendation,
            assumptions=list(dict.fromkeys(assumptions)),
            limitations=limitations,
            explanation=_template(r.severity, label, m, lead),
        )


def _price(
    chosen: _Terms | None, last_po: tuple[PurchaseOrderLine, PurchaseOrder] | None
) -> tuple[Decimal | None, str | None, Evidence | None]:
    if (
        last_po is not None
        and last_po[0].unit_price is not None
        and (chosen is None or last_po[1].supplier_id == chosen.supplier.id)
    ):
        line, po = last_po
        price = line.unit_price
        assert price is not None
        return (
            price,
            po.currency,
            Evidence(
                key="unit_price",
                label=f"Unit price on purchase order {po.number}",
                value=money(price, po.currency),
                numeric=price,
                source_type="purchase_order_line",
                source_id=line.id,
                source_ref=f"{po.number} / line {line.external_id}",
                connection_id=line.connection_id,
            ),
        )
    if chosen is not None and chosen.supplier_product.price is not None:
        sp = chosen.supplier_product
        assert sp.price is not None
        return (
            sp.price,
            sp.currency,
            Evidence(
                key="unit_price",
                label=f"Unit price from {chosen.supplier.name}'s terms",
                value=money(sp.price, sp.currency),
                numeric=sp.price,
                source_type="supplier_product",
                source_id=sp.id,
                source_ref=sp.external_id,
                connection_id=sp.connection_id,
            ),
        )
    return None, None, None


def _template(severity: str, label: str, m: dict[str, str], lead: int) -> dict[str, str]:
    if severity == "critical":
        happened = (
            f"{label} has {m['on_hand']} on hand and {m['inbound']} due within the {lead}-day "
            f"lead time. Selling {m['avg_daily_demand']} a day, it is projected to run out "
            f"around {m['stockout_date']}, before an order placed today could arrive."
        )
        why = (
            "Customers may go unserved until replenishment arrives, and any delay to inbound "
            "purchase orders extends the gap."
        )
    elif severity == "high":
        happened = (
            f"{label} has {m['on_hand']} on hand and {m['inbound']} due within the {lead}-day "
            f"lead time, below the reorder point of {m['reorder_point']}. At "
            f"{m['avg_daily_demand']} a day, stock is projected to fall to "
            f"{m['projected_position']} by the time an order placed today arrives."
        )
        why = (
            f"That is below the safety stock of {m['safety_stock']} held for demand swings at "
            f"the {m['service_level']} service level, so a busier-than-usual week could cause "
            "a stockout."
        )
    else:
        happened = (
            f"{label} has {m['on_hand']} on hand and {m['inbound']} due within the {lead}-day "
            f"lead time. Selling {m['avg_daily_demand']} a day, it will reach the reorder point "
            f"of {m['reorder_point']} before the next review."
        )
        why = (
            f"Ordering at this review keeps the safety stock of {m['safety_stock']} intact "
            "through the lead time; waiting for the next one risks dipping into it."
        )
    return {"what_happened": happened, "why_it_matters": why}


__all__ = ["StockoutInputs", "StockoutParams", "StockoutResult", "StockoutRiskDetector", "compute"]
