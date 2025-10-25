"""Tests for catalog ingestion helper scripts."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.entangledhome.models import CatalogPayload


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class FakeHAClient:
    def __init__(self, areas: list[dict[str, Any]], entities: list[dict[str, Any]]) -> None:
        self._areas = areas
        self._entities = entities
        self.calls: list[str] = []

    async def get_areas(self) -> list[dict[str, Any]]:
        self.calls.append("areas")
        await asyncio.sleep(0)
        return list(self._areas)

    async def get_entities(self) -> list[dict[str, Any]]:
        self.calls.append("entities")
        await asyncio.sleep(0)
        return list(self._entities)


class FakePlexClient:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items
        self.calls: list[str] = []

    async def get_items(self) -> list[dict[str, Any]]:
        self.calls.append("items")
        await asyncio.sleep(0)
        return list(self._items)


@pytest.mark.anyio("asyncio")
async def test_ingest_entities_batches_and_upserts(monkeypatch):
    from scripts import ingest_entities

    areas = [
        {"area_id": "living_room", "name": "Living Room", "aliases": ["lounge"]},
    ]
    entities = [
        {
            "entity_id": "light.lamp",
            "domain": "light",
            "friendly_name": "Lamp",
            "area_id": "living_room",
            "device_id": "device-1",
            "capabilities": {"supported_color_modes": ["brightness"]},
            "aliases": ["floor lamp"],
        },
        {
            "entity_id": "switch.fan",
            "domain": "switch",
            "friendly_name": "Fan",
            "area_id": None,
            "device_id": None,
            "capabilities": {},
            "aliases": [],
        },
    ]

    fake_client = FakeHAClient(areas, entities)
    embed_calls: list[list[str]] = []
    upsert_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        embed_calls.append(list(texts))
        return [[idx + 0.1, idx + 0.2, idx + 0.3] for idx in range(len(texts))]

    async def fake_upsert(collection: str, points: list[dict[str, Any]]) -> None:
        upsert_calls.append((collection, points))

    payload = await ingest_entities.ingest_entities(
        fake_client,
        embed_texts=fake_embed,
        upsert_points=fake_upsert,
        batch_size=1,
    )

    assert isinstance(payload, CatalogPayload)
    assert embed_calls == [
        [
            "Lamp | light.lamp | light | area:living_room | floor lamp",
        ],
        [
            "Fan | switch.fan | switch",
        ],
    ]
    assert [call[0] for call in upsert_calls] == ["ha_entities", "ha_entities"]
    assert upsert_calls[0][1][0]["id"] == "entity::light.lamp"
    assert upsert_calls[0][1][0]["payload"]["friendly_name"] == "Lamp"
    assert upsert_calls[1][1][0]["id"] == "entity::switch.fan"
    assert payload.entities[0].friendly_name == "Lamp"
    assert fake_client.calls == ["areas", "entities"]


@pytest.mark.anyio("asyncio")
async def test_ingest_plex_pushes_vectors(monkeypatch):
    from scripts import ingest_plex

    items = [
        {
            "rating_key": "123",
            "title": "Example Movie",
            "type": "movie",
            "year": 2020,
            "collection": ["Favorites"],
            "genres": ["Adventure"],
            "actors": ["Lead Actor"],
            "audio_language": "en",
            "subtitles": ["en"],
        }
    ]

    fake_client = FakePlexClient(items)
    embed_calls: list[list[str]] = []
    upsert_calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        embed_calls.append(list(texts))
        return [[0.42 for _ in range(3)] for _ in texts]

    async def fake_upsert(collection: str, points: list[dict[str, Any]]) -> None:
        upsert_calls.append((collection, points))

    payload = await ingest_plex.ingest_plex(
        fake_client,
        embed_texts=fake_embed,
        upsert_points=fake_upsert,
        batch_size=32,
    )

    assert isinstance(payload, CatalogPayload)
    assert embed_calls == [["Example Movie | movie | 2020 | collection:Favorites | Adventure | Lead Actor"]]
    assert upsert_calls and upsert_calls[0][0] == "plex_media"
    point = upsert_calls[0][1][0]
    assert point["id"] == "plex::123"
    assert point["payload"]["title"] == "Example Movie"
    assert fake_client.calls == ["items"]
