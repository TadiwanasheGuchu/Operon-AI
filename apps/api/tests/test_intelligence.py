"""Phase 4 acceptance: detectors, evidence, explanations, insight lifecycle (plan §4)."""

import math
import statistics
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel

from operon.main import create_app
from operon.modules.ai.provider import StructuredResult
from operon.modules.ai.service import ProviderRegistry
from operon.modules.intelligence import explain
from operon.modules.intelligence.detectors.po_overdue import PoOverdueParams, severity_for
from operon.modules.intelligence.detectors.stockout import StockoutInputs, compute
from tests.conftest import Api, AppFactory, make_settings
from tests.helpers import error_code, invite_and_join, seed_operations, upload

STOCKOUT = "inventory.stockout_risk"
OVERDUE = "procurement.po_overdue"

# --- golden numbers: the pure calculation against an independent float implementation -----------


def reference(on_hand: float, sales: list[float], inbound: float, lead: int, z: float,
              review: int, moq: float) -> dict[str, float]:  # fmt: skip
    d = statistics.fmean(sales)
    sigma = statistics.stdev(sales)
    ss = z * sigma * math.sqrt(lead)
    rop = d * lead + ss
    position = on_hand + inbound
    projected = position - d * lead
    qty = max(moq, math.ceil(rop + d * review - position))
    return {"d": d, "sigma": sigma, "ss": ss, "rop": rop, "projected": projected, "qty": qty}


@pytest.mark.parametrize(
    ("on_hand", "sales", "inbound", "lead", "level", "z", "moq", "severity"),
    [
        # The seeded scenario: projected -134 -> stockout before replenishment.
        (1240, [180, 192] * 14, 300, 9, "0.95", 1.65, 500, "critical"),
        # Enough to cover lead-time demand but not the safety stock.
        (1700, [180, 192] * 14, 0, 9, "0.95", 1.65, 500, "high"),
        # Low-volume item at a 99% service level, with a 14-day lead time.
        (60, [3, 5, 4, 6, 2, 4, 4] * 4, 0, 14, "0.99", 2.33, 0, "high"),
    ],
)
def test_stockout_golden_numbers(
    on_hand: float, sales: list[float], inbound: float, lead: int, level: str, z: float,
    moq: float, severity: str,
) -> None:  # fmt: skip
    r = compute(
        StockoutInputs(
            on_hand=Decimal(on_hand),
            daily_sales=[Decimal(x) for x in sales],
            inbound_within_lead=Decimal(inbound),
            lead_time_days=lead,
            service_level=level,
            review_period_days=7,
            min_order_quantity=Decimal(moq) if moq else None,
        )
    )
    ref = reference(on_hand, sales, inbound, lead, z, 7, moq)
    assert r.triggered
    assert r.severity == severity
    assert float(r.demand_per_day) == pytest.approx(ref["d"], abs=1e-9)
    assert float(r.demand_std_dev) == pytest.approx(ref["sigma"], abs=1e-9)
    assert float(r.safety_stock) == pytest.approx(ref["ss"], abs=1e-9)
    assert float(r.reorder_point) == pytest.approx(ref["rop"], abs=1e-9)
    assert float(r.projected) == pytest.approx(ref["projected"], abs=1e-9)
    assert r.recommended_quantity == ref["qty"]


def test_stockout_severity_bands_and_non_triggers() -> None:
    def at(on_hand: int) -> Any:
        # d = 10, sigma = 0 -> SS = 0, ROP = 100; review period 7 -> medium band up to 170.
        return compute(
            StockoutInputs(
                on_hand=Decimal(on_hand),
                inbound_within_lead=Decimal(0),
                daily_sales=[Decimal(10)] * 28,
                lead_time_days=10,
            )
        )

    assert at(171).triggered is False
    assert (at(170).severity, at(170).recommended_quantity) == ("medium", 1)
    assert (at(120).severity, at(120).recommended_quantity) == ("medium", 50)
    assert at(100).severity == "critical"  # P = 0 = SS
    assert (
        compute(
            StockoutInputs(
                on_hand=Decimal(50),
                inbound_within_lead=Decimal(50),
                daily_sales=[Decimal(8), Decimal(12)] * 14,
                lead_time_days=10,
            )
        ).severity
        == "critical"
    )

    # With variability: just above the reorder point is medium, just below is high.
    def var(on_hand: Decimal) -> Any:
        return compute(
            StockoutInputs(
                on_hand=on_hand,
                inbound_within_lead=Decimal(0),
                daily_sales=[Decimal(8), Decimal(12)] * 14,
                lead_time_days=4,
            )
        )

    rop = var(Decimal(0)).reorder_point
    above, below = var(rop + 1), var(rop - 1)
    assert (above.severity, below.severity) == ("medium", "high")
    # No demand → never triggers, even with nothing on hand.
    assert not compute(
        StockoutInputs(
            on_hand=Decimal(0),
            inbound_within_lead=Decimal(0),
            daily_sales=[Decimal(0)] * 28,
            lead_time_days=5,
        )
    ).triggered
    # MOQ raises the recommendation.
    big = compute(
        StockoutInputs(
            on_hand=Decimal(0),
            inbound_within_lead=Decimal(0),
            daily_sales=[Decimal(1)] * 28,
            lead_time_days=5,
            min_order_quantity=Decimal(1000),
        )
    )
    assert big.recommended_quantity == 1000


def test_po_overdue_severity_bands() -> None:
    p = PoOverdueParams()
    assert [severity_for(d, p) for d in (2, 3, 7, 21)] == ["low", "medium", "high", "critical"]
    with pytest.raises(ValueError, match="increase"):
        PoOverdueParams(medium_after_days=10, high_after_days=5)


# --- explanation validator ----------------------------------------------------------------------


def _payload() -> explain.AlertPayload:
    return explain.AlertPayload(
        {
            "alert": "Gloves may run out",
            "evidence": [
                {"label": "On hand", "value": "1,240 boxes"},
                {"label": "Average daily sales", "value": "186 boxes"},
                {"label": "Reorder point", "value": "1,704.2 boxes"},
                {"label": "Stockout date", "value": "2026-11-19"},
            ],
        }
    )


def test_validator_accepts_numbers_from_evidence() -> None:
    ok = explain.Explanation(
        what_happened="There are 1,240 boxes on hand against a reorder point of 1704.2 boxes, "
        "selling 186 a day; stock may run out on 2026-11-19.",
        why_it_matters="Customers may go unserved until the next delivery arrives.",
    )
    assert explain.validate(ok, _payload()) == []


def test_validator_rejects_invented_numbers_and_links() -> None:
    bad = explain.Explanation(
        what_happened="There are 1,240 boxes on hand, about 7 days of cover at 186 a day.",
        why_it_matters="See https://example.com for the 12% shortfall analysis details.",
    )
    problems = explain.validate(bad, _payload())
    assert any("numbers not in the evidence: 7" in p for p in problems), problems
    assert any("12" in p for p in problems)
    assert any("link" in p for p in problems)


# --- fake provider ------------------------------------------------------------------------------


@dataclass
class FakeProvider:
    """Answers with a function of the user message; records what it was sent."""

    respond: Any
    name: str = "anthropic"
    model: str = "fake-model-1"
    calls: list[str] = field(default_factory=list)

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], max_output_tokens: int
    ) -> StructuredResult[T]:
        self.calls.append(user)
        out = self.respond(user)
        if out is None:
            return StructuredResult(None, self.model, 50, 0, "refused", "test")
        return StructuredResult(schema.model_validate(out), self.model, 400, 120, "ok")


def faithful(user: str) -> dict[str, str]:
    return {
        "what_happened": "Stock of this item is below its reorder point and may run out before "
        "the next delivery can arrive.",
        "why_it_matters": "Customers ordering it could go unserved, so a purchase request is "
        "worth raising now.",
    }


def inventive(user: str) -> dict[str, str]:
    return {
        "what_happened": "Only 3 days of stock remain, roughly 41% below the safe level.",
        "why_it_matters": "Expect lost sales of about 9,000 pounds this month if nothing is done.",
    }


@asynccontextmanager
async def ai_api(api_factory: AppFactory, provider: FakeProvider) -> Any:
    app = create_app(make_settings())
    app.state.ai_providers = ProviderRegistry({"anthropic": provider})
    async with api_factory(app=app) as a:
        yield a


async def enable_ai(api: Api, budget: int = 100_000) -> None:
    r = await api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "anthropic", "monthly_token_budget": budget},
    )
    assert r.status_code == 200, r.text


# --- end-to-end: data in, insights out ----------------------------------------------------------


async def insights(api: Api, **params: Any) -> list[dict[str, Any]]:
    r = await api.get("/insights", params={"status": "all", **params})
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def by_rule(items: list[dict[str, Any]], rule: str) -> dict[str, Any]:
    return next(i for i in items if i["rule_id"] == rule)


async def test_seeded_data_raises_expected_insights_with_golden_numbers(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    items = await insights(api)
    assert sorted((i["rule_id"], i["severity"]) for i in items) == [
        (STOCKOUT, "critical"),
        (OVERDUE, "high"),
    ]
    stockout = by_rule(items, STOCKOUT)
    assert stockout["reference"].startswith("INS-")
    assert stockout["subject_label"] == "GLV at Leeds DC"
    d = (await api.get(f"/insights/{stockout['id']}")).json()
    assert d["metrics"] == {
        "on_hand": "1,240 box",
        "avg_daily_demand": "186 box",
        "demand_std_dev": "6.1 box",
        "lead_time": "9 days",
        "service_level": "95% (z = 1.65)",
        "safety_stock": "30.2 box",
        "reorder_point": "1,704.2 box",
        "inbound": "300 box",
        "projected_position": "-134 box",
        "days_of_cover": "6.7 days",
        "stockout_date": (datetime.now(UTC).date() + timedelta(days=6)).isoformat(),
        "recommended_quantity": "1,467 box",
    }
    rec = d["recommendation"]
    assert (rec["action"], rec["quantity"], rec["supplier_name"]) == (
        "create_purchase_request",
        1467,
        "Brightline Safety Supplies",
    )
    # Priced from the most recent PO (PO-NEW at 4.85), not the older one.
    assert rec["estimated_value_display"] == "GBP 7,114.95"
    assert any("already late" in a for a in d["assumptions"])
    assert d["confidence"] == "normal"
    assert d["explanation"]["source"] == "template"

    overdue = (await api.get(f"/insights/{by_rule(items, OVERDUE)['id']}")).json()
    assert overdue["metrics"]["days_late"] == "10 days"
    assert overdue["metrics"]["number"] == "PO-OLD"
    assert overdue["metrics"]["outstanding_value"] == "GBP 1,410.00"
    assert overdue["recommendation"]["action"] == "contact_supplier"


async def test_evidence_traces_to_source_records(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    stockout = by_rule(await insights(api), STOCKOUT)
    d = (await api.get(f"/insights/{stockout['id']}")).json()
    resolvable = [e for e in d["evidence"] if e["resolvable"]]
    assert {e["source_type"] for e in resolvable} >= {
        "stock_level",
        "sales_daily",
        "supplier_product",
        "purchase_order_line",
    }
    for e in resolvable:
        r = await api.get(f"/insights/{stockout['id']}/evidence/{e['id']}/source")
        assert r.status_code == 200, (e, r.text)
        src = r.json()
        assert src["connection"]["connector"] == "csv"
        if e["source_type"] == "stock_level":
            assert src["fields"]["on_hand"] == "1240.0000"
            assert src["fields"]["location"] == "Leeds DC"
        if e["source_type"] == "sales_daily":
            assert len(src["fields"]["daily_sales"]) == 28
    computed = [e for e in d["evidence"] if e["source_type"] == "computed"]
    assert computed
    assert all(e["formula"] for e in computed)
    r = await api.get(f"/insights/{stockout['id']}/evidence/{computed[0]['id']}/source")
    assert (r.status_code, error_code(r)) == (404, "no_source")


async def test_template_explanations_pass_the_validator(api: Api) -> None:
    """With AI off, the insight still explains itself, using only evidence numbers."""
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    for item in await insights(api):
        d = (await api.get(f"/insights/{item['id']}")).json()
        ex = d["explanation"]
        assert ex["source"] == "template"
        assert not ex["pending"]
        allowed = explain.numbers_in(
            " ".join(
                [d["title"], d["summary"], d["subject_label"]]
                + [f"{e['label']} {e['value']}" for e in d["evidence"]]
            )
        )
        for text in (ex["what_happened"], ex["why_it_matters"]):
            assert explain.numbers_in(text) <= allowed, text


async def test_ai_explanation_is_validated_and_recorded(api_factory: AppFactory) -> None:
    provider = FakeProvider(faithful)
    async with ai_api(api_factory, provider) as api:
        await api.sign_up("owner@acme.example")
        await enable_ai(api)
        await seed_operations(api)
        d = (await api.get(f"/insights/{by_rule(await insights(api), STOCKOUT)['id']}")).json()
        assert d["explanation"]["source"] == "model"
        assert d["explanation"]["model"] == "fake-model-1"
        assert d["explanation"]["what_happened"].startswith("Stock of this item")
        assert "explained" in [e["kind"] for e in d["events"]]
        # Evidence is sent as data, fenced from instructions.
        assert provider.calls
        assert provider.calls[0].startswith("<alert>")
        assert "1,240 box" in provider.calls[0]
        status = (await api.get("/intelligence/ai-settings")).json()
        assert status["tokens_used_this_month"] >= 520


async def test_invented_numbers_fall_back_to_template(api_factory: AppFactory) -> None:
    async with ai_api(api_factory, FakeProvider(inventive)) as api:
        await api.sign_up("owner@acme.example")
        await enable_ai(api)
        await seed_operations(api)
        d = (await api.get(f"/insights/{by_rule(await insights(api), STOCKOUT)['id']}")).json()
        assert d["explanation"]["source"] == "template"
        assert "1,240 box on hand" in d["explanation"]["what_happened"]


async def test_refusals_and_budget_fall_back_to_template(api_factory: AppFactory) -> None:
    async with ai_api(api_factory, FakeProvider(lambda _: None)) as api:
        await api.sign_up("owner@acme.example")
        await enable_ai(api)
        await seed_operations(api)
        for item in await insights(api):
            d = (await api.get(f"/insights/{item['id']}")).json()
            assert d["explanation"]["source"] == "template"
    provider = FakeProvider(faithful)
    async with ai_api(api_factory, provider) as api:
        await api.sign_up("frugal@acme.example")
        await enable_ai(api, budget=0)
        await seed_operations(api)
        assert provider.calls == []  # budget spent: no call at all
        for item in await insights(api):
            assert (await api.get(f"/insights/{item['id']}")).json()["explanation"][
                "source"
            ] == "template"


async def test_ai_settings_require_a_configured_provider_and_organisation_manage(
    api: Api, second_api: Api
) -> None:
    await api.sign_up("owner@acme.example")
    r = await api.put(
        "/intelligence/ai-settings",
        json={"enabled": True, "provider": "openai", "monthly_token_budget": 1000},
    )
    assert (r.status_code, error_code(r)) == (409, "provider_unavailable")
    # Turning it off (or leaving it off) is always allowed.
    r = await api.put(
        "/intelligence/ai-settings",
        json={"enabled": False, "provider": "openai", "monthly_token_budget": 1000},
    )
    assert r.status_code == 200
    assert r.json()["provider_available"] is False
    await invite_and_join(api, second_api, "ops@acme.example", "operations_manager")
    r = await second_api.put(
        "/intelligence/ai-settings",
        json={"enabled": False, "provider": "anthropic", "monthly_token_budget": 5},
    )
    assert r.status_code == 403
    assert (await second_api.get("/intelligence/ai-settings")).status_code == 200


# --- lifecycle ----------------------------------------------------------------------------------


async def test_redetection_is_idempotent_and_auto_resolves(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    cid = await seed_operations(api)
    first = await insights(api)
    run = (await api.post("/intelligence/run")).json()
    assert run["status"] == "succeeded"
    assert run["stats"][STOCKOUT]["raised"] == 0
    assert run["stats"][STOCKOUT]["updated"] == 0
    assert [i["id"] for i in await insights(api)] == [i["id"] for i in first]
    # Stock arrives: the condition clears and the insight resolves itself.
    await upload(api, cid, "stock", [["GLV", "LEEDS", 9000, 0], ["MSK", "LEEDS", 5000, 0]])
    stockout = by_rule(await insights(api), STOCKOUT)
    assert stockout["status"] == "resolved"
    d = (await api.get(f"/insights/{stockout['id']}")).json()
    assert d["close_reason"] == "The condition was no longer detected."
    kinds = [e["kind"] for e in d["events"]]
    # Seeding uploads files one by one, so the insight was updated as purchase orders arrived.
    assert (kinds[0], kinds[-1]) == ("detected", "resolved")


async def test_changed_numbers_update_the_same_insight(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    cid = await seed_operations(api)
    before = by_rule(await insights(api), STOCKOUT)
    await upload(api, cid, "stock", [["GLV", "LEEDS", 1200, 0], ["MSK", "LEEDS", 5000, 0]])
    after = by_rule(await insights(api), STOCKOUT)
    assert after["id"] == before["id"]
    d = (await api.get(f"/insights/{after['id']}")).json()
    assert d["metrics"]["on_hand"] == "1,200 box"
    assert "updated" in [e["kind"] for e in d["events"]]


async def test_dismissal_needs_a_reason_and_suppresses_until_worse(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    overdue = by_rule(await insights(api), OVERDUE)
    r = await api.post(f"/insights/{overdue['id']}/status", json={"status": "dismissed"})
    assert (r.status_code, error_code(r)) == (422, "reason_required")
    r = await api.post(
        f"/insights/{overdue['id']}/status",
        json={"status": "dismissed", "reason": "Supplier confirmed delivery Friday"},
    )
    assert r.status_code == 200
    assert r.json()["suppressed_until"]
    run = (await api.post("/intelligence/run")).json()
    assert run["stats"][OVERDUE]["suppressed"] == 1
    assert len([i for i in await insights(api) if i["rule_id"] == OVERDUE]) == 1
    # Worse than when dismissed (critical after 21 days): raised again.
    r = await api.put(
        f"/intelligence/detectors/{OVERDUE}",
        json={"enabled": True, "params": {"critical_after_days": 10}},
    )
    assert r.status_code == 200, r.text
    await api.post("/intelligence/run")
    raised = [i for i in await insights(api) if i["rule_id"] == OVERDUE and i["status"] == "open"]
    assert [i["severity"] for i in raised] == ["critical"]


async def test_invalid_transitions_are_refused(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    item = by_rule(await insights(api), STOCKOUT)
    ok = await api.post(f"/insights/{item['id']}/status", json={"status": "resolved"})
    assert ok.status_code == 200
    assert ok.json()["allowed_transitions"] == []
    r = await api.post(f"/insights/{item['id']}/status", json={"status": "acknowledged"})
    assert (r.status_code, error_code(r)) == (409, "invalid_transition")


async def test_owner_must_be_a_member_and_is_notified(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    item = by_rule(await insights(api), STOCKOUT)
    r = await api.put(
        f"/insights/{item['id']}/owner", json={"user_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert (r.status_code, error_code(r)) == (422, "invalid_owner")
    await invite_and_join(api, second_api, "ops@acme.example", "operations_manager", "Olu Ops")
    me = (await second_api.get("/users/me")).json()
    r = await api.put(f"/insights/{item['id']}/owner", json={"user_id": me["id"]})
    assert r.status_code == 200
    assert r.json()["owner"]["full_name"] == "Olu Ops"
    notes = (await second_api.get("/notifications")).json()["items"]
    assert any(n["title"].startswith(f"You own {item['reference']}") for n in notes)
    mine = (await second_api.get("/insights", params={"owner": "me"})).json()["items"]
    assert [i["id"] for i in mine] == [item["id"]]


async def test_viewers_read_but_cannot_act(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    await invite_and_join(api, second_api, "viewer@acme.example", "viewer")
    item = by_rule(await insights(second_api), STOCKOUT)
    assert (await second_api.get(f"/insights/{item['id']}")).status_code == 200
    for method, path, body in [
        ("POST", f"/insights/{item['id']}/status", {"status": "acknowledged"}),
        ("PUT", f"/insights/{item['id']}/owner", {"user_id": None}),
        ("POST", f"/insights/{item['id']}/incident", {}),
        ("POST", "/intelligence/run", None),
        ("PUT", f"/intelligence/detectors/{STOCKOUT}", {"enabled": False}),
    ]:
        r = await second_api.request(method, path, json=body)
        assert r.status_code == 403, (method, path)


async def test_detector_configuration_is_validated_and_audited(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    detectors = (await api.get("/intelligence/detectors")).json()
    assert [d["rule_id"] for d in detectors] == [STOCKOUT, OVERDUE]
    sl = next(p for p in detectors[0]["params"] if p["name"] == "service_level")
    assert sl["choices"] == ["0.90", "0.95", "0.975", "0.99"]
    assert sl["value"] == "0.95"
    r = await api.put(
        f"/intelligence/detectors/{STOCKOUT}",
        json={"enabled": True, "params": {"sales_window_days": 1000}},
    )
    assert (r.status_code, error_code(r)) == (422, "invalid_params")
    r = await api.put(
        f"/intelligence/detectors/{STOCKOUT}", json={"enabled": True, "params": {"bogus": 1}}
    )
    assert r.status_code == 422
    r = await api.put(f"/intelligence/detectors/{STOCKOUT}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    audit = (await api.get("/audit", params={"limit": 5})).json()["items"]
    assert audit[0]["action"] == "detector.updated"


async def test_disabling_a_detector_closes_its_insights(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    await api.put(f"/intelligence/detectors/{STOCKOUT}", json={"enabled": False})
    await api.post("/intelligence/run")
    stockout = by_rule(await insights(api), STOCKOUT)
    assert stockout["status"] == "resolved"


async def test_short_history_is_low_confidence_not_dropped(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    cid = (await api.post("/integrations", json={"connector": "csv", "name": "New"})).json()["id"]
    today = datetime.now(UTC).date()
    await upload(api, cid, "locations", [["LEEDS", "Leeds DC"]])
    await upload(api, cid, "products", [["NEW", "New line", "unit"]])
    await upload(api, cid, "stock", [["NEW", "LEEDS", 10]])
    await upload(
        api,
        cid,
        "sales",
        [[(today - timedelta(days=i)).isoformat(), "NEW", 5, "LEEDS"] for i in range(1, 6)],
    )
    item = by_rule(await insights(api), STOCKOUT)
    d = (await api.get(f"/insights/{item['id']}")).json()
    assert d["confidence"] == "low"
    assert any("Only 5 days of sales history" in lim for lim in d["limitations"])
    assert any("No supplier lead time" in lim for lim in d["limitations"])
    assert d["metrics"]["lead_time"] == "14 days"


async def test_high_severity_insights_notify_managers(api: Api, second_api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await invite_and_join(api, second_api, "analyst@acme.example", "analyst")
    await seed_operations(api)
    owner_notes = (await api.get("/notifications")).json()["items"]
    assert sum(n["kind"] == "insight" for n in owner_notes) == 2  # critical + high
    analyst_notes = (await second_api.get("/notifications")).json()["items"]
    assert not any(n["kind"] == "insight" for n in analyst_notes)  # read-only role


async def test_dashboard_shows_live_insights_incidents_and_risk(api: Api) -> None:
    await api.sign_up("owner@acme.example")
    await seed_operations(api)
    overdue = by_rule(await insights(api), OVERDUE)
    await api.post(f"/insights/{overdue['id']}/incident", json={})
    s = (await api.get("/dashboard/summary")).json()
    assert s["insights"]["provenance"] == "live"
    top = s["insights"]["data"]
    assert [i["severity"] for i in top] == ["critical", "high"]
    assert top[0]["recommended_action"].startswith("Raise a purchase request for 1,467 box")
    assert top[0]["source_system"] == "Operations import"
    assert top[0]["explanation_generated_by"] == "template"
    assert s["incidents"]["data"] == {"critical": 0, "high": 1, "medium": 0, "low": 0}
    assert s["inventory_risk"]["data"] == [
        {"location": "Leeds DC", "skus_at_risk": 1, "skus_tracked": 2}
    ]
    indicator = next(i for i in s["indicators"] if i["key"] == "open_insights")
    assert (indicator["value"], indicator["state"]) == (2, "critical")
