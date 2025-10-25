"""Shared Qdrant HTTP helper for ingestion scripts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from custom_components.entangledhome.exporter import _chunk_sequence

__all__ = ["QdrantHttpClient"]

_LOGGER = logging.getLogger(__name__)


class QdrantHttpClient:
    """HTTP client that performs Qdrant point upserts."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        batch_size: int = 64,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"api-key": api_key} if api_key else None,
        )
        self._batch_size = max(1, batch_size)
        self._max_retries = max(1, max_retries)

    async def __aenter__(self) -> "QdrantHttpClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def upsert(self, collection: str, points: Sequence[dict[str, Any]]) -> None:
        if not points:
            return
        for chunk in _chunk_sequence(list(points), self._batch_size):
            await self._post_with_retry(collection, list(chunk))

    async def _post_with_retry(self, collection: str, points: list[dict[str, Any]]) -> None:
        attempt = 0
        backoff = 0.2
        while True:
            attempt += 1
            try:
                response = await self._client.post(
                    f"/collections/{collection}/points/upsert",
                    json={"points": points},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise
                _LOGGER.warning(
                    "Qdrant upsert failed for %s (attempt %s/%s): %s",
                    collection,
                    attempt,
                    self._max_retries,
                    exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 2.0)
                continue
            break
