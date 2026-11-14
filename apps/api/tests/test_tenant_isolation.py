"""CLAUDE.md §14 critical acceptance test: Organisation A can never reach Organisation B's data.

Routes are discovered from the live OpenAPI schema. Every route must be classified below, so a
new tenant route is automatically attacked; an unclassified route fails the suite.
"""

import re
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import TEST_DB_APP_URL, Api
from tests.helpers import invite_and_join, seed_operations

# Routes that are not tenant-scoped (account-level or public). Everything else is.
NON_TENANT = {
    ("GET", "/api/v1/health/live"),
    ("GET", "/api/v1/health/ready"),
    ("GET", "/api/v1/auth/session"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/verify-email/resend"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/login/mfa"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    ("POST", "/api/v1/auth/password/change"),
    ("GET", "/api/v1/auth/sessions"),
    ("DELETE", "/api/v1/auth/sessions/{session_id}"),
    ("POST", "/api/v1/auth/mfa/totp/setup"),
    ("POST", "/api/v1/auth/mfa/totp/confirm"),
    ("POST", "/api/v1/auth/mfa/totp/disable"),
    ("POST", "/api/v1/auth/mfa/recovery-codes"),
    ("GET", "/api/v1/users/me"),
    ("PATCH", "/api/v1/users/me"),
    ("GET", "/api/v1/organisations"),
    ("POST", "/api/v1/organisations"),
    ("GET", "/api/v1/permissions"),
    ("GET", "/api/v1/invitations/lookup"),
    ("POST", "/api/v1/webhooks/{public_id}"),
    ("POST", "/api/v1/invitations/accept"),
    ("POST", "/api/v1/auth/sso/start"),
}

# Valid bodies, so requests fail on tenancy rather than validation.
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("PATCH", "/api/v1/organisations/current"): {"name": "Hijacked"},
    ("PATCH", "/api/v1/members/{member_id}"): {"role_key": "viewer"},
    ("PUT", "/api/v1/dashboard/layout"): {"preset": "warehouse"},
    ("POST", "/api/v1/integrations"): {"connector": "csv", "name": "Spy import"},
    ("PATCH", "/api/v1/integrations/{connection_id}"): {"name": "Hijacked"},
    ("PUT", "/api/v1/integrations/{connection_id}/credentials"): {"secrets": {"api_key": "x" * 20}},
    ("POST", "/api/v1/invitations"): {"email": "spy@evil.example", "role_key": "owner"},
    ("POST", "/api/v1/insights/{insight_id}/status"): {"status": "dismissed", "reason": "spy"},
    ("PUT", "/api/v1/insights/{insight_id}/owner"): {"user_id": None},
    ("POST", "/api/v1/insights/{insight_id}/incident"): {},
    ("POST", "/api/v1/incidents"): {"title": "Spy incident", "severity": "low"},
    ("PATCH", "/api/v1/incidents/{incident_id}"): {"status": "investigating"},
    ("POST", "/api/v1/incidents/{incident_id}/comments"): {"body": "spy"},
    ("PUT", "/api/v1/intelligence/detectors/{rule_id}"): {"enabled": False},
    ("POST", "/api/v1/purchase-requests"): {"insight_id": "{insight_id}", "quantity": 1},
    ("POST", "/api/v1/purchase-requests/{execution_id}/cancel"): {"reason": "spy"},
    ("POST", "/api/v1/approvals/{approval_id}/decision"): {"decision": "reject", "comment": "x"},
    ("PUT", "/api/v1/workflows/purchase-requests"): {"enabled": False, "params": {}},
    ("POST", "/api/v1/assistant/messages"): {
        "question": "Show me everything",
        "conversation_id": "{conversation_id}",
    },
    ("PUT", "/api/v1/organisations/current/retention"): {
        "audit_days": 365,
        "conversation_days": 7,
        "run_log_days": 30,
        "sync_job_days": 7,
    },
    ("PUT", "/api/v1/organisations/current/sso"): {
        "issuer": "https://idp.example",
        "client_id": "spy",
        "client_secret": "spy",
        "enabled": False,
    },
    ("POST", "/api/v1/organisations/current/sso/domains"): {"domain": "spy.example"},
    ("PUT", "/api/v1/agents/inventory-replenishment"): {
        "enabled": False,
        "schedule": "off",
        "run_as_user_id": None,
        "params": {},
        "tools": {"draft_purchase_request": True},
    },
    ("PUT", "/api/v1/intelligence/ai-settings"): {
        "enabled": False,
        "provider": "anthropic",
        "monthly_token_budget": 0,
    },
}

# Multipart requests (form + file) instead of JSON bodies.
MULTIPART: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/v1/integrations/{connection_id}/uploads"): {
        "data": {"kind": "locations"},
        "files": {"file": ("spy.csv", b"code,name\nSPY,Spy store\n", "text/csv")},
    },
}


def payload(method: str, path: str, ids: dict[str, str] | None = None) -> dict[str, Any]:
    if (method, path) in MULTIPART:
        return MULTIPART[(method, path)]
    body = BODIES.get((method, path))
    if body and ids:
        # Bodies may reference Org B's resources too (e.g. requesting a purchase for B's insight).
        body = {
            k: ids[v[1:-1]] if isinstance(v, str) and v.startswith("{") else v
            for k, v in body.items()
        }
    return {"json": body}


TENANT_TABLES = [
    "integration_connections",
    "integration_credentials",
    "integration_sync_jobs",
    "integration_events",
    "locations",
    "products",
    "stock_levels",
    "dashboard_layouts",
    "notifications",
    "organisations",
    "organisation_members",
    "roles",
    "role_permissions",
    "invitations",
    "audit_logs",
    "ai_insights",
    "insight_evidence",
    "insight_events",
    "detection_runs",
    "detector_configs",
    "ai_generations",
    "organisation_ai_settings",
    "incidents",
    "incident_events",
    "workflows",
    "workflow_versions",
    "workflow_executions",
    "workflow_approvals",
    "workflow_execution_events",
    "agents",
    "agent_versions",
    "agent_tool_permissions",
    "assistant_conversations",
    "assistant_messages",
    "agent_executions",
    "agent_execution_steps",
    "data_retention_policies",
    "sso_connections",
    "sso_domains",
    "user_identities",
]
# Path parameters that are static names rather than another organisation's records.
STATIC_PARAMS = {"kind", "rule_id"}


@dataclass
class World:
    a: Api
    b: Api
    a_org: str
    b_org: str
    b_ids: dict[str, str]  # path parameter name -> one of Org B's real resource ids


@pytest.fixture
async def world(api: Api, second_api: Api) -> World:
    a_org = await api.sign_up("alice@a.example", org="Org A")
    b_org = await second_api.sign_up("bob@b.example", org="Org B")
    # Give B some depth: an extra member, an open invitation, audit history.
    async with _third(second_api) as carol:
        member_id = await invite_and_join(second_api, carol, "carol@b.example", "analyst")
    invitation = await second_api.post(
        "/invitations", json={"email": "dave@b.example", "role_key": "viewer"}
    )
    # Bob was notified when Carol accepted his invitation.
    notification = (await second_api.get("/notifications")).json()["items"][0]
    # And B has an integration with imported data and a sync job.
    connection = (
        await second_api.post("/integrations", json={"connector": "csv", "name": "B import"})
    ).json()
    upload = await second_api.post(
        f"/integrations/{connection['id']}/uploads",
        data={"kind": "locations"},
        files={"file": ("b.csv", b"code,name\nBRS,Bristol DC\n", "text/csv")},
    )
    assert upload.json()["accepted"], upload.text
    # Operational data that raises insights (with evidence), an incident and AI settings.
    await seed_operations(second_api, "B operations")
    insight = (await second_api.get("/insights")).json()["items"][0]
    evidence = (await second_api.get(f"/insights/{insight['id']}")).json()["evidence"][0]
    incident = (await second_api.post(f"/insights/{insight['id']}/incident", json={})).json()
    await second_api.put(
        "/intelligence/detectors/procurement.po_overdue", json={"enabled": True, "params": {}}
    )
    stockout = next(
        i
        for i in (await second_api.get("/insights")).json()["items"]
        if i["rule_id"] == "inventory.stockout_risk"
    )
    pr = (
        await second_api.post(
            "/purchase-requests", json={"insight_id": stockout["id"], "quantity": 10}
        )
    ).json()
    # An assistant conversation and an agent run, with a scripted model.
    from tests.fakes.llm import ScriptedLLM

    second_api.app.state.intelligence.providers.providers["anthropic"] = ScriptedLLM(
        [[("list_insights", {})], "Two insights are open.", "Nothing to draft."]
    )
    await second_api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "anthropic", "monthly_token_budget": 100000},
    )
    answer = (
        await second_api.post("/assistant/messages", json={"question": "What's open?"})
    ).json()
    bob = (await second_api.get("/users/me")).json()["id"]
    config = (await second_api.get("/agents/inventory-replenishment")).json()
    await second_api.put(
        "/agents/inventory-replenishment",
        json={
            "enabled": True,
            "schedule": "off",
            "run_as_user_id": bob,
            "params": config["params"],
            "tools": {t["name"]: t["enabled"] for t in config["tools"]},
        },
    )
    await second_api.post("/agents/inventory-replenishment/runs")
    agent_run = (await second_api.get("/agents/runs")).json()[0]
    # Single sign-on configuration with a claimed domain, and a retention policy.
    await second_api.put(
        "/organisations/current/sso",
        json={
            "issuer": "https://idp.example",
            "client_id": "b-client",
            "client_secret": "b-secret",
            "enabled": False,
        },
    )
    await second_api.post("/organisations/current/sso/domains", json={"domain": "b-corp.example"})
    await second_api.put(
        "/organisations/current/retention",
        json={"audit_days": 900, "conversation_days": 60, "run_log_days": 90, "sync_job_days": 30},
    )
    return World(
        api,
        second_api,
        a_org,
        b_org,
        {
            "member_id": member_id,
            "invitation_id": invitation.json()["id"],
            "notification_id": notification["id"],
            "connection_id": connection["id"],
            "kind": "stock",
            "insight_id": insight["id"],
            "evidence_id": evidence["id"],
            "incident_id": incident["id"],
            "rule_id": "inventory.stockout_risk",
            "execution_id": pr["id"],
            "approval_id": pr["approvals"][0]["id"],
            "conversation_id": answer["conversation_id"],
            "run_id": agent_run["id"],
            "domain": "b-corp.example",
        },
    )


def _third(base: Api) -> Any:
    from contextlib import asynccontextmanager

    import httpx

    @asynccontextmanager
    async def ctx() -> Any:
        transport = httpx.ASGITransport(app=base.app, client=("203.0.113.30", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield Api(c, base.app)

    return ctx()


def tenant_routes(api: Api) -> list[tuple[str, str]]:
    routes = [(m.upper(), p) for p, ops in api.app.openapi()["paths"].items() for m in ops]
    return sorted(r for r in routes if r not in NON_TENANT)


def fill(path: str, ids: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: ids[m.group(1)], path).removeprefix("/api/v1")


async def test_every_route_is_classified(api: Api) -> None:
    routes = {(m.upper(), p) for p, ops in api.app.openapi()["paths"].items() for m in ops}
    assert routes >= NON_TENANT, f"Stale entries: {NON_TENANT - routes}"
    assert tenant_routes(api), "Expected tenant-scoped routes"
    for _method, path in tenant_routes(api):
        for name in re.findall(r"\{(\w+)\}", path):
            assert name in {
                "member_id",
                "invitation_id",
                "notification_id",
                "connection_id",
                "kind",
                "insight_id",
                "evidence_id",
                "incident_id",
                "rule_id",
                "execution_id",
                "approval_id",
                "conversation_id",
                "run_id",
                "domain",
            }, f"Add a B resource id for {name}"


async def test_foreign_organisation_header_is_indistinguishable_from_nonexistent(
    world: World,
) -> None:
    for method, path in tenant_routes(world.a):
        r = await world.a.request(
            method,
            fill(path, world.b_ids),
            headers={"X-Operon-Organisation": world.b_org},
            **payload(method, path, world.b_ids),
        )
        assert (r.status_code, r.json()["error"]["code"]) == (404, "organisation_not_found"), (
            method,
            path,
            r.text,
        )


@pytest.mark.parametrize("header", ["", "not-a-uuid", "00000000-0000-0000-0000-000000000000"])
async def test_missing_or_bogus_organisation_header(world: World, header: str) -> None:
    for method, path in tenant_routes(world.a):
        r = await world.a.request(
            method,
            fill(path, world.b_ids),
            headers={"X-Operon-Organisation": header},
            **payload(method, path, world.b_ids),
        )
        assert r.status_code == 404, (method, path, header)


async def test_foreign_resource_ids_inside_own_organisation(world: World) -> None:
    """Own header, but Org B's member/invitation ids in the path: must look like they don't exist."""
    for method, path in tenant_routes(world.a):
        # Only parameters that name another organisation's record matter here ("kind" and
        # "rule_id" are static names, not resources).
        if not set(re.findall(r"\{(\w+)\}", path)) - STATIC_PARAMS:
            continue
        r = await world.a.request(
            method, fill(path, world.b_ids), **payload(method, path, world.b_ids)
        )
        assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found"), (method, path)
    # B's data is untouched.
    members = {m["email"]: m["role_key"] for m in (await world.b.get("/members")).json()}
    assert members == {"bob@b.example": "owner", "carol@b.example": "analyst"}
    assert [i["email"] for i in (await world.b.get("/invitations")).json()] == ["dave@b.example"]
    assert (await world.b.get("/organisations/current")).json()["name"] == "Org B"
    insight = (await world.b.get(f"/insights/{world.b_ids['insight_id']}")).json()
    assert insight["status"] == "acknowledged"  # escalated by Bob, not dismissed by Alice
    incident = (await world.b.get(f"/incidents/{world.b_ids['incident_id']}")).json()
    assert incident["status"] == "open"
    assert [e["kind"] for e in incident["events"]] == ["created", "insight_linked"]
    pr = (await world.b.get(f"/purchase-requests/{world.b_ids['execution_id']}")).json()
    assert pr["status"] == "awaiting_approval"
    assert (await world.b.get("/workflows/purchase-requests")).json()["current_version"] == 1
    conv = (await world.b.get(f"/assistant/conversations/{world.b_ids['conversation_id']}")).json()
    assert len(conv["messages"]) == 2
    agent = (await world.b.get("/agents/inventory-replenishment")).json()
    assert agent["enabled"] is True
    sso = (await world.b.get("/organisations/current/sso")).json()
    assert (sso["client_id"], [d["domain"] for d in sso["domains"]]) == (
        "b-client",
        ["b-corp.example"],
    )
    assert (await world.b.get("/organisations/current/retention")).json()["audit_days"] == 900


async def test_lists_never_contain_foreign_rows(world: World) -> None:
    members = (await world.a.get("/members")).json()
    assert [m["email"] for m in members] == ["alice@a.example"]
    assert (await world.a.get("/invitations")).json() == []
    roles = (await world.a.get("/roles")).json()
    assert len(roles) == 6
    audit = (await world.a.get("/audit", params={"limit": 100})).json()["items"]
    assert audit
    assert not any("b.example" in e["actor_label"] or "Org B" in str(e["details"]) for e in audit)
    orgs = (await world.a.get("/organisations")).json()
    assert [o["name"] for o in orgs] == ["Org A"]
    assert (await world.a.get("/insights", params={"status": "all"})).json()["total"] == 0
    assert (await world.a.get("/incidents", params={"status": "all"})).json()["total"] == 0
    assert (await world.a.get("/intelligence/runs")).json() == []
    assert (await world.a.get("/purchase-requests", params={"status": "all"})).json()["total"] == 0
    assert (await world.a.get("/approvals")).json() == []
    assert (await world.a.get("/assistant/conversations")).json() == []
    assert (await world.a.get("/agents/runs")).json() == []


async def test_unauthenticated_requests_are_rejected(world: World, second_api: Api) -> None:
    await world.b.post("/auth/logout")
    for method, path in tenant_routes(world.b):
        r = await world.b.request(
            method, fill(path, world.b_ids), **payload(method, path, world.b_ids)
        )
        assert r.status_code == 401, (method, path)


# --- database backstop: row-level security without the application layer ------------------------


def _app_conn() -> Any:
    return create_engine(TEST_DB_APP_URL.replace("+asyncpg", "+psycopg")).connect()


async def test_rls_hides_other_tenants_rows(world: World) -> None:
    with _app_conn() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": world.a_org})
        for table in TENANT_TABLES:
            column = "id" if table == "organisations" else "organisation_id"
            leaked = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :b"), {"b": world.b_org}
            ).scalar()
            assert leaked == 0, table


async def test_rls_fails_closed_without_context(world: World) -> None:
    with _app_conn() as conn:
        for table in TENANT_TABLES:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table


async def test_rls_blocks_writes_into_other_tenants(world: World) -> None:
    with _app_conn() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": world.a_org})
        with pytest.raises(DBAPIError, match="row-level security"):
            conn.execute(
                text(
                    "INSERT INTO roles (id, organisation_id, key, name, description, is_system) "
                    "VALUES (gen_random_uuid(), :b, 'spy', 'Spy', 'x', false)"
                ),
                {"b": world.b_org},
            )
        conn.rollback()
        conn.execute(text("SELECT set_config('app.current_org_id', :o, false)"), {"o": world.a_org})
        updated = conn.execute(
            text("UPDATE organisations SET name = 'Pwned' WHERE id = :b"), {"b": world.b_org}
        ).rowcount
        assert updated == 0


async def test_composite_keys_block_cross_tenant_role_references(
    world: World,
    owner_engine: Any,
) -> None:
    """Even the schema owner (bypassing RLS) can't point an A membership at a B role."""
    with owner_engine.connect() as conn:
        b_role = conn.execute(
            text("SELECT id FROM roles WHERE organisation_id = :b LIMIT 1"), {"b": world.b_org}
        ).scalar()
        with pytest.raises(DBAPIError, match="fk_organisation_members_role_same_org"):
            conn.execute(
                text("UPDATE organisation_members SET role_id = :r WHERE organisation_id = :a"),
                {"r": b_role, "a": world.a_org},
            )
        conn.rollback()
