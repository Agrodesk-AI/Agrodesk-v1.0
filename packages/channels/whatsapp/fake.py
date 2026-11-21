"""Dev BSP: in-process send sink + HMAC-SHA256 webhook signature over raw body.

Not a real BSP integration. Replace with a vendor-specific class that
implements the same Protocol."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime

from packages.channels.whatsapp.base import (
    InboundEvent,
    ProviderError,
    ProviderResult,
    WhatsAppProvider,
)

log = logging.getLogger("whatsapp.fake")


class FakeWhatsAppProvider:
    name = "fake"

    # Allow tests to reset / inspect what was sent
    sent: list[dict] = []
    # Allow tests to force errors for the next call
    _force_error: str | None = None

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    # --- send ---

    async def send_session(
        self, *, to_phone: str, from_phone: str, body: str, idempotency_key: str
    ) -> ProviderResult:
        return await self._send(
            {"kind": "session", "to": to_phone, "from": from_phone, "body": body,
             "idempotency_key": idempotency_key},
        )

    async def send_template(
        self, *, to_phone: str, from_phone: str, template_name: str,
        template_vars: dict, idempotency_key: str,
    ) -> ProviderResult:
        return await self._send(
            {"kind": "template", "to": to_phone, "from": from_phone,
             "template": template_name, "vars": template_vars,
             "idempotency_key": idempotency_key},
        )

    async def _send(self, payload: dict) -> ProviderResult:
        if FakeWhatsAppProvider._force_error == "retryable":
            FakeWhatsAppProvider._force_error = None
            raise ProviderError("simulated 500", retryable=True)
        if FakeWhatsAppProvider._force_error == "permanent":
            FakeWhatsAppProvider._force_error = None
            raise ProviderError("simulated 400", retryable=False)
        pmid = f"fake-{uuid.uuid4()}"
        FakeWhatsAppProvider.sent.append({**payload, "provider_message_id": pmid,
                                          "at": datetime.now(UTC).isoformat()})
        log.info("[FAKE WA SEND] %s", payload)
        return ProviderResult(provider_message_id=pmid)

    # --- signature ---

    def sign(self, body: bytes) -> str:
        return "sha256=" + hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def verify_signature(self, headers: dict, body: bytes) -> bool:
        sig = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not sig:
            return False
        expected = self.sign(body)
        return hmac.compare_digest(sig, expected)

    # --- webhook parse ---

    def parse_webhook(self, body: bytes) -> list[InboundEvent]:
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            return []
        events: list[InboundEvent] = []
        for raw in data.get("events", []):
            if raw.get("type") == "message":
                events.append(InboundEvent(
                    kind="message",
                    provider_message_id=raw["id"],
                    from_phone=raw["from"],
                    to_phone=raw["to"],
                    text=raw.get("text"),
                    media_url=raw.get("media_url"),
                    occurred_at=datetime.now(UTC),
                    raw=raw,
                ))
            elif raw.get("type") == "status":
                events.append(InboundEvent(
                    kind="status",
                    provider_message_id=raw["id"],
                    from_phone="",
                    to_phone="",
                    status=raw.get("status"),
                    failure_reason=raw.get("failure_reason"),
                    raw=raw,
                ))
        return events
