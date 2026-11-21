import json

from fastapi import APIRouter, HTTPException, Request, status

from app.core.db import SessionLocal
from app.security.tenant import set_tenant_context
from app.services import message_service
from packages.channels.whatsapp import get_provider

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> dict:
    provider = get_provider()
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not provider.verify_signature(headers, body):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad_signature")

    events = provider.parse_webhook(body)
    processed = 0
    duplicates = 0
    status_updates = 0
    unknown_dealer = 0
    async with SessionLocal() as session, session.begin():
        # Start as platform admin so we can look up the dealer.
        await set_tenant_context(session, dealer_id=None, is_platform_admin=True)
        for ev in events:
            if ev.kind == "status":
                ok = await message_service.record_status(session, ev)
                if ok:
                    status_updates += 1
                continue
            # kind == "message"
            dealer = await message_service.resolve_dealer_by_number(session, ev.to_phone)
            if dealer is None:
                unknown_dealer += 1
                continue
            msg = await message_service.record_inbound_message(session, dealer, ev)
            if msg is None:
                duplicates += 1
            else:
                processed += 1
            # Reset context for the next event's platform-admin lookup
            await set_tenant_context(session, dealer_id=None, is_platform_admin=True)

    return {
        "ok": True,
        "processed": processed,
        "duplicates": duplicates,
        "status_updates": status_updates,
        "unknown_dealer": unknown_dealer,
    }
