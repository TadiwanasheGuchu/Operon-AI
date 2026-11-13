"""Connector contract: every external system implements this; sync code depends only on it."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal, Protocol

import httpx
from pydantic import BaseModel

Entity = Literal[
    "locations", "suppliers", "products", "supplier_products", "stock", "sales", "purchase_orders"
]
# Dependency order: later entities reference earlier ones.
SYNC_ORDER: tuple[Entity, ...] = (
    "locations",
    "suppliers",
    "products",
    "supplier_products",
    "stock",
    "sales",
    "purchase_orders",
)


class ConnectorError(Exception):
    """Base for failures talking to an external system. `user_message` is safe to show."""

    retryable = False

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail  # for logs only, never shown or stored


class AuthError(ConnectorError):
    """Credentials rejected: needs a person to fix them (connection → action_required)."""


class ConfigError(ConnectorError):
    """Settings are wrong or a required module/permission is missing."""


class TransientError(ConnectorError):
    """Network trouble, timeouts, rate limits, 5xx: safe to retry."""

    retryable = True


class ProtocolError(ConnectorError):
    """The system answered with something we don't understand."""


# --- canonical records (connector output) ------------------------------------------------------


@dataclass(frozen=True)
class LocationRecord:
    external_id: str
    name: str
    code: str | None = None


@dataclass(frozen=True)
class SupplierRecord:
    external_id: str
    name: str
    email: str | None = None
    active: bool = True


@dataclass(frozen=True)
class ProductRecord:
    external_id: str
    name: str
    sku: str | None = None
    uom: str | None = None
    unit_cost: Decimal | None = None
    currency: str | None = None
    active: bool = True


@dataclass(frozen=True)
class SupplierProductRecord:
    external_id: str
    supplier_external_id: str
    product_external_id: str
    lead_time_days: int | None = None
    min_quantity: Decimal | None = None
    price: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True)
class StockRecord:
    product_external_id: str
    location_external_id: str
    on_hand: Decimal
    reserved: Decimal = Decimal(0)


@dataclass(frozen=True)
class SalesRecord:
    product_external_id: str
    day: date
    quantity: Decimal
    location_external_id: str | None = None


@dataclass(frozen=True)
class PurchaseOrderLineRecord:
    external_id: str
    product_external_id: str | None
    quantity: Decimal
    received_quantity: Decimal = Decimal(0)
    unit_price: Decimal | None = None
    expected_at: datetime | None = None


@dataclass(frozen=True)
class PurchaseOrderRecord:
    external_id: str
    number: str
    status: Literal["draft", "open", "received", "cancelled"]
    supplier_external_id: str | None = None
    location_external_id: str | None = None
    ordered_at: datetime | None = None
    expected_at: datetime | None = None
    currency: str | None = None
    total: Decimal | None = None
    lines: tuple[PurchaseOrderLineRecord, ...] = ()


@dataclass(frozen=True)
class ConnectionCheck:
    summary: str  # e.g. "Odoo 18.0 · database acme · signed in as api@acme.example"
    capabilities: tuple[Entity, ...]
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookEvent:
    source_event_id: str
    topic: str


# How entities are synchronised: incremental entities use a cursor; snapshots replace the
# connection's rows for that entity; windowed entities replace the trailing N days.
SNAPSHOT_ENTITIES: frozenset[Entity] = frozenset({"stock"})
WINDOWED_ENTITIES: frozenset[Entity] = frozenset({"sales"})


class Connector(Protocol):
    key: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]
    secrets_model: ClassVar[type[BaseModel]]
    supports_webhooks: ClassVar[bool]

    async def check(self) -> ConnectionCheck: ...

    def fetch(
        self, entity: Entity, *, since: datetime | None, sales_from: date | None = None
    ) -> AsyncIterator[list[Any]]: ...


@dataclass
class ConnectorContext:
    """What a connector instance needs: validated settings, decrypted secrets, an HTTP client."""

    config: BaseModel
    secrets: BaseModel
    http: httpx.AsyncClient


def raise_for_http(response: httpx.Response, system: str) -> None:
    """Map HTTP failures to connector errors with safe, actionable messages."""
    status = response.status_code
    if status in (401, 403):
        raise AuthError(
            f"{system} rejected the credentials. Check the key and its permissions.",
            detail=response.text[:300],
        )
    if status == 404:
        raise ConfigError(
            f"{system} couldn't find that address. Check the URL.", detail=response.text[:300]
        )
    if status == 429 or status >= 500:
        raise TransientError(
            f"{system} is busy or unavailable. Operon will retry.",
            detail=f"HTTP {status}: {response.text[:300]}",
        )
    if status >= 400:
        raise ProtocolError(
            f"{system} refused the request (HTTP {status}).", detail=response.text[:300]
        )
