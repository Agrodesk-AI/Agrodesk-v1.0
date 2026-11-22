"""Farmer foundation: LGD import, onboarding, profiles, RLS, nearby.

Location fixtures use made-up LGD codes (9xxxxx) — they are test data, not the
real directory. Two states in different scripts make sure nothing is
Maharashtra-specific.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import District, Farmer, State, Tehsil
from app.security.tenant import set_tenant_context
from app.services import location_import
from tests._helpers import make_dealer_and_owner, make_platform_admin, token_for
from tests.test_auth_otp import _peek_code_hash_and_set

STATES_CSV = """S.No.,State Code,State Name (In English),State Name (In Local)
1,900027,Maharashtra,महाराष्ट्र
2,900033,Tamil Nadu,தமிழ்நாடு
"""
DISTRICTS_CSV = """District Code,District Name (In English),District Name (In Local),State Code
900516,Nashik,नाशिक,900027
900603,Thanjavur,தஞ்சாவூர்,900033
"""
TEHSILS_CSV = """Sub-District Code,Sub-District Name (In English),Sub-District Name (In Local),District Code
"""  # noqa: E501
TEHSILS_CSV += """\
904101,Niphad,निफाड,900516
904102,Sinnar,सिन्नर,900516
904103,Yeola,येवला,900516
905201,Kumbakonam,கும்பகோணம்,900603
"""
VILLAGES_CSV = """Village Code,Village Name (In English),Village Name (In Local),Sub-District Code
9550001,Pimpalgaon Baswant,पिंपळगाव बसवंत,904101
9550002,Ozar,ओझर,904101
9550003,Vadangali,वडांगळी,904102
"""


async def _seed_locations() -> None:
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        await location_import.import_level(s, "states", STATES_CSV, None)
        await location_import.import_level(s, "districts", DISTRICTS_CSV, None)
        await location_import.import_level(s, "tehsils", TEHSILS_CSV, "mr")
        await location_import.import_level(s, "villages", VILLAGES_CSV, "mr")


async def _login(client, phone: str, code: str = "424242") -> dict:
    r = await client.post("/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    await _peek_code_hash_and_set("+91" + phone[-10:], code)
    r = await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


def _h(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _onboard_body(**kw) -> dict:
    body = {
        "display_name": "Sunita Pawar",
        "language": "mr",
        "tehsil_id": 904101,
        "village_id": 9550001,
        "dob": "1980-05-01",
    }
    body.update(kw)
    return body


# ---------------- import ----------------


@pytest.mark.asyncio
async def test_lgd_import_is_idempotent_and_merges_languages(client):
    await _seed_locations()
    await _seed_locations()  # re-run: no duplicates, no errors
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        assert len((await s.scalars(select(State))).all()) == 2
        # second file adds Hindi for the same district without dropping the default key
        await location_import.import_level(
            s,
            "districts",
            "District Code,District Name (In English),District Name (In Local),State Code\n"
            "900516,Nashik,नासिक,900027\n",
            "hi",
        )
        d = await s.get(District, 900516)
        await s.refresh(d)
        assert d.names == {"local": "नाशिक", "hi": "नासिक"}
        assert d.name_in("hi") == "नासिक"
        assert d.name_in("mr") == "नाशिक"  # untagged Devanagari serves mr readers
        assert d.name_in("ta") == "Nashik"  # never Devanagari for a Tamil reader
        assert d.name_in("en") == "Nashik"
        # Tamil names are auto-tagged by script
        assert (await s.get(State, 900033)).names == {"ta": "தமிழ்நாடு"}
        # tehsils file was tagged --local-lang mr, but Kumbakonam's Tamil name
        # must not be labelled Marathi
        assert (await s.get(Tehsil, 905201)).names == {"ta": "கும்பகோணம்"}
        assert (await s.get(Tehsil, 904101)).names == {"mr": "निफाड"}


def test_lgd_import_rejects_missing_columns():
    with pytest.raises(location_import.ImportError_):
        list(location_import.parse_rows("Foo,Bar\n1,2\n", "districts", None))
    with pytest.raises(location_import.ImportError_):
        list(
            location_import.parse_rows(
                "District Code,District Name (In English),State Code\nabc,X,1\n", "districts", None
            )
        )


# ---------------- onboarding ----------------


@pytest.mark.asyncio
async def test_new_phone_onboards_as_farmer(client):
    await _seed_locations()
    acct = await _login(client, "9888800001")
    assert acct["active_kind"] == "account"

    # onboarding token can browse locations
    r = await client.get("/v1/locations/states", params={"lang": "ta"}, headers=_h(acct))
    assert r.status_code == 200
    # Tamil reader: Tamil where present, English (not Devanagari) otherwise
    assert {s["name"] for s in r.json()} == {"Maharashtra", "தமிழ்நாடு"}
    r = await client.get(
        "/v1/locations/districts/900516/tehsils", params={"lang": "mr"}, headers=_h(acct)
    )
    assert [t["name"] for t in r.json()] == ["निफाड", "सिन्नर", "येवला"]

    # but not farmer routes yet
    assert (await client.get("/v1/farmer/me", headers=_h(acct))).status_code == 403

    r = await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(acct))
    assert r.status_code == 201, r.text
    farmer_tokens = r.json()
    assert farmer_tokens["active_kind"] == "farmer"
    assert [p["kind"] for p in farmer_tokens["profiles"]] == ["farmer"]

    r = await client.get("/v1/farmer/me", headers=_h(farmer_tokens))
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["phone"] == "+919888800001"
    assert me["tehsil"]["name"] == "निफाड"
    assert me["village"]["name"] == "पिंपळगाव बसवंत"
    assert me["district"]["name_en"] == "Nashik"
    assert me["state"]["id"] == 900027

    # farmer token must never reach dealer routes
    assert (await client.get("/v1/leads", headers=_h(farmer_tokens))).status_code == 403
    assert (await client.get("/v1/me", headers=_h(farmer_tokens))).status_code == 403

    # update: move tehsil drops the old village
    r = await client.patch(
        "/v1/farmer/me", json={"tehsil_id": 904102, "language": "hi"}, headers=_h(farmer_tokens)
    )
    assert r.status_code == 200, r.text
    assert r.json()["village"] is None
    assert r.json()["language"] == "hi"

    # second login lands straight on the farmer profile
    again = await _login(client, "9888800001", "515151")
    assert again["active_kind"] == "farmer"


@pytest.mark.asyncio
async def test_onboarding_rules(client):
    await _seed_locations()
    acct = await _login(client, "9888800002")
    today = datetime.now(UTC).date()
    minor = date(today.year - 15, 1, 1).isoformat()

    r = await client.post("/v1/farmer/onboard", json=_onboard_body(dob=minor), headers=_h(acct))
    assert r.status_code == 403 and r.json()["detail"] == "age_gate"

    r = await client.post(
        "/v1/farmer/onboard",
        json=_onboard_body(tehsil_id=904102, village_id=9550001),
        headers=_h(acct),
    )
    assert r.status_code == 422 and r.json()["detail"] == "village_not_in_tehsil"

    r = await client.post("/v1/farmer/onboard", json=_onboard_body(tehsil_id=1), headers=_h(acct))
    assert r.status_code == 422 and r.json()["detail"] == "unknown_tehsil"

    r = await client.post("/v1/farmer/onboard", json=_onboard_body(language="xx"), headers=_h(acct))
    assert r.status_code == 422

    # a Tamil farmer, no village picked: fine
    r = await client.post(
        "/v1/farmer/onboard",
        json=_onboard_body(language="ta", tehsil_id=905201, village_id=None),
        headers=_h(acct),
    )
    assert r.status_code == 201, r.text
    r = await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(acct))
    assert r.status_code == 409


# ---------------- multi-profile ----------------


@pytest.mark.asyncio
async def test_dealer_owner_can_also_be_farmer_and_switch(client):
    await _seed_locations()
    _, owner_id, phone, _ = await make_dealer_and_owner("Sai Tractors", "9888800003")
    staff = await _login(client, "9888800003")
    assert staff["active_kind"] == "staff"
    assert staff["active_profile_id"] == owner_id

    r = await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(staff))
    assert r.status_code == 201, r.text
    farmer = r.json()
    assert {p["kind"] for p in farmer["profiles"]} == {"staff", "farmer"}

    # login still defaults to staff; profile_id picks farmer
    assert (await _login(client, "9888800003", "111222"))["active_kind"] == "staff"

    r = await client.post(
        "/v1/auth/switch-profile", json={"profile_id": owner_id}, headers=_h(farmer)
    )
    assert r.status_code == 200
    back = r.json()
    assert back["active_kind"] == "staff"
    assert (await client.get("/v1/me", headers=_h(back))).status_code == 200

    # someone else's profile id is refused
    other = await _login(client, "9888800004")
    r = await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(other))
    other_farmer_id = r.json()["active_profile_id"]
    r = await client.post(
        "/v1/auth/switch-profile", json={"profile_id": other_farmer_id}, headers=_h(back)
    )
    assert r.status_code == 403

    # refresh keeps the farmer profile
    r = await client.post("/v1/auth/refresh", json={"refresh_token": farmer["refresh_token"]})
    assert r.status_code == 200 and r.json()["active_kind"] == "farmer"


@pytest.mark.asyncio
async def test_account_refresh_moves_onto_new_farmer_profile(client):
    await _seed_locations()
    acct = await _login(client, "9888800005")
    await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(acct))
    r = await client.post("/v1/auth/refresh", json={"refresh_token": acct["refresh_token"]})
    assert r.status_code == 200 and r.json()["active_kind"] == "farmer"


# ---------------- RLS ----------------


@pytest.mark.asyncio
async def test_farmer_rls_isolation(client):
    await _seed_locations()
    a = await _login(client, "9888800006")
    a = (await client.post("/v1/farmer/onboard", json=_onboard_body(), headers=_h(a))).json()
    b = await _login(client, "9888800007")
    b = (
        await client.post("/v1/farmer/onboard", json=_onboard_body(display_name="B"), headers=_h(b))
    ).json()

    async with SessionLocal() as s, s.begin():
        await set_tenant_context(
            s, dealer_id=None, is_platform_admin=False, farmer_id=a["active_profile_id"]
        )
        ids = {str(f.id) for f in (await s.scalars(select(Farmer))).all()}
        assert ids == {a["active_profile_id"]}
        n = (await s.execute(text("SELECT count(*) FROM accounts"))).scalar()
        assert n == 0  # no account GUC -> no account rows
        # cannot write B's row either
        res = await s.execute(
            text("UPDATE farmers SET display_name='pwned' WHERE id = :id"),
            {"id": b["active_profile_id"]},
        )
        assert res.rowcount == 0

    # dealer context sees no farmers
    dealer_id, owner_id, _, _ = await make_dealer_and_owner("Isolated", "9888800008")
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer_id, is_platform_admin=False)
        assert (await s.scalars(select(Farmer))).all() == []


# ---------------- nearby ----------------


@pytest.mark.asyncio
async def test_nearby_falls_back_to_district_then_uses_curated(client):
    await _seed_locations()
    admin_id, _ = await make_platform_admin("9888800009")
    admin_h = {"Authorization": f"Bearer {token_for(admin_id, 'platform_admin', None)}"}
    acct = await _login(client, "9888800010")

    r = await client.get("/v1/locations/tehsils/904101/nearby", headers=_h(acct))
    assert r.status_code == 200
    assert [(t["id"], t["rank"]) for t in r.json()] == [(904101, 0), (904102, 99), (904103, 99)]

    body = {"neighbours": [{"tehsil_id": 904103, "rank": 1}]}
    r = await client.put(
        "/v1/admin/locations/tehsils/904101/neighbours", json=body, headers=_h(acct)
    )
    assert r.status_code == 403
    r = await client.put(
        "/v1/admin/locations/tehsils/904101/neighbours", json=body, headers=admin_h
    )
    assert r.status_code == 200, r.text
    assert [(t["id"], t["rank"]) for t in r.json()] == [(904101, 0), (904103, 1)]

    # symmetric: Yeola now lists Niphad
    r = await client.get("/v1/locations/tehsils/904103/nearby", headers=_h(acct))
    assert [(t["id"], t["rank"]) for t in r.json()] == [(904103, 0), (904101, 1)]

    r = await client.put(
        "/v1/admin/locations/tehsils/904101/neighbours",
        json={"neighbours": [{"tehsil_id": 1}]},
        headers=admin_h,
    )
    assert r.status_code == 422

    assert (await client.get("/v1/locations/tehsils/1/nearby", headers=_h(acct))).status_code == 404


@pytest.mark.asyncio
async def test_village_search(client):
    await _seed_locations()
    acct = await _login(client, "9888800011")
    r = await client.get("/v1/locations/villages", params={"q": "oz"}, headers=_h(acct))
    assert r.status_code == 422  # must scope to tehsil or district

    r = await client.get(
        "/v1/locations/villages", params={"q": "oz", "district_id": 900516}, headers=_h(acct)
    )
    assert [v["name_en"] for v in r.json()] == ["Ozar"]

    r = await client.get(
        "/v1/locations/villages",
        params={"q": "पिंपळ", "tehsil_id": 904101, "lang": "mr"},
        headers=_h(acct),
    )
    assert [v["name"] for v in r.json()] == ["पिंपळगाव बसवंत"]

    r = await client.get(
        "/v1/locations/villages", params={"q": "%", "tehsil_id": 904101}, headers=_h(acct)
    )
    assert r.json() == []  # LIKE wildcards are escaped
