import pytest
from sqlalchemy import text

from app.core.db import SessionLocal
from tests._helpers import last_otp_for, make_dealer_and_owner


async def _peek_code_hash_and_set(phone: str, plain_code: str) -> None:
    """Replace the hash of the latest OTP for `phone` with a hash of `plain_code`,
    so the test can verify without reading the log."""
    from app.security.otp import hash_code

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await s.execute(
            text("""UPDATE otp_codes SET code_hash = :h
                    WHERE id = (SELECT id FROM otp_codes WHERE phone = :p
                                ORDER BY created_at DESC LIMIT 1)"""),
            {"h": hash_code(plain_code), "p": phone},
        )


@pytest.mark.asyncio
async def test_happy_path(client):
    _, _, phone, _ = await make_dealer_and_owner("Acme Tractors", "9999900001")
    r = await client.post("/v1/auth/otp/request", json={"phone": "9999900001"})
    assert r.status_code == 200
    assert (await last_otp_for(phone)) is not None

    await _peek_code_hash_and_set(phone, "123456")
    r = await client.post("/v1/auth/otp/verify", json={"phone": "9999900001", "code": "123456"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data and "refresh_token" in data

    r = await client.get("/v1/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert r.status_code == 200
    assert r.json()["phone"] == phone


@pytest.mark.asyncio
async def test_wrong_and_replay_otp(client):
    _, _, phone, _ = await make_dealer_and_owner("Acme", "9999900002")
    await client.post("/v1/auth/otp/request", json={"phone": phone})
    await _peek_code_hash_and_set(phone, "654321")

    r = await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": "000000"})
    assert r.status_code == 401

    r = await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": "654321"})
    assert r.status_code == 200

    # replay the same code → rejected because the OTP is now used
    r = await client.post("/v1/auth/otp/verify", json={"phone": phone, "code": "654321"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit(client):
    _, _, phone, _ = await make_dealer_and_owner("Acme", "9999900003")
    for _ in range(3):
        r = await client.post("/v1/auth/otp/request", json={"phone": phone})
        assert r.status_code == 200
    r = await client.post("/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_unknown_phone_rejected(client):
    # No user exists for this phone; request returns 200 (no enumeration), verify fails.
    r = await client.post("/v1/auth/otp/request", json={"phone": "9999999999"})
    assert r.status_code == 200
    await _peek_code_hash_and_set("+919999999999", "111111")
    r = await client.post("/v1/auth/otp/verify", json={"phone": "9999999999", "code": "111111"})
    assert r.status_code == 401
