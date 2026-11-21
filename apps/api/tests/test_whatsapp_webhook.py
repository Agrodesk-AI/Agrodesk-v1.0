import json

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import Conversation, Customer, Message
from packages.channels.whatsapp.factory import get_provider, reset_provider
from tests._helpers import make_dealer_and_owner


async def _set_dealer_whatsapp(dealer_id: str, number: str) -> None:
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        await s.execute(
            text("UPDATE dealers SET whatsapp_number=:n WHERE id=:id"),
            {"n": number, "id": dealer_id},
        )


async def _post_webhook(client, body: dict, provider=None):
    if provider is None:
        provider = get_provider()
    raw = json.dumps(body).encode()
    sig = provider.sign(raw)
    return await client.post(
        "/v1/webhooks/whatsapp",
        content=raw,
        headers={"X-Hub-Signature-256": sig, "content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_inbound_message_creates_conversation(client):
    reset_provider()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9006000001")
    await _set_dealer_whatsapp(dealer, "+919100000001")

    body = {"events": [
        {"type": "message", "id": "wa-msg-1", "from": "9876000001",
         "to": "+919100000001", "text": "Hello"}
    ]}
    r = await _post_webhook(client, body)
    assert r.status_code == 200, r.text
    assert r.json()["processed"] == 1

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        msg = await s.scalar(select(Message).where(Message.provider_message_id == "wa-msg-1"))
        assert msg is not None
        assert msg.direction == "inbound"
        conv = await s.scalar(select(Conversation).where(Conversation.id == msg.conversation_id))
        assert conv.last_customer_message_at is not None


@pytest.mark.asyncio
async def test_webhook_replay_is_idempotent(client):
    reset_provider()
    dealer, _, _, _ = await make_dealer_and_owner("A", "9006000002")
    await _set_dealer_whatsapp(dealer, "+919100000002")

    body = {"events": [
        {"type": "message", "id": "wa-msg-2", "from": "9876000002",
         "to": "+919100000002", "text": "Hi"}
    ]}
    r1 = await _post_webhook(client, body)
    r2 = await _post_webhook(client, body)
    assert r1.json()["processed"] == 1 and r2.json()["duplicates"] == 1

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        rows = (await s.scalars(
            select(Message).where(Message.provider_message_id == "wa-msg-2")
        )).all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_bad_signature_rejected(client):
    reset_provider()
    dealer, _, _, _ = await make_dealer_and_owner("A", "9006000003")
    await _set_dealer_whatsapp(dealer, "+919100000003")
    r = await client.post(
        "/v1/webhooks/whatsapp",
        content=b'{"events":[]}',
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_status_updates_message(client):
    reset_provider()
    dealer, _, _, _ = await make_dealer_and_owner("A", "9006000004")
    await _set_dealer_whatsapp(dealer, "+919100000004")

    inbound = {"events": [
        {"type": "message", "id": "wa-msg-s1", "from": "9876000004",
         "to": "+919100000004", "text": "Hey"}
    ]}
    await _post_webhook(client, inbound)
    status = {"events": [
        {"type": "status", "id": "wa-msg-s1", "status": "delivered"}
    ]}
    r = await _post_webhook(client, status)
    assert r.json()["status_updates"] == 1
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        msg = await s.scalar(select(Message).where(Message.provider_message_id == "wa-msg-s1"))
        assert msg.status == "delivered"


@pytest.mark.asyncio
async def test_opt_out_marks_customer(client):
    reset_provider()
    dealer, _, _, _ = await make_dealer_and_owner("A", "9006000005")
    await _set_dealer_whatsapp(dealer, "+919100000005")

    body = {"events": [
        {"type": "message", "id": "wa-msg-opt1", "from": "9876000005",
         "to": "+919100000005", "text": "STOP"}
    ]}
    r = await _post_webhook(client, body)
    assert r.json()["processed"] == 1

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        cust = await s.scalar(select(Customer).where(Customer.phone == "+919876000005"))
        assert cust.opted_out_at is not None
        assert cust.consent_whatsapp is False


@pytest.mark.asyncio
async def test_unknown_dealer_does_not_crash(client):
    reset_provider()
    # No dealer has this business number
    body = {"events": [
        {"type": "message", "id": "wa-msg-x", "from": "9876000099",
         "to": "+919999999999", "text": "Hi"}
    ]}
    r = await _post_webhook(client, body)
    assert r.status_code == 200
    assert r.json()["unknown_dealer"] == 1
