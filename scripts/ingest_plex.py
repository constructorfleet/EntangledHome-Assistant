"""Ingest Plex metadata into the Qdrant plex_media collection."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import httpx

from adapter_service.embeddings import EmbeddingService
from custom_components.entangledhome.catalog import build_catalog_payload
from custom_components.entangledhome.exporter import (
    _chunk_sequence,
    _format_plex_embedding_text,
    _point_id,
)
from custom_components.entangledhome.models import CatalogPayload, PlexMediaItem

from ._qdrant import QdrantHttpClient

_LOGGER = logging.getLogger(__name__)

EmbedTexts = Callable[[list[str]], Awaitable[Sequence[Sequence[float]]]]
UpsertPoints = Callable[[str, list[dict[str, Any]]], Awaitable[None]]


class PlexCatalogClient:
    """HTTP client for collecting Plex library metadata."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        library_key: str | None = None,
    ) -> None:
        headers = {
            "Accept": "application/json",
            "X-Plex-Token": token,
            "X-Plex-Client-Identifier": secrets.token_hex(8),
            "X-Plex-Product": "EntangledHomeExporter",
        }
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )
        self._library_key = library_key

    async def __aenter__(self) -> "PlexCatalogClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.__aexit__(*exc_info)

    async def get_items(self) -> list[Mapping[str, Any]]:
        path = "/library/all"
        if self._library_key:
            path = f"/library/sections/{self._library_key}/all"
        response = await self._client.get(path, params={"type": 1})
        response.raise_for_status()
        data = response.json()
        container = data.get("MediaContainer", {}) if isinstance(data, Mapping) else {}
        metadata = container.get("Metadata", [])
        items: list[dict[str, Any]] = []
        for item in metadata or []:
            if not isinstance(item, Mapping):
                continue
            normalized = _coerce_metadata(item)
            if normalized:
                items.append(normalized)
        return items


async def ingest_plex(
    plex_client: Any,
    *,
    embed_texts: EmbedTexts,
    upsert_points: UpsertPoints,
    batch_size: int = 64,
) -> CatalogPayload:
    """Fetch Plex metadata, embed descriptions, and upsert Qdrant points."""

    items = await plex_client.get_items()
    payload = build_catalog_payload(
        areas=[],
        entities=[],
        scenes=[],
        plex_media=items,
    )

    if not payload.plex_media:
        return payload

    for chunk in _chunk_sequence(payload.plex_media, max(1, batch_size)):
        chunk_list = list(chunk)
        texts = [_format_plex_embedding_text(item) for item in chunk_list]
        vectors = await embed_texts(list(texts))
        vector_list = [_normalize_vector(vec) for vec in vectors]
        if len(vector_list) != len(chunk_list):
            raise RuntimeError("Embedding backend returned unexpected vector count")

        points = [
            {
                "id": _point_id("plex_media", item),
                "vector": vector,
                "payload": _plex_payload(item),
            }
            for item, vector in zip(chunk_list, vector_list)
        ]
        await upsert_points("plex_media", points)

    return payload


def _normalize_vector(vector: Sequence[float]) -> list[float]:
    return [float(value) for value in vector]


def _plex_payload(item: PlexMediaItem) -> dict[str, Any]:
    data = item.model_dump(mode="json", exclude_none=True)
    data.setdefault("collection", [])
    data.setdefault("genres", [])
    data.setdefault("actors", [])
    data.setdefault("subtitles", [])
    return data


def _coerce_metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    rating_key = item.get("ratingKey")
    title = item.get("title")
    media_type = item.get("type")
    if not rating_key or not title or not media_type:
        return {}

    def _tags(field: str) -> list[str]:
        values = item.get(field) or []
        tags = []
        for entry in values:
            if isinstance(entry, Mapping) and entry.get("tag"):
                tags.append(str(entry["tag"]))
        return tags

    subtitles: list[str] = []
    media_entries = item.get("Media") or []
    for media in media_entries:
        if not isinstance(media, Mapping):
            continue
        for part in media.get("Part", []) or []:
            if not isinstance(part, Mapping):
                continue
            for stream in part.get("Stream", []) or []:
                if not isinstance(stream, Mapping):
                    continue
                if stream.get("streamType") == 3 and stream.get("language"):
                    subtitles.append(str(stream["language"]))

    return {
        "rating_key": str(rating_key),
        "title": str(title),
        "type": str(media_type),
        "year": item.get("year"),
        "collection": _tags("Collection"),
        "genres": _tags("Genre"),
        "actors": _tags("Role"),
        "audio_language": item.get("originalLanguage"),
        "subtitles": sorted(set(subtitles)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Plex media into Qdrant")
    parser.add_argument("--plex-url", default=os.getenv("PLEX_URL"))
    parser.add_argument("--plex-token", default=os.getenv("PLEX_TOKEN"))
    parser.add_argument("--library", default=os.getenv("PLEX_LIBRARY_KEY"))
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
    if not args.plex_url or not args.plex_token:
        raise SystemExit("Plex URL and token are required")
    if not args.qdrant_url:
        raise SystemExit("Qdrant URL is required")

    logging.basicConfig(level=logging.INFO)

    embed_service = EmbeddingService(model=args.embedding_model)

    async with (
        PlexCatalogClient(
            args.plex_url,
            args.plex_token,
            timeout=args.timeout,
            library_key=args.library,
        ) as plex_client,
        QdrantHttpClient(
            args.qdrant_url,
            api_key=args.qdrant_key,
            timeout=args.timeout,
            batch_size=args.qdrant_batch,
            max_retries=args.qdrant_retries,
        ) as qdrant,
    ):
        payload = await ingest_plex(
            plex_client,
            embed_texts=embed_service.embed,
            upsert_points=qdrant.upsert,
            batch_size=args.batch_size,
        )

    _LOGGER.info(
        "Exported %s Plex media items to Qdrant collection plex_media",
        len(payload.plex_media),
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover - manual execution only
    main()
