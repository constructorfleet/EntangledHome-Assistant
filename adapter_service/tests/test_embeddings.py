"""Tests for the adapter service embedding helper."""

from __future__ import annotations

import asyncio


class _RecordingBackend:
    """Test double that records embedding requests."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def generate(self, model: str, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text))] for text in texts]


def test_embedding_service_caches_vectors() -> None:
    """Repeated inputs should reuse cached vectors."""

    from adapter_service.embeddings import EmbeddingService

    backend = _RecordingBackend()
    service = EmbeddingService(model="mock-model", backend=backend, cache_size=4)

    async def _run() -> None:
        first = await service.embed(["alpha", "beta"])
        second = await service.embed(["alpha", "beta"])
        third = await service.embed(["beta", "gamma"])

        assert first == [[5.0], [4.0]]
        assert second == first
        assert third == [[4.0], [5.0]]
        assert backend.calls == [["alpha", "beta"], ["gamma"]]

    asyncio.run(_run())
