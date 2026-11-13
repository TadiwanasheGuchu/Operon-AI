"""CSV import: a connection type for organisations whose systems have no connector yet.

Each upload is one file of one kind. Validation is strict and all-or-nothing: if any row is
invalid, nothing is written and the response lists the problems (row, column, message).
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from operon.modules.integrations.connectors.base import (
    LocationRecord,
    ProductRecord,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    SalesRecord,
    StockRecord,
    SupplierProductRecord,
    SupplierRecord,
)

Kind = Literal["locations", "products", "supplier_terms", "stock", "sales", "purchase_orders"]
MAX_ROWS = 50_000
MAX_ERRORS = 50

COLUMNS: dict[str, tuple[list[str], list[str]]] = {  # kind -> (required, optional)
    "locations": (["code", "name"], []),
    "products": (["sku", "name"], ["uom", "unit_cost", "currency", "active"]),
    "supplier_terms": (
        ["supplier", "sku"],
        ["lead_time_days", "min_quantity", "price", "currency"],
    ),
    "stock": (["sku", "location_code", "on_hand"], ["reserved"]),
    "sales": (["date", "sku", "quantity"], ["location_code"]),
    "purchase_orders": (
        ["po_number", "supplier", "status", "sku", "quantity"],
        [
            "location_code",
            "ordered_at",
            "expected_at",
            "currency",
            "received_quantity",
            "unit_price",
        ],
    ),
}
DESCRIPTIONS = {
    "locations": "Warehouses and stores. Import these first.",
    "products": "One row per SKU.",
    "supplier_terms": "Lead time, minimum order and price per supplier and SKU.",
    "stock": "Current on-hand stock per SKU and location. Replaces the previous stock import.",
    "sales": "Units sold per day, SKU and (optionally) location. Replaces those days' values.",
    "purchase_orders": "One row per order line; order details repeat on each line.",
}
EXAMPLES = {
    "locations": [["LEEDS", "Leeds DC"]],
    "products": [["HV-GLV-220", "Nitrile gloves, size L", "box", "4.85", "GBP", "true"]],
    "supplier_terms": [["Brightline Safety Supplies", "HV-GLV-220", "9", "500", "4.85", "GBP"]],
    "stock": [["HV-GLV-220", "LEEDS", "1240", "0"]],
    "sales": [["2026-11-12", "HV-GLV-220", "186", "LEEDS"]],
    "purchase_orders": [
        [
            "PO-10482",
            "Brightline Safety Supplies",
            "open",
            "HV-GLV-220",
            "2000",
            "LEEDS",
            "2026-11-10",
            "2026-11-27",
            "GBP",
            "0",
            "4.85",
        ]
    ],
}
PO_STATUSES = {"draft", "open", "received", "cancelled"}


def template(kind: Kind) -> str:
    required, optional = COLUMNS[kind]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(required + optional)
    writer.writerows(EXAMPLES[kind])
    return out.getvalue()


@dataclass
class RowError:
    row: int
    column: str | None
    message: str


@dataclass
class Parsed:
    kind: Kind
    rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    error_count: int = 0
    records: dict[str, list[Any]] = field(default_factory=dict)

    def error(self, row: int, column: str | None, message: str) -> None:
        self.error_count += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(RowError(row, column, message))


def _decimal(
    p: Parsed, row: int, col: str, value: str, *, required: bool = True, non_negative: bool = True
) -> Decimal | None:
    if not value:
        if required:
            p.error(row, col, "is required")
        return None
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        p.error(row, col, f"“{value[:30]}” is not a number")
        return None
    if not number.is_finite() or (non_negative and number < 0):
        p.error(row, col, "must be zero or more")
        return None
    return number


def _date(p: Parsed, row: int, col: str, value: str, *, required: bool = True) -> date | None:
    if not value:
        if required:
            p.error(row, col, "is required")
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        p.error(row, col, f"“{value[:30]}” is not a date (use YYYY-MM-DD)")
        return None


def _at(d: date | None) -> datetime | None:
    return datetime(d.year, d.month, d.day, tzinfo=UTC) if d else None


def parse(kind: Kind, content: bytes, *, known_skus: set[str], known_locations: set[str]) -> Parsed:
    """Validate a file and convert it to connector records (no database access)."""
    p = Parsed(kind)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        p.error(0, None, "The file isn't UTF-8 text. Save it as “CSV UTF-8” and try again.")
        return p
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    required, optional = COLUMNS[kind]
    missing = [c for c in required if c not in headers]
    if missing:
        p.error(1, None, f"Missing column(s): {', '.join(missing)}")
        return p
    unknown = [h for h in headers if h and h not in required + optional]
    if unknown:
        p.error(1, None, f"Unexpected column(s): {', '.join(unknown)}")
        return p

    skus = set(known_skus)
    locations = set(known_locations)
    out: list[Any] = []
    suppliers: dict[str, SupplierRecord] = {}
    orders: dict[str, dict[str, Any]] = {}
    convert: dict[str, Callable[[int, dict[str, str]], None]] = {}

    def loc(r: int, d: dict[str, str]) -> None:
        code = d["code"]
        if not code or not d["name"]:
            p.error(r, "code" if not code else "name", "is required")
            return
        locations.add(code)
        out.append(LocationRecord(code, d["name"], code))

    def prod(r: int, d: dict[str, str]) -> None:
        if not d["sku"] or not d["name"]:
            p.error(r, "sku" if not d["sku"] else "name", "is required")
            return
        cost = _decimal(p, r, "unit_cost", d.get("unit_cost", ""), required=False)
        active = d.get("active", "").lower() not in ("false", "no", "0")
        skus.add(d["sku"])
        out.append(
            ProductRecord(
                d["sku"],
                d["name"],
                sku=d["sku"],
                uom=d.get("uom") or None,
                unit_cost=cost,
                currency=(d.get("currency") or None),
                active=active,
            )
        )

    def need_sku(r: int, sku: str) -> bool:
        if not sku:
            p.error(r, "sku", "is required")
            return False
        if sku not in skus:
            p.error(r, "sku", f"Unknown SKU “{sku[:40]}”. Import products first.")
            return False
        return True

    def need_location(r: int, code: str, *, required: bool) -> bool:
        if not code:
            if required:
                p.error(r, "location_code", "is required")
            return not required
        if code not in locations:
            p.error(r, "location_code", f"Unknown location “{code[:40]}”. Import locations first.")
            return False
        return True

    def terms(r: int, d: dict[str, str]) -> None:
        if not d["supplier"]:
            p.error(r, "supplier", "is required")
            return
        if not need_sku(r, d["sku"]):
            return
        lead = _decimal(p, r, "lead_time_days", d.get("lead_time_days", ""), required=False)
        suppliers.setdefault(d["supplier"], SupplierRecord(d["supplier"], d["supplier"]))
        out.append(
            SupplierProductRecord(
                external_id=f"{d['supplier']}|{d['sku']}",
                supplier_external_id=d["supplier"],
                product_external_id=d["sku"],
                lead_time_days=int(lead) if lead is not None else None,
                min_quantity=_decimal(
                    p, r, "min_quantity", d.get("min_quantity", ""), required=False
                ),
                price=_decimal(p, r, "price", d.get("price", ""), required=False),
                currency=d.get("currency") or None,
            )
        )

    def stock(r: int, d: dict[str, str]) -> None:
        ok = need_sku(r, d["sku"]) & need_location(r, d["location_code"], required=True)
        on_hand = _decimal(p, r, "on_hand", d["on_hand"])
        reserved = _decimal(p, r, "reserved", d.get("reserved", ""), required=False)
        if ok and on_hand is not None:
            out.append(StockRecord(d["sku"], d["location_code"], on_hand, reserved or Decimal(0)))

    def sales(r: int, d: dict[str, str]) -> None:
        day = _date(p, r, "date", d["date"])
        ok = need_sku(r, d["sku"]) & need_location(r, d.get("location_code", ""), required=False)
        qty = _decimal(p, r, "quantity", d["quantity"])
        if day and day > datetime.now(UTC).date():
            p.error(r, "date", "is in the future")
            return
        if ok and day and qty is not None:
            out.append(SalesRecord(d["sku"], day, qty, d.get("location_code") or None))

    def po(r: int, d: dict[str, str]) -> None:
        number, status = d["po_number"], d["status"].lower()
        if not number or not d["supplier"]:
            p.error(r, "po_number" if not number else "supplier", "is required")
            return
        if status not in PO_STATUSES:
            p.error(r, "status", f"must be one of {', '.join(sorted(PO_STATUSES))}")
            return
        ok = need_sku(r, d["sku"]) & need_location(r, d.get("location_code", ""), required=False)
        qty = _decimal(p, r, "quantity", d["quantity"])
        received = _decimal(
            p, r, "received_quantity", d.get("received_quantity", ""), required=False
        )
        price = _decimal(p, r, "unit_price", d.get("unit_price", ""), required=False)
        ordered = _date(p, r, "ordered_at", d.get("ordered_at", ""), required=False)
        expected = _date(p, r, "expected_at", d.get("expected_at", ""), required=False)
        if not ok or qty is None:
            return
        suppliers.setdefault(d["supplier"], SupplierRecord(d["supplier"], d["supplier"]))
        order = orders.setdefault(
            number,
            {
                "supplier": d["supplier"],
                "status": status,
                "location": d.get("location_code") or None,
                "ordered": ordered,
                "expected": expected,
                "currency": d.get("currency") or None,
                "lines": [],
            },
        )
        if order["supplier"] != d["supplier"] or order["status"] != status:
            p.error(r, "po_number", "has different supplier or status on another line")
            return
        order["lines"].append(
            PurchaseOrderLineRecord(
                external_id=f"{number}|{len(order['lines']) + 1}",
                product_external_id=d["sku"],
                quantity=qty,
                received_quantity=received or Decimal(0),
                unit_price=price,
                expected_at=_at(expected),
            )
        )

    convert = {
        "locations": loc,
        "products": prod,
        "supplier_terms": terms,
        "stock": stock,
        "sales": sales,
        "purchase_orders": po,
    }
    for index, raw in enumerate(reader, start=2):
        if index - 1 > MAX_ROWS:
            p.error(index, None, f"Files are limited to {MAX_ROWS:,} rows.")
            break
        data = {k: (v or "").strip() for k, v in raw.items() if k}
        if not any(data.values()):
            continue
        p.rows += 1
        convert[kind](index, data)
    if p.rows == 0 and not p.errors:
        p.error(2, None, "The file has no data rows.")

    if kind == "purchase_orders":
        for number, o in orders.items():
            total = sum(((ln.unit_price or 0) * ln.quantity for ln in o["lines"]), Decimal(0))
            out.append(
                PurchaseOrderRecord(
                    external_id=number,
                    number=number,
                    status=o["status"],
                    supplier_external_id=o["supplier"],
                    location_external_id=o["location"],
                    ordered_at=_at(o["ordered"]),
                    expected_at=_at(o["expected"]),
                    currency=o["currency"],
                    total=total,
                    lines=tuple(o["lines"]),
                )
            )
    p.records = {kind: out, "suppliers": list(suppliers.values())}
    return p
