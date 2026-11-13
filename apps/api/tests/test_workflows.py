"""Phase 5 acceptance: approval-gated purchase requests (plan §2 scenario, §5)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from operon.modules.workflows import engine
from tests.conftest import Api, Fakes
from tests.helpers import another_client, error_code, invite_and_join, seed_operations
from tests.test_integrations import ODOO, connect

STOCKOUT = "inventory.stockout_risk"


async def stockout(api: Api) -> dict[str, Any]:
    items = (await api.get("/insights")).json()["items"]
    item = next(i for i in items if i["rule_id"] == STOCKOUT)
    return dict((await api.get(f"/insights/{item['id']}")).json())


def odoo_orders(fakes: Fakes, execution_id: str) -> list[dict[str, Any]]:
    key = engine.idempotency_key(UUID(execution_id))
    return [o for o in fakes.odoo.data["purchase.order"] if o.get("partner_ref") == key]


async def submit(api: Api, insight: dict[str, Any], quantity: int | None = None) -> dict[str, Any]:
    r = await api.post(
        "/purchase-requests",
        json={
            "insight_id": insight["id"],
            "quantity": quantity or insight["recommendation"]["quantity"],
            "note": "Cover next fortnight",
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def decide(api: Api, pr: dict[str, Any], decision: str = "approve", comment: str = "") -> Any:
    approval = next(a for a in pr["approvals"] if a["status"] == "pending")
    return await api.post(
        f"/approvals/{approval['id']}/decision", json={"decision": decision, "comment": comment}
    )


async def test_stockout_to_approved_draft_po_in_odoo(iapi: Api, fakes: Fakes) -> None:
    """The MVP scenario: detect → explain → recommend → request → approve → create → record."""
    await iapi.sign_up("owner@acme.example", name="Olu Owner")
    await connect(iapi, ODOO)
    insight = await stockout(iapi)
    assert insight["recommendation"]["quantity"] == 1736

    pr = await submit(iapi, insight)
    assert pr["reference"] == "PR-0001"
    assert (pr["status"], pr["target"], pr["value_display"]) == (
        "awaiting_approval",
        "odoo",
        "GBP 8,419.60",
    )
    # Under the finance threshold: one stage.
    assert [a["name"] for a in pr["approvals"]] == ["Operations approval"]
    # The requester can't approve their own request.
    assert pr["approvals"][0]["blocked_reason"] == (
        "You requested this, so someone else must approve it."
    )
    r = await decide(iapi, pr)
    assert (r.status_code, error_code(r)) == (403, "cannot_decide")
    # Nothing reaches Odoo before approval.
    assert odoo_orders(fakes, pr["id"]) == []
    assert ("purchase.order", "create") not in fakes.odoo.calls

    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager", "Ola Ops")
        inbox = (await ops.get("/approvals", params={"actionable": True})).json()
        assert [i["execution"]["reference"] for i in inbox] == ["PR-0001"]
        r = await decide(ops, pr, comment="Agreed, stock is critical.")
        assert r.status_code == 200, r.text

    done = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert done["status"] == "completed", done
    [order] = odoo_orders(fakes, pr["id"])
    assert done["external_reference"] == order["name"]
    assert done["result"]["external_id"] == str(order["id"])
    line = order["order_line"][0][2]
    assert (line["product_qty"], line["price_unit"]) == (1736.0, 4.85)
    assert [e["kind"] for e in done["events"]] == [
        "submitted",
        "stage_approved",
        "approved",
        "execution_started",
        "completed",
    ]
    # The insight records the outcome; the requester is told; everything is audited.
    detail = (await iapi.get(f"/insights/{insight['id']}")).json()
    assert detail["status"] == "actioned"
    assert "purchase_requested" in [e["kind"] for e in detail["events"]]
    notes = [n["title"] for n in (await iapi.get("/notifications")).json()["items"]]
    assert "PR-0001 is done" in notes
    assert "PR-0001 operations approval approved" in notes
    actions = [
        e["action"] for e in (await iapi.get("/audit", params={"limit": 20})).json()["items"]
    ]
    for a in ("workflow.submitted", "approval.approved", "workflow.completed"):
        assert a in actions


async def test_large_requests_need_two_different_approvers(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    insight = await stockout(iapi)
    pr = await submit(iapi, insight, quantity=2100)  # 2,100 x 4.85 = 10,185.00
    assert [a["name"] for a in pr["approvals"]] == ["Operations approval", "Finance approval"]
    assert [a["status"] for a in pr["approvals"]] == ["pending", "waiting"]
    assert "quantity_changed" in [e["kind"] for e in pr["events"]]
    async with (
        another_client(iapi, "203.0.113.41") as ops,
        another_client(iapi, "203.0.113.42") as fin,
    ):
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        await invite_and_join(iapi, fin, "fin@acme.example", "approver")
        r = await decide(ops, pr)
        assert r.status_code == 200
        pr = r.json()
        stage2 = pr["approvals"][1]
        assert stage2["status"] == "pending"
        # Same person can't approve both stages; operations managers aren't finance approvers.
        assert stage2["blocked_reason"] == "You already decided an earlier stage of this request."
        r = await decide(ops, pr)
        assert (r.status_code, error_code(r)) == (403, "cannot_decide")
        assert odoo_orders(fakes, pr["id"]) == []
        r = await decide(fin, pr)
        assert r.status_code == 200
    assert (await iapi.get(f"/purchase-requests/{pr['id']}")).json()["status"] == "completed"
    assert len(odoo_orders(fakes, pr["id"])) == 1


async def test_rejection_needs_a_reason_and_creates_nothing(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    insight = await stockout(iapi)
    pr = await submit(iapi, insight)
    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        r = await decide(ops, pr, "reject")
        assert (r.status_code, error_code(r)) == (422, "comment_required")
        r = await decide(ops, pr, "reject", "A transfer from Bristol covers this.")
        assert r.json()["status"] == "rejected"
    assert odoo_orders(fakes, pr["id"]) == []
    # The insight stays open for another decision; a new request is allowed.
    assert (await iapi.get(f"/insights/{insight['id']}")).json()["status"] == "acknowledged"
    again = await iapi.post(
        "/purchase-requests", json={"insight_id": insight["id"], "quantity": 100}
    )
    assert again.status_code == 201


async def test_crash_after_external_write_does_not_duplicate(
    iapi: Api, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan §5 acceptance: the worker dies after Odoo created the order, before Operon recorded it."""
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    pr = await submit(iapi, await stockout(iapi))
    real = engine.record_completion

    async def crash(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("worker killed")

    monkeypatch.setattr(engine, "record_completion", crash)
    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        await decide(ops, pr)  # the background advance crashes after the Odoo write
    assert (await iapi.get(f"/purchase-requests/{pr['id']}")).json()["status"] == "executing"
    assert len(odoo_orders(fakes, pr["id"])) == 1

    monkeypatch.setattr(engine, "record_completion", real)
    rt = iapi.app.state.workflow_runtime
    step = await engine.advance(rt, UUID(iapi.org_id or ""), UUID(pr["id"]))  # worker restarts
    assert step.done
    done = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert done["status"] == "completed"
    [order] = odoo_orders(fakes, pr["id"])  # still exactly one
    assert done["result"]["external_id"] == str(order["id"])


async def test_transient_failures_retry_then_succeed(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    pr = await submit(iapi, await stockout(iapi))
    fakes.odoo.fail_with = 503
    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        await decide(ops, pr)
    d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert (d["status"], d["attempts"]) == ("executing", 1)
    assert d["events"][-1]["kind"] == "attempt_failed"
    assert d["error"]
    fakes.odoo.fail_with = None
    rt = iapi.app.state.workflow_runtime
    # Not due yet: the sweep leaves it alone.
    assert await engine.sweep(rt) == 0
    assert await engine.sweep(rt, now=datetime.now(UTC) + timedelta(minutes=2)) == 1
    d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert d["status"] == "completed"
    assert len(odoo_orders(fakes, pr["id"])) == 1


async def test_permanent_failure_notifies_and_can_be_retried(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    pr = await submit(iapi, await stockout(iapi))
    good_key = fakes.odoo.api_key
    fakes.odoo.api_key = "rotated-elsewhere-key-0000"
    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        await decide(ops, pr)
        d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
        assert d["status"] == "failed"
        assert d["can_retry"] is True
        notes = [n["title"] for n in (await iapi.get("/notifications")).json()["items"]]
        assert any(t.startswith("PR-0001 failed") for t in notes)
        # Operations managers can't retry; workflow managers can.
        r = await ops.post(f"/purchase-requests/{pr['id']}/retry")
        assert r.status_code == 403
    fakes.odoo.api_key = good_key
    r = await iapi.post(f"/purchase-requests/{pr['id']}/retry")
    assert r.status_code == 200
    d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert d["status"] == "completed"
    assert "retried" in [e["kind"] for e in d["events"]]


async def test_undecided_approvals_escalate_then_expire(iapi: Api, fakes: Fakes) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    pr = await submit(iapi, await stockout(iapi))
    async with another_client(iapi) as ops:
        await invite_and_join(iapi, ops, "ops@acme.example", "operations_manager")
        rt = iapi.app.state.workflow_runtime
        later = datetime.now(UTC) + timedelta(hours=49)
        assert await engine.sweep(rt, now=later) == 1
        d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
        assert d["status"] == "awaiting_approval"
        assert d["approvals"][0]["escalated_at"]
        notes = [n["title"] for n in (await ops.get("/notifications")).json()["items"]]
        assert any(t.startswith("Overdue approval: PR-0001") for t in notes)
        await engine.sweep(rt, now=later + timedelta(hours=49))
        d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
        assert d["status"] == "expired"
        r = await decide(ops, pr)
        assert r.status_code == 409
    assert odoo_orders(fakes, pr["id"]) == []


async def test_cancel_rules(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    pr = await submit(iapi, await stockout(iapi))
    async with another_client(iapi) as analyst:
        await invite_and_join(iapi, analyst, "an@acme.example", "analyst")
        r = await analyst.post(f"/purchase-requests/{pr['id']}/cancel", json={})
        assert r.status_code == 403
    r = await iapi.post(f"/purchase-requests/{pr['id']}/cancel", json={"reason": "Duplicate"})
    d = r.json()
    assert d["status"] == "cancelled"
    assert [a["status"] for a in d["approvals"]] == ["cancelled"]
    r = await iapi.post(f"/purchase-requests/{pr['id']}/cancel", json={})
    assert (r.status_code, error_code(r)) == (409, "cannot_cancel")


async def test_one_request_in_flight_per_insight(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    insight = await stockout(iapi)
    pr = await submit(iapi, insight)
    r = await iapi.post("/purchase-requests", json={"insight_id": insight["id"], "quantity": 5})
    assert (r.status_code, error_code(r)) == (409, "request_exists")
    assert r.json()["error"]["details"]["execution_id"] == pr["id"]


async def test_policy_versions_pin_in_flight_requests(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    await connect(iapi, ODOO)
    config = (await iapi.get("/workflows/purchase-requests")).json()
    assert config["current_version"] == 1
    pr = await submit(iapi, await stockout(iapi))
    params = config["params"]
    params["stages"][1]["min_value"] = "5000"
    r = await iapi.put("/workflows/purchase-requests", json={"enabled": True, "params": params})
    assert r.status_code == 200
    assert r.json()["current_version"] == 2
    # The request in flight keeps version 1 and its single stage.
    d = (await iapi.get(f"/purchase-requests/{pr['id']}")).json()
    assert (d["policy_version"], len(d["approvals"])) == (1, 1)
    await iapi.post(f"/purchase-requests/{pr['id']}/cancel", json={})
    insight = await stockout(iapi)
    new = await submit(iapi, insight)
    assert (new["policy_version"], len(new["approvals"])) == (2, 2)
    # Invalid policies are refused; saving the same settings doesn't create a version.
    bad = {**params, "stages": [{**params["stages"][0], "min_value": "100"}]}
    r = await iapi.put("/workflows/purchase-requests", json={"enabled": True, "params": bad})
    assert (r.status_code, error_code(r)) == (422, "invalid_params")
    r = await iapi.put("/workflows/purchase-requests", json={"enabled": True, "params": params})
    assert r.json()["current_version"] == 2


async def test_csv_sources_record_the_request_without_an_external_write(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    insight = await stockout(api)
    pr = await submit(api, insight)
    assert pr["target"] == "record_only"
    assert "can't receive purchase orders" in pr["input"]["target_reason"]
    async with another_client(api) as ops:
        await invite_and_join(api, ops, "ops@acme.example", "operations_manager")
        await decide(ops, pr)
    d = (await api.get(f"/purchase-requests/{pr['id']}")).json()
    assert d["status"] == "completed"
    assert d["result"]["mode"] == "record_only"
    assert d["events"][-1]["message"].startswith("Purchase request recorded in Operon")


async def test_workflow_permissions(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    insight = await stockout(api)
    async with another_client(api) as analyst, another_client(api, "203.0.113.50") as viewer:
        await invite_and_join(api, analyst, "an@acme.example", "analyst")
        await invite_and_join(api, viewer, "vi@acme.example", "viewer")
        r = await analyst.post(
            "/purchase-requests", json={"insight_id": insight["id"], "quantity": 1}
        )
        assert r.status_code == 403
        assert (await analyst.get("/purchase-requests")).status_code == 200
        assert (await viewer.get("/purchase-requests")).status_code == 403
        r = await analyst.put("/workflows/purchase-requests", json={"enabled": False, "params": {}})
        assert r.status_code == 403


async def test_cannot_request_purchases_from_another_organisations_insight(
    api: Api, second_api: Api
) -> None:
    await api.sign_up("alice@a.example", org="Org A")
    await second_api.sign_up("bob@b.example", org="Org B")
    await seed_operations(second_api)
    b_insight = await stockout(second_api)
    r = await api.post("/purchase-requests", json={"insight_id": b_insight["id"], "quantity": 5})
    assert (r.status_code, error_code(r)) == (404, "not_found")
    assert (await second_api.get("/purchase-requests", params={"status": "all"})).json()[
        "total"
    ] == 0


async def test_dashboard_shows_live_approvals_and_workflow_status(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    s = (await api.get("/dashboard/summary")).json()
    assert s["approvals"]["provenance"] == "live"
    assert s["approvals"]["data"] == []
    assert s["workflows"]["state"] == "unavailable"
    await seed_operations(api)
    pr = await submit(api, await stockout(api))
    s = (await api.get("/dashboard/summary")).json()
    [approval] = s["approvals"]["data"]
    assert (approval["id"], approval["ref"], approval["amount"], approval["currency"]) == (
        pr["id"],
        "PR-0001",
        7114.95,
        "GBP",
    )
    assert approval["policy"].startswith("Operations approval: Required for every")
    assert s["workflows"]["data"][0]["awaiting_approval"] == 1
    indicator = next(i for i in s["indicators"] if i["key"] == "pending_approvals")
    assert (indicator["value"], indicator["provenance"]) == (1, "live")
