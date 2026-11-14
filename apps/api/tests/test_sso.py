"""Single sign-on (OIDC): configuration, domain proof, sign-in, and the checks that matter."""

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from operon.main import create_app
from operon.modules.sso import service as sso
from tests.conftest import Api, AppFactory, make_settings
from tests.fakes.idp import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdP
from tests.helpers import another_client, error_code


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
async def sapi(
    api_factory: AppFactory, idp: FakeIdP, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Api]:
    txt: dict[str, list[str]] = {}

    async def lookup(name: str) -> list[str]:
        return txt.get(name, [])

    monkeypatch.setattr(sso, "lookup_txt", lookup)
    app = create_app(make_settings(web_base_url="https://app.operon.test"))
    app.state.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    async with api_factory(app) as a:
        a.txt = txt  # type: ignore[attr-defined]
        yield a


async def configure(
    api: Api, *, enforce: bool = False, jit: bool = True, verify: bool = True
) -> None:
    r = await api.put(
        "/organisations/current/sso",
        json={
            "issuer": ISSUER,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "enabled": True,
            "jit_provisioning": jit,
        },
    )
    assert r.status_code == 200, r.text
    d = (
        await api.post("/organisations/current/sso/domains", json={"domain": "acme.example"})
    ).json()
    if verify:
        api.txt[d["txt_name"]] = [d["txt_value"]]  # type: ignore[attr-defined]
        r = await api.post("/organisations/current/sso/domains/acme.example/verify")
        assert r.json()["verified"] is True
    if enforce:
        body = {
            "issuer": ISSUER,
            "client_id": CLIENT_ID,
            "enabled": True,
            "enforce": True,
            "jit_provisioning": jit,
        }
        assert (await api.put("/organisations/current/sso", json=body)).status_code == 200


async def sso_sign_in(
    browser: Api, idp: FakeIdP, login: str = "pat@acme.example", **claims: Any
) -> httpx.Response:
    r = await browser.post("/auth/sso/start", json={"email": login})
    assert r.status_code == 200, r.text
    url = r.json()["redirect_url"]
    assert url.startswith(f"{ISSUER}/authorize?")
    code = idp.authorize(url, **claims)
    state = url.split("state=", 1)[1].split("&", 1)[0]
    return await browser.get(f"/auth/sso/callback?code={code}&state={state}")


async def test_configuration_requires_proof_of_domain(sapi: Api) -> None:
    await sapi.sign_up("owner@acme.example")
    r = await sapi.put(
        "/organisations/current/sso",
        json={"issuer": ISSUER, "client_id": CLIENT_ID, "enabled": True},
    )
    assert (r.status_code, error_code(r)) == (422, "secret_required")
    r = await sapi.put(
        "/organisations/current/sso",
        json={
            "issuer": "https://idp.test/wrong",
            "client_id": CLIENT_ID,
            "client_secret": "s",
            "enabled": True,
        },
    )
    assert error_code(r) in ("discovery_failed", "issuer_mismatch")
    await configure(sapi, verify=False)
    r = await sapi.post("/organisations/current/sso/domains", json={"domain": "gmail.com"})
    assert (r.status_code, error_code(r)) == (422, "public_domain")
    r = await sapi.post("/organisations/current/sso/domains/acme.example/verify")
    assert (r.status_code, error_code(r)) == (422, "not_verified")
    body = {"issuer": ISSUER, "client_id": CLIENT_ID, "enabled": True, "enforce": True}
    r = await sapi.put("/organisations/current/sso", json=body)
    assert (r.status_code, error_code(r)) == (422, "enforce_requires_domain")
    # Unverified domains don't route anyone.
    r = await sapi.post("/auth/sso/start", json={"email": "pat@acme.example"})
    assert (r.status_code, error_code(r)) == (404, "sso_not_configured")
    config = (await sapi.get("/organisations/current/sso")).json()
    assert config["has_client_secret"] is True
    assert "client_secret" not in config
    assert config["redirect_uri"] == "https://app.operon.test/api/v1/auth/sso/callback"


async def test_a_verified_domain_cannot_be_claimed_by_another_organisation(sapi: Api) -> None:
    await sapi.sign_up("owner@acme.example", org="Acme")
    await configure(sapi)
    async with another_client(sapi) as rival:
        await rival.sign_up("evil@rival.example", org="Rival")
        await rival.put(
            "/organisations/current/sso",
            json={
                "issuer": ISSUER,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "enabled": True,
            },
        )
        r = await rival.post("/organisations/current/sso/domains", json={"domain": "acme.example"})
        assert (r.status_code, error_code(r)) == (409, "domain_taken")


async def test_sign_in_provisions_a_member_and_links_their_identity(
    sapi: Api, idp: FakeIdP
) -> None:
    await sapi.sign_up("owner@acme.example")
    org = sapi.org_id
    await configure(sapi)
    async with another_client(sapi) as pat:
        r = await sso_sign_in(pat, idp)
        assert r.status_code == 303
        assert r.headers["location"] == f"https://app.operon.test/overview?org={org}"
        session = (await pat.get("/auth/session")).json()
        assert session["user"]["email"] == "pat@acme.example"
        assert [(o["name"], o["role_key"]) for o in session["organisations"]] == [
            ("Acme Distribution", "viewer")
        ]
        # PKCE verifier sent to the provider; state is single-use.
        assert idp.token_requests[-1]["code_verifier"]
        await pat.post("/auth/logout")
        r = await sso_sign_in(pat, idp, login="PAT@acme.example")
        assert r.status_code == 303
        assert "sso_error" not in r.headers["location"]
    members = [m["email"] for m in (await sapi.get("/members")).json()]
    assert members.count("pat@acme.example") == 1
    audit = (await sapi.get("/audit", params={"limit": 20})).json()["items"]
    joined = [e for e in audit if e["action"] == "member.joined"]
    assert joined
    assert joined[0]["details"]["via"] == "sso"


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"email": "pat@elsewhere.example"}, "domain_not_allowed"),
        ({"email_verified": False}, "email_not_verified"),
        ({"nonce": "replayed"}, "sso_failed"),
        ({"aud": "someone-else"}, "sso_failed"),
        ({"iss": "https://evil.test"}, "sso_failed"),
        ({"exp": int(time.time()) - 3600}, "sso_failed"),
    ],
)
async def test_untrustworthy_tokens_are_refused(
    sapi: Api, idp: FakeIdP, claims: dict[str, Any], error: str
) -> None:
    await sapi.sign_up("owner@acme.example")
    await configure(sapi)
    async with another_client(sapi) as pat:
        r = await sso_sign_in(pat, idp, **claims)
        assert r.headers["location"].endswith(f"/login?sso_error={error}")
        assert (await pat.get("/auth/session")).json()["user"] is None


async def test_forged_signature_and_reused_state_are_refused(sapi: Api, idp: FakeIdP) -> None:
    await sapi.sign_up("owner@acme.example")
    await configure(sapi)
    async with another_client(sapi) as pat:
        r = await pat.post("/auth/sso/start", json={"email": "pat@acme.example"})
        url = r.json()["redirect_url"]
        code = idp.authorize(url)
        attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        idp.codes[code]["token"] = idp.sign(idp.codes[code]["claims"], key=attacker)
        state = url.split("state=", 1)[1].split("&", 1)[0]
        r = await pat.get(f"/auth/sso/callback?code={code}&state={state}")
        assert r.headers["location"].endswith("sso_error=sso_failed")
        r = await pat.get(f"/auth/sso/callback?code={code}&state={state}")
        assert r.headers["location"].endswith("sso_error=sso_state_invalid")


async def test_a_sign_in_cannot_be_completed_in_another_browser(sapi: Api, idp: FakeIdP) -> None:
    """Login CSRF: an attacker starts SSO with their own account and sends the victim the
    callback link. Without the starting browser's binding cookie it must be refused."""
    await sapi.sign_up("owner@acme.example")
    await configure(sapi)
    async with another_client(sapi) as attacker, another_client(sapi) as victim:
        r = await attacker.post("/auth/sso/start", json={"email": "pat@acme.example"})
        url = r.json()["redirect_url"]
        code = idp.authorize(url)
        state = url.split("state=", 1)[1].split("&", 1)[0]
        r = await victim.get(f"/auth/sso/callback?code={code}&state={state}")
        assert r.headers["location"].endswith("sso_error=sso_state_invalid")
        assert "operon_session" not in r.headers.get("set-cookie", "")
        # The state is single-use: the attacker can't complete it afterwards either.
        r = await attacker.get(f"/auth/sso/callback?code={code}&state={state}")
        assert r.headers["location"].endswith("sso_error=sso_state_invalid")


async def test_without_jit_only_existing_members_get_in(sapi: Api, idp: FakeIdP) -> None:
    await sapi.sign_up("owner@acme.example")
    await configure(sapi, jit=False)
    async with another_client(sapi) as pat:
        r = await sso_sign_in(pat, idp)
        assert r.headers["location"].endswith("sso_error=not_a_member")


async def test_enforced_sso_blocks_passwords_except_for_owners(sapi: Api, idp: FakeIdP) -> None:
    from tests.helpers import invite_and_join

    await sapi.sign_up("owner@acme.example")
    async with another_client(sapi) as ana:
        await invite_and_join(sapi, ana, "ana@acme.example", "analyst")
        await configure(sapi, enforce=True)
        await ana.post("/auth/logout")
        r = await ana.post(
            "/auth/login", json={"email": "ana@acme.example", "password": "whatever-it-is-1"}
        )
        assert (r.status_code, error_code(r)) == (403, "sso_required")
    await sapi.post("/auth/logout")
    await sapi.login("owner@acme.example")  # break-glass: owners keep password sign-in
