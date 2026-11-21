from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import Conversation, Customer, LeadEvent, Message, OutboxItem
from app.security.tenant import set_tenant_context
from app.services import outbox_service
from packages.channels.whatsapp.factory import get_provider, reset_provider
from packages.channels.whatsapp.fake import FakeWhatsAppProvider
from tests._helpers import future, make_dealer_and_owner, token_for


async def _mklead_and_customer(client, hdr, phone):
    r = await client.post(
        "/v1/leads", headers=hdr,
        json={"name": "R", "phone": phone, "source": "facebook", "next_action_at": future()},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _make_session_conversation(dealer_id: str, customer_id: str) -> None:
    """Set last_customer_message_at = now so the session-window gate passes."""
    now = datetime.now(UTC)
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        conv = Conversation(
            dealer_id=dealer_id, customer_id=customer_id, channel="whatsapp",
            last_customer_message_at=now, last_message_at=now,
        )
        s.add(conv)


@pytest.mark.asyncio
async def test_send_session_happy_path(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000001")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000001")
    await _make_session_conversation(dealer, lead["customer_id"])

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            lead_id=lead["id"],
            kind="wa_session",
            payload={"body": "Hi Ramesh, this is Mitra."},
            idempotency_key=key,
        )

    out = await outbox_service.process_pending()
    assert out["sent"] == 1
    assert len(FakeWhatsAppProvider.sent) == 1

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        row = await s.scalar(select(OutboxItem).where(OutboxItem.idempotency_key == key))
        assert row.status == "sent"
        msg = await s.scalar(select(Message).where(Message.idempotency_key == key))
        assert msg is not None and msg.status == "sent"


@pytest.mark.asyncio
async def test_opted_out_customer_rejects(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000002")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000002")

    # Opt the customer out
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        cust = await s.scalar(select(Customer).where(Customer.id == lead["customer_id"]))
        cust.opted_out_at = datetime.now(UTC)

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            kind="wa_session",
            payload={"body": "hi"},
            idempotency_key=key,
        )
    out = await outbox_service.process_pending()
    assert out["rejected"] == 1
    assert len(FakeWhatsAppProvider.sent) == 0


@pytest.mark.asyncio
async def test_outside_window_session_send_rejected(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000003")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000003")
    # no conversation → no last_customer_message_at → outside window

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            kind="wa_session",
            payload={"body": "cold outreach"},
            idempotency_key=key,
        )
    out = await outbox_service.process_pending()
    assert out["rejected"] == 1
    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        row = await s.scalar(select(OutboxItem).where(OutboxItem.idempotency_key == key))
        assert row.last_error == "outside_session_window"


@pytest.mark.asyncio
async def test_template_send_works_outside_window(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000004")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000004")

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            kind="wa_template",
            payload={"template_name": "lead_first_touch", "template_vars": {"name": "Ramesh"}},
            idempotency_key=key,
        )
    out = await outbox_service.process_pending()
    assert out["sent"] == 1
    sent = FakeWhatsAppProvider.sent[-1]
    assert sent["template"] == "lead_first_touch"


@pytest.mark.asyncio
async def test_retry_on_retryable_error(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000005")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000005")
    await _make_session_conversation(dealer, lead["customer_id"])

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            kind="wa_session",
            payload={"body": "hi"},
            idempotency_key=key,
        )

    FakeWhatsAppProvider._force_error = "retryable"
    out = await outbox_service.process_pending()
    assert out["retried"] == 1

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        row = await s.scalar(select(OutboxItem).where(OutboxItem.idempotency_key == key))
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.next_attempt_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_dead_letter_after_max_attempts(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000006")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000006")
    await _make_session_conversation(dealer, lead["customer_id"])

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            lead_id=lead["id"],
            kind="wa_session",
            payload={"body": "hi"},
            idempotency_key=key,
        )

    # Force 6 failures; between each run, reset next_attempt_at so it is picked up again.
    for _ in range(6):
        FakeWhatsAppProvider._force_error = "retryable"
        await outbox_service.process_pending()
        async with SessionLocal() as s, s.begin():
            await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
            await s.execute(text(
                "UPDATE outbox SET next_attempt_at = now() WHERE idempotency_key = :k"
            ), {"k": key})

    async with SessionLocal() as s, s.begin():
        await s.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        row = await s.scalar(select(OutboxItem).where(OutboxItem.idempotency_key == key))
        assert row.status == "failed"
        # Dead-letter event on the lead
        events = (await s.scalars(
            select(LeadEvent).where(LeadEvent.lead_id == lead["id"], LeadEvent.type == "note")
        )).all()
        kinds = [e.payload.get("kind") for e in events]
        assert "message_dead_letter" in kinds


@pytest.mark.asyncio
async def test_permanent_error_rejects(client):
    reset_provider()
    FakeWhatsAppProvider.sent.clear()
    dealer, owner, _, _ = await make_dealer_and_owner("A", "9007000007")
    hdr = {"Authorization": f"Bearer {token_for(owner, 'owner', dealer)}"}
    lead = await _mklead_and_customer(client, hdr, "9877000007")
    await _make_session_conversation(dealer, lead["customer_id"])

    key = f"test-{uuid4()}"
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=dealer, is_platform_admin=False)
        await outbox_service.enqueue(
            s,
            dealer_id=dealer,
            customer_id=lead["customer_id"],
            kind="wa_session",
            payload={"body": "hi"},
            idempotency_key=key,
        )
    FakeWhatsAppProvider._force_error = "permanent"
    out = await outbox_service.process_pending()
    assert out["rejected"] == 1
