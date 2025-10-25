"""Background job that exports Home Assistant and Plex catalogs to Qdrant."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any, Mapping

from homeassistant.core import HomeAssistant

from .catalog import build_catalog_payload
from .models import CatalogEntity, CatalogPayload, PlexMediaItem

AreaSource = Callable[[], Iterable[Mapping[str, Any]] | Awaitable[Iterable[Mapping[str, Any]]]]
EntitySource = Callable[[], Iterable[Mapping[str, Any]] | Awaitable[Iterable[Mapping[str, Any]]]]
SceneSource = Callable[[], Iterable[Mapping[str, Any]] | Awaitable[Iterable[Mapping[str, Any]]]]
PlexSource = Callable[[], Iterable[Mapping[str, Any]] | Awaitable[Iterable[Mapping[str, Any]]]]
EmbedTexts = Callable[[list[str]], Awaitable[list[list[float]]]]
UpsertPoints = Callable[[str, list[dict[str, Any]]], Awaitable[None]]
MetricsLogger = Callable[[str, Any], None]


class CatalogExporter:
    """Coordinate catalog export batches and Qdrant upserts."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        embed_texts: EmbedTexts,
        upsert_points: UpsertPoints,
        metrics_logger: Callable[[str, Any], None],
        area_source: AreaSource,
        entity_source: EntitySource,
        scene_source: SceneSource,
        plex_source: PlexSource,
        batch_size: int = 64,
        max_retries: int = 3,
        enable_plex_sync: bool = True,
    ) -> None:
        self._hass = hass
        self._embed_texts = embed_texts
        self._upsert_points = upsert_points
        self._metrics_logger = metrics_logger
        self._area_source = area_source
        self._entity_source = entity_source
        self._scene_source = scene_source
        self._plex_source = plex_source
        self._batch_size = max(1, batch_size)
        self._max_retries = max(1, max_retries)
        self._enable_plex_sync = enable_plex_sync

    async def run_once(self) -> CatalogPayload:
        """Collect registries, compute embeddings, and push to Qdrant."""

        areas = await _resolve_source(self._area_source)
        entities = await _resolve_source(self._entity_source)
        scenes = await _resolve_source(self._scene_source)
        plex_items: Sequence[Mapping[str, Any]] = []
        if self._enable_plex_sync:
            plex_items = await _resolve_source(self._plex_source)

        payload = build_catalog_payload(
            areas=areas,
            entities=entities,
            scenes=scenes,
            plex_media=plex_items,
        )

        retry_counts: dict[str, int] = {}

        if payload.entities:
            retry_counts.setdefault("ha_entities", 0)
            await self._process_collection(
                collection_name="ha_entities",
                items=payload.entities,
                text_formatter=_format_entity_embedding_text,
                payload_formatter=lambda entity: entity.model_dump(mode="json"),
                retry_counts=retry_counts,
            )

        if self._enable_plex_sync and payload.plex_media:
            retry_counts.setdefault("plex_media", 0)
            await self._process_collection(
                collection_name="plex_media",
                items=payload.plex_media,
                text_formatter=_format_plex_embedding_text,
                payload_formatter=lambda item: item.model_dump(mode="json"),
                retry_counts=retry_counts,
            )

        self._log_metrics(payload, retry_counts)

        return payload

    async def _process_collection(
        self,
        *,
        collection_name: str,
        items: Sequence[CatalogEntity] | Sequence[PlexMediaItem],
        text_formatter: Callable[[CatalogEntity | PlexMediaItem], str],
        payload_formatter: Callable[[CatalogEntity | PlexMediaItem], dict[str, Any]],
        retry_counts: dict[str, int],
    ) -> None:
        """Embed and upsert items for a particular collection."""

        for chunk in _chunk_sequence(items, self._batch_size):
            texts = [text_formatter(item) for item in chunk]
            vectors = await self._embed_texts(list(texts))
            points = [
                {
                    "id": _point_id(collection_name, item),
                    "vector": vector,
                    "payload": payload_formatter(item),
                }
                for item, vector in zip(chunk, vectors)
            ]
            await self._retry_upsert(collection_name, points, retry_counts)

    async def _retry_upsert(
        self,
        collection_name: str,
        points: list[dict[str, Any]],
        retry_counts: dict[str, int],
    ) -> None:
        """Attempt an upsert, retrying if the client raises."""

        attempts = 0
        while True:
            try:
                await self._upsert_points(collection_name, points)
            except Exception:  # pragma: no cover - surface via retries/tests
                attempts += 1
                retry_counts[collection_name] = retry_counts.get(collection_name, 0) + 1
                if attempts >= self._max_retries:
                    raise
                await asyncio.sleep(0)
                continue
            break

    def _log_metrics(self, payload: CatalogPayload, retry_counts: dict[str, int]) -> None:
        """Emit a metrics event summarizing the export."""

        counts = {
            "areas": len(payload.areas),
            "entities": len(payload.entities),
            "scenes": len(payload.scenes),
            "plex_media": len(payload.plex_media),
        }
        normalized_retries = {"ha_entities": 0, "plex_media": 0}
        normalized_retries.update(retry_counts)

        self._metrics_logger(
            "catalog_export",
            counts=counts,
            batch_size=self._batch_size,
            retries=normalized_retries,
        )


async def _resolve_source(
    source: Callable[[], Iterable[Mapping[str, Any]] | Awaitable[Iterable[Mapping[str, Any]]]],
) -> Sequence[Mapping[str, Any]]:
    """Resolve a data source that may be synchronous or awaitable."""

    result = source()
    if asyncio.iscoroutine(result):
        result = await result  # type: ignore[assignment]
    return list(result)


def _chunk_sequence(items: Sequence[Any], chunk_size: int) -> Iterable[Sequence[Any]]:
    """Yield ``items`` in fixed-size chunks."""

    size = max(1, chunk_size)
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _format_entity_embedding_text(entity: CatalogEntity) -> str:
    """Build a descriptive string suitable for embedding an HA entity."""

    parts = [
        entity.friendly_name or entity.entity_id,
        entity.entity_id,
        entity.domain,
    ]
    if entity.area_id:
        parts.append(f"area:{entity.area_id}")
    if entity.aliases:
        parts.extend(entity.aliases)
    return " | ".join(part for part in parts if part)


def _format_plex_embedding_text(item: PlexMediaItem) -> str:
    """Return a prompt-friendly string for embedding Plex media items."""

    parts = [item.title, item.type, str(item.year) if item.year else ""]
    if item.collection:
        parts.extend(f"collection:{name}" for name in item.collection)
    if item.genres:
        parts.extend(item.genres)
    if item.actors:
        parts.extend(item.actors)
    return " | ".join(part for part in parts if part)


def _point_id(collection: str, item: CatalogEntity | PlexMediaItem) -> str:
    """Generate a deterministic point identifier for Qdrant."""

    if isinstance(item, CatalogEntity):
        return f"entity::{item.entity_id}"
    return f"plex::{item.rating_key}"
