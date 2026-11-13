"""Connector logic that doesn't need a server."""

from decimal import Decimal

from operon.modules.integrations.connectors.base import PurchaseOrderLineRecord
from operon.modules.integrations.connectors.odoo import OdooConnector
from operon.modules.integrations.connectors.shopify import ShopifyConnector, ShopifySecrets
from tests.fakes.shopify import WEBHOOK_SECRET, sign


def line(qty: int, received: int) -> PurchaseOrderLineRecord:
    return PurchaseOrderLineRecord("1", "p", Decimal(qty), Decimal(received))


def test_odoo_purchase_order_status_mapping() -> None:
    assert OdooConnector._po_status("draft", ()) == "draft"
    assert OdooConnector._po_status("to approve", ()) == "draft"
    assert OdooConnector._po_status("cancel", (line(5, 0),)) == "cancelled"
    assert OdooConnector._po_status("purchase", (line(5, 2),)) == "open"
    assert OdooConnector._po_status("purchase", (line(5, 5),)) == "received"
    assert OdooConnector._po_status("done", (line(5, 0),)) == "received"


def test_shopify_webhook_verification() -> None:
    secrets = ShopifySecrets(access_token="shpat_xxxxxxxxxx", webhook_secret=WEBHOOK_SECRET)
    body = b'{"id": 1}'
    headers = {
        "x-shopify-hmac-sha256": sign(body),
        "x-shopify-webhook-id": "w1",
        "x-shopify-topic": "orders/create",
    }
    event = ShopifyConnector.verify_webhook(headers, body, secrets)
    assert event is not None
    assert (event.source_event_id, event.topic) == ("w1", "orders/create")
    assert ShopifyConnector.verify_webhook(headers, body + b" ", secrets) is None
    assert (
        ShopifyConnector.verify_webhook({**headers, "x-shopify-webhook-id": ""}, body, secrets)
        is None
    )
    no_secret = ShopifySecrets(access_token="shpat_xxxxxxxxxx")
    assert ShopifyConnector.verify_webhook(headers, body, no_secret) is None
