"""Inbound message handling (webhook ingestion)."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Customer, Dealer, LeadEvent, Message
from app.security.phone import normalize_phone
from app.security.tenant import set_tenant_context
from packages.channels.whatsapp.base import InboundEvent

OPT_OUT_LATIN = {"STOP", "STOP ALL", "BAND", "UNSUBSCRIBE"}
# Marathi/Hindi phrases — will need native-speaker review before pilot.
OPT_OUT_DEVANAGARI = {"रद्द", "बंद", "बंद करो", "मैसेज बंद"}


def _is_opt_out(body: str | None) -> bool:
    if not body:
        return False
    stripped = body.strip()
    if stripped.upper() in OPT_OUT_LATIN:
        return True
    return any(p in stripped for p in OPT_OUT_DEVANAGARI)


async def resolve_dealer_by_number(session: AsyncSession, business_phone: str) -> Dealer | None:
    # Resolution needs to bypass tenant scoping (we don't yet know the dealer).
    norm = normalize_phone(business_phone)
    return await session.scalar(select(Dealer).where(Dealer.whatsapp_number == norm))


async def record_inbound_message(
    session: AsyncSession, dealer: Dealer, event: InboundEvent
) -> Message | None:
    """Returns the inserted Message, or None if this provider_message_id already exists."""
    # Idempotency: unique index on provider_message_id.
    existing = await session.scalar(
        select(Message).where(Message.provider_message_id == event.provider_message_id)
    )
    if existing is not None:
        return None

    # Scope to the dealer for the writes.
    await set_tenant_context(session, dealer_id=str(dealer.id), is_platform_admin=False)

    customer_phone = normalize_phone(event.from_phone)
    customer = await session.scalar(
        select(Customer).where(
            Customer.dealer_id == dealer.id, Customer.phone == customer_phone
        )
    )
    if customer is None:
        customer = Customer(
            dealer_id=dealer.id,
            name=f"WhatsApp {customer_phone}",
            phone=customer_phone,
            language=dealer.default_language or "mr",
        )
        session.add(customer)
        await session.flush()

    conv = await session.scalar(
        select(Conversation).where(
            Conversation.dealer_id == dealer.id,
            Conversation.customer_id == customer.id,
            Conversation.channel == "whatsapp",
        )
    )
    now = event.occurred_at or datetime.now(UTC)
    if conv is None:
        conv = Conversation(
            dealer_id=dealer.id, customer_id=customer.id, channel="whatsapp",
            last_message_at=now, last_customer_message_at=now,
        )
        session.add(conv)
        await session.flush()
    else:
        conv.last_message_at = now
        conv.last_customer_message_at = now

    msg = Message(
        dealer_id=dealer.id,
        conversation_id=conv.id,
        direction="inbound",
        content=event.text,
        media_url=event.media_url,
        transcript=event.transcript,
        status="delivered",
        provider_message_id=event.provider_message_id,
        occurred_at=now,
    )
    session.add(msg)
    await session.flush()

    # Opt-out?
    if _is_opt_out(event.text):
        customer.opted_out_at = now
        customer.consent_whatsapp = False
        customer.consent_call = False
        # Attach an opt-out event to the most recent open lead, if any.
        from app.models import Lead
        lead = await session.scalar(
            select(Lead).where(Lead.customer_id == customer.id, Lead.stage.notin_(("won", "lost")))
            .order_by(Lead.created_at.desc()).limit(1)
        )
        if lead is not None:
            session.add(LeadEvent(
                dealer_id=dealer.id, lead_id=lead.id, type="opted_out",
                payload={"via": "whatsapp_message", "message": event.text},
                actor_type="system", occurred_at=now,
            ))
        await session.flush()

    return msg


async def record_status(session: AsyncSession, event: InboundEvent) -> bool:
    msg = await session.scalar(
        select(Message).where(Message.provider_message_id == event.provider_message_id)
    )
    if msg is None:
        return False
    if event.status is not None:
        # Don't overwrite a terminal status with an earlier one.
        rank = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4, "rejected": 4}
        if rank.get(event.status, 0) >= rank.get(msg.status, 0):
            msg.status = event.status
        if event.failure_reason:
            msg.failure_reason = event.failure_reason
    await session.flush()
    return True
