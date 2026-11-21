from __future__ import annotations

from app.core.config import settings
from packages.channels.whatsapp.base import WhatsAppProvider
from packages.channels.whatsapp.fake import FakeWhatsAppProvider

_provider: WhatsAppProvider | None = None


def get_provider() -> WhatsAppProvider:
    global _provider
    if _provider is None:
        name = (settings.whatsapp_provider or "fake").lower()
        if name == "fake":
            _provider = FakeWhatsAppProvider(secret=settings.whatsapp_webhook_secret)
        else:
            raise RuntimeError(f"unknown whatsapp_provider: {name}")
    return _provider


def reset_provider() -> None:
    """Test helper; forces re-initialization."""
    global _provider
    _provider = None
