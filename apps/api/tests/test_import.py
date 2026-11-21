import io
from datetime import UTC, datetime, timedelta

import pytest
from openpyxl import Workbook

from tests._helpers import make_dealer_and_owner, token_for


def _csv(rows: list[list[str]]) -> bytes:
    lines = [",".join(cols) for cols in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _xlsx(rows: list[list[str]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_HEADER = ["phone", "name", "model", "source", "next_action_at"]
_MAPPING = (
    '{"phone":"phone","name":"name","model_interest":"model",'
    '"source":"source","next_action_at":"next_action_at"}'
)


def _tomorrow_iso() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")


async def _post(client, hdr, body: bytes, filename: str = "leads.csv", **extra):
    form = {
        "mapping": _MAPPING,
        "default_source": "other",
        "duplicate_policy": "create_lead_only",
        "dry_run": "false",
    }
    form.update({k: str(v) for k, v in extra.items()})
    return await client.post(
        "/v1/leads/import",
        headers=hdr,
        files={"file": (filename, body, "application/octet-stream")},
        data=form,
    )


@pytest.mark.asyncio
async def test_csv_all_valid_creates_leads(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000001")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER] + [
        [f"98000{10000 + i:05d}", f"Farmer {i}", "Mahindra 575", "facebook", _tomorrow_iso()]
        for i in range(5)
    ]
    r = await _post(client, hdr, _csv(rows))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 5 and d["errors"] == [] and d["total"] == 5


@pytest.mark.asyncio
async def test_xlsx_all_valid(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000002")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER] + [
        [f"98010{20000 + i:05d}", f"F{i}", "", "walk_in", _tomorrow_iso()] for i in range(3)
    ]
    r = await _post(client, hdr, _xlsx(rows), filename="leads.xlsx")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created"] == 3


@pytest.mark.asyncio
async def test_bad_phone_is_reported(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000003")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER, ["abc", "Bad", "", "facebook", _tomorrow_iso()],
            ["9876500001", "Good", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows))
    d = r.json()
    assert d["created"] == 1
    assert len(d["errors"]) == 1
    assert d["errors"][0]["field"] == "phone"


@pytest.mark.asyncio
async def test_bad_source_is_reported(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000004")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER, ["9876500002", "N", "", "whatever", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows))
    d = r.json()
    assert d["created"] == 0
    assert d["errors"][0]["field"] == "source"


@pytest.mark.asyncio
async def test_duplicate_skip(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000005")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER,
            ["9876500010", "A", "", "facebook", _tomorrow_iso()],
            ["9876500010", "A again", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows), duplicate_policy="skip")
    d = r.json()
    assert d["created"] == 1 and d["skipped"] == 1


@pytest.mark.asyncio
async def test_duplicate_update_customer(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000006")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER,
            ["9876500020", "First Name", "", "facebook", _tomorrow_iso()],
            ["9876500020", "Updated Name", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows), duplicate_policy="update_customer")
    d = r.json()
    assert d["created"] == 2 and d["updated"] == 1


@pytest.mark.asyncio
async def test_duplicate_create_lead_only_keeps_customer(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000007")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER,
            ["9876500030", "First", "", "facebook", _tomorrow_iso()],
            ["9876500030", "Should Be Ignored", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows), duplicate_policy="create_lead_only")
    d = r.json()
    assert d["created"] == 2 and d["updated"] == 0

    # The customer's name stays the first one (not updated)
    r = await client.get("/v1/leads", headers=hdr)
    leads = r.json()
    customer_id = leads[0]["customer_id"]
    r = await client.get(f"/v1/customers/{customer_id}", headers=hdr)
    assert r.json()["name"] == "First"


@pytest.mark.asyncio
async def test_cross_tenant_import(client):
    dealer_a, owner_a, _, _ = await make_dealer_and_owner("A", "9004000008")
    dealer_b, owner_b, _, _ = await make_dealer_and_owner("B", "9004000009")
    hdr_b = {"Authorization": f"Bearer {token_for(owner_b, 'owner', dealer_b)}"}
    # Seed dealer B with a phone
    rows_b = [_HEADER, ["9876500050", "B owner", "", "facebook", _tomorrow_iso()]]
    await _post(client, hdr_b, _csv(rows_b))

    # Dealer A imports the same phone — must create a new customer in A, not touch B
    hdr_a = {"Authorization": f"Bearer {token_for(owner_a, 'owner', dealer_a)}"}
    rows_a = [_HEADER, ["9876500050", "A owner", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr_a, _csv(rows_a))
    assert r.json()["created"] == 1


@pytest.mark.asyncio
async def test_acceptance_100_rows_10_dup_5_invalid(client):
    """From the brief: 100-row file with 10 duplicates and 5 invalid phones
    yields 85 valid results on 'skip', and 15 reported (10 skipped + 5 errors)."""
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000010")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    tomorrow = _tomorrow_iso()
    rows: list[list[str]] = [_HEADER]
    # 85 unique valid
    for i in range(85):
        rows.append([f"98030{10000 + i:05d}", f"Farmer {i}", "", "facebook", tomorrow])
    # 10 duplicates of the first phone
    dup_phone = rows[1][0]
    for _ in range(10):
        rows.append([dup_phone, "Dup", "", "facebook", tomorrow])
    # 5 invalid phones
    for i in range(5):
        rows.append([f"abc{i}", f"Bad {i}", "", "facebook", tomorrow])

    r = await _post(client, hdr, _csv(rows), duplicate_policy="skip")
    d = r.json()
    assert d["total"] == 100
    assert d["created"] == 85
    assert d["skipped"] == 10
    assert len(d["errors"]) == 5
    assert all(e["field"] == "phone" for e in d["errors"])


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000011")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [_HEADER, ["9876500090", "F", "", "facebook", _tomorrow_iso()]]
    r = await _post(client, hdr, _csv(rows), dry_run=True)
    d = r.json()
    assert d["created"] == 1 and d["dry_run"] is True

    r = await client.get("/v1/leads", headers=hdr)
    assert r.json() == []


@pytest.mark.asyncio
async def test_missing_required_column_rejects(client):
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9004000012")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    rows = [["name", "source"], ["X", "facebook"]]
    r = await _post(client, hdr, _csv(rows))
    assert r.status_code == 422
    assert "missing_column" in r.json()["detail"]
