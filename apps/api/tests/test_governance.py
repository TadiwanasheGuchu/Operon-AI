"""Phase 7: retention, export, interrupted runs, request limits."""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from operon.modules.agents.service import fail_stale_runs
from operon.modules.governance.service import apply_retention
from tests.conftest import Api
from tests.fakes.llm import ScriptedLLM
from tests.helpers import another_client, error_code, invite_and_join
from tests.test_integrations import ODOO, connect


def org_count(owner_engine: Any, table: str, org: str, extra: str = "") -> int:
    with owner_engine.connect() as c:
        return int(
            c.execute(
                text(f"SELECT count(*) FROM {table} WHERE organisation_id = :o {extra}"), {"o": org}
            ).scalar()
        )


async def test_retention_policy_is_bounded_and_audited(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    r = (await api.get("/organisations/current/retention")).json()
    assert (r["audit_days"], r["conversation_days"]) == (730, 90)
    bad = {"audit_days": 30, "conversation_days": 90, "run_log_days": 180, "sync_job_days": 90}
    assert (await api.put("/organisations/current/retention", json=bad)).status_code == 422
    good = {**bad, "audit_days": 400}
    assert (await api.put("/organisations/current/retention", json=good)).json()[
        "audit_days"
    ] == 400
    async with another_client(api) as analyst:
        await invite_and_join(api, analyst, "an@acme.example", "analyst")
        assert (await analyst.put("/organisations/current/retention", json=good)).status_code == 403
    actions = [e["action"] for e in (await api.get("/audit", params={"limit": 10})).json()["items"]]
    assert "retention.updated" in actions


async def test_retention_removes_only_what_has_aged_out(api: Api, owner_engine: Any) -> None:
    await api.sign_up("owner@acme.example")
    org = api.org_id or ""
    llm = ScriptedLLM(["Hello."])
    api.app.state.intelligence.providers.providers["anthropic"] = llm
    await api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "anthropic", "monthly_token_budget": 100000},
    )
    await api.post("/assistant/messages", json={"question": "Hello?"})
    old = datetime.now(UTC) - timedelta(days=1000)
    with owner_engine.begin() as c:
        c.execute(
            text(
                "UPDATE audit_logs SET occurred_at = :t WHERE organisation_id = :o AND action = 'organisation.created'"
            ),
            {"t": old, "o": org},
        )
        c.execute(
            text("UPDATE agent_executions SET started_at = :t WHERE organisation_id = :o"),
            {"t": old, "o": org},
        )
        c.execute(
            text("UPDATE assistant_conversations SET updated_at = :t WHERE organisation_id = :o"),
            {"t": old, "o": org},
        )
    before_audit = org_count(owner_engine, "audit_logs", org)
    totals = await apply_retention(api.app.state.db)
    assert totals["audit"] == 1
    assert totals["runs"] == 1
    assert totals["conversations"] == 1
    assert org_count(owner_engine, "audit_logs", org, "AND action = 'organisation.created'") == 0
    # Recent history stays, and the purge itself is recorded.
    assert org_count(owner_engine, "audit_logs", org) == before_audit - 1 + 1
    assert org_count(owner_engine, "agent_execution_steps", org) == 0  # cascaded with the run
    assert await apply_retention(api.app.state.db) == {
        "audit": 0,
        "conversations": 0,
        "runs": 0,
        "sync_jobs": 0,
    }


async def test_purge_functions_refuse_short_retention(api: Api) -> None:
    from sqlalchemy import create_engine

    from tests.conftest import TEST_DB_APP_URL

    await api.sign_up("owner@acme.example")
    engine = create_engine(TEST_DB_APP_URL.replace("+asyncpg", "+psycopg"))
    with engine.connect() as c:
        with pytest.raises(DBAPIError, match="at least 365 days"):
            c.execute(text("SELECT operon_purge_audit(:o, now())"), {"o": api.org_id})
        c.rollback()
        with pytest.raises(DBAPIError, match="at least 7 days"):
            c.execute(text("SELECT operon_purge_conversations(:o, now())"), {"o": api.org_id})
    engine.dispose()


async def test_export_contains_the_organisations_data_and_no_secrets(
    iapi: Api, second_api: Api
) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    r = await iapi.post("/organisations/current/export")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["counts"]["products"] > 0
    assert manifest["counts"]["ai_insights"] > 0
    assert manifest["counts"]["members"] == 1
    blob = b"".join(zf.read(n) for n in zf.namelist()).decode()
    from tests.fakes.odoo import API_KEY

    assert API_KEY not in blob
    assert "argon2" not in blob
    assert "secret_encrypted" not in blob
    assert "token_hash" not in blob
    first = json.loads(zf.read("ai_insights.jsonl").splitlines()[0])
    assert first["organisation_id"] == iapi.org_id
    actions = [e["action"] for e in (await iapi.get("/audit", params={"limit": 5})).json()["items"]]
    assert "organisation.exported" in actions


async def test_export_is_limited_and_restricted(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    for _ in range(5):
        assert (await api.post("/organisations/current/export")).status_code == 200
    r = await api.post("/organisations/current/export")
    assert (r.status_code, error_code(r)) == (429, "rate_limited")
    async with another_client(api) as viewer:
        await invite_and_join(api, viewer, "v@acme.example", "viewer")
        assert (await viewer.post("/organisations/current/export")).status_code == 403


async def test_interrupted_agent_runs_are_marked_failed(api: Api, owner_engine: Any) -> None:
    await api.sign_up("owner@acme.example")
    api.app.state.intelligence.providers.providers["anthropic"] = ScriptedLLM(["Hi."])
    await api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "anthropic", "monthly_token_budget": 100000},
    )
    msg = (await api.post("/assistant/messages", json={"question": "Hi?"})).json()["message"]
    with owner_engine.begin() as c:
        c.execute(
            text(
                "UPDATE agent_executions SET status = 'running', finished_at = NULL, started_at = now() - interval '2 hours'"
            ),
        )
    assert await fail_stale_runs(api.app.state.db) == 1
    run = (await api.get(f"/agents/runs/{msg['execution_id']}")).json()
    assert (run["status"], run["stop_reason"]) == ("failed", "interrupted")
    assert run["log"][-1]["kind"] == "error"
    assert await fail_stale_runs(api.app.state.db) == 0


async def test_oversized_requests_are_refused(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    r = await api.patch("/users/me", json={"full_name": "x" * (2 * 1024 * 1024)})
    assert (r.status_code, error_code(r)) == (413, "payload_too_large")


async def test_assistant_use_is_rate_limited(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    api.app.state.intelligence.providers.providers["anthropic"] = ScriptedLLM(
        ["Ok."], repeat_last=True
    )
    await api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "anthropic", "monthly_token_budget": 10_000_000},
    )
    codes = [
        (await api.post("/assistant/messages", json={"question": f"Question {i}?"})).status_code
        for i in range(21)
    ]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429
