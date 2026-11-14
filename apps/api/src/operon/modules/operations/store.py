"""Write connector output into the canonical tables. One call = one entity, one transaction.

Rules (plan §3, CLAUDE.md §13 "integration failures must never silently corrupt data"):
- catalogue entities (locations, suppliers, products, supplier terms, purchase orders) are
  idempotent upserts keyed on (connection_id, external_id);
- stock is a snapshot: the connection's previous stock rows are replaced as a whole;
- sales are windowed: the connection's rows for the synced days are replaced;
- records referring to unknown products/locations/suppliers are skipped and counted, never
  guessed.
The caller provides a transaction with the organisation's RLS context already set.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from operon.core.ids import uuid7
from operon.modules.integrations.connectors.base import (
    LocationRecord,
    ProductRecord,
    PurchaseOrderRecord,
    SalesRecord,
    StockRecord,
    SupplierProductRecord,
    SupplierRecord,
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

CHUNK = 5000


@dataclass
class EntityStats:
    received: int = 0
    written: int = 0
    skipped: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped += 1
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"received": self.received, "written": self.written}
        if self.skipped:
            out["skipped"] = self.skipped
            out["skipped_reasons"] = self.skipped_reasons
        return out


class Store:
    def __init__(self, session: AsyncSession, organisation_id: UUID, connection_id: UUID) -> None:
        self.s = session
        self.org = organisation_id
        self.conn = connection_id
        self._ids: dict[type, dict[str, UUID]] = {}

    def _base(self) -> dict[str, Any]:
        return {"organisation_id": self.org, "connection_id": self.conn}

    async def _id_map(self, model: Any) -> dict[str, UUID]:
        if model not in self._ids:
            rows = await self.s.execute(
                select(model.external_id, model.id).where(
                    model.organisation_id == self.org, model.connection_id == self.conn
                )
            )
            self._ids[model] = {ext: ident for ext, ident in rows.all()}
        return self._ids[model]

    async def _upsert(self, model: Any, rows: list[dict[str, Any]], update: Sequence[str]) -> None:
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i : i + CHUNK]
            stmt = insert(model)
            stmt = stmt.on_conflict_do_update(
                index_elements=["connection_id", "external_id"],
                set_={c: getattr(stmt.excluded, c) for c in [*update, "updated_at"]},
            )
            # executemany: one cached statement, batched by SQLAlchemy ("insertmanyvalues").
            await self.s.execute(stmt, chunk)
        self._ids.pop(model, None)

    async def locations(self, records: Sequence[LocationRecord]) -> EntityStats:
        rows = [
            {
                **self._base(),
                "id": uuid7(),
                "external_id": r.external_id,
                "name": r.name,
                "code": r.code,
                "updated_at": datetime.now(UTC),
            }
            for r in _dedupe(records)
        ]
        await self._upsert(Location, rows, ["name", "code"]) if rows else None
        return EntityStats(len(records), len(rows))

    async def suppliers(self, records: Sequence[SupplierRecord]) -> EntityStats:
        rows = [
            {
                **self._base(),
                "id": uuid7(),
                "external_id": r.external_id,
                "name": r.name,
                "email": r.email,
                "active": r.active,
                "updated_at": datetime.now(UTC),
            }
            for r in _dedupe(records)
        ]
        await self._upsert(Supplier, rows, ["name", "email", "active"]) if rows else None
        return EntityStats(len(records), len(rows))

    async def products(self, records: Sequence[ProductRecord]) -> EntityStats:
        rows = [
            {
                **self._base(),
                "id": uuid7(),
                "external_id": r.external_id,
                "sku": r.sku,
                "name": r.name,
                "uom": r.uom,
                "unit_cost": r.unit_cost,
                "currency": r.currency,
                "active": r.active,
                "updated_at": datetime.now(UTC),
            }
            for r in _dedupe(records)
        ]
        await self._upsert(
            Product, rows, ["sku", "name", "uom", "unit_cost", "currency", "active"]
        ) if rows else None
        return EntityStats(len(records), len(rows))

    async def supplier_products(self, records: Sequence[SupplierProductRecord]) -> EntityStats:
        stats = EntityStats(received=len(records))
        suppliers, products = await self._id_map(Supplier), await self._id_map(Product)
        rows = []
        for r in _dedupe(records):
            sid, pid = suppliers.get(r.supplier_external_id), products.get(r.product_external_id)
            if not sid or not pid:
                stats.skip("unknown supplier or product")
                continue
            rows.append(
                {
                    **self._base(),
                    "id": uuid7(),
                    "external_id": r.external_id,
                    "supplier_id": sid,
                    "product_id": pid,
                    "lead_time_days": r.lead_time_days,
                    "min_quantity": r.min_quantity,
                    "price": r.price,
                    "currency": r.currency,
                    "updated_at": datetime.now(UTC),
                }
            )
        if rows:
            await self._upsert(
                SupplierProduct,
                rows,
                [
                    "supplier_id",
                    "product_id",
                    "lead_time_days",
                    "min_quantity",
                    "price",
                    "currency",
                ],
            )
        stats.written = len(rows)
        return stats

    async def stock_snapshot(self, records: Sequence[StockRecord]) -> EntityStats:
        """Replace this connection's stock with the snapshot (all or nothing)."""
        stats = EntityStats(received=len(records))
        products, locations = await self._id_map(Product), await self._id_map(Location)
        now = datetime.now(UTC)
        merged: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        for r in records:
            pid, lid = products.get(r.product_external_id), locations.get(r.location_external_id)
            if not pid or not lid:
                stats.skip("unknown product or location")
                continue
            row = merged.setdefault(
                (pid, lid),
                {
                    **self._base(),
                    "id": uuid7(),
                    "product_id": pid,
                    "location_id": lid,
                    "on_hand": 0,
                    "reserved": 0,
                    "as_of": now,
                },
            )
            row["on_hand"] += r.on_hand
            row["reserved"] += r.reserved
        await self.s.execute(
            delete(StockLevel).where(
                StockLevel.organisation_id == self.org, StockLevel.connection_id == self.conn
            )
        )
        rows = list(merged.values())
        for i in range(0, len(rows), CHUNK):
            await self.s.execute(insert(StockLevel), rows[i : i + CHUNK])
        stats.written = len(rows)
        return stats

    async def sales_window(self, records: Sequence[SalesRecord], from_day: date) -> EntityStats:
        """Replace this connection's daily sales from `from_day` onwards."""
        stats = EntityStats(received=len(records))
        products, locations = await self._id_map(Product), await self._id_map(Location)
        merged: dict[tuple[UUID, str, date], dict[str, Any]] = {}
        for r in records:
            pid = products.get(r.product_external_id)
            lid = locations.get(r.location_external_id) if r.location_external_id else None
            if not pid or (r.location_external_id and not lid):
                stats.skip("unknown product or location")
                continue
            if r.day < from_day:
                stats.skip("outside sync window")
                continue
            key = (pid, str(lid or ""), r.day)
            row = merged.setdefault(
                key,
                {
                    **self._base(),
                    "id": uuid7(),
                    "product_id": pid,
                    "location_id": lid,
                    "location_key": str(lid or ""),
                    "day": r.day,
                    "quantity": 0,
                },
            )
            row["quantity"] += r.quantity
        await self.s.execute(
            delete(SalesDaily).where(
                SalesDaily.organisation_id == self.org,
                SalesDaily.connection_id == self.conn,
                SalesDaily.day >= from_day,
            )
        )
        rows = list(merged.values())
        for i in range(0, len(rows), CHUNK):
            await self.s.execute(insert(SalesDaily), rows[i : i + CHUNK])
        stats.written = len(rows)
        return stats

    async def sales_upsert_days(self, records: Sequence[SalesRecord]) -> EntityStats:
        """Replace exactly the (product, location, day) cells present (CSV imports)."""
        stats = EntityStats(received=len(records))
        if not records:
            return stats
        products, locations = await self._id_map(Product), await self._id_map(Location)
        keys = set()
        for r in records:
            pid = products.get(r.product_external_id)
            lid = locations.get(r.location_external_id) if r.location_external_id else None
            if pid:
                keys.add((pid, str(lid or ""), r.day))
        if keys:
            await self.s.execute(
                delete(SalesDaily).where(
                    SalesDaily.organisation_id == self.org,
                    SalesDaily.connection_id == self.conn,
                    tuple_(SalesDaily.product_id, SalesDaily.location_key, SalesDaily.day).in_(
                        list(keys)
                    ),
                )
            )
        merged: dict[tuple[UUID, str, date], dict[str, Any]] = {}
        for r in records:
            pid = products.get(r.product_external_id)
            lid = locations.get(r.location_external_id) if r.location_external_id else None
            if not pid or (r.location_external_id and not lid):
                stats.skip("unknown product or location")
                continue
            key = (pid, str(lid or ""), r.day)
            row = merged.setdefault(
                key,
                {
                    **self._base(),
                    "id": uuid7(),
                    "product_id": pid,
                    "location_id": lid,
                    "location_key": str(lid or ""),
                    "day": r.day,
                    "quantity": 0,
                },
            )
            row["quantity"] += r.quantity
        rows = list(merged.values())
        for i in range(0, len(rows), CHUNK):
            await self.s.execute(insert(SalesDaily), rows[i : i + CHUNK])
        stats.written = len(rows)
        return stats

    async def purchase_orders(self, records: Sequence[PurchaseOrderRecord]) -> EntityStats:
        stats = EntityStats(received=len(records))
        suppliers, locations, products = (
            await self._id_map(Supplier),
            await self._id_map(Location),
            await self._id_map(Product),
        )
        orders = _dedupe(records)
        rows = [
            {
                **self._base(),
                "id": uuid7(),
                "external_id": r.external_id,
                "number": r.number,
                "supplier_id": suppliers.get(r.supplier_external_id or ""),
                "location_id": locations.get(r.location_external_id or ""),
                "status": r.status,
                "ordered_at": r.ordered_at,
                "expected_at": r.expected_at,
                "currency": r.currency,
                "total": r.total,
                "updated_at": datetime.now(UTC),
            }
            for r in orders
        ]
        if not rows:
            return stats
        await self._upsert(
            PurchaseOrder,
            rows,
            [
                "number",
                "supplier_id",
                "location_id",
                "status",
                "ordered_at",
                "expected_at",
                "currency",
                "total",
            ],
        )
        po_ids = await self._id_map(PurchaseOrder)
        # Lines are replaced per order, so lines removed upstream disappear here too.
        touched = [po_ids[r.external_id] for r in orders]
        await self.s.execute(
            delete(PurchaseOrderLine).where(
                PurchaseOrderLine.organisation_id == self.org,
                PurchaseOrderLine.purchase_order_id.in_(touched),
            )
        )
        lines = []
        for r in orders:
            for ln in r.lines:
                pid = products.get(ln.product_external_id or "")
                if ln.product_external_id and not pid:
                    stats.skip("line for unknown product")
                lines.append(
                    {
                        **self._base(),
                        "id": uuid7(),
                        "external_id": ln.external_id,
                        "purchase_order_id": po_ids[r.external_id],
                        "product_id": pid,
                        "quantity": ln.quantity,
                        "received_quantity": ln.received_quantity,
                        "unit_price": ln.unit_price,
                        "expected_at": ln.expected_at,
                    }
                )
        for i in range(0, len(lines), CHUNK):
            await self.s.execute(insert(PurchaseOrderLine), lines[i : i + CHUNK])
        stats.written = len(rows)
        return stats


def _dedupe[T](records: Sequence[T]) -> list[T]:
    """Last record wins for a repeated external id (pages can overlap during edits upstream)."""
    seen: dict[str, T] = {}
    for r in records:
        seen[getattr(r, "external_id")] = r  # noqa: B009
    return list(seen.values())
