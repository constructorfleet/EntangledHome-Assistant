"""Tests for coordinator catalog payload assembly."""

from __future__ import annotations

import asyncio

def test_build_catalog_payload_includes_metadata() -> None:
    """Coordinator should include friendly names, aliases, capabilities, and Plex metadata."""

    from custom_components.entangledhome.coordinator import build_catalog_payload

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

    from custom_components.entangledhome.coordinator import serialize_catalog_for_qdrant

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
