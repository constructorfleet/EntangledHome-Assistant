"""Tests for coordinator catalog payload assembly."""

from __future__ import annotations


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
