from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    dims: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
