from __future__ import annotations

from app.core.config import settings
from packages.channels.embeddings.base import EmbeddingProvider
from packages.channels.embeddings.fake import FakeEmbeddingProvider

_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        name = (settings.embedding_provider or "fake").lower()
        if name == "fake":
            _provider = FakeEmbeddingProvider(dims=settings.embedding_dims)
        else:
            raise RuntimeError(f"unknown embedding_provider: {name}")
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None
