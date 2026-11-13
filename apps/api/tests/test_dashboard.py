"""Operations overview: provenance, permissions, layouts and demo organisations."""

from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from operon.cli import seed_demo
from tests.conftest import TEST_DB_APP_URL, TEST_DB_OWNER_URL, Api
from tests.helpers import invite_and_join

SECTIONS = [
    "getting_started",
    "insights",
    "approvals",
    "incidents",
    "fill_rate",
    "inventory_risk",
    "workflows",
    "integrations",
    "activity",
    "team",
]


async def make_demo_org(owner_email: str) -> str:
    engine = create_async_engine(TEST_DB_OWNER_URL.replace("+psycopg", "+asyncpg"))
    async with async_sessionmaker(engine)() as session, session.begin():
        org_id = await seed_demo(session, owner_email, "Harbour & Vale (demo)")
    await engine.dispose()
    return str(org_id)


def assert_honest(summary: dict[str, Any]) -> None:
    """No section ever carries data without a provenance, and unavailable means no data."""
    for key in SECTIONS:
        section = summary[key]
        if section["state"] == "ready":
            assert section["provenance"] in {"live", "demo"}, key
            assert section["as_of"], key
        else:
            assert section["data"] is None, key
            assert section["provenance"] == "unavailable", key
            assert section["message"], key
    for indicator in summary["indicators"]:
        if indicator["provenance"] == "unavailable":
            assert indicator["value"] is None


async def test_real_organisation_shows_only_real_data(api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme", name="Olu Owner")
    s = (await api.get("/dashboard/summary")).json()
    assert_honest(s)
    assert s["organisation"]["is_demo"] is False
    assert s["viewer"] == {"name": "Olu Owner", "role_key": "owner", "role_name": "Owner"}
    # Nothing operational exists yet, and the API says so (with the phase that brings it, for
    # features not built yet; data-dependent sections carry no phase).
    for key, phase in [
        ("insights", None),
        ("fill_rate", None),
        ("inventory_risk", None),
        ("workflows", None),
        ("integrations", 3),
    ]:
        assert s[key]["state"] == "unavailable", key
        assert s[key]["available_in_phase"] == phase, key
    # What does exist is live.
    assert s["approvals"]["provenance"] == "live"
    assert s["approvals"]["data"] == []
    assert s["incidents"]["provenance"] == "live"
    assert s["incidents"]["data"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert s["team"]["provenance"] == "live"
    assert s["team"]["data"]["members"] == 1
    indicators = {i["key"]: i for i in s["indicators"]}
    assert indicators["members"]["value"] == 1
    assert indicators["mfa_coverage"] == {
        **indicators["mfa_coverage"],
        "value": 0,
        "total": 1,
        "state": "attention",
    }
    assert indicators["open_insights"]["value"] is None
    steps = {st["key"]: st for st in s["getting_started"]["data"]}
    assert steps["mfa"]["done"] is False
    assert steps["team"]["done"] is False
    assert steps["integrations"] == {
        **steps["integrations"],
        "available": True,
        "done": False,
        "href": "/integrations",
    }


async def test_activity_is_derived_from_the_audit_trail(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme", name="Olu Owner")
    await invite_and_join(api, second_api, "bo@acme.example", "analyst", name="Bo Lin")
    activity = (await api.get("/dashboard/summary")).json()["activity"]["data"]
    messages = [(e["actor"], e["message"]) for e in activity]
    assert ("Bo Lin", "Joined the organisation") in messages
    assert ("Olu Owner", "Invited bo@acme.example as analyst") in messages
    assert ("Olu Owner", "Created the organisation") in messages


async def test_sections_follow_permissions(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "viewer@acme.example", "viewer")
    s = (await second_api.get("/dashboard/summary")).json()
    assert_honest(s)
    assert s["team"]["state"] == "restricted"
    assert s["activity"]["state"] == "restricted"
    assert s["team"]["data"] is None
    assert {i["key"] for i in s["indicators"]}.isdisjoint({"members", "mfa_coverage"})
    steps = {st["key"]: st for st in s["getting_started"]["data"]}
    assert steps["team"]["available"] is False


async def test_period_is_validated(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    assert (await api.get("/dashboard/summary", params={"period": "1y"})).status_code == 422


async def test_layout_defaults_by_role_and_can_be_saved(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "approver@acme.example", "approver")
    owner = (await api.get("/dashboard/layout")).json()
    assert owner["current"]["preset"] == "executive"
    assert owner["current"]["is_default"] is True
    assert [p["key"] for p in owner["presets"]] == [
        "executive",
        "operations",
        "finance",
        "warehouse",
    ]
    assert (await second_api.get("/dashboard/layout")).json()["current"]["preset"] == "finance"

    saved = (await api.put("/dashboard/layout", json={"preset": "warehouse"})).json()
    assert saved["current"] == {**saved["current"], "preset": "warehouse", "is_default": False}
    summary = (await api.get("/dashboard/summary")).json()
    assert summary["layout"]["preset"] == "warehouse"
    assert summary["layout"]["sections"][1] == {"key": "inventory_risk", "size": "narrow"}
    # One user's choice doesn't affect another's.
    assert (await second_api.get("/dashboard/layout")).json()["current"]["preset"] == "finance"
    reset = (await api.put("/dashboard/layout", json={"preset": None})).json()
    assert reset["current"]["preset"] == "executive"
    assert reset["current"]["is_default"] is True
    assert (await api.put("/dashboard/layout", json={"preset": "chaos"})).status_code == 422


async def test_demo_organisation_is_labelled_throughout(api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    demo_id = await make_demo_org("owner@acme.example")
    orgs = {o["id"]: o for o in (await api.get("/organisations")).json()}
    assert orgs[demo_id]["is_demo"] is True
    api.org_id = demo_id
    s = (await api.get("/dashboard/summary", params={"period": "30d"})).json()
    assert_honest(s)
    assert s["organisation"]["is_demo"] is True
    for key in [
        "insights",
        "approvals",
        "incidents",
        "fill_rate",
        "inventory_risk",
        "workflows",
        "integrations",
        "activity",
    ]:
        assert s[key]["provenance"] == "demo", key
    assert all(i["provenance"] == "demo" for i in s["indicators"])
    assert len(s["fill_rate"]["data"]["points"]) == 30
    # Real data stays real even in a demo organisation.
    assert s["team"]["provenance"] == "live"
    stockout = next(i for i in s["insights"]["data"] if i["ref"] == "INS-2041")
    assert stockout["severity"] == "critical"
    evidence = {e["label"]: e["value"] for e in stockout["evidence"]}
    assert evidence["Reorder point"] == "1,877 units"


async def test_demo_seed_is_audited_and_requires_verified_owner(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    demo_id = await make_demo_org("owner@acme.example")
    api.org_id = demo_id
    [created] = (await api.get("/audit", params={"action": "organisation.created"})).json()["items"]
    assert created["actor_type"] == "system"
    assert created["details"]["demo"] is True
    with pytest.raises(SystemExit):
        await make_demo_org("nobody@acme.example")


async def test_application_role_cannot_create_or_flip_demo_organisations(api: Api) -> None:
    org = await api.sign_up("owner@acme.example")
    engine = create_engine(TEST_DB_APP_URL.replace("+asyncpg", "+psycopg"))
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": org})
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("UPDATE organisations SET is_demo = true WHERE id = :o"), {"o": org})
        conn.rollback()
        conn.execute(
            text(
                "SELECT set_config('app.current_org_id', '00000000-0000-0000-0000-000000000001', false)"
            )
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(
                text(
                    "INSERT INTO organisations (id, name, mfa_required, is_demo) "
                    "VALUES ('00000000-0000-0000-0000-000000000001', 'Fake', false, true)"
                )
            )
    engine.dispose()
    # And the API has no way to set it either.
    r = await api.patch("/organisations/current", json={"is_demo": True})
    assert r.status_code == 200
    assert r.json()["is_demo"] is False
