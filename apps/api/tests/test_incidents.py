"""Incidents: escalation from insights, assignment, timeline, time-based escalation (plan §4.6)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from operon.modules.incidents.service import escalate_overdue
from tests.conftest import Api
from tests.helpers import error_code, invite_and_join, seed_operations


async def overdue_insight(api: Api) -> dict[str, Any]:
    items = (await api.get("/insights")).json()["items"]
    return next(i for i in items if i["rule_id"] == "procurement.po_overdue")


async def test_overdue_po_escalates_to_an_assigned_incident(api: Api, second_api: Api) -> None:
    """Plan §4 acceptance: an overdue PO produces an insight, escalated and assigned."""
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    await invite_and_join(api, second_api, "buyer@acme.example", "operations_manager", "Bea Buyer")
    buyer = (await second_api.get("/users/me")).json()
    insight = await overdue_insight(api)
    assert insight["severity"] == "high"

    r = await api.post(
        f"/insights/{insight['id']}/incident",
        json={"assignee_user_id": buyer["id"], "note": "Chase Brightline today."},
    )
    assert r.status_code == 201, r.text
    incident = r.json()
    assert incident["reference"] == "INC-0001"
    assert (incident["severity"], incident["status"]) == ("high", "open")
    assert incident["assignee"]["full_name"] == "Bea Buyer"
    assert incident["insight"]["id"] == insight["id"]
    assert incident["description"].startswith("Chase Brightline today.")
    assert [e["kind"] for e in incident["events"]] == ["created", "insight_linked", "assigned"]
    due = datetime.fromisoformat(incident["response_due_at"])
    assert timedelta(hours=3, minutes=59) < due - datetime.now(UTC) <= timedelta(hours=4)

    # The insight records the escalation and is acknowledged.
    detail = (await api.get(f"/insights/{insight['id']}")).json()
    assert detail["status"] == "acknowledged"
    assert detail["incident_id"] == incident["id"]
    assert "escalated" in [e["kind"] for e in detail["events"]]
    # The assignee was told.
    notes = (await second_api.get("/notifications")).json()["items"]
    assert any(n["title"].startswith("INC-0001 assigned to you") for n in notes)
    # Escalating again points at the existing incident.
    again = await api.post(f"/insights/{insight['id']}/incident", json={})
    assert (again.status_code, error_code(again)) == (409, "incident_exists")
    assert again.json()["error"]["details"]["incident_id"] == incident["id"]
    audit = [e["action"] for e in (await api.get("/audit", params={"limit": 5})).json()["items"]]
    assert "incident.created" in audit


async def test_lifecycle_comments_and_resolution(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    r = await api.post("/incidents", json={"title": "Dock 3 door jammed", "severity": "medium"})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r = await api.post(f"/incidents/{iid}/comments", json={"body": "Engineer booked for 2pm."})
    assert r.status_code == 201
    assert r.json()["kind"] == "comment"
    r = await api.patch(f"/incidents/{iid}", json={"status": "resolved"})
    assert (r.status_code, error_code(r)) == (422, "resolution_required")
    r = await api.patch(f"/incidents/{iid}", json={"status": "investigating", "severity": "high"})
    assert r.status_code == 200
    assert r.json()["severity"] == "high"
    r = await api.patch(
        f"/incidents/{iid}", json={"status": "resolved", "resolution": "Door motor replaced."}
    )
    body = r.json()
    assert body["status"] == "resolved"
    assert body["resolution"] == "Door motor replaced."
    assert body["allowed_transitions"] == ["investigating"]
    assert [e["kind"] for e in body["events"]] == [
        "created",
        "comment",
        "severity_changed",
        "status_changed",
        "status_changed",
    ]
    # Reopening clears the resolution; the timeline keeps it.
    r = await api.patch(f"/incidents/{iid}", json={"status": "investigating"})
    assert r.json()["resolution"] is None
    assert any(e["body"] == "Door motor replaced." for e in r.json()["events"])
    r = await api.patch(f"/incidents/{iid}", json={"status": "open"})
    assert (r.status_code, error_code(r)) == (409, "invalid_transition")


async def test_assignee_must_be_a_member_and_can_be_cleared(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    iid = (await api.post("/incidents", json={"title": "Scanner down", "severity": "low"})).json()[
        "id"
    ]
    r = await api.patch(
        f"/incidents/{iid}", json={"assignee_user_id": "00000000-0000-0000-0000-000000000009"}
    )
    assert (r.status_code, error_code(r)) == (422, "invalid_assignee")
    me = (await api.get("/users/me")).json()
    r = await api.patch(f"/incidents/{iid}", json={"assignee_user_id": me["id"]})
    assert r.json()["assignee"]["user_id"] == me["id"]
    r = await api.patch(f"/incidents/{iid}", json={"severity": "medium"})
    assert r.json()["assignee"]["user_id"] == me["id"]  # omitted → unchanged
    r = await api.patch(f"/incidents/{iid}", json={"assignee_user_id": None})
    assert r.json()["assignee"] is None
    mine = (await api.get("/incidents", params={"assignee": "none"})).json()
    assert [i["id"] for i in mine["items"]] == [iid]


async def test_unanswered_incidents_escalate_until_someone_investigates(
    api: Api, second_api: Api
) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "ops@acme.example", "operations_manager")
    iid = (
        await api.post("/incidents", json={"title": "Cold store alarm", "severity": "critical"})
    ).json()["id"]
    db = api.app.state.db
    assert await escalate_overdue(db) == 0  # not due yet
    later = datetime.now(UTC) + timedelta(hours=1, minutes=1)
    assert await escalate_overdue(db, now=later) == 1
    assert await escalate_overdue(db, now=later) == 0  # idempotent: next due in an hour
    detail = (await api.get(f"/incidents/{iid}")).json()
    assert detail["escalation_level"] == 1
    assert detail["events"][-1]["kind"] == "escalated"
    notes = (await second_api.get("/notifications")).json()["items"]
    assert any(n["title"].startswith("Escalated: INC-0001") for n in notes)
    # Escalations stop at three.
    for hours in (3, 5, 7):
        await escalate_overdue(db, now=datetime.now(UTC) + timedelta(hours=hours))
    assert (await api.get(f"/incidents/{iid}")).json()["escalation_level"] == 3
    # Investigating stops escalation.
    iid2 = (await api.post("/incidents", json={"title": "Second", "severity": "critical"})).json()[
        "id"
    ]
    await api.patch(f"/incidents/{iid2}", json={"status": "investigating"})
    await escalate_overdue(db, now=datetime.now(UTC) + timedelta(hours=2))
    assert (await api.get(f"/incidents/{iid2}")).json()["escalation_level"] == 0


async def test_incident_permissions(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    iid = (await api.post("/incidents", json={"title": "Forklift", "severity": "low"})).json()["id"]
    await invite_and_join(api, second_api, "analyst@acme.example", "analyst")
    assert (await second_api.get(f"/incidents/{iid}")).status_code == 200
    for method, path, body in [
        ("POST", "/incidents", {"title": "x" * 5, "severity": "low"}),
        ("PATCH", f"/incidents/{iid}", {"status": "investigating"}),
        ("POST", f"/incidents/{iid}/comments", {"body": "hi"}),
    ]:
        r = await second_api.request(method, path, json=body)
        assert r.status_code == 403, (method, path)


async def test_list_orders_by_severity_and_counts_unresolved(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    for title, sev in [("Low one", "low"), ("Crit one", "critical"), ("Med one", "medium")]:
        await api.post("/incidents", json={"title": title, "severity": sev})
    body = (await api.get("/incidents")).json()
    assert [i["severity"] for i in body["items"]] == ["critical", "medium", "low"]
    assert body["unresolved_by_severity"] == {"critical": 1, "medium": 1, "low": 1}
    assert body["total"] == 3
