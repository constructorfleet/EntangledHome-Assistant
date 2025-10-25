"""Tests for coordinator catalog payload assembly."""

from __future__ import annotations

import asyncio


def test_build_catalog_payload_includes_metadata() -> None:
    """Coordinator should include friendly names, aliases, capabilities, and Plex metadata."""

    from custom_components.entangledhome.catalog import build_catalog_payload

    payload = build_catalog_payload(
        areas=[{"area_id": "living_room", "name": "Living Room", "aliases": ["lounge"]}],
        entities=[
            {
                "entity_id": "light.kitchen",
                "domain": "light",
                "area_id": "kitchen",
                "device_id": "device-1",
                "friendly_name": "Kitchen Light",
                "capabilities": {"color": True, "brightness": True},
                "aliases": ["cooking light"],
            }
        ],
        scenes=[{"entity_id": "scene.movie_time", "name": "Movie Time", "aliases": ["cinema"]}],
        plex_media=[
            {
                "rating_key": "1",
                "title": "Inception",
                "type": "movie",
                "year": 2010,
                "collection": ["Sci-Fi"],
                "genres": ["Science Fiction"],
                "actors": ["Leonardo DiCaprio"],
                "audio_language": "en",
                "subtitles": ["en"],
            }
        ],
    )

    entity = payload.entities[0]
    assert entity.friendly_name == "Kitchen Light"
    assert entity.capabilities == {"color": True, "brightness": True}
    assert entity.aliases == ["cooking light"]

    plex = payload.plex_media[0]
    assert plex.title == "Inception"
    assert plex.actors == ["Leonardo DiCaprio"]
    assert plex.subtitles == ["en"]


def test_serialize_catalog_for_qdrant_validates_models() -> None:
    """Payload serialization should validate against catalog models before Qdrant upserts."""

    import pytest
    from pydantic import ValidationError

    from custom_components.entangledhome.catalog import serialize_catalog_for_qdrant

    valid_payload = {
        "areas": [],
        "entities": [
            {
                "entity_id": "light.kitchen",
                "domain": "light",
                "friendly_name": "Kitchen Light",
                "capabilities": {},
                "aliases": [],
            }
        ],
        "scenes": [],
        "plex_media": [
            {
                "rating_key": "1",
                "title": "Inception",
                "type": "movie",
            }
        ],
    }

    serialized = serialize_catalog_for_qdrant(valid_payload)
    assert serialized["entities"][0]["entity_id"] == "light.kitchen"
    assert serialized["plex_media"][0]["title"] == "Inception"

    with pytest.raises(ValidationError):
        serialize_catalog_for_qdrant(
            {
                "areas": [],
                "entities": [{"domain": "light"}],
                "scenes": [],
                "plex_media": [],
            }
        )


def test_coordinator_invokes_exporter_when_sync_enabled() -> None:
    """Coordinator should build an exporter and trigger a run when sync is enabled."""

    from datetime import timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from homeassistant.core import HomeAssistant

    from custom_components.entangledhome.coordinator import EntangledHomeCoordinator
    from custom_components.entangledhome.const import (
        OPT_ENABLE_CATALOG_SYNC,
        OPT_ENABLE_PLEX_SYNC,
        OPT_REFRESH_INTERVAL_MINUTES,
    )

    hass = HomeAssistant()
    options = {
        OPT_ENABLE_CATALOG_SYNC: True,
        OPT_ENABLE_PLEX_SYNC: False,
        OPT_REFRESH_INTERVAL_MINUTES: 12,
    }
    entry = SimpleNamespace(options=options)

    with patch(
        "custom_components.entangledhome.coordinator.CatalogExporter",
        create=True,
    ) as exporter_cls:
        exporter = exporter_cls.return_value
        exporter.run_once = AsyncMock(return_value=None)

        coordinator = EntangledHomeCoordinator(hass, entry)
        assert coordinator.update_interval == timedelta(minutes=12)

        asyncio.run(coordinator._async_update_data())

    exporter_cls.assert_called_once()
    kwargs = exporter_cls.call_args.kwargs
    assert kwargs["enable_plex_sync"] is False
    exporter.run_once.assert_awaited_once()


def test_coordinator_skips_export_when_sync_disabled() -> None:
    """No exporter should be constructed when sync is disabled."""

    from types import SimpleNamespace
    from unittest.mock import patch

    from homeassistant.core import HomeAssistant

    from custom_components.entangledhome.coordinator import EntangledHomeCoordinator
    from custom_components.entangledhome.const import OPT_ENABLE_CATALOG_SYNC

    hass = HomeAssistant()
    entry = SimpleNamespace(options={OPT_ENABLE_CATALOG_SYNC: False})

    with patch(
        "custom_components.entangledhome.coordinator.CatalogExporter", create=True
    ) as exporter:
        coordinator = EntangledHomeCoordinator(hass, entry)
        asyncio.run(coordinator._async_update_data())

    exporter.assert_not_called()


def test_coordinator_does_not_reexport_catalog_helpers() -> None:
    """Catalog helpers should live in the catalog module, not coordinator."""

    import importlib

    module = importlib.import_module("custom_components.entangledhome.coordinator")

    assert not hasattr(module, "build_catalog_payload")
    assert not hasattr(module, "serialize_catalog_for_qdrant")


def test_coordinator_embed_texts_uses_entry_provider() -> None:
    """Embed texts should delegate to the entry-specific provider when present."""

    from types import SimpleNamespace

    from homeassistant.core import HomeAssistant

    from custom_components.entangledhome.coordinator import EntangledHomeCoordinator
    from custom_components.entangledhome.const import DOMAIN

    hass = HomeAssistant()
    entry = SimpleNamespace(options={}, entry_id="entry-1")
    result_holder: list[list[float]] = [[1.0, 2.0]]

    def embedder(texts: list[str]) -> list[list[float]]:
        assert texts == ["hello"]
        return result_holder

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"embed_texts": embedder}

    coordinator = EntangledHomeCoordinator(hass, entry)

    result = asyncio.run(coordinator._embed_texts(["hello"]))

    assert result is result_holder


def test_coordinator_upsert_points_uses_entry_provider() -> None:
    """Upsert should call the entry-specific Qdrant function when available."""

    from types import SimpleNamespace

    from homeassistant.core import HomeAssistant

    from custom_components.entangledhome.coordinator import EntangledHomeCoordinator
    from custom_components.entangledhome.const import DOMAIN

    hass = HomeAssistant()
    entry = SimpleNamespace(options={}, entry_id="entry-2")
    calls: list[tuple[str, list[dict[str, object]]]] = []

    async def upsert(collection: str, points: list[dict[str, object]]) -> None:
        calls.append((collection, points))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"qdrant_upsert": upsert}

    coordinator = EntangledHomeCoordinator(hass, entry)
    points_payload = [{"id": 1, "vector": [0.9, 0.1]}]

    asyncio.run(coordinator._upsert_points("entities", points_payload))

    assert calls == [("entities", points_payload)]
    assert calls[0][1][0]["vector"] == [0.9, 0.1]


def test_coordinator_collect_plex_media_uses_entry_client() -> None:
    """Plex catalog should be obtained from the entry-specific client when provided."""

    from types import SimpleNamespace

    from homeassistant.core import HomeAssistant

    from custom_components.entangledhome.coordinator import EntangledHomeCoordinator
    from custom_components.entangledhome.const import DOMAIN

    hass = HomeAssistant()
    entry = SimpleNamespace(options={}, entry_id="entry-3")

    class PlexClient:
        async def async_get_catalog(self):
            return [{"title": "Example"}]

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"plex_client": PlexClient()}

    coordinator = EntangledHomeCoordinator(hass, entry)

    media = asyncio.run(coordinator._collect_plex_media())

    assert media == [{"title": "Example"}]
