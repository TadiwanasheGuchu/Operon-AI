"""Registration, verification, login, sessions, password reset and CSRF."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from tests.conftest import PASSWORD, Api


async def test_full_sign_up_journey(api: Api) -> None:
    org_id = await api.sign_up("ana@acme.example", org="Acme Distribution", name="Ana Silva")
    session = (await api.get("/auth/session")).json()
    assert session["user"]["email"] == "ana@acme.example"
    assert session["user"]["email_verified"] is True
    assert session["organisations"] == [
        {
            "id": org_id,
            "name": "Acme Distribution",
            "role_key": "owner",
            "role_name": "Owner",
            "mfa_required": False,
            "is_demo": False,
        }
    ]


async def test_signed_out_session_is_not_an_error(api: Api) -> None:
    r = await api.get("/auth/session")
    assert r.status_code == 200
    assert r.json() == {"user": None, "organisations": []}


async def test_email_is_normalised(api: Api) -> None:
    await api.sign_up("Ana@ACME.example")
    assert (await api.get("/users/me")).json()["email"] == "ana@acme.example"


async def test_cannot_sign_in_before_verifying(api: Api) -> None:
    await api.post(
        "/auth/register",
        json={
            "email": "u@x.example",
            "password": PASSWORD,
            "full_name": "U",
            "organisation_name": "X",
        },
    )
    r = await api.post("/auth/login", json={"email": "u@x.example", "password": PASSWORD})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_not_verified"


async def test_unverified_state_not_revealed_without_password(api: Api) -> None:
    await api.post(
        "/auth/register",
        json={
            "email": "u@x.example",
            "password": PASSWORD,
            "full_name": "U",
            "organisation_name": "X",
        },
    )
    r = await api.post("/auth/login", json={"email": "u@x.example", "password": "wrong password!"})
    assert r.status_code == 401


async def test_registration_does_not_reveal_existing_accounts(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    before = len(api.outbox)
    r = await api.post(
        "/auth/register",
        json={
            "email": "ana@acme.example",
            "password": PASSWORD,
            "full_name": "Impostor",
            "organisation_name": "X",
        },
    )
    assert r.status_code == 202
    assert r.json()["message"].startswith("If the details are valid")
    notice = api.outbox[before]
    assert notice.subject == "Someone tried to register with your email"


async def test_wrong_and_unknown_credentials_look_identical(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    wrong = await api.post(
        "/auth/login", json={"email": "ana@acme.example", "password": "nope-nope-nope"}
    )
    unknown = await api.post(
        "/auth/login", json={"email": "no@one.example", "password": "nope-nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_failed_login_is_audited_despite_rollback(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    await api.post("/auth/login", json={"email": "ana@acme.example", "password": "nope-nope-nope"})
    with owner_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT outcome, host(ip_address) FROM audit_logs WHERE action = 'auth.login_failed'"
            )
        ).one()
    assert row == ("failure", "203.0.113.10")


async def test_login_is_rate_limited_per_email(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    codes = [
        (
            await api.post(
                "/auth/login", json={"email": "ana@acme.example", "password": "wrong-password"}
            )
        ).status_code
        for _ in range(9)
    ]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429
    # Even the right password is refused while locked.
    r = await api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    assert r.status_code == 429
    assert r.json()["error"]["details"]["retry_after_seconds"] > 0


async def test_session_cookie_is_hardened(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    r = await api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    cookie = next(
        v
        for k, v in r.headers.multi_items()
        if k == "set-cookie" and v.startswith("operon_session=")
    )
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie


async def test_session_tokens_are_stored_hashed(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    token = api.http.cookies["operon_session"]
    with owner_engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM user_sessions")).scalars().all()
    assert token not in stored
    assert all(len(h) == 64 for h in stored)


async def test_logout_revokes_the_session(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    token = api.http.cookies["operon_session"]
    assert (await api.post("/auth/logout")).status_code == 204
    api.http.cookies.set("operon_session", token)  # replaying the old cookie must not work
    assert (await api.get("/users/me")).status_code == 401


async def test_idle_sessions_expire(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE user_sessions SET last_seen_at = :t"),
            {"t": datetime.now(UTC) - timedelta(hours=2)},
        )
    assert (await api.get("/users/me")).status_code == 401


async def test_absolute_session_lifetime(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE user_sessions SET expires_at = now() - interval '1 second'"))
    assert (await api.get("/users/me")).status_code == 401


async def test_password_reset_flow(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await second_api.login("ana@acme.example")
    assert (
        await api.post("/auth/password/forgot", json={"email": "ana@acme.example"})
    ).status_code == 202
    token = api.last_link_token("ana@acme.example", "/reset-password")
    new = "a brand new passphrase"
    assert (
        await api.post("/auth/password/reset", json={"token": token, "password": new})
    ).status_code == 200
    # Every existing session is signed out.
    assert (await api.get("/users/me")).status_code == 401
    assert (await second_api.get("/users/me")).status_code == 401
    # Old password fails, new one works, the link is single-use.
    assert (
        await api.post("/auth/login", json={"email": "ana@acme.example", "password": PASSWORD})
    ).status_code == 401
    await api.login("ana@acme.example", new)
    again = await api.post(
        "/auth/password/reset", json={"token": token, "password": "another one here"}
    )
    assert again.status_code == 400


async def test_forgot_password_for_unknown_email_looks_the_same(api: Api) -> None:
    r = await api.post("/auth/password/forgot", json={"email": "nobody@x.example"})
    assert r.status_code == 202
    assert api.outbox == []


async def test_expired_reset_link_is_refused(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    await api.post("/auth/password/forgot", json={"email": "ana@acme.example"})
    token = api.last_link_token("ana@acme.example", "/reset-password")
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE user_action_tokens SET expires_at = now() - interval '1 second'"))
    r = await api.post(
        "/auth/password/reset", json={"token": token, "password": "a brand new passphrase"}
    )
    assert r.status_code == 400


async def test_change_password_keeps_current_session_only(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await second_api.login("ana@acme.example")
    bad = await api.post(
        "/auth/password/change", json={"current_password": "wrong-one!", "new_password": "x" * 14}
    )
    assert bad.status_code == 400
    ok = await api.post(
        "/auth/password/change",
        json={"current_password": PASSWORD, "new_password": "fresh passphrase 2"},
    )
    assert ok.status_code == 204
    assert (await api.get("/users/me")).status_code == 200
    assert (await second_api.get("/users/me")).status_code == 401


async def test_short_passwords_are_rejected(api: Api) -> None:
    r = await api.post(
        "/auth/register",
        json={
            "email": "u@x.example",
            "password": "short",
            "full_name": "U",
            "organisation_name": "X",
        },
    )
    assert r.status_code == 422


async def test_list_and_revoke_sessions(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await second_api.login("ana@acme.example")
    sessions = (await api.get("/auth/sessions")).json()
    assert len(sessions) == 2
    other = next(s for s in sessions if not s["current"])
    assert (await api.delete(f"/auth/sessions/{other['id']}")).status_code == 204
    assert (await second_api.get("/users/me")).status_code == 401


async def test_cannot_revoke_someone_elses_session(api: Api, second_api: Api) -> None:
    await api.sign_up("ana@acme.example")
    await second_api.sign_up("bo@beta.example", org="Beta")
    theirs = (await second_api.get("/auth/sessions")).json()[0]["id"]
    assert (await api.delete(f"/auth/sessions/{theirs}")).status_code == 404


async def test_state_changes_require_csrf_token(api: Api) -> None:
    await api.sign_up("ana@acme.example")
    r = await api.http.patch(
        "/api/v1/users/me", json={"full_name": "Hijacked"}, headers={"X-CSRF-Token": "forged"}
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    r = await api.http.patch("/api/v1/users/me", json={"full_name": "Hijacked"})
    assert r.status_code == 403
    assert (await api.get("/users/me")).json()["full_name"] == "Test User"


async def test_profile_update_is_audited(api: Api, owner_engine: Any) -> None:
    await api.sign_up("ana@acme.example")
    r = await api.patch("/users/me", json={"full_name": "Ana Silva"})
    assert r.json()["full_name"] == "Ana Silva"
    with owner_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'user.profile_updated'")
            ).scalar()
            == 1
        )
