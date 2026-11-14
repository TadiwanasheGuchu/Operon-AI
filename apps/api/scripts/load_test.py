"""Load test: N organisations x K SKUs through the real write path, detection and read APIs.

Usage (from apps/api, test database and Redis running; wipes the TEST database):
    uv run python scripts/load_test.py --orgs 3 --skus 10000 [--report scripts/load-report.json]

For each organisation it writes a synced catalogue with the same `Store` code a sync uses
(locations, suppliers, products, supplier terms, stock, 28 days of sales, purchase orders), then
times detection and the main read endpoints, then runs every organisation's detection at once
(the scheduled case). Plan §7 target: 50 organisations x 10,000 SKUs syncing on schedule.
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis
from sqlalchemy import create_engine, text
from tests.conftest import TEST_DB_OWNER_URL, TEST_REDIS_URL, Api, _api_for, make_settings

from operon.core.db import set_rls_context
from operon.main import create_app
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
from operon.modules.intelligence.engine import run_detection
from operon.modules.operations.store import Store

DAYS = 28


def reset() -> None:
    engine = create_engine(TEST_DB_OWNER_URL)
    with engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'permissions')"
                )
            )
            .scalars()
            .all()
        )
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    engine.dispose()
    redis.Redis.from_url(TEST_REDIS_URL).flushdb()


def catalogue(skus: int, seed: int) -> dict[str, list[Any]]:
    rnd = random.Random(seed)  # noqa: S311 — synthetic test data, seeded for repeatability
    today = datetime.now(UTC).date()
    locations = [LocationRecord(f"L{i}", f"Warehouse {i}", f"WH{i}") for i in range(3)]
    suppliers = [SupplierRecord(f"S{i}", f"Supplier {i}") for i in range(50)]
    products, terms, stock, sales, orders = [], [], [], [], []
    for n in range(skus):
        pid = f"P{n}"
        products.append(ProductRecord(pid, f"Product {n}", sku=f"SKU-{n:05d}", uom="unit"))
        terms.append(
            SupplierProductRecord(
                f"T{n}",
                f"S{n % 50}",
                pid,
                lead_time_days=rnd.randint(3, 21),
                min_quantity=Decimal(rnd.choice([0, 10, 50])),
                price=Decimal("4.50"),
                currency="GBP",
            )
        )
        loc = f"L{n % 3}"
        mean = rnd.uniform(0.5, 40)
        # About 3% of items are short, so detection has real work and real insights.
        cover = rnd.uniform(1, 6) if rnd.random() < 0.03 else rnd.uniform(30, 120)
        stock.append(StockRecord(pid, loc, Decimal(int(mean * cover))))
        for d in range(1, DAYS + 1):
            q = max(0, int(rnd.gauss(mean, mean / 3)))
            if q:
                sales.append(SalesRecord(pid, today - timedelta(days=d), Decimal(q), loc))
    for o in range(max(1, skus // 20)):
        lines = [
            PurchaseOrderLineRecord(
                f"PL{o}-{i}", f"P{rnd.randrange(skus)}", Decimal(rnd.randint(10, 500))
            )
            for i in range(3)
        ]
        late = rnd.random() < 0.1
        orders.append(
            PurchaseOrderRecord(
                f"PO{o}",
                f"PO-{o:05d}",
                "open",
                supplier_external_id=f"S{o % 50}",
                location_external_id=f"L{o % 3}",
                ordered_at=datetime.now(UTC) - timedelta(days=20),
                expected_at=datetime.now(UTC) + timedelta(days=-8 if late else rnd.randint(2, 30)),
                currency="GBP",
                lines=lines,
            )
        )
    return {
        "locations": locations,
        "suppliers": suppliers,
        "products": products,
        "supplier_products": terms,
        "stock": stock,
        "sales": sales,
        "purchase_orders": orders,
    }


async def write(api: Api, org: UUID, conn: UUID, data: dict[str, list[Any]]) -> dict[str, float]:
    db = api.app.state.db
    timings: dict[str, float] = {}
    sales_from: date = datetime.now(UTC).date() - timedelta(days=DAYS)
    for entity, records in data.items():
        t0 = time.perf_counter()
        async with db.sessionmaker() as s, s.begin():
            await set_rls_context(s, organisation_id=org)
            store = Store(s, org, conn)
            if entity == "stock":
                await store.stock_snapshot(records)
            elif entity == "sales":
                await store.sales_window(records, sales_from)
            else:
                await getattr(store, entity)(records)
        timings[entity] = round(time.perf_counter() - t0, 2)
    return timings


async def latency(api: Api, path: str, n: int = 5) -> float:
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = await api.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        samples.append(time.perf_counter() - t0)
    return round(statistics.median(samples) * 1000)


async def main(orgs: int, skus: int, report: Path | None) -> None:
    reset()
    results: dict[str, Any] = {"orgs": orgs, "skus_per_org": skus, "per_org": []}
    app = create_app(make_settings(inline_maintenance_interval_seconds=0, log_level="WARNING"))
    async with _api_for(app):
        tenants: list[tuple[UUID, Api]] = []
        for i in range(orgs):
            import httpx

            transport = httpx.ASGITransport(app=app, client=(f"203.0.113.{60 + i}", 1))
            client = httpx.AsyncClient(transport=transport, base_url="http://test")
            api = Api(client, app)
            await api.sign_up(f"load{i}@load.example", org=f"Load org {i}")
            conn = (
                await api.post("/integrations", json={"connector": "csv", "name": "Load"})
            ).json()
            data = catalogue(skus, seed=i)
            t0 = time.perf_counter()
            timings = await write(api, UUID(api.org_id), UUID(conn["id"]), data)
            ingest = round(time.perf_counter() - t0, 1)
            t0 = time.perf_counter()
            run = await run_detection(app.state.intelligence, UUID(api.org_id), "manual")
            detect = round(time.perf_counter() - t0, 1)
            entry = {
                "rows": {k: len(v) for k, v in data.items()},
                "ingest_seconds": ingest,
                "ingest_by_entity": timings,
                "detection_seconds": detect,
                "insights": {
                    r: s.get("raised") for r, s in run.stats.items() if isinstance(s, dict)
                },
                "latency_ms": {
                    "insights_list": await latency(api, "/insights"),
                    "dashboard": await latency(api, "/dashboard/summary"),
                    "intelligence_runs": await latency(api, "/intelligence/runs"),
                },
            }
            results["per_org"].append(entry)
            print(json.dumps(entry), flush=True)
            tenants.append((UUID(api.org_id), api))
        t0 = time.perf_counter()
        await asyncio.gather(
            *(run_detection(app.state.intelligence, o, "schedule") for o, _ in tenants)
        )
        results["concurrent_detection_seconds"] = round(time.perf_counter() - t0, 1)
        for _, api in tenants:
            await api.http.aclose()
    per = results["per_org"]
    results["summary"] = {
        "median_ingest_seconds": statistics.median(p["ingest_seconds"] for p in per),
        "median_detection_seconds": statistics.median(p["detection_seconds"] for p in per),
        "median_insights_list_ms": statistics.median(p["latency_ms"]["insights_list"] for p in per),
        "median_dashboard_ms": statistics.median(p["latency_ms"]["dashboard"] for p in per),
    }
    print(json.dumps(results["summary"], indent=1))
    print(
        f"Concurrent detection for {orgs} organisations: {results['concurrent_detection_seconds']}s"
    )
    if report:
        await asyncio.to_thread(report.write_text, json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--orgs", type=int, default=3)
    p.add_argument("--skus", type=int, default=10_000)
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    asyncio.run(main(a.orgs, a.skus, a.report))
