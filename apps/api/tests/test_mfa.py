"""TOTP two-factor authentication and organisation MFA policy."""

import time
from typing import Any

import pyotp
from sqlalchemy import text

from tests.conftest import PASSWORD, Api


def next_code(secret: str) -> str:
    """A code for the next time step, so it can't collide with one already used."""
    return pyotp.TOTP(secret).at(int(time.time()) + 30)


async def enable_mfa(api: Api) -> tuple[str, list[str]]:
    setup = (await api.post("/auth/mfa/totp/setup")).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/Operon:")
    r = await api.post("/auth/mfa/totp/confirm", json={"code": pyotp.TOTP(setup["secret"]).now()})
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()["recovery_codes"]


async def test_enable_mfa_returns_recovery_codes(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    _, codes = await enable_mfa(api)
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert (await api.get("/users/me")).json()["mfa_enabled"] is True


async def test_secret_is_encrypted_at_rest(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    secret, _ = await enable_mfa(api)
    with owner_engine.connect() as conn:
        stored = conn.execute(text("SELECT secret_encrypted FROM mfa_factors")).scalar_one()
    assert secret not in stored
    assert stored.startswith("v1:")


async def test_wrong_confirmation_code_does_not_enable(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await api.post("/auth/mfa/totp/setup")
    r = await api.post("/auth/mfa/totp/confirm", json={"code": "000000"})
    assert r.status_code == 400
    assert (await api.get("/users/me")).json()["mfa_enabled"] is False


async def test_login_requires_second_factor(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    secret, _ = await enable_mfa(api)
    r = await second_api.post(
        "/auth/login", json={"email": "ana@acme.example", "password": PASSWORD}
    )
    assert r.json() == {"status": "mfa_required"}
    assert "operon_session" not in second_api.http.cookies
    assert (await second_api.get("/users/me")).status_code == 401

    bad = await second_api.post("/auth/login/mfa", json={"code": "123456"})
    assert bad.status_code == 401
    ok = await second_api.post("/auth/login/mfa", json={"code": next_code(secret)})
    assert ok.json() == {"status": "authenticated"}
    assert (await second_api.get("/users/me")).status_code == 200


async def test_totp_codes_cannot_be_replayed(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    secret, _ = await enable_mfa(api)
    code = next_code(secret)
    await second_api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    assert (await second_api.post("/auth/login/mfa", json={"code": code})).status_code == 200
    await second_api.post("/auth/logout")
    await second_api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    replay = await second_api.post("/auth/login/mfa", json={"code": code})
    assert replay.status_code == 401


async def test_recovery_codes_are_single_use(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    _, codes = await enable_mfa(api)
    await second_api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    assert (await second_api.post("/auth/login/mfa", json={"code": codes[0]})).status_code == 200
    await second_api.post("/auth/logout")
    await second_api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    assert (await second_api.post("/auth/login/mfa", json={"code": codes[0]})).status_code == 401
    assert (await second_api.post("/auth/login/mfa", json={"code": codes[1]})).status_code == 200


async def test_mfa_challenge_is_rate_limited(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await enable_mfa(api)
    await second_api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    statuses = [
        (await second_api.post("/auth/login/mfa", json={"code": "000000"})).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


async def test_mfa_step_without_password_step_fails(second_api: Api) -> None:
    r = await second_api.post("/auth/login/mfa", json={"code": "123456"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "mfa_challenge_expired"


async def test_disable_mfa_requires_password_and_code(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    secret, _ = await enable_mfa(api)
    wrong_pw = await api.post(
        "/auth/mfa/totp/disable", json={"password": "wrong-password", "code": next_code(secret)}
    )
    assert wrong_pw.status_code == 400
    ok = await api.post(
        "/auth/mfa/totp/disable", json={"password": PASSWORD, "code": next_code(secret)}
    )
    assert ok.status_code == 204
    assert (await api.get("/users/me")).json()["mfa_enabled"] is False


async def test_organisation_mfa_policy(api: Api, second_api: Api) -> None:
    org = await api.sign_up("owner@acme.example")
    # The owner can't impose MFA before having it (would lock themselves out).
    r = await api.patch("/organisations/current", json={"mfa_required": True})
    assert r.status_code == 409
    await enable_mfa(api)
    assert (
        await api.patch("/organisations/current", json={"mfa_required": True})
    ).status_code == 200

    # A member without MFA is blocked from the workspace until they enable it.
    invite = await api.post("/invitations", json={"email": "bo@acme.example", "role_key": "viewer"})
    assert invite.status_code == 201
    token = api.last_link_token("bo@acme.example", "/invite")
    await second_api.post(
        "/auth/register",
        json={
            "email": "bo@acme.example",
            "password": PASSWORD,
            "full_name": "Bo",
            "invitation_token": token,
        },
    )
    await second_api.login("bo@acme.example")
    second_api.org_id = org
    blocked = await second_api.get("/organisations/current")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "mfa_required"
    await enable_mfa(second_api)
    assert (await second_api.get("/organisations/current")).status_code == 200
