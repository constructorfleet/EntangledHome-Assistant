"""Tests for the catalog exporter background job."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from homeassistant.core import HomeAssistant


def test_exporter_batches_embeddings_and_logs_metrics() -> None:
    """Exporter should batch embeddings, upsert to Qdrant, and emit metrics."""

    from custom_components.entangledhome.exporter import CatalogExporter

    hass = HomeAssistant()

    embed_calls: list[list[str]] = []

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        embed_calls.append(texts)
        return [[float(index)] * 2 for index, _ in enumerate(texts, start=1)]

    upsert_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def upsert_points(collection: str, points: list[dict[str, Any]]) -> None:
        upsert_calls.append((collection, points))

    metrics_events: list[tuple[str, dict[str, Any]]] = []

    def metrics_logger(event: str, **fields: Any) -> None:
        metrics_events.append((event, fields))

    async def _run() -> None:
        exporter = CatalogExporter(
            hass=hass,
            embed_texts=embed_texts,
            upsert_points=upsert_points,
            metrics_logger=metrics_logger,
            area_source=lambda: [{"area_id": "kitchen", "name": "Kitchen", "aliases": ["cooking"]}],
            entity_source=lambda: [
                {
                    "entity_id": "light.kitchen",
                    "domain": "light",
                    "friendly_name": "Kitchen Light",
                    "area_id": "kitchen",
                },
                {
                    "entity_id": "switch.fan",
                    "domain": "switch",
                    "friendly_name": "Ceiling Fan",
                    "area_id": "living_room",
                },
            ],
            scene_source=lambda: [{"entity_id": "scene.movie", "name": "Movie", "aliases": []}],
            plex_source=lambda: [
                {
                    "rating_key": "1",
                    "title": "Inception",
                    "type": "movie",
                    "year": 2010,
                },
                {
                    "rating_key": "2",
                    "title": "Tenet",
                    "type": "movie",
                },
                {
                    "rating_key": "3",
                    "title": "Dune",
                    "type": "movie",
                },
            ],
            batch_size=2,
            max_retries=2,
            enable_plex_sync=True,
        )

        payload = await exporter.run_once()

        # Entities and Plex media should be embedded in batches of two.
        batch_sizes = [len(batch) for batch in embed_calls]
        assert batch_sizes == [2, 2, 1]

        # Upserts should target both HA entities and Plex collections with matching counts.
        collection_counts = Counter(name for name, _ in upsert_calls)
        assert collection_counts == {"ha_entities": 1, "plex_media": 2}
        assert sum(len(points) for name, points in upsert_calls if name == "ha_entities") == 2
        assert sum(len(points) for name, points in upsert_calls if name == "plex_media") == 3

        # Metrics should include counts and batch size information.
        assert metrics_events[-1][0] == "catalog_export"
        metrics = metrics_events[-1][1]
        assert metrics["counts"] == {
            "areas": 1,
            "entities": 2,
            "scenes": 1,
            "plex_media": 3,
        }
        assert metrics["batch_size"] == 2
        assert metrics["retries"] == {"ha_entities": 0, "plex_media": 0}

        # The payload returned to the caller should mirror the exported catalog.
        assert len(payload.entities) == 2
        assert len(payload.plex_media) == 3

    asyncio.run(_run())


def test_exporter_retries_failed_upserts() -> None:
    """Upserts should retry when failures occur and surface retry counts in metrics."""

    from custom_components.entangledhome.exporter import CatalogExporter

    hass = HomeAssistant()

    async def embed_texts(texts: list[str]) -> list[list[float]]:
        return [[1.0] * 2 for _ in texts]

    attempts: dict[str, int] = Counter()

    async def upsert_points(collection: str, points: list[dict[str, Any]]) -> None:
        attempts[collection] += 1
        if attempts[collection] == 1:
            raise RuntimeError("temporary failure")

    metrics_events: list[tuple[str, dict[str, Any]]] = []

    def metrics_logger(event: str, **fields: Any) -> None:
        metrics_events.append((event, fields))

    async def _run() -> None:
        exporter = CatalogExporter(
            hass=hass,
            embed_texts=embed_texts,
            upsert_points=upsert_points,
            metrics_logger=metrics_logger,
            area_source=lambda: [],
            entity_source=lambda: [
                {
                    "entity_id": "light.kitchen",
                    "domain": "light",
                    "friendly_name": "Kitchen Light",
                }
            ],
            scene_source=lambda: [],
            plex_source=lambda: [],
            batch_size=1,
            max_retries=3,
            enable_plex_sync=False,
        )

        payload = await exporter.run_once()

        assert len(payload.entities) == 1
        assert attempts["ha_entities"] == 2
        assert metrics_events[-1][1]["retries"]["ha_entities"] == 1

    asyncio.run(_run())
