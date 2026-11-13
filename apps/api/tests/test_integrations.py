"""Integrations: connecting, syncing into canonical tables, failures, credentials, webhooks."""

import json
from typing import Any

from sqlalchemy import text

from tests.conftest import Api, Fakes
from tests.fakes.odoo import API_KEY
from tests.fakes.shopify import DOMAIN, TOKEN, WEBHOOK_SECRET, sign
from tests.helpers import error_code, invite_and_join

ODOO: dict[str, Any] = {
    "connector": "odoo",
    "name": "Odoo production",
    "config": {"url": "https://odoo.test", "database": "acme", "username": "api@acme.example"},
    "secrets": {"api_key": API_KEY},
}
SHOPIFY: dict[str, Any] = {
    "connector": "shopify",
    "name": "Web store",
    "config": {"shop_domain": DOMAIN},
    "secrets": {"access_token": TOKEN, "webhook_secret": WEBHOOK_SECRET},
}


def counts(engine: Any, connection_id: str) -> dict[str, int]:
    out = {}
    with engine.connect() as conn:
        for table in [
            "locations",
            "suppliers",
            "products",
            "supplier_products",
            "stock_levels",
            "sales_daily",
            "purchase_orders",
            "purchase_order_lines",
        ]:
            out[table] = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE connection_id = :c"), {"c": connection_id}
            ).scalar()
    return out


async def connect(api: Api, body: dict[str, Any]) -> dict[str, Any]:
    r = await api.post("/integrations", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_catalogue_is_honest_about_verification(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    catalogue = {c["key"]: c for c in (await iapi.get("/integrations/catalogue")).json()}
    assert set(catalogue) == {"odoo", "shopify", "csv"}
    assert catalogue["csv"]["verified_live"] is True
    assert catalogue["odoo"]["verified_live"] is False
    assert "Not yet verified against a live Odoo" in catalogue["odoo"]["verification_note"]
    secret_fields = {f["name"] for f in catalogue["odoo"]["fields"] if f["secret"]}
    assert secret_fields == {"api_key"}


async def test_odoo_initial_sync_fills_canonical_tables(
    iapi: Api, fakes: Fakes, owner_engine: Any
) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    assert conn["status"] == "active"
    [job] = (await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()
    assert job["trigger"] == "initial"
    assert job["status"] == "succeeded", job
    assert counts(owner_engine, conn["id"]) == {
        "locations": 2,
        "suppliers": 2,
        "products": 3,  # service products excluded
        "supplier_products": 2,
        "stock_levels": 2,
        "sales_daily": 2,
        "purchase_orders": 2,
        "purchase_order_lines": 2,
    }
    with owner_engine.connect() as c:
        # Quants are summed per product and warehouse; non-internal locations excluded.
        leeds = c.execute(
            text(
                "SELECT s.on_hand, s.reserved FROM stock_levels s JOIN products p ON p.id = s.product_id "
                "WHERE p.sku = 'HV-GLV-220' AND s.connection_id = :c"
            ),
            {"c": conn["id"]},
        ).one()
        assert (float(leeds[0]), float(leeds[1])) == (1240.0, 40.0)
        # Confirmed orders only, within the 90-day window, summed per day.
        gloves = c.execute(
            text(
                "SELECT sum(sd.quantity) FROM sales_daily sd JOIN products p ON p.id = sd.product_id "
                "WHERE p.sku = 'HV-GLV-220' AND sd.connection_id = :c"
            ),
            {"c": conn["id"]},
        ).scalar()
        assert float(gloves) == 186.0
        # Template-level supplier terms map onto the variant; lead times kept.
        lead = c.execute(
            text(
                "SELECT sp.lead_time_days FROM supplier_products sp JOIN products p ON p.id = sp.product_id "
                "WHERE p.sku = 'CTN-600'"
            )
        ).scalar()
        assert lead == 5
        statuses = dict(
            c.execute(
                text("SELECT number, status FROM purchase_orders WHERE connection_id = :c"),
                {"c": conn["id"]},
            ).all()
        )
        assert statuses == {"PO-10482": "open", "PO-10391": "received"}


async def test_odoo_json2_transport(iapi: Api, fakes: Fakes) -> None:
    fakes.odoo.mode = "json2"
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    check = (await iapi.post(f"/integrations/{conn['id']}/test")).json()
    assert check["ok"] is True
    assert "JSON-2" in check["summary"]
    assert "stock" in check["provides"]


async def test_rejected_credentials_are_never_stored(iapi: Api, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    r = await iapi.post("/integrations", json={**ODOO, "secrets": {"api_key": "wrong-key-123456"}})
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "Odoo rejected the username or API key."
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM integration_connections")).scalar() == 0


async def test_credentials_are_encrypted_and_never_returned(iapi: Api, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    for path in ["/integrations", f"/integrations/{conn['id']}"]:
        assert API_KEY not in (await iapi.get(path)).text
    with owner_engine.connect() as c:
        stored = c.execute(
            text("SELECT secret_encrypted FROM integration_credentials")
        ).scalar_one()
    assert API_KEY not in stored
    assert stored.startswith("v1:")


async def test_private_and_insecure_addresses_are_refused(api_factory: Any, fakes: Fakes) -> None:
    from operon.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(allow_private_integration_hosts=False))
    async with api_factory(app) as api:
        await api.sign_up("owner@acme.example")
        for url, needle in [
            ("http://odoo.example.com", "https"),
            ("https://127.0.0.1", "private"),
            ("https://169.254.169.254", "private"),
            ("https://user:pw@odoo.example.com", "credentials"),
        ]:
            r = await api.post(
                "/integrations", json={**ODOO, "config": {**ODOO["config"], "url": url}}
            )
            assert r.status_code == 422, url
            assert r.json()["error"]["code"] == "unsafe_url"
            assert needle in r.json()["error"]["message"], url


async def test_resync_is_idempotent_and_tracks_changes(
    iapi: Api, fakes: Fakes, owner_engine: Any
) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    before = counts(owner_engine, conn["id"])
    # Upstream edits: a renamed product, a quant that disappears (stock snapshot).
    product = next(p for p in fakes.odoo.data["product.product"] if p["id"] == 101)
    product["name"] = "Hi-vis vest, orange"
    product["write_date"] = "2099-01-01 00:00:00"
    fakes.odoo.data["stock.quant"] = [q for q in fakes.odoo.data["stock.quant"] if q["id"] != 3]
    assert (await iapi.post(f"/integrations/{conn['id']}/sync")).status_code == 202
    after = counts(owner_engine, conn["id"])
    assert after == {**before, "stock_levels": 1}
    with owner_engine.connect() as c:
        assert (
            c.execute(text("SELECT name FROM products WHERE sku = 'HV-VST-104'")).scalar()
            == "Hi-vis vest, orange"
        )
    jobs = (await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()
    assert [j["trigger"] for j in jobs] == ["manual", "initial"]
    # The second products fetch was incremental (write_date filter applied).
    assert jobs[0]["stats"]["products"]["received"] == 1


async def test_auth_failure_needs_attention_and_notifies_once(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    fakes.odoo.api_key = "rotated-upstream-key"
    await iapi.post(f"/integrations/{conn['id']}/sync")
    detail = (await iapi.get(f"/integrations/{conn['id']}")).json()
    assert detail["status"] == "action_required"
    assert detail["last_error"] == "Odoo rejected the username or API key."
    await iapi.post(f"/integrations/{conn['id']}/sync")
    titles = [n["title"] for n in (await iapi.get("/notifications")).json()["items"]]
    assert titles.count("Odoo production needs attention") == 1
    # Rotating to the new key restores the connection (credentials are tested first).
    bad = await iapi.put(
        f"/integrations/{conn['id']}/credentials", json={"secrets": {"api_key": "still-wrong-123"}}
    )
    assert bad.status_code == 422
    ok = await iapi.put(
        f"/integrations/{conn['id']}/credentials",
        json={"secrets": {"api_key": "rotated-upstream-key"}},
    )
    assert ok.status_code == 200
    # Rotation triggers a sync; its success (not the rotation itself) restores the connection.
    assert (await iapi.get(f"/integrations/{conn['id']}")).json()["status"] == "active"
    titles = [n["title"] for n in (await iapi.get("/notifications")).json()["items"]]
    assert "Odoo production is syncing again" in titles


async def test_outage_degrades_without_touching_data(
    iapi: Api, fakes: Fakes, owner_engine: Any
) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    before = counts(owner_engine, conn["id"])
    fakes.odoo.fail_with = 503
    await iapi.post(f"/integrations/{conn['id']}/sync")
    detail = (await iapi.get(f"/integrations/{conn['id']}")).json()
    assert detail["status"] == "degraded"
    assert "Operon will retry" in detail["last_error"]
    assert counts(owner_engine, conn["id"]) == before
    job = (await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()[0]
    assert job["status"] == "failed"
    assert "503" not in (job["error"] or "")  # upstream detail stays in logs


async def test_paused_connections_do_not_sync(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    assert (await iapi.patch(f"/integrations/{conn['id']}", json={"paused": True})).json()[
        "status"
    ] == "paused"
    r = await iapi.post(f"/integrations/{conn['id']}/sync")
    assert (r.status_code, error_code(r)) == (409, "paused")


async def test_disconnect_removes_connection_and_its_data(iapi: Api, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    assert (await iapi.delete(f"/integrations/{conn['id']}")).status_code == 204
    assert set(counts(owner_engine, conn["id"]).values()) == {0}
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM integration_credentials")).scalar() == 0
    actions = [
        e["action"]
        for e in (await iapi.get("/audit", params={"action": "integration."})).json()["items"]
    ]
    assert (
        actions[:2] == ["integration.disconnected", "integration.connected"]
        or "integration.disconnected" in actions
    )


async def test_permissions(iapi: Api, second_api: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    await invite_and_join(iapi, second_api, "analyst@acme.example", "analyst")
    conn = await connect(iapi, ODOO)
    assert (await second_api.get("/integrations")).status_code == 200
    assert (await second_api.post(f"/integrations/{conn['id']}/sync")).status_code == 403
    assert (await second_api.delete(f"/integrations/{conn['id']}")).status_code == 403
    assert (
        await second_api.post("/integrations", json={"connector": "csv", "name": "x"})
    ).status_code == 403


async def test_shopify_sync(iapi: Api, fakes: Fakes, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, SHOPIFY)
    job = (await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()[0]
    assert job["status"] == "succeeded", job
    c = counts(owner_engine, conn["id"])
    assert c["locations"] == 1  # inactive location skipped
    assert c["products"] == 150  # two GraphQL pages
    assert c["stock_levels"] == 2
    with owner_engine.connect() as db:
        sold = db.execute(
            text(
                "SELECT p.sku, sum(sd.quantity) FROM sales_daily sd JOIN products p "
                "ON p.id = sd.product_id GROUP BY p.sku ORDER BY p.sku"
            )
        ).all()
        stock = db.execute(
            text(
                "SELECT on_hand, reserved FROM stock_levels s JOIN products p ON "
                "p.id = s.product_id WHERE p.sku = 'SKU-001'"
            )
        ).one()
        archived = db.execute(text("SELECT active FROM products WHERE sku = 'SKU-050'")).scalar()
    assert [(s, float(q)) for s, q in sold] == [
        ("SKU-001", 5.0),
        ("SKU-002", 1.0),
    ]  # cancelled excluded
    assert (float(stock[0]), float(stock[1])) == (120.0, 7.0)
    assert archived is False
    detail = (await iapi.get(f"/integrations/{conn['id']}")).json()
    assert detail["webhook_url"].endswith(
        f"/api/v1/webhooks/{detail['webhook_url'].rsplit('/', 1)[-1]}"
    )
    assert detail["has_webhook_secret"] is True


async def test_shopify_throttling_is_retryable(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, SHOPIFY)
    fakes.shopify.throttle_next = 1
    await iapi.post(f"/integrations/{conn['id']}/sync")
    detail = (await iapi.get(f"/integrations/{conn['id']}")).json()
    assert detail["status"] == "degraded"
    assert "rate limiting" in detail["last_error"]


async def test_shopify_domain_is_validated(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    r = await iapi.post(
        "/integrations", json={**SHOPIFY, "config": {"shop_domain": "evil.example.com"}}
    )
    assert (r.status_code, error_code(r)) == (422, "invalid_settings")


async def test_webhooks(iapi: Api, fakes: Fakes, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, SHOPIFY)
    url = (
        "/"
        + (await iapi.get(f"/integrations/{conn['id']}"))
        .json()["webhook_url"]
        .split("/api/v1/", 1)[1]
    )
    body = json.dumps({"id": 1}).encode()
    headers = {
        "X-Shopify-Hmac-Sha256": sign(body),
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Webhook-Id": "wh-001",
        "Content-Type": "application/json",
    }
    # Machine callers: a separate client with no session cookie or CSRF token.
    import httpx

    raw = httpx.AsyncClient(transport=httpx.ASGITransport(app=iapi.app), base_url="http://test")
    r = await raw.post(f"/api/v1{url}", content=body, headers=headers)
    assert r.json() == {"status": "accepted"}
    jobs = (await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()
    assert jobs[0]["trigger"] == "webhook"
    # Redelivery is acknowledged but not processed twice.
    again = await raw.post(f"/api/v1{url}", content=body, headers=headers)
    assert again.json() == {"status": "duplicate"}
    assert len((await iapi.get(f"/integrations/{conn['id']}/sync-jobs")).json()) == len(jobs)
    events = (await iapi.get(f"/integrations/{conn['id']}/events")).json()
    assert [(e["source_event_id"], e["status"]) for e in events] == [("wh-001", "processed")]
    # Irrelevant topics are stored as ignored; forged signatures are rejected and audited.
    other = {**headers, "X-Shopify-Topic": "customers/create", "X-Shopify-Webhook-Id": "wh-002"}
    assert (await raw.post(f"/api/v1{url}", content=body, headers=other)).json() == {
        "status": "ignored"
    }
    forged = {
        **headers,
        "X-Shopify-Hmac-Sha256": sign(body, "attacker-secret-123"),
        "X-Shopify-Webhook-Id": "wh-003",
    }
    r = await raw.post(f"/api/v1{url}", content=body, headers=forged)
    assert r.status_code == 401
    assert (
        await raw.post("/api/v1/webhooks/" + "x" * 43, content=body, headers=headers)
    ).status_code == 404
    rejected = (await iapi.get("/audit", params={"action": "integration.webhook_rejected"})).json()[
        "items"
    ]
    assert len(rejected) == 1
    await raw.aclose()


async def test_sync_lock_prevents_concurrent_runs(iapi: Api, owner_engine: Any) -> None:
    from operon.modules.integrations.sync import run_sync

    org = await iapi.sign_up("owner@acme.example")
    conn = await connect(iapi, ODOO)
    with owner_engine.connect() as c:
        c.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": f"sync:{conn['id']}"})
        from uuid import UUID

        outcome = await run_sync(
            iapi.app.state.sync_runtime,
            organisation_id=UUID(org),
            connection_id=UUID(conn["id"]),
            trigger="manual",
        )
        c.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"sync:{conn['id']}"})
    assert outcome.status == "skipped"


async def test_dashboard_reflects_connections(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    s = (await iapi.get("/dashboard/summary")).json()
    assert s["integrations"]["state"] == "ready"
    assert s["integrations"]["provenance"] == "live"
    [row] = s["integrations"]["data"]
    assert (row["name"], row["status"]) == ("Odoo production", "healthy")
    indicator = next(i for i in s["indicators"] if i["key"] == "integrations")
    assert (indicator["value"], indicator["total"], indicator["provenance"]) == (1, 1, "live")
    step = next(st for st in s["getting_started"]["data"] if st["key"] == "integrations")
    assert step["done"] is True
    # Synced stock makes inventory risk and insights live (detection ran after the sync).
    assert s["inventory_risk"]["provenance"] == "live"
    assert s["inventory_risk"]["data"]
    assert s["insights"]["provenance"] == "live"
    assert next(i for i in s["indicators"] if i["key"] == "open_insights")["provenance"] == "live"
