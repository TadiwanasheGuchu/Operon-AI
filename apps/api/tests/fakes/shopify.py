"""Protocol-level Shopify GraphQL Admin API test server for the connector's operations."""

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

TOKEN = "shpat_test_token_0123456789"
WEBHOOK_SECRET = "shpss_test_secret_0123456789"
DOMAIN = "harbour-vale.myshopify.com"
NOW = datetime.now(UTC).replace(microsecond=0)


def gid(kind: str, n: int) -> str:
    return f"gid://shopify/{kind}/{n}"


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


class FakeShopify:
    def __init__(self) -> None:
        self.token = TOKEN
        self.throttle_next = 0
        self.locations = [
            {"id": gid("Location", 1), "name": "Online warehouse", "isActive": True},
            {"id": gid("Location", 2), "name": "Old shop", "isActive": False},
        ]
        # 150 variants so products span two pages of 100.
        self.variants = [
            {
                "id": gid("ProductVariant", i),
                "sku": f"SKU-{i:03d}",
                "displayName": f"Product {i}",
                "product": {"status": "ACTIVE" if i % 50 else "ARCHIVED"},
                "inventoryItem": {"unitCost": {"amount": "2.50", "currencyCode": "GBP"}},
            }
            for i in range(1, 151)
        ]
        self.levels = {
            gid("Location", 1): [
                {
                    "item": {"variant": {"id": gid("ProductVariant", 1)}},
                    "quantities": [
                        {"name": "on_hand", "quantity": 120},
                        {"name": "committed", "quantity": 7},
                    ],
                },
                {
                    "item": {"variant": {"id": gid("ProductVariant", 2)}},
                    "quantities": [
                        {"name": "on_hand", "quantity": 0},
                        {"name": "committed", "quantity": 0},
                    ],
                },
            ]
        }
        day1 = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        self.orders = [
            {
                "id": gid("Order", 1),
                "createdAt": day1,
                "cancelledAt": None,
                "lineItems": {
                    "nodes": [
                        {"quantity": 3, "variant": {"id": gid("ProductVariant", 1)}},
                        {"quantity": 1, "variant": {"id": gid("ProductVariant", 2)}},
                    ]
                },
            },
            {
                "id": gid("Order", 2),
                "createdAt": day1,
                "cancelledAt": None,
                "lineItems": {
                    "nodes": [
                        {"quantity": 2, "variant": {"id": gid("ProductVariant", 1)}},
                        {"quantity": 5, "variant": None},
                    ]
                },
            },
            {
                "id": gid("Order", 3),
                "createdAt": day1,
                "cancelledAt": day1,
                "lineItems": {
                    "nodes": [{"quantity": 50, "variant": {"id": gid("ProductVariant", 1)}}]
                },
            },
        ]

    @staticmethod
    def _page(nodes: list[Any], after: str | None, size: int) -> dict[str, Any]:
        start = int(after or 0)
        chunk = nodes[start : start + size]
        has_next = start + size < len(nodes)
        return {
            "nodes": chunk,
            "pageInfo": {
                "hasNextPage": has_next,
                "endCursor": str(start + size) if has_next else None,
            },
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != DOMAIN or not request.url.path.endswith("/graphql.json"):
            return httpx.Response(404)
        if request.headers.get("x-shopify-access-token") != self.token:
            return httpx.Response(401, json={"errors": "[API] Invalid API key or access token"})
        if self.throttle_next:
            self.throttle_next -= 1
            return httpx.Response(
                200,
                json={"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
            )
        body = json.loads(request.content)
        op = re.match(r"\s*query\s+(\w+)", body["query"]).group(1)  # type: ignore[union-attr]
        v = body.get("variables") or {}
        if op == "Shop":
            data: dict[str, Any] = {
                "shop": {"name": "Harbour & Vale", "currencyCode": "GBP", "myshopifyDomain": DOMAIN}
            }
        elif op == "Locations":
            data = {"locations": self._page(self.locations, v.get("after"), 50)}
        elif op == "Variants":
            data = {"productVariants": self._page(self.variants, v.get("after"), 100)}
        elif op == "Levels":
            data = {
                "location": {
                    "inventoryLevels": self._page(
                        self.levels.get(v["location"], []), v.get("after"), 100
                    )
                }
            }
        elif op == "Orders":
            data = {"orders": self._page(self.orders, v.get("after"), 50)}
        else:
            return httpx.Response(200, json={"errors": [{"message": f"unknown op {op}"}]})
        return httpx.Response(200, json={"data": data})
