"""Audit trail guarantees and permission-catalogue consistency."""

from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from operon.modules.permissions.catalogue import PERMISSION_DESCRIPTIONS, SYSTEM_ROLES, Perm
from tests.conftest import TEST_DB_APP_URL, Api


async def test_audit_log_is_append_only_for_the_app_role(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    engine = create_engine(TEST_DB_APP_URL.replace("+asyncpg", "+psycopg"))
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": api.org_id})
        for statement in (
            "UPDATE audit_logs SET action = 'tampered'",
            "DELETE FROM audit_logs",
            "TRUNCATE audit_logs",
        ):
            with pytest.raises(DBAPIError, match="permission denied"):
                conn.execute(text(statement))
            conn.rollback()
            conn.execute(
                text("SELECT set_config('app.current_org_id', :o, false)"), {"o": api.org_id}
            )
    engine.dispose()


async def test_organisation_creation_is_recorded(api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    actions = [e["action"] for e in (await api.get("/audit")).json()["items"]]
    assert set(actions) >= {"organisation.created", "member.joined"}


async def test_audit_pagination_and_filters(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    for i in range(5):
        await api.post("/invitations", json={"email": f"p{i}@acme.example", "role_key": "viewer"})
    first = (await api.get("/audit", params={"limit": 3, "action": "invitation."})).json()
    assert len(first["items"]) == 3
    assert first["next_cursor"]
    second = (
        await api.get(
            "/audit", params={"limit": 3, "action": "invitation.", "cursor": first["next_cursor"]}
        )
    ).json()
    assert len(second["items"]) == 2
    assert second["next_cursor"] is None
    ids = [e["id"] for e in first["items"] + second["items"]]
    assert len(set(ids)) == 5
    times = [e["occurred_at"] for e in first["items"] + second["items"]]
    assert times == sorted(times, reverse=True)


async def test_audit_rejects_bad_cursor(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    r = await api.get("/audit", params={"cursor": "garbage"})
    assert r.status_code == 422


async def test_account_events_do_not_leak_into_organisation_logs(api: Api) -> None:
    """Login and password events have no organisation; they never appear in a tenant's trail."""
    await api.sign_up("owner@acme.example")
    actions = {
        e["action"] for e in (await api.get("/audit", params={"limit": 100})).json()["items"]
    }
    assert not {a for a in actions if a.startswith("auth.")}


async def test_catalogue_matches_database(api: Api, owner_engine: Any) -> None:
    with owner_engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT key, description FROM permissions")).all())
    assert rows == {p.value: d for p, d in PERMISSION_DESCRIPTIONS.items()}
    assert set(PERMISSION_DESCRIPTIONS) == set(Perm)


async def test_system_roles_are_provisioned_from_catalogue(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    roles = {r["key"]: set(r["permissions"]) for r in (await api.get("/roles")).json()}
    assert roles == {k.value: {p.value for p in perms} for k, (_, _, perms) in SYSTEM_ROLES.items()}
