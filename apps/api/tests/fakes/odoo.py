"""Protocol-level Odoo test server (JSON-2 and JSON-RPC), backed by an in-memory dataset.

Implements the parts of Odoo's external API the connector uses: authentication, search_read
with domains (=, !=, >, >=, <, in, dotted paths), limit/offset/order, create, and read of
company/model metadata. It is a test double for the transport, not a re-implementation of Odoo.
"""

import json
import operator
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

API_KEY = "odoo-test-key-1234567890"
NOW = datetime.now(UTC).replace(microsecond=0)


def ts(days_ago: float = 0) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def dataset() -> dict[str, list[dict[str, Any]]]:
    return {
        "res.company": [{"id": 1, "currency_id": [3, "GBP"]}],
        "ir.model": [
            {"id": i, "model": m}
            for i, m in enumerate(
                [
                    "stock.warehouse",
                    "product.product",
                    "product.supplierinfo",
                    "res.partner",
                    "stock.quant",
                    "sale.order",
                    "purchase.order",
                ],
                start=1,
            )
        ],
        "stock.warehouse": [
            {"id": 1, "name": "Leeds DC", "code": "LDS", "write_date": ts(30)},
            {"id": 2, "name": "Bristol DC", "code": "BRS", "write_date": ts(30)},
        ],
        "res.partner": [
            {
                "id": 10,
                "name": "Brightline Safety Supplies",
                "email": "orders@brightline.example",
                "active": True,
                "supplier_rank": 1,
                "write_date": ts(30),
            },
            {
                "id": 11,
                "name": "Kestrel Packaging",
                "email": None,
                "active": True,
                "supplier_rank": 2,
                "write_date": ts(30),
            },
            {
                "id": 12,
                "name": "A customer",
                "email": None,
                "active": True,
                "supplier_rank": 0,
                "write_date": ts(30),
            },
        ],
        "product.product": [
            {
                "id": 100,
                "default_code": "HV-GLV-220",
                "name": "Nitrile gloves, size L",
                "uom_id": [1, "Units"],
                "standard_price": 4.85,
                "active": True,
                "type": "consu",
                "product_tmpl_id": [500, "Nitrile gloves"],
                "write_date": ts(10),
            },
            {
                "id": 101,
                "default_code": "HV-VST-104",
                "name": "Hi-vis vest",
                "uom_id": [1, "Units"],
                "standard_price": 2.1,
                "active": True,
                "type": "consu",
                "product_tmpl_id": [501, "Hi-vis vest"],
                "write_date": ts(10),
            },
            {
                "id": 102,
                "default_code": "CTN-600",
                "name": "Carton 600x400",
                "uom_id": [1, "Units"],
                "standard_price": 0.78,
                "active": True,
                "type": "product",
                "product_tmpl_id": [502, "Carton"],
                "write_date": ts(10),
            },
            {
                "id": 103,
                "default_code": "SVC-1",
                "name": "Delivery service",
                "uom_id": [1, "Units"],
                "standard_price": 0,
                "active": True,
                "type": "service",
                "product_tmpl_id": [503, "Delivery"],
                "write_date": ts(10),
            },
        ],
        "product.supplierinfo": [
            # Variant-level terms…
            {
                "id": 900,
                "partner_id": [10, "Brightline"],
                "product_id": [100, "Gloves"],
                "product_tmpl_id": [500, "Gloves"],
                "min_qty": 500,
                "price": 4.85,
                "delay": 9,
                "currency_id": [3, "GBP"],
                "write_date": ts(10),
            },
            # …and template-level terms, which apply to every variant of the template.
            {
                "id": 901,
                "partner_id": [11, "Kestrel"],
                "product_id": False,
                "product_tmpl_id": [502, "Carton"],
                "min_qty": 1000,
                "price": 0.78,
                "delay": 5,
                "currency_id": [3, "GBP"],
                "write_date": ts(10),
            },
        ],
        "stock.quant": [
            {
                "id": 1,
                "product_id": [100, "Gloves"],
                "warehouse_id": [1, "Leeds DC"],
                "location_usage": "internal",
                "quantity": 1000,
                "reserved_quantity": 40,
            },
            {
                "id": 2,
                "product_id": [100, "Gloves"],
                "warehouse_id": [1, "Leeds DC"],
                "location_usage": "internal",
                "quantity": 240,
                "reserved_quantity": 0,
            },
            {
                "id": 3,
                "product_id": [101, "Vest"],
                "warehouse_id": [2, "Bristol DC"],
                "location_usage": "internal",
                "quantity": 1610,
                "reserved_quantity": 10,
            },
            {
                "id": 4,
                "product_id": [100, "Gloves"],
                "warehouse_id": False,
                "location_usage": "customer",
                "quantity": 99,
                "reserved_quantity": 0,
            },
        ],
        "sale.order": [
            {"id": 70, "date_order": ts(1), "warehouse_id": [1, "Leeds DC"], "state": "sale"},
            {"id": 71, "date_order": ts(1), "warehouse_id": [1, "Leeds DC"], "state": "done"},
            {"id": 72, "date_order": ts(2), "warehouse_id": [2, "Bristol DC"], "state": "sale"},
            {"id": 73, "date_order": ts(1), "warehouse_id": [1, "Leeds DC"], "state": "cancel"},
            {"id": 74, "date_order": ts(200), "warehouse_id": [1, "Leeds DC"], "state": "sale"},
        ],
        "sale.order.line": [
            {
                "id": 1,
                "order_id": [70, "S70"],
                "product_id": [100, "Gloves"],
                "product_uom_qty": 100,
            },
            {
                "id": 2,
                "order_id": [71, "S71"],
                "product_id": [100, "Gloves"],
                "product_uom_qty": 86,
            },
            {"id": 3, "order_id": [72, "S72"], "product_id": [101, "Vest"], "product_uom_qty": 61},
            {
                "id": 4,
                "order_id": [73, "S73"],
                "product_id": [100, "Gloves"],
                "product_uom_qty": 999,
            },
            {
                "id": 5,
                "order_id": [74, "S74"],
                "product_id": [100, "Gloves"],
                "product_uom_qty": 777,
            },
        ],
        "stock.picking.type": [
            {"id": 7, "code": "incoming", "warehouse_id": [1, "Leeds DC"]},
            {"id": 8, "code": "incoming", "warehouse_id": [2, "Bristol DC"]},
        ],
        "purchase.order": [
            {
                "id": 300,
                "name": "PO-10482",
                "partner_id": [10, "Brightline"],
                "state": "purchase",
                "date_order": ts(3),
                "date_planned": ts(-14),
                "currency_id": [3, "GBP"],
                "amount_total": 9700.0,
                "picking_type_id": [7, "Leeds: Receipts"],
                "partner_ref": False,
                "write_date": ts(3),
            },
            {
                "id": 301,
                "name": "PO-10391",
                "partner_id": [11, "Kestrel"],
                "state": "purchase",
                "date_order": ts(12),
                "date_planned": ts(3),
                "currency_id": [3, "GBP"],
                "amount_total": 3120.0,
                "picking_type_id": [8, "Bristol: Receipts"],
                "partner_ref": False,
                "write_date": ts(12),
            },
        ],
        "purchase.order.line": [
            {
                "id": 1,
                "order_id": [300, "PO-10482"],
                "product_id": [100, "Gloves"],
                "product_qty": 2000,
                "qty_received": 0,
                "price_unit": 4.85,
                "date_planned": ts(-14),
            },
            {
                "id": 2,
                "order_id": [301, "PO-10391"],
                "product_id": [102, "Carton"],
                "product_qty": 4000,
                "qty_received": 4000,
                "price_unit": 0.78,
                "date_planned": ts(3),
            },
        ],
    }


def _present(fn: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    return lambda a, v: a is not None and fn(a, v)


OPS: dict[str, Callable[[Any, Any], bool]] = {
    "=": operator.eq,
    "!=": operator.ne,
    ">": _present(operator.gt),
    ">=": _present(operator.ge),
    "<": _present(operator.lt),
    "in": lambda a, v: a in v,
}


def _match(record: dict[str, Any], domain: list[Any]) -> bool:
    for field, op, value in domain:
        if field == "location_id.usage":
            actual: Any = record.get("location_usage")
        elif field == "order_id.date_order":
            actual = record.get("date_order")
        else:
            actual = record.get(field)
        if isinstance(actual, list):
            actual = actual[0] if actual else None
        ok = OPS[op](actual, value)
        if not ok:
            return False
    return True


class FakeOdoo:
    """`mode`: "json2" (Odoo 19+) or "jsonrpc" (Odoo 17/18: no /json/2 route)."""

    def __init__(
        self, mode: str = "jsonrpc", api_key: str = API_KEY, base: str = "https://odoo.test"
    ) -> None:
        self.mode = mode
        self.api_key = api_key
        self.base = base
        self.data = dataset()
        self.calls: list[tuple[str, str]] = []
        self.fail_with: int | None = None  # simulate an outage (HTTP status)
        self._next_id = 1000

    # --- shared model operations ---------------------------------------------------------------

    def _execute(self, model: str, method: str, kwargs: dict[str, Any], args: list[Any]) -> Any:
        self.calls.append((model, method))
        if method == "context_get":
            return {"lang": "en_GB", "tz": "Europe/London", "uid": 2}
        rows = self.data.get(model)
        if rows is None:
            raise KeyError(model)
        if method == "search_read":
            domain = kwargs.get("domain", args[0] if args else [])
            found = [r for r in rows if _match(r, domain)]
            found.sort(key=lambda r: r["id"])
            offset, limit = kwargs.get("offset", 0), kwargs.get("limit")
            found = found[offset : offset + limit if limit else None]
            fields = kwargs.get("fields")
            return [
                {"id": r["id"], **{f: deepcopy(r.get(f, False)) for f in fields}}
                if fields
                else deepcopy(r)
                for r in found
            ]
        if method == "create":
            vals_list = kwargs.get("vals_list", args[0] if args else [])
            ids = []
            for vals in vals_list:
                self._next_id += 1
                record = {
                    "id": self._next_id,
                    **vals,
                    "name": f"P{self._next_id:05d}",
                    "state": "draft",
                    "write_date": ts(),
                }
                rows.append(record)
                ids.append(self._next_id)
            return ids
        raise NotImplementedError(method)

    # --- HTTP ----------------------------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail_with:
            return httpx.Response(self.fail_with, text="Service Unavailable")
        path = request.url.path
        body = json.loads(request.content or b"{}")
        if path.startswith("/json/2/"):
            if self.mode != "json2":
                return httpx.Response(404, text="Not Found")
            if request.headers.get("authorization") != f"bearer {self.api_key}":
                return httpx.Response(
                    401, json={"name": "AccessDenied", "message": "Invalid apikey"}
                )
            _, _, model, method = path.strip("/").split("/", 3)
            try:
                return httpx.Response(200, json=self._execute(model, method, body, []))
            except KeyError:
                return httpx.Response(404, json={"name": "MissingError", "message": "model"})
        if path == "/jsonrpc":
            params = body["params"]
            service, method, args = params["service"], params["method"], params["args"]
            if service == "common" and method == "version":
                return self._ok(body, {"server_version": "17.0", "protocol_version": 1})
            if service == "common" and method == "authenticate":
                return self._ok(body, 2 if args[2] == self.api_key else False)
            if service == "object" and method == "execute_kw":
                _db, uid, key, model, meth, margs, mkwargs = args
                if key != self.api_key or uid != 2:
                    return self._err(body, "odoo.exceptions.AccessDenied", "Access Denied")
                try:
                    return self._ok(body, self._execute(model, meth, mkwargs, margs))
                except KeyError:
                    return self._err(body, "builtins.KeyError", model)
        return httpx.Response(404, text="Not Found")

    @staticmethod
    def _ok(body: dict[str, Any], result: Any) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    @staticmethod
    def _err(body: dict[str, Any], name: str, message: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": 200,
                    "message": "Odoo Server Error",
                    "data": {"name": name, "message": message},
                },
            },
        )
