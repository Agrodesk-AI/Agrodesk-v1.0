"""Outbox pattern. Writers call enqueue() inside their own transaction;
process_pending() runs on a Celery beat tick, dispatches to the WhatsApp
provider, handles retries, dead-letters after N attempts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Conversation, Customer, LeadEvent, Message, OutboxItem
from app.security.tenant import set_tenant_context
from packages.channels.whatsapp import OptOutError, ProviderError, get_provider

RETRY_DELAYS_SEC = [60, 300, 900, 3600, 14400, 86400]


class NotInSessionWindow(Exception):
    pass


async def enqueue(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    customer_id: UUID,
    kind: str,
    payload: dict,
    idempotency_key: str,
    lead_id: UUID | None = None,
) -> OutboxItem:
    now = datetime.now(UTC)
    row = OutboxItem(
        dealer_id=dealer_id,
        customer_id=customer_id,
        lead_id=lead_id,
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
        next_attempt_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def _dispatch_one(session: AsyncSession, row: OutboxItem) -> None:
    provider = get_provider()

    customer = await session.scalar(select(Customer).where(Customer.id == row.customer_id))
    if customer is None:
        row.status = "rejected"
        row.last_error = "customer_missing"
        return
    if customer.opted_out_at is not None:
        row.status = "rejected"
        row.last_error = "opted_out"
        return

    conv = await session.scalar(
        select(Conversation).where(
            Conversation.dealer_id == row.dealer_id,
            Conversation.customer_id == row.customer_id,
            Conversation.channel == "whatsapp",
        )
    )
    now = datetime.now(UTC)
    within_window = (
        conv is not None
        and conv.last_customer_message_at is not None
        and (now - conv.last_customer_message_at)
        < timedelta(hours=settings.whatsapp_session_window_hours)
    )

    from_phone = row.payload.get("from_phone", "")
    to_phone = row.payload.get("to_phone", customer.phone)

    try:
        if row.kind == "wa_session":
            if not within_window:
                row.status = "rejected"
                row.last_error = "outside_session_window"
                return
            res = await provider.send_session(
                to_phone=to_phone,
                from_phone=from_phone,
                body=row.payload["body"],
                idempotency_key=row.idempotency_key,
            )
            content = row.payload["body"]
            template_name = None
            template_vars = None
        elif row.kind == "wa_template":
            res = await provider.send_template(
                to_phone=to_phone,
                from_phone=from_phone,
                template_name=row.payload["template_name"],
                template_vars=row.payload.get("template_vars", {}),
                idempotency_key=row.idempotency_key,
            )
            content = None
            template_name = row.payload["template_name"]
            template_vars = row.payload.get("template_vars", {})
        else:
            row.status = "rejected"
            row.last_error = f"unknown_kind:{row.kind}"
            return
    except OptOutError:
        row.status = "rejected"
        row.last_error = "opted_out_at_provider"
        return
    except ProviderError as e:
        if not e.retryable:
            row.status = "rejected"
            row.last_error = str(e)
            return
        raise

    if conv is None:
        conv = Conversation(
            dealer_id=row.dealer_id, customer_id=row.customer_id, channel="whatsapp",
            last_message_at=now,
        )
        session.add(conv)
        await session.flush()
    else:
        conv.last_message_at = now

    msg = Message(
        dealer_id=row.dealer_id,
        conversation_id=conv.id,
        direction="outbound",
        content=content,
        template_name=template_name,
        template_vars=template_vars,
        status="sent",
        provider_message_id=res.provider_message_id,
        idempotency_key=row.idempotency_key,
        occurred_at=now,
    )
    session.add(msg)
    await session.flush()

    row.status = "sent"
    row.message_id = msg.id
    row.last_error = None


async def process_pending(now: datetime | None = None, limit: int = 100) -> dict:
    now = now or datetime.now(UTC)
    sent = failed = rejected = retried = 0
    async with SessionLocal() as s, s.begin():
        await set_tenant_context(s, dealer_id=None, is_platform_admin=True)
        rows = (await s.scalars(
            select(OutboxItem)
            .where(OutboxItem.status == "pending", OutboxItem.next_attempt_at <= now)
            .order_by(OutboxItem.next_attempt_at.asc())
            .limit(limit)
        )).all()
        for row in rows:
            try:
                await _dispatch_one(s, row)
            except ProviderError as e:
                row.attempts += 1
                row.last_error = str(e)
                if row.attempts >= settings.outbox_max_attempts:
                    row.status = "failed"
                    if row.lead_id is not None:
                        s.add(LeadEvent(
                            dealer_id=row.dealer_id, lead_id=row.lead_id, type="note",
                            payload={"kind": "message_dead_letter", "outbox_id": str(row.id),
                                     "last_error": row.last_error},
                            actor_type="system", occurred_at=now,
                        ))
                    failed += 1
                else:
                    delay_sec = RETRY_DELAYS_SEC[min(row.attempts, len(RETRY_DELAYS_SEC)) - 1]
                    row.next_attempt_at = now + timedelta(seconds=delay_sec)
                    retried += 1
                continue
            except Exception as e:
                # Unexpected error — treat as retryable.
                row.attempts += 1
                row.last_error = f"error:{type(e).__name__}:{e}"
                if row.attempts >= settings.outbox_max_attempts:
                    row.status = "failed"
                    failed += 1
                else:
                    delay_sec = RETRY_DELAYS_SEC[min(row.attempts, len(RETRY_DELAYS_SEC)) - 1]
                    row.next_attempt_at = now + timedelta(seconds=delay_sec)
                    retried += 1
                continue

            if row.status == "sent":
                sent += 1
            elif row.status == "rejected":
                rejected += 1
    return {"sent": sent, "rejected": rejected, "retried": retried, "failed": failed}
