"""Ingest Home Assistant registries into the Qdrant ha_entities collection."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import httpx

from adapter_service.embeddings import EmbeddingService
from custom_components.entangledhome.catalog import build_catalog_payload
from custom_components.entangledhome.exporter import (
    _chunk_sequence,
    _format_entity_embedding_text,
    _point_id,
)
from custom_components.entangledhome.models import CatalogEntity, CatalogPayload

from ._qdrant import QdrantHttpClient

_LOGGER = logging.getLogger(__name__)

EmbedTexts = Callable[[list[str]], Awaitable[Sequence[Sequence[float]]]]
UpsertPoints = Callable[[str, list[dict[str, Any]]], Awaitable[None]]

_AREA_ENDPOINT = "/api/config/area_registry/list"
_ENTITY_ENDPOINT = "/api/config/entity_registry/list"


class HomeAssistantRegistryClient:
    """Minimal HTTP client for Home Assistant registry endpoints."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    async def __aenter__(self) -> "HomeAssistantRegistryClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def get_areas(self) -> list[Mapping[str, Any]]:
        return await self._get_json(_AREA_ENDPOINT)

    async def get_entities(self) -> list[Mapping[str, Any]]:
        return await self._get_json(_ENTITY_ENDPOINT)

    async def _get_json(self, path: str) -> list[Mapping[str, Any]]:
        response = await self._client.get(path)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]
        return []


async def ingest_entities(
    ha_client: Any,
    *,
    embed_texts: EmbedTexts,
    upsert_points: UpsertPoints,
    batch_size: int = 64,
) -> CatalogPayload:
    """Fetch HA registries, embed entity strings, and upsert Qdrant points."""

    areas = await ha_client.get_areas()
    entities = await ha_client.get_entities()
    payload = build_catalog_payload(
        areas=areas,
        entities=entities,
        scenes=[],
        plex_media=[],
    )

    if not payload.entities:
        return payload

    for chunk in _chunk_sequence(payload.entities, max(1, batch_size)):
        chunk_list = list(chunk)
        texts = [_format_entity_embedding_text(entity) for entity in chunk_list]
        vectors = await embed_texts(list(texts))
        vector_list = [_normalize_vector(vec) for vec in vectors]
        if len(vector_list) != len(chunk_list):
            raise RuntimeError("Embedding backend returned unexpected vector count")

        points = [
            {
                "id": _point_id("ha_entities", entity),
                "vector": vector,
                "payload": _entity_payload(entity),
            }
            for entity, vector in zip(chunk_list, vector_list)
        ]
        await upsert_points("ha_entities", points)

    return payload


def _entity_payload(entity: CatalogEntity) -> dict[str, Any]:
    data = entity.model_dump(mode="json", exclude_none=True)
    data.setdefault("aliases", [])
    data.setdefault("capabilities", {})
    return data


def _normalize_vector(vector: Sequence[float]) -> list[float]:
    return [float(value) for value in vector]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Home Assistant entities into Qdrant")
    parser.add_argument("--ha-url", default=os.getenv("HA_URL") or os.getenv("HOME_ASSISTANT_URL"))
    parser.add_argument("--ha-token", default=os.getenv("HA_TOKEN"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_HOST"))
    parser.add_argument("--qdrant-key", default=os.getenv("QDRANT_API_KEY"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BATCH_SIZE", "64")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("HTTP_TIMEOUT", "10.0")))
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )
    parser.add_argument(
        "--qdrant-retries",
        type=int,
        default=int(os.getenv("QDRANT_MAX_RETRIES", "3")),
    )
    parser.add_argument(
        "--qdrant-batch",
        type=int,
        default=int(os.getenv("QDRANT_BATCH_SIZE", "64")),
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    if not args.ha_url or not args.ha_token:
        raise SystemExit("Home Assistant URL and token are required")
    if not args.qdrant_url:
        raise SystemExit("Qdrant URL is required")

    logging.basicConfig(level=logging.INFO)

    embed_service = EmbeddingService(model=args.embedding_model)

    async with HomeAssistantRegistryClient(
        args.ha_url, args.ha_token, timeout=args.timeout
    ) as ha_client, QdrantHttpClient(
        args.qdrant_url,
        api_key=args.qdrant_key,
        timeout=args.timeout,
        batch_size=args.qdrant_batch,
        max_retries=args.qdrant_retries,
    ) as qdrant:
        payload = await ingest_entities(
            ha_client,
            embed_texts=embed_service.embed,
            upsert_points=qdrant.upsert,
            batch_size=args.batch_size,
        )

    _LOGGER.info(
        "Exported %s entities across %s areas to Qdrant collection ha_entities",
        len(payload.entities),
        len(payload.areas),
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover - manual execution only
    main()
