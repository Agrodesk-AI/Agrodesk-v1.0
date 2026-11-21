from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol


class ProviderError(Exception):
    """Transient BSP failure (5xx or network). The outbox should retry."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class OptOutError(Exception):
    """The customer has opted out. The outbox should mark the row rejected
    and never retry."""


@dataclass
class ProviderResult:
    provider_message_id: str


@dataclass
class InboundEvent:
    kind: Literal["message", "status"]
    provider_message_id: str
    from_phone: str  # customer (E.164)
    to_phone: str    # business (E.164)
    text: str | None = None
    media_url: str | None = None
    transcript: str | None = None
    occurred_at: datetime | None = None
    status: Literal["sent", "delivered", "read", "failed"] | None = None
    failure_reason: str | None = None
    raw: dict = field(default_factory=dict)


class WhatsAppProvider(Protocol):
    name: str

    async def send_session(
        self, *, to_phone: str, from_phone: str, body: str, idempotency_key: str
    ) -> ProviderResult: ...

    async def send_template(
        self,
        *,
        to_phone: str,
        from_phone: str,
        template_name: str,
        template_vars: dict,
        idempotency_key: str,
    ) -> ProviderResult: ...

    def verify_signature(self, headers: dict, body: bytes) -> bool: ...

    def parse_webhook(self, body: bytes) -> list[InboundEvent]: ...
