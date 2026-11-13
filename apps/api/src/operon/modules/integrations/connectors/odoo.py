"""Odoo connector: inventory, purchasing and sales via Odoo's external API.

Two transports, chosen automatically (or pinned in settings):
- JSON-2 (Odoo 19+): POST {url}/json/2/{model}/{method}, API key as a bearer token.
- JSON-RPC (Odoo 17/18): POST {url}/jsonrpc, `common.authenticate` then `object.execute_kw`.

Data mapping (Odoo model → Operon):
  stock.warehouse → locations · res.partner (supplier_rank > 0) → suppliers
  product.product → products · product.supplierinfo → supplier terms
  stock.quant (internal locations, per warehouse) → stock snapshot
  sale.order (+ lines, confirmed) → daily sales · purchase.order (+ lines) → purchase orders
"""

from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import count
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field, SecretStr

from operon.modules.integrations.connectors.base import (
    AuthError,
    ConfigError,
    ConnectionCheck,
    ConnectorContext,
    Entity,
    LocationRecord,
    ProductRecord,
    ProtocolError,
    PurchaseOrderLineRecord,
    PurchaseOrderRecord,
    SalesRecord,
    StockRecord,
    SupplierProductRecord,
    SupplierRecord,
    TransientError,
    raise_for_http,
)

PAGE = 200
ODOO_DATETIME = "%Y-%m-%d %H:%M:%S"
REQUIRED_MODELS = {
    "stock.warehouse": ("locations", "stock"),
    "product.product": ("products",),
    "product.supplierinfo": ("supplier_products",),
    "res.partner": ("suppliers",),
    "stock.quant": ("stock",),
    "sale.order": ("sales",),
    "purchase.order": ("purchase_orders",),
}


class OdooConfig(BaseModel):
    url: str = Field(description="Base address, e.g. https://acme.odoo.com")
    database: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=320, description="Login of the API user")
    api_version: Literal["auto", "json2", "jsonrpc"] = "auto"


class OdooSecrets(BaseModel):
    api_key: SecretStr = Field(min_length=8, max_length=200)


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(str(value)[:19], ODOO_DATETIME).replace(tzinfo=UTC)


def _m2o(value: Any) -> tuple[str | None, str | None]:
    """Odoo many2one: [id, "Display name"] or False."""
    if isinstance(value, list) and value:
        return str(value[0]), str(value[1]) if len(value) > 1 else None
    return None, None


def _dec(value: Any) -> Decimal:
    return Decimal(str(value or 0))


class _Transport:
    async def call(self, model: str, method: str, **kwargs: Any) -> Any:
        raise NotImplementedError


class _Json2(_Transport):
    def __init__(self, http: httpx.AsyncClient, cfg: OdooConfig, key: str) -> None:
        self.http, self.cfg, self.key = http, cfg, key

    async def call(self, model: str, method: str, **kwargs: Any) -> Any:
        try:
            r = await self.http.post(
                f"{self.cfg.url}/json/2/{model}/{method}",
                json=kwargs,
                headers={
                    "Authorization": f"bearer {self.key}",
                    "X-Odoo-Database": self.cfg.database,
                },
            )
        except httpx.HTTPError as exc:
            raise TransientError(
                "Odoo could not be reached. Operon will retry.", detail=repr(exc)
            ) from exc
        raise_for_http(r, "Odoo")
        return r.json()


class _JsonRpc(_Transport):
    def __init__(self, http: httpx.AsyncClient, cfg: OdooConfig, key: str) -> None:
        self.http, self.cfg, self.key = http, cfg, key
        self.uid: int | None = None
        self._ids = count(1)

    async def _rpc(self, service: str, method: str, args: list[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "id": next(self._ids),
            "params": {"service": service, "method": method, "args": args},
        }
        try:
            r = await self.http.post(f"{self.cfg.url}/jsonrpc", json=payload)
        except httpx.HTTPError as exc:
            raise TransientError(
                "Odoo could not be reached. Operon will retry.", detail=repr(exc)
            ) from exc
        raise_for_http(r, "Odoo")
        body = r.json()
        if "error" in body:
            err = body["error"]
            data = err.get("data") or {}
            name = str(data.get("name", ""))
            if "AccessDenied" in name or "AccessError" in name:
                raise AuthError(
                    "Odoo denied access. Check the user's permissions and API key.",
                    detail=str(data.get("message")),
                )
            raise ProtocolError(
                "Odoo returned an error for a request.",
                detail=f"{name}: {data.get('message') or err.get('message')}",
            )
        return body.get("result")

    async def version(self) -> dict[str, Any]:
        return dict(await self._rpc("common", "version", []))

    async def authenticate(self) -> int:
        uid = await self._rpc(
            "common", "authenticate", [self.cfg.database, self.cfg.username, self.key, {}]
        )
        if not uid:
            raise AuthError("Odoo rejected the username or API key.")
        self.uid = int(uid)
        return self.uid

    async def call(self, model: str, method: str, **kwargs: Any) -> Any:
        if self.uid is None:
            await self.authenticate()
        args: list[Any] = []
        if method in ("search_read", "search_count", "search"):
            args = [kwargs.pop("domain", [])]
        elif method in ("read", "write"):
            args = [kwargs.pop("ids")] + ([kwargs.pop("vals")] if method == "write" else [])
        elif method == "create":
            args = [kwargs.pop("vals_list")]
        return await self._rpc(
            "object",
            "execute_kw",
            [self.cfg.database, self.uid, self.key, model, method, args, kwargs],
        )


class OdooConnector:
    key: ClassVar[str] = "odoo"
    name: ClassVar[str] = "Odoo"
    description: ClassVar[str] = (
        "Inventory, purchasing and sales from Odoo 17 or later (Community or Enterprise)."
    )
    config_model: ClassVar[type[BaseModel]] = OdooConfig
    secrets_model: ClassVar[type[BaseModel]] = OdooSecrets
    supports_webhooks: ClassVar[bool] = False

    def __init__(self, ctx: ConnectorContext) -> None:
        self.cfg: OdooConfig = ctx.config  # type: ignore[assignment]
        self.key_value = ctx.secrets.api_key.get_secret_value()  # type: ignore[attr-defined]
        self.http = ctx.http
        self._transport: _Transport | None = None
        self._currency: str | None = None

    async def _t(self) -> _Transport:
        if self._transport is not None:
            return self._transport
        mode = self.cfg.api_version
        if mode in ("auto", "json2"):
            j2 = _Json2(self.http, self.cfg, self.key_value)
            try:
                await j2.call("res.users", "context_get")
                self._transport = j2
                return j2
            except ConfigError:
                if mode == "json2":
                    raise
        rpc = _JsonRpc(self.http, self.cfg, self.key_value)
        await rpc.authenticate()
        self._transport = rpc
        return rpc

    async def _read_all(
        self, model: str, domain: list[Any], fields: list[str], order: str = "id"
    ) -> AsyncIterator[list[dict[str, Any]]]:
        t = await self._t()
        offset = 0
        while True:
            rows = await t.call(
                model,
                "search_read",
                domain=domain,
                fields=fields,
                limit=PAGE,
                offset=offset,
                order=order,
            )
            if not isinstance(rows, list):
                raise ProtocolError("Odoo returned an unexpected response.", detail=str(rows)[:200])
            if rows:
                yield rows
            if len(rows) < PAGE:
                return
            offset += PAGE

    async def _company_currency(self) -> str | None:
        if self._currency is None:
            t = await self._t()
            rows = await t.call(
                "res.company", "search_read", domain=[], fields=["currency_id"], limit=1
            )
            self._currency = _m2o(rows[0]["currency_id"])[1] if rows else None
        return self._currency

    # --- check ---------------------------------------------------------------------------------

    async def check(self) -> ConnectionCheck:
        t = await self._t()
        installed = await t.call(
            "ir.model",
            "search_read",
            domain=[["model", "in", list(REQUIRED_MODELS)]],
            fields=["model"],
        )
        models = {row["model"] for row in installed}
        caps: list[Entity] = []
        for model, entities in REQUIRED_MODELS.items():
            if model in models:
                caps += [e for e in entities if e not in caps]  # type: ignore[misc]
        if "stock.quant" not in models:
            raise ConfigError(
                "Odoo's Inventory app isn't installed for this database, so there's "
                "no stock to monitor."
            )
        transport = "JSON-2" if isinstance(t, _Json2) else "JSON-RPC"
        version = ""
        if isinstance(t, _JsonRpc):
            version = str((await t.version()).get("server_version", ""))
        ordered = tuple(
            e
            for e in (
                "locations",
                "suppliers",
                "products",
                "supplier_products",
                "stock",
                "sales",
                "purchase_orders",
            )
            if e in caps
        )
        summary = f"Odoo {version} · database {self.cfg.database} · {transport}".replace(
            "Odoo  ·", "Odoo ·"
        )
        missing = sorted(set(REQUIRED_MODELS) - models)
        return ConnectionCheck(
            summary=summary,
            capabilities=ordered,
            details={"transport": transport, "missing_models": missing},
        )

    # --- fetch ---------------------------------------------------------------------------------

    def fetch(
        self, entity: Entity, *, since: datetime | None, sales_from: date | None = None
    ) -> AsyncIterator[list[Any]]:
        handler = {
            "locations": self._locations,
            "suppliers": self._suppliers,
            "products": self._products,
            "supplier_products": self._supplier_products,
            "stock": self._stock,
            "sales": self._sales,
            "purchase_orders": self._purchase_orders,
        }[entity]
        return handler(since, sales_from)

    @staticmethod
    def _changed(since: datetime | None) -> list[Any]:
        return [["write_date", ">", since.strftime(ODOO_DATETIME)]] if since else []

    async def _locations(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        async for rows in self._read_all("stock.warehouse", [], ["id", "name", "code"]):
            yield [LocationRecord(str(r["id"]), r["name"], r.get("code") or None) for r in rows]

    async def _suppliers(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        domain = [["supplier_rank", ">", 0], *self._changed(since)]
        async for rows in self._read_all("res.partner", domain, ["id", "name", "email", "active"]):
            yield [
                SupplierRecord(
                    str(r["id"]), r["name"], r.get("email") or None, bool(r.get("active", True))
                )
                for r in rows
            ]

    async def _products(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        currency = await self._company_currency()
        domain = [["type", "in", ["consu", "product"]], *self._changed(since)]
        fields = ["id", "default_code", "name", "uom_id", "standard_price", "active"]
        async for rows in self._read_all("product.product", domain, fields):
            yield [
                ProductRecord(
                    external_id=str(r["id"]),
                    name=r["name"],
                    sku=r.get("default_code") or None,
                    uom=_m2o(r.get("uom_id"))[1],
                    unit_cost=_dec(r.get("standard_price")),
                    currency=currency,
                    active=bool(r.get("active", True)),
                )
                for r in rows
            ]

    async def _supplier_products(
        self, since: datetime | None, _: date | None
    ) -> AsyncIterator[list[Any]]:
        t = await self._t()
        fields = [
            "id",
            "partner_id",
            "product_id",
            "product_tmpl_id",
            "min_qty",
            "price",
            "delay",
            "currency_id",
        ]
        async for rows in self._read_all("product.supplierinfo", self._changed(since), fields):
            # Terms set on a product template apply to each of its variants.
            templates = {_m2o(r["product_tmpl_id"])[0] for r in rows if not r.get("product_id")}
            variants: dict[str, list[str]] = defaultdict(list)
            if templates - {None}:
                for v in await t.call(
                    "product.product",
                    "search_read",
                    domain=[["product_tmpl_id", "in", [int(x) for x in templates if x]]],
                    fields=["id", "product_tmpl_id"],
                ):
                    variants[str(_m2o(v["product_tmpl_id"])[0])].append(str(v["id"]))
            out = []
            for r in rows:
                supplier = _m2o(r["partner_id"])[0]
                if not supplier:
                    continue
                product = _m2o(r.get("product_id"))[0]
                targets = (
                    [product] if product else variants.get(str(_m2o(r["product_tmpl_id"])[0]), [])
                )
                for pid in targets:
                    out.append(
                        SupplierProductRecord(
                            external_id=f"{r['id']}:{pid}",
                            supplier_external_id=supplier,
                            product_external_id=str(pid),
                            lead_time_days=int(r.get("delay") or 0),
                            min_quantity=_dec(r.get("min_qty")),
                            price=_dec(r.get("price")),
                            currency=_m2o(r.get("currency_id"))[1],
                        )
                    )
            yield out

    async def _stock(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        totals: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
        domain = [["location_id.usage", "=", "internal"]]
        fields = ["product_id", "warehouse_id", "quantity", "reserved_quantity"]
        async for rows in self._read_all("stock.quant", domain, fields):
            for r in rows:
                product, warehouse = _m2o(r["product_id"])[0], _m2o(r.get("warehouse_id"))[0]
                if product and warehouse:
                    totals[(product, warehouse)][0] += _dec(r.get("quantity"))
                    totals[(product, warehouse)][1] += _dec(r.get("reserved_quantity"))
        yield [StockRecord(p, w, on_hand=v[0], reserved=v[1]) for (p, w), v in totals.items()]

    async def _sales(
        self, since: datetime | None, sales_from: date | None
    ) -> AsyncIterator[list[Any]]:
        t = await self._t()
        start = sales_from or (datetime.now(UTC) - timedelta(days=90)).date()
        domain = [
            ["state", "in", ["sale", "done"]],
            ["date_order", ">=", f"{start.isoformat()} 00:00:00"],
        ]
        totals: dict[tuple[str, str | None, date], Decimal] = defaultdict(Decimal)
        async for orders in self._read_all(
            "sale.order", domain, ["id", "date_order", "warehouse_id"]
        ):
            by_id = {o["id"]: o for o in orders}
            lines = await t.call(
                "sale.order.line",
                "search_read",
                domain=[["order_id", "in", list(by_id)]],
                fields=["order_id", "product_id", "product_uom_qty"],
            )
            for line in lines:
                order = by_id.get(int(_m2o(line["order_id"])[0] or 0))
                product = _m2o(line.get("product_id"))[0]
                when = _dt(order["date_order"]) if order else None
                if not order or not product or not when:
                    continue
                key = (product, _m2o(order.get("warehouse_id"))[0], when.date())
                totals[key] += _dec(line.get("product_uom_qty"))
        yield [SalesRecord(p, d, q, location_external_id=w) for (p, w, d), q in totals.items()]

    async def _purchase_orders(
        self, since: datetime | None, _: date | None
    ) -> AsyncIterator[list[Any]]:
        t = await self._t()
        types = await t.call(
            "stock.picking.type",
            "search_read",
            domain=[["code", "=", "incoming"]],
            fields=["id", "warehouse_id"],
        )
        warehouse_of = {str(p["id"]): _m2o(p.get("warehouse_id"))[0] for p in types}
        fields = [
            "id",
            "name",
            "partner_id",
            "state",
            "date_order",
            "date_planned",
            "currency_id",
            "amount_total",
            "picking_type_id",
        ]
        async for orders in self._read_all("purchase.order", self._changed(since), fields):
            lines = await t.call(
                "purchase.order.line",
                "search_read",
                domain=[["order_id", "in", [o["id"] for o in orders]]],
                fields=[
                    "id",
                    "order_id",
                    "product_id",
                    "product_qty",
                    "qty_received",
                    "price_unit",
                    "date_planned",
                ],
            )
            by_order: dict[int, list[PurchaseOrderLineRecord]] = defaultdict(list)
            for ln in lines:
                by_order[int(_m2o(ln["order_id"])[0] or 0)].append(
                    PurchaseOrderLineRecord(
                        external_id=str(ln["id"]),
                        product_external_id=_m2o(ln.get("product_id"))[0],
                        quantity=_dec(ln.get("product_qty")),
                        received_quantity=_dec(ln.get("qty_received")),
                        unit_price=_dec(ln.get("price_unit")),
                        expected_at=_dt(ln.get("date_planned")),
                    )
                )
            out = []
            for o in orders:
                order_lines = tuple(by_order.get(o["id"], []))
                out.append(
                    PurchaseOrderRecord(
                        external_id=str(o["id"]),
                        number=o["name"],
                        status=self._po_status(o["state"], order_lines),
                        supplier_external_id=_m2o(o.get("partner_id"))[0],
                        location_external_id=warehouse_of.get(
                            str(_m2o(o.get("picking_type_id"))[0])
                        ),
                        ordered_at=_dt(o.get("date_order")),
                        expected_at=_dt(o.get("date_planned")),
                        currency=_m2o(o.get("currency_id"))[1],
                        total=_dec(o.get("amount_total")),
                        lines=order_lines,
                    )
                )
            yield out

    @staticmethod
    def _po_status(state: str, lines: tuple[PurchaseOrderLineRecord, ...]) -> Any:
        if state == "cancel":
            return "cancelled"
        if state in ("draft", "sent", "to approve"):
            return "draft"
        if state == "done" or (lines and all(ln.received_quantity >= ln.quantity for ln in lines)):
            return "received"
        return "open"

    # --- actions (used by approval workflows, Phase 5) -----------------------------------------

    async def create_draft_purchase_order(
        self,
        *,
        supplier_external_id: str,
        product_external_id: str,
        quantity: Decimal,
        unit_price: Decimal | None,
        idempotency_key: str,
    ) -> str:
        """Create an RFQ (draft purchase order) in Odoo. A person confirms it there.

        Idempotent: the key is stored in `partner_ref`; a retry finds the existing order.
        """
        t = await self._t()
        existing = await t.call(
            "purchase.order",
            "search_read",
            domain=[["partner_ref", "=", idempotency_key]],
            fields=["id"],
            limit=1,
        )
        if existing:
            return str(existing[0]["id"])
        line: dict[str, Any] = {
            "product_id": int(product_external_id),
            "product_qty": float(quantity),
        }
        if unit_price is not None:
            line["price_unit"] = float(unit_price)
        created = await t.call(
            "purchase.order",
            "create",
            vals_list=[
                {
                    "partner_id": int(supplier_external_id),
                    "partner_ref": idempotency_key,
                    "order_line": [[0, 0, line]],
                }
            ],
        )
        ids = created if isinstance(created, list) else [created]
        return str(ids[0])

    async def get_purchase_order(self, external_id: str) -> dict[str, Any] | None:
        """Read back an order: its reference (e.g. P00042), state and supplier reference."""
        t = await self._t()
        rows = await t.call(
            "purchase.order",
            "search_read",
            domain=[["id", "=", int(external_id)]],
            fields=["name", "state", "partner_ref"],
            limit=1,
        )
        return dict(rows[0]) if rows else None
