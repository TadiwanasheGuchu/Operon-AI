from collections.abc import Sequence
from typing import Any

import httpx

from tests.conftest import PASSWORD, Api


async def invite_and_join(
    admin: Api, joiner: Api, email: str, role: str, name: str = "Member"
) -> str:
    """Invite `email` into admin's organisation; the joiner registers via the link. Returns member id."""
    r = await admin.post("/invitations", json={"email": email, "role_key": role})
    assert r.status_code == 201, r.text
    token = admin.last_link_token(email, "/invite")
    r = await joiner.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name, "invitation_token": token},
    )
    assert r.status_code == 202, r.text
    await joiner.login(email)
    joiner.org_id = admin.org_id
    members = (await admin.get("/members")).json()
    return str(next(m["id"] for m in members if m["email"] == email))


def error_code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


async def upload(api: Api, connection_id: str, kind: str, rows: Sequence[Sequence[object]]) -> None:
    from operon.modules.integrations.csv_import import COLUMNS

    required, optional = COLUMNS[kind]
    header = required + optional
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([["" if v is None else v for v in r] for r in rows])
    r = await api.post(
        f"/integrations/{connection_id}/uploads",
        data={"kind": kind},
        files={"file": (f"{kind}.csv", buf.getvalue().encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"], r.text


async def seed_operations(api: Api, name: str = "Operations import") -> str:
    """A CSV-imported distribution scenario relative to today. Returns the connection id.

    GLV (gloves, Leeds): 1,240 boxes on hand, sells 180/192 on alternate days (mean 186), 9-day
    lead time from Brightline (MOQ 500), 300 boxes on PO-OLD (10 days late) and 2,000 on PO-NEW
    (due in 20 days, beyond the lead time). → critical stockout risk; PO-OLD is overdue (high).
    MSK (masks, Leeds): plenty of stock → no insight.
    """
    from datetime import date, timedelta

    today = date.today()
    conn = (await api.post("/integrations", json={"connector": "csv", "name": name})).json()
    cid = str(conn["id"])
    await upload(api, cid, "locations", [["LEEDS", "Leeds DC"]])
    await upload(
        api,
        cid,
        "products",
        [
            ["GLV", "Nitrile gloves, size L", "box", "4.85", "GBP", "true"],
            ["MSK", "FFP2 masks", "box", "9.10", "GBP", "true"],
        ],
    )
    await upload(
        api,
        cid,
        "supplier_terms",
        [
            ["Brightline Safety Supplies", "GLV", 9, 500, "4.85", "GBP"],
            ["Brightline Safety Supplies", "MSK", 9, 100, "9.10", "GBP"],
        ],
    )
    await upload(api, cid, "stock", [["GLV", "LEEDS", 1240, 0], ["MSK", "LEEDS", 5000, 0]])
    sales = []
    for i in range(1, 29):
        day = (today - timedelta(days=i)).isoformat()
        sales.append([day, "GLV", 180 if i % 2 else 192, "LEEDS"])
        sales.append([day, "MSK", 20, "LEEDS"])
    await upload(api, cid, "sales", sales)
    await upload(
        api,
        cid,
        "purchase_orders",
        [
            [
                "PO-OLD",
                "Brightline Safety Supplies",
                "open",
                "GLV",
                300,
                "LEEDS",
                (today - timedelta(days=30)).isoformat(),
                (today - timedelta(days=10)).isoformat(),
                "GBP",
                0,
                "4.70",
            ],
            [
                "PO-NEW",
                "Brightline Safety Supplies",
                "open",
                "GLV",
                2000,
                "LEEDS",
                (today - timedelta(days=2)).isoformat(),
                (today + timedelta(days=20)).isoformat(),
                "GBP",
                0,
                "4.85",
            ],
        ],
    )
    return cid


def another_client(base: Api, ip: str = "203.0.113.40") -> Any:
    """A second browser (own cookies) on the same app as `base`."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def ctx() -> Any:
        transport = httpx.ASGITransport(
            app=base.app, client=(ip, 50000), raise_app_exceptions=False
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield Api(c, base.app)

    return ctx()
