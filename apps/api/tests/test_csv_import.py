"""CSV import: templates, strict all-or-nothing validation, and correct writes."""

from typing import Any

from sqlalchemy import text

from operon.modules.integrations import csv_import
from tests.conftest import Api
from tests.helpers import error_code


async def csv_connection(api: Api) -> str:
    r = await api.post("/integrations", json={"connector": "csv", "name": "Spreadsheets"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def upload(api: Api, conn: str, kind: str, content: str) -> dict[str, Any]:
    r = await api.post(
        f"/integrations/{conn}/uploads",
        data={"kind": kind},
        files={"file": (f"{kind}.csv", content.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_templates_parse_as_valid_imports(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await csv_connection(iapi)
    for kind in ["locations", "products", "supplier_terms", "stock", "sales", "purchase_orders"]:
        r = await iapi.get(f"/integrations/csv-templates/{kind}")
        assert r.headers["content-type"].startswith("text/csv")
        result = await upload(iapi, conn, kind, r.text)
        assert result["accepted"], (kind, result["errors"])


async def test_full_import_journey(iapi: Api, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await csv_connection(iapi)
    await upload(iapi, conn, "locations", "code,name\nLDS,Leeds DC\nBRS,Bristol DC\n")
    await upload(
        iapi,
        conn,
        "products",
        "sku,name,unit_cost,currency\nA-1,Gloves,4.85,GBP\nB-2,Vest,2.10,GBP\n",
    )
    await upload(
        iapi,
        conn,
        "supplier_terms",
        "supplier,sku,lead_time_days,min_quantity\nBrightline,A-1,9,500\n",
    )
    r = await upload(iapi, conn, "stock", "sku,location_code,on_hand\nA-1,LDS,1240\nB-2,BRS,1610\n")
    assert (r["rows"], r["written"]) == (2, 2)
    await upload(
        iapi,
        conn,
        "sales",
        "date,sku,quantity,location_code\n2026-11-10,A-1,100,LDS\n2026-11-10,A-1,86,LDS\n",
    )
    await upload(
        iapi,
        conn,
        "purchase_orders",
        "po_number,supplier,status,sku,quantity,unit_price,expected_at\n"
        "PO-1,Brightline,open,A-1,2000,4.85,2026-11-27\nPO-1,Brightline,open,B-2,10,2.10,2026-11-27\n",
    )
    with owner_engine.connect() as c:
        assert float(c.execute(text("SELECT quantity FROM sales_daily")).scalar()) == 186.0
        assert c.execute(text("SELECT lead_time_days FROM supplier_products")).scalar() == 9
        po = c.execute(
            text(
                "SELECT status, total, (SELECT count(*) FROM purchase_order_lines) FROM purchase_orders"
            )
        ).one()
        assert (po[0], float(po[1]), po[2]) == ("open", 9721.0, 2)
    # A new stock file replaces the previous snapshot entirely.
    await upload(iapi, conn, "stock", "sku,location_code,on_hand\nA-1,LDS,900\n")
    with owner_engine.connect() as c:
        rows = c.execute(text("SELECT on_hand FROM stock_levels")).scalars().all()
        assert [float(x) for x in rows] == [900.0]
    jobs = (await iapi.get(f"/integrations/{conn}/sync-jobs")).json()
    assert {j["trigger"] for j in jobs} == {"upload"}
    activity = [
        e["message"] for e in (await iapi.get("/dashboard/summary")).json()["activity"]["data"]
    ]
    assert "Imported 1 row of stock levels" in activity


async def test_invalid_files_write_nothing(iapi: Api, owner_engine: Any) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await csv_connection(iapi)
    await upload(iapi, conn, "locations", "code,name\nLDS,Leeds DC\n")
    await upload(iapi, conn, "products", "sku,name\nA-1,Gloves\n")
    bad = await upload(
        iapi,
        conn,
        "stock",
        "sku,location_code,on_hand\nA-1,LDS,10\nZZZ,LDS,5\nA-1,NOPE,5\nA-1,LDS,-3\nA-1,LDS,lots\n",
    )
    assert bad["accepted"] is False
    assert bad["written"] == 0
    messages = {(e["row"], e["column"]): e["message"] for e in bad["errors"]}
    assert messages[(3, "sku")] == "Unknown SKU “ZZZ”. Import products first."
    assert messages[(4, "location_code")].startswith("Unknown location “NOPE”")
    assert messages[(5, "on_hand")] == "must be zero or more"
    assert messages[(6, "on_hand")] == "“lots” is not a number"
    with owner_engine.connect() as c:
        assert (
            c.execute(text("SELECT count(*) FROM stock_levels")).scalar() == 0
        )  # row 2 was valid, still not written
    missing = await upload(iapi, conn, "stock", "sku,on_hand\nA-1,10\n")
    assert missing["errors"][0]["message"] == "Missing column(s): location_code"
    extra = await upload(iapi, conn, "locations", "code,name,evil\nX,Y,Z\n")
    assert extra["errors"][0]["message"] == "Unexpected column(s): evil"


async def test_upload_limits_and_rules(iapi: Api) -> None:
    await iapi.sign_up("owner@acme.example")
    conn = await csv_connection(iapi)
    big = "code,name\n" + "X,Y\n" * (5 * 1024 * 1024 // 4 + 10)
    r = await iapi.post(
        f"/integrations/{conn}/uploads",
        data={"kind": "locations"},
        files={"file": ("big.csv", big.encode(), "text/csv")},
    )
    assert (r.status_code, error_code(r)) == (413, "file_too_large")
    r = await iapi.post(
        f"/integrations/{conn}/uploads",
        data={"kind": "locations"},
        files={"file": ("bin.csv", b"\xff\xfe\x00bad", "text/csv")},
    )
    assert "UTF-8" in r.json()["errors"][0]["message"]
    r = await iapi.post(f"/integrations/{conn}/sync")
    assert (r.status_code, error_code(r)) == (409, "not_syncable")


def test_future_sales_dates_are_rejected() -> None:
    parsed = csv_import.parse(
        "sales", b"date,sku,quantity\n2999-01-01,A,1\n", known_skus={"A"}, known_locations=set()
    )
    assert parsed.errors[0].message == "is in the future"


def test_purchase_order_lines_must_agree() -> None:
    parsed = csv_import.parse(
        "purchase_orders",
        b"po_number,supplier,status,sku,quantity\nPO-1,X,open,A,1\nPO-1,Y,open,A,1\n",
        known_skus={"A"},
        known_locations=set(),
    )
    assert parsed.errors[0].message == "has different supplier or status on another line"
