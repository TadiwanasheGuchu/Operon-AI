"""Shopify connector: locations, product variants, stock per location and daily sales.

Uses the GraphQL Admin API with the shop's admin API access token (a custom app created in the
merchant's admin; ADR 0010). Webhooks are verified with HMAC-SHA256 over the raw body using the
app's API secret key, and only trigger an incremental sync.
"""

import base64
import hashlib
import hmac
import re
from collections import defaultdict
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field, SecretStr, field_validator

from operon.modules.integrations.connectors.base import (
    AuthError,
    ConnectionCheck,
    ConnectorContext,
    Entity,
    LocationRecord,
    ProductRecord,
    ProtocolError,
    SalesRecord,
    StockRecord,
    TransientError,
    WebhookEvent,
    raise_for_http,
)

API_VERSION = "2025-10"
SHOP_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$")
RELEVANT_TOPICS = {
    "orders/create",
    "orders/updated",
    "orders/cancelled",
    "inventory_levels/update",
    "products/create",
    "products/update",
    "locations/update",
}


class ShopifyConfig(BaseModel):
    shop_domain: str = Field(description="your-store.myshopify.com")

    @field_validator("shop_domain")
    @classmethod
    def _domain(cls, value: str) -> str:
        value = value.strip().lower().removeprefix("https://").removesuffix("/")
        if not SHOP_DOMAIN.match(value):
            raise ValueError("Use the store's myshopify.com address, e.g. acme.myshopify.com.")
        return value


class ShopifySecrets(BaseModel):
    access_token: SecretStr = Field(min_length=10, max_length=200)
    # API secret key of the custom app; needed only to verify webhooks.
    webhook_secret: SecretStr | None = Field(default=None, min_length=10, max_length=200)


def _gid(value: str) -> str:
    return value.rsplit("/", 1)[-1]


Q_SHOP = "query Shop { shop { name currencyCode myshopifyDomain } }"
Q_LOCATIONS = """query Locations($after: String) {
  locations(first: 50, after: $after) { nodes { id name isActive } pageInfo { hasNextPage endCursor } } }"""
Q_VARIANTS = """query Variants($after: String, $query: String) {
  productVariants(first: 100, after: $after, query: $query) {
    nodes { id sku displayName product { status } inventoryItem { unitCost { amount currencyCode } } }
    pageInfo { hasNextPage endCursor } } }"""
Q_LEVELS = """query Levels($location: ID!, $after: String) {
  location(id: $location) { inventoryLevels(first: 100, after: $after) {
    nodes { item { variant { id } } quantities(names: ["on_hand", "committed"]) { name quantity } }
    pageInfo { hasNextPage endCursor } } } }"""
Q_ORDERS = """query Orders($after: String, $query: String) {
  orders(first: 50, after: $after, query: $query) {
    nodes { id createdAt cancelledAt lineItems(first: 100) { nodes { quantity variant { id } } } }
    pageInfo { hasNextPage endCursor } } }"""


class ShopifyConnector:
    key: ClassVar[str] = "shopify"
    name: ClassVar[str] = "Shopify"
    description: ClassVar[str] = (
        "Sales orders, products and stock per location from a Shopify store."
    )
    config_model: ClassVar[type[BaseModel]] = ShopifyConfig
    secrets_model: ClassVar[type[BaseModel]] = ShopifySecrets
    supports_webhooks: ClassVar[bool] = True

    def __init__(self, ctx: ConnectorContext) -> None:
        self.cfg: ShopifyConfig = ctx.config  # type: ignore[assignment]
        self.secrets: ShopifySecrets = ctx.secrets  # type: ignore[assignment]
        self.http = ctx.http

    async def _gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            r = await self.http.post(
                f"https://{self.cfg.shop_domain}/admin/api/{API_VERSION}/graphql.json",
                json={"query": query, "variables": variables or {}},
                headers={"X-Shopify-Access-Token": self.secrets.access_token.get_secret_value()},
            )
        except httpx.HTTPError as exc:
            raise TransientError(
                "Shopify could not be reached. Operon will retry.", detail=repr(exc)
            ) from exc
        raise_for_http(r, "Shopify")
        body = r.json()
        errors = body.get("errors")
        if errors:
            codes = (
                {str((e.get("extensions") or {}).get("code", "")) for e in errors}
                if isinstance(errors, list)
                else set()
            )
            if "THROTTLED" in codes:
                raise TransientError("Shopify is rate limiting requests. Operon will retry.")
            if "ACCESS_DENIED" in codes:
                raise AuthError(
                    "The Shopify app is missing a permission (scope). Check its "
                    "read_products, read_inventory, read_locations and read_orders scopes.",
                    detail=str(errors)[:300],
                )
            raise ProtocolError(
                "Shopify returned an error for a request.", detail=str(errors)[:300]
            )
        return dict(body.get("data") or {})

    async def _pages(
        self, query: str, path: str, variables: dict[str, Any]
    ) -> AsyncIterator[list[dict[str, Any]]]:
        after = None
        while True:
            data = await self._gql(query, {**variables, "after": after})
            node: Any = data
            for key in path.split("."):
                node = (node or {}).get(key)
            if node is None:
                return
            yield list(node.get("nodes") or [])
            info = node.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                return
            after = info.get("endCursor")

    async def check(self) -> ConnectionCheck:
        shop = (await self._gql(Q_SHOP)).get("shop") or {}
        if not shop:
            raise ProtocolError("Shopify returned no shop details.")
        return ConnectionCheck(
            summary=f"Shopify · {shop.get('name')} · {shop.get('myshopifyDomain')}",
            capabilities=("locations", "products", "stock", "sales"),
            details={"currency": shop.get("currencyCode")},
        )

    def fetch(
        self, entity: Entity, *, since: datetime | None, sales_from: date | None = None
    ) -> AsyncIterator[list[Any]]:
        handlers = {
            "locations": self._locations,
            "products": self._products,
            "stock": self._stock,
            "sales": self._sales,
        }
        if entity not in handlers:
            raise ProtocolError(f"Shopify doesn't provide {entity}.")
        return handlers[entity](since, sales_from)

    async def _locations(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        async for nodes in self._pages(Q_LOCATIONS, "locations", {}):
            yield [
                LocationRecord(_gid(n["id"]), n["name"]) for n in nodes if n.get("isActive", True)
            ]

    async def _products(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        query = f"updated_at:>'{since.isoformat()}'" if since else None
        async for nodes in self._pages(Q_VARIANTS, "productVariants", {"query": query}):
            out = []
            for n in nodes:
                cost = (n.get("inventoryItem") or {}).get("unitCost") or {}
                out.append(
                    ProductRecord(
                        external_id=_gid(n["id"]),
                        name=n.get("displayName") or n["id"],
                        sku=n.get("sku") or None,
                        unit_cost=Decimal(str(cost["amount"]))
                        if cost.get("amount") is not None
                        else None,
                        currency=cost.get("currencyCode"),
                        active=(n.get("product") or {}).get("status", "ACTIVE") == "ACTIVE",
                    )
                )
            yield out

    async def _stock(self, since: datetime | None, _: date | None) -> AsyncIterator[list[Any]]:
        locations: list[str] = []
        async for nodes in self._pages(Q_LOCATIONS, "locations", {}):
            locations += [n["id"] for n in nodes if n.get("isActive", True)]
        for loc in locations:
            async for nodes in self._pages(Q_LEVELS, "location.inventoryLevels", {"location": loc}):
                out = []
                for n in nodes:
                    variant = ((n.get("item") or {}).get("variant") or {}).get("id")
                    if not variant:
                        continue
                    q = {x["name"]: Decimal(str(x["quantity"])) for x in n.get("quantities") or []}
                    out.append(
                        StockRecord(
                            _gid(variant),
                            _gid(loc),
                            on_hand=q.get("on_hand", Decimal(0)),
                            reserved=q.get("committed", Decimal(0)),
                        )
                    )
                yield out

    async def _sales(
        self, since: datetime | None, sales_from: date | None
    ) -> AsyncIterator[list[Any]]:
        start = sales_from or (datetime.now(UTC) - timedelta(days=90)).date()
        totals: dict[tuple[str, date], Decimal] = defaultdict(Decimal)
        query = f"created_at:>='{start.isoformat()}' status:any"
        async for nodes in self._pages(Q_ORDERS, "orders", {"query": query}):
            for order in nodes:
                if order.get("cancelledAt"):
                    continue
                day = datetime.fromisoformat(order["createdAt"].replace("Z", "+00:00")).date()
                for item in (order.get("lineItems") or {}).get("nodes") or []:
                    variant = (item.get("variant") or {}).get("id")
                    if variant:
                        totals[(_gid(variant), day)] += Decimal(str(item.get("quantity") or 0))
        yield [SalesRecord(p, d, q) for (p, d), q in totals.items()]

    # --- webhooks ------------------------------------------------------------------------------

    @staticmethod
    def verify_webhook(
        headers: Mapping[str, str], body: bytes, secrets: BaseModel
    ) -> WebhookEvent | None:
        """Return the event if the signature is valid, else None. Constant-time comparison."""
        secret = getattr(secrets, "webhook_secret", None)
        signature = headers.get("x-shopify-hmac-sha256", "")
        if secret is None or not signature:
            return None
        expected = base64.b64encode(
            hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).digest()
        ).decode()
        if not hmac.compare_digest(expected, signature):
            return None
        event_id = headers.get("x-shopify-webhook-id") or headers.get("x-shopify-event-id")
        topic = headers.get("x-shopify-topic", "")
        if not event_id:
            return None
        return WebhookEvent(source_event_id=event_id[:200], topic=topic[:100])

    @staticmethod
    def is_relevant(topic: str) -> bool:
        return topic in RELEVANT_TOPICS
