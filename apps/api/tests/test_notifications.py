"""In-app notifications from real events; each user sees only their own."""

import pyotp

from tests.conftest import Api
from tests.helpers import invite_and_join


async def test_inviter_is_notified_when_someone_joins(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    await invite_and_join(api, second_api, "bo@acme.example", "analyst", name="Bo Lin")
    page = (await api.get("/notifications")).json()
    assert page["unread_count"] == 1
    [n] = page["items"]
    assert n["title"] == "Bo Lin joined Acme"
    assert n["link"] == "/admin/members"
    assert n["kind"] == "member"
    # The joiner didn't get it.
    assert (await second_api.get("/notifications")).json()["items"] == []


async def test_member_is_notified_of_role_change(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    member_id = await invite_and_join(api, second_api, "bo@acme.example", "analyst")
    await api.patch(f"/members/{member_id}", json={"role_key": "operations_manager"})
    [n] = (await second_api.get("/notifications")).json()["items"]
    assert n["title"] == "Your role in Acme is now Operations manager"


async def test_mfa_policy_notifies_members_without_mfa(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    await invite_and_join(api, second_api, "bo@acme.example", "analyst")
    setup = (await api.post("/auth/mfa/totp/setup")).json()
    await api.post("/auth/mfa/totp/confirm", json={"code": pyotp.TOTP(setup["secret"]).now()})
    await api.patch("/organisations/current", json={"mfa_required": True})
    # Bo is now blocked from the organisation, so read his notifications after enabling MFA.
    bo_setup = (await second_api.post("/auth/mfa/totp/setup")).json()
    await second_api.post(
        "/auth/mfa/totp/confirm", json={"code": pyotp.TOTP(bo_setup["secret"]).now()}
    )
    titles = [n["title"] for n in (await second_api.get("/notifications")).json()["items"]]
    assert "Acme now requires two-factor authentication" in titles
    # The owner, who already had MFA, wasn't told to set it up.
    owner_titles = [n["title"] for n in (await api.get("/notifications")).json()["items"]]
    assert "Acme now requires two-factor authentication" not in owner_titles


async def test_mark_read_and_read_all(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example", org="Acme")
    member_id = await invite_and_join(api, second_api, "bo@acme.example", "analyst")
    await api.patch(f"/members/{member_id}", json={"role_key": "viewer"})
    await api.patch(f"/members/{member_id}", json={"role_key": "analyst"})
    page = (await second_api.get("/notifications")).json()
    assert page["unread_count"] == 2
    first = page["items"][0]["id"]
    assert (await second_api.post(f"/notifications/{first}/read")).status_code == 204
    assert (await second_api.get("/notifications")).json()["unread_count"] == 1
    unread = (await second_api.get("/notifications", params={"unread_only": True})).json()
    assert len(unread["items"]) == 1
    assert (await second_api.post("/notifications/read-all")).status_code == 204
    assert (await second_api.get("/notifications")).json()["unread_count"] == 0


async def test_cannot_read_a_colleagues_notification(api: Api, second_api: Api) -> None:
    """Same organisation, different recipient: the row is invisible (RLS + service filter)."""
    await api.sign_up("owner@acme.example", org="Acme")
    await invite_and_join(api, second_api, "bo@acme.example", "administrator")
    [owners] = (await api.get("/notifications")).json()["items"]
    r = await second_api.post(f"/notifications/{owners['id']}/read")
    assert r.status_code == 404
    assert (await api.get("/notifications")).json()["unread_count"] == 1
