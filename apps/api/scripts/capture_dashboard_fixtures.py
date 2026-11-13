"""Regenerate the web app's dashboard contract fixtures from the real API.

Usage (from apps/api, test database and Redis running):
    uv run python scripts/capture_dashboard_fixtures.py ../web/src/test/fixtures

Wipes the *test* database, signs up users through the in-process API, seeds operational
data and a demo organisation, and writes each response as JSON.
Never point it at a database you care about.
"""

import asyncio
import json
import sys
from pathlib import Path

# Make `tests.*` importable when run as a script from apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import redis
from sqlalchemy import create_engine, text
from tests.conftest import TEST_DB_OWNER_URL, TEST_REDIS_URL, Api, _api_for, make_settings
from tests.helpers import invite_and_join, seed_operations
from tests.test_dashboard import make_demo_org

from operon.main import create_app


def _write(out: Path, name: str, payload: object) -> None:
    (out / name).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


async def main(out: Path) -> None:
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

    async with _api_for(create_app(make_settings())) as owner:
        await owner.sign_up("olu@acme.example", org="Acme Distribution", name="Olu Owner")
        transport = httpx.ASGITransport(app=owner.app, client=("203.0.113.9", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            viewer = Api(client, owner.app)
            await invite_and_join(owner, viewer, "bo@acme.example", "viewer", name="Bo Lin")
            _write(out, "dashboard-viewer.json", (await viewer.get("/dashboard/summary")).json())
        _write(out, "dashboard-live.json", (await owner.get("/dashboard/summary")).json())
        # The same organisation once operational data arrives: live insights, incidents, risk.
        await seed_operations(owner, "Warehouse spreadsheets")
        insights = (await owner.get("/insights")).json()["items"]
        stockout = next(i for i in insights if i["rule_id"] == "inventory.stockout_risk")
        detail = (await owner.get(f"/insights/{stockout['id']}")).json()
        await owner.post(
            "/purchase-requests",
            json={"insight_id": stockout["id"], "quantity": detail["recommendation"]["quantity"]},
        )
        _write(out, "dashboard-operations.json", (await owner.get("/dashboard/summary")).json())
        owner.org_id = await make_demo_org("olu@acme.example")
        _write(out, "dashboard-demo.json", (await owner.get("/dashboard/summary")).json())
        _write(out, "dashboard-layout.json", (await owner.get("/dashboard/layout")).json())


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
