"""Deterministic hash-based embedding. Lets tests + local dev run offline.

Semantic similarity against a real-world query is near-random here, which is
precisely why hybrid search (keyword + vector) matters and is tested."""
from __future__ import annotations

import hashlib
import math
import struct


class FakeEmbeddingProvider:
    name = "fake"

    def __init__(self, dims: int = 384) -> None:
        self.dims = dims

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        buf = b""
        seed = text.encode("utf-8", errors="ignore")
        # Expand via repeated SHA-256 until we have 4*dims bytes of entropy.
        counter = 0
        while len(buf) < self.dims * 4:
            buf += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            counter += 1
        floats = list(struct.unpack(f"{self.dims}f", buf[: self.dims * 4]))
        # Replace NaN/Inf, then L2-normalize.
        cleaned = [0.0 if (math.isnan(f) or math.isinf(f)) else f for f in floats]
        norm = math.sqrt(sum(f * f for f in cleaned)) or 1.0
        return [f / norm for f in cleaned]
