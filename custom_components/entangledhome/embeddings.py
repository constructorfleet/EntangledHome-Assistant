"""Embedding helpers bundled with the EntangledHome integration."""

from __future__ import annotations

import asyncio
import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Protocol, Sequence

import httpx


class EmbeddingServiceError(RuntimeError):
    """Raised when the embedding backend returns an unexpected response."""


class EmbeddingBackend(Protocol):
    """Protocol for embedding backends used by :class:`EmbeddingService`."""

    async def generate(
        self, model: str, texts: list[str]
    ) -> list[Sequence[float]]:  # pragma: no cover - Protocol
        """Return embeddings for the provided texts."""


@dataclass(slots=True)
class OpenAIEmbeddingBackend:
    """HTTP client that calls the OpenAI compatible embeddings endpoint."""

    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    timeout: float | None = 10.0
    client: Any | None = None

    async def generate(self, model: str, texts: list[str]) -> list[Sequence[float]]:
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request_payload = {"model": model, "input": texts}

        client = self.client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
            close_client = True

        try:
            response = await client.post("/embeddings", json=request_payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise EmbeddingServiceError("Failed to obtain embeddings") from exc
        finally:
            if close_client:
                await client.aclose()

        data = response.json()
        items = data.get("data")
        if not isinstance(items, list):  # pragma: no cover - defensive branch
            raise EmbeddingServiceError("Invalid embedding response structure")

        vectors: list[Sequence[float]] = []
        for item in items:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if embedding is None:
                raise EmbeddingServiceError("Embedding item missing vector")
            vectors.append(embedding)

        return vectors


class EmbeddingService:
    """Caches embedding vectors while delegating to a backend implementation."""

    def __init__(
        self,
        *,
        model: str,
        backend: EmbeddingBackend | None = None,
        cache_size: int = 256,
    ) -> None:
        self._model = model
        self._backend = backend or OpenAIEmbeddingBackend(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self._cache_size = max(cache_size, 0)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return embeddings for ``texts`` while caching repeated lookups."""

        async with self._lock:
            return await self._embed_locked(texts)

    async def _embed_locked(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        pending: list[str] = []
        pending_indexes: list[int] = []
        results: list[list[float] | None] = [None] * len(texts)

        for index, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                results[index] = list(cached)
            else:
                pending.append(text)
                pending_indexes.append(index)

        if pending:
            fresh_vectors = await self._backend.generate(self._model, pending)
            if len(fresh_vectors) != len(pending):
                raise EmbeddingServiceError("Embedding backend returned mismatched vector count")

            for text, vector, index in zip(pending, fresh_vectors, pending_indexes):
                normalized = self._normalize_vector(vector)
                results[index] = list(normalized)
                if self._cache_size:
                    self._cache[text] = normalized
                    self._cache.move_to_end(text)
                    self._enforce_cache_limit()

        # At this point all entries should be populated.
        return [vector if vector is not None else [] for vector in results]

    def _enforce_cache_limit(self) -> None:
        if not self._cache_size:
            self._cache.clear()
            return

        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached embeddings."""

        self._cache.clear()

    def cached_keys(self) -> Iterable[str]:
        """Return an iterable of cached text keys for inspection."""

        return tuple(self._cache.keys())

    @staticmethod
    def _normalize_vector(vector: Sequence[float]) -> list[float]:
        """Convert the backend vector into a list of floats."""

        return [float(value) for value in vector]


__all__ = [
    "EmbeddingBackend",
    "EmbeddingService",
    "EmbeddingServiceError",
    "OpenAIEmbeddingBackend",
]
