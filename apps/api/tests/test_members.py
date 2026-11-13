"""Organisations, roles, members and invitations."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from tests.conftest import PASSWORD, Api
from tests.helpers import error_code, invite_and_join


async def test_new_organisation_has_system_roles(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    roles = (await api.get("/roles")).json()
    assert [r["key"] for r in roles] == [
        "owner",
        "administrator",
        "operations_manager",
        "approver",
        "analyst",
        "viewer",
    ]
    current = (await api.get("/organisations/current")).json()
    assert current["role_key"] == "owner"
    assert "members.manage" in current["permissions"]
    viewer = roles[-1]
    assert viewer["permissions"] == [
        "assistant.use",
        "dashboard.read",
        "incidents.read",
        "insights.read",
        "organisation.read",
    ]
    assert all(r["assignable_by_you"] for r in roles)


async def test_user_can_create_and_switch_organisations(api: Api) -> None:
    first = await api.sign_up("owner@acme.example", org="Acme")
    r = await api.post("/organisations", json={"name": "Acme Logistics"})
    assert r.status_code == 201
    second = r.json()["id"]
    names = [o["name"] for o in (await api.get("/organisations")).json()]
    assert names == ["Acme", "Acme Logistics"]
    api.org_id = second
    assert (await api.get("/organisations/current")).json()["name"] == "Acme Logistics"
    api.org_id = first
    assert (await api.get("/organisations/current")).json()["name"] == "Acme"


async def test_invitation_journey_for_new_user(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme", name="Olu Owner")
    await api.post("/invitations", json={"email": "bo@acme.example", "role_key": "analyst"})
    token = api.last_link_token("bo@acme.example", "/invite")
    assert "Olu Owner invited you to Acme" in api.outbox[-1].subject

    lookup = (await second_api.get("/invitations/lookup", params={"token": token})).json()
    assert lookup["organisation_name"] == "Acme"
    assert lookup["role_name"] == "Analyst"
    assert lookup["status"] == "open"

    r = await second_api.post(
        "/auth/register",
        json={
            "email": "bo@acme.example",
            "password": PASSWORD,
            "full_name": "Bo",
            "invitation_token": token,
        },
    )
    assert r.status_code == 202
    # The invitation link proved the address, so Bo can sign in straight away.
    await second_api.login("bo@acme.example")
    orgs = (await second_api.get("/organisations")).json()
    assert [(o["name"], o["role_key"]) for o in orgs] == [("Acme", "analyst")]
    assert (await second_api.get("/invitations/lookup", params={"token": token})).json()[
        "status"
    ] == "accepted"


async def test_existing_user_accepts_invitation(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    await second_api.sign_up("bo@beta.example", org="Beta")
    await api.post("/invitations", json={"email": "bo@beta.example", "role_key": "viewer"})
    token = api.last_link_token("bo@beta.example", "/invite")
    r = await second_api.post("/invitations/accept", json={"token": token})
    assert r.json() == {"organisation_id": api.org_id}
    assert {o["name"] for o in (await second_api.get("/organisations")).json()} == {"Acme", "Beta"}
    again = await second_api.post("/invitations/accept", json={"token": token})
    assert again.status_code == 410


async def test_invitation_is_bound_to_its_email(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await second_api.sign_up("mallory@evil.example", org="Evil")
    await api.post("/invitations", json={"email": "bo@acme.example", "role_key": "administrator"})
    token = api.last_link_token("bo@acme.example", "/invite")
    r = await second_api.post("/invitations/accept", json={"token": token})
    assert r.status_code == 403
    assert error_code(r) == "invitation_email_mismatch"
    r = await second_api.post(
        "/auth/register",
        json={
            "email": "other@evil.example",
            "password": PASSWORD,
            "full_name": "M",
            "invitation_token": token,
        },
    )
    assert r.status_code == 400


async def test_expired_and_revoked_invitations(
    api: Api, second_api: Api, owner_engine: Any
) -> None:
    await api.sign_up("owner@acme.example")
    await second_api.sign_up("bo@beta.example", org="Beta")
    invite = (
        await api.post("/invitations", json={"email": "bo@beta.example", "role_key": "viewer"})
    ).json()
    token = api.last_link_token("bo@beta.example", "/invite")
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE invitations SET expires_at = :t"),
            {"t": datetime.now(UTC) - timedelta(minutes=1)},
        )
    r = await second_api.post("/invitations/accept", json={"token": token})
    assert (r.status_code, error_code(r)) == (410, "invitation_expired")

    assert (await api.delete(f"/invitations/{invite['id']}")).status_code == 204
    r = await second_api.post("/invitations/accept", json={"token": token})
    assert error_code(r) == "invitation_revoked"
    assert (await api.get("/invitations")).json() == []


async def test_duplicate_invitations_and_existing_members(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await api.post("/invitations", json={"email": "bo@acme.example", "role_key": "viewer"})
    dup = await api.post("/invitations", json={"email": "BO@acme.example", "role_key": "viewer"})
    assert error_code(dup) == "already_invited"
    me = await api.post("/invitations", json={"email": "owner@acme.example", "role_key": "viewer"})
    assert error_code(me) == "already_member"


async def test_unknown_invitation_token(second_api: Api) -> None:
    r = await second_api.get("/invitations/lookup", params={"token": "x" * 43})
    assert r.status_code == 404


async def test_viewer_cannot_write_and_attempts_are_audited(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "viewer@acme.example", "viewer")
    for r in [
        await second_api.post(
            "/invitations", json={"email": "x@acme.example", "role_key": "viewer"}
        ),
        await second_api.patch("/organisations/current", json={"name": "Pwned"}),
        await second_api.get("/members"),
        await second_api.get("/audit"),
    ]:
        assert r.status_code == 403
        assert error_code(r) == "forbidden"
    denied = (await api.get("/audit", params={"outcome": "denied"})).json()["items"]
    assert {e["details"]["permission"] for e in denied} == {
        "members.invite",
        "organisation.manage",
        "members.read",
        "audit.read",
    }
    assert (await api.get("/organisations/current")).json()["name"] != "Pwned"


async def test_role_changes_follow_the_rules(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    admin_id = await invite_and_join(api, second_api, "admin@acme.example", "administrator")
    members = (await api.get("/members")).json()
    owner_id = next(m["id"] for m in members if m["email"] == "owner@acme.example")

    # Nobody changes their own role.
    r = await api.patch(f"/members/{owner_id}", json={"role_key": "viewer"})
    assert error_code(r) == "cannot_change_own_role"
    # Administrators can't touch owners or grant ownership.
    r = await second_api.patch(f"/members/{owner_id}", json={"role_key": "viewer"})
    assert (r.status_code, error_code(r)) == (403, "role_not_assignable")
    r = await second_api.post("/invitations", json={"email": "x@acme.example", "role_key": "owner"})
    assert error_code(r) == "role_not_assignable"
    # Owners can.
    r = await api.patch(f"/members/{admin_id}", json={"role_key": "owner"})
    assert r.json()["role_key"] == "owner"
    # With two owners, one can be demoted; the last one never.
    assert (
        await second_api.patch(f"/members/{owner_id}", json={"role_key": "analyst"})
    ).status_code == 200
    r = await api.get("/members")  # api is now an analyst: can read members
    assert r.status_code == 200
    r = await second_api.delete(f"/members/{admin_id}")
    assert error_code(r) == "cannot_remove_self"


async def test_last_owner_cannot_be_removed(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "admin@acme.example", "administrator")
    owner_id = next(
        m["id"] for m in (await api.get("/members")).json() if m["email"] == "owner@acme.example"
    )
    r = await second_api.delete(f"/members/{owner_id}")
    assert error_code(r) == "role_not_assignable"


async def test_removed_member_loses_access_immediately(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    member_id = await invite_and_join(api, second_api, "bo@acme.example", "analyst")
    assert (await second_api.get("/organisations/current")).status_code == 200
    assert (await api.delete(f"/members/{member_id}")).status_code == 204
    r = await second_api.get("/organisations/current")
    assert (r.status_code, error_code(r)) == (404, "organisation_not_found")


async def test_members_list_shows_mfa_and_you(api: Api) -> None:
    await api.sign_up("owner@acme.example", name="Olu Owner")
    [me] = (await api.get("/members")).json()
    assert me["is_you"] is True
    assert me["mfa_enabled"] is False
    assert me["full_name"] == "Olu Owner"
