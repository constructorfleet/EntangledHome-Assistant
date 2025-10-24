"""Model serialization tests for EntangledHome adapter schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from custom_components.entangledhome.models import (
    CatalogArea,
    CatalogEntity,
    CatalogPayload,
    CatalogScene,
    InterpretRequest,
    InterpretResponse,
    PlexMediaItem,
)


def _sample_catalog() -> CatalogPayload:
    return CatalogPayload(
        areas=[
            CatalogArea(area_id="kitchen", name="Kitchen", aliases=["cooking space"]),
        ],
        entities=[
            CatalogEntity(
                entity_id="light.kitchen",
                domain="light",
                area_id="kitchen",
                device_id="device_kitchen",
                friendly_name="Kitchen Light",
                capabilities={"color": True, "brightness": True},
                aliases=["cooking light"],
            ),
        ],
        scenes=[
            CatalogScene(entity_id="scene.movie", name="Movie", aliases=["movie time"]),
        ],
        plex_media=[
            PlexMediaItem(
                rating_key="1",
                title="Inception",
                type="movie",
                year=2010,
                collection=["Sci-Fi"],
                genres=["Sci-Fi"],
                actors=["Leonardo DiCaprio"],
                audio_language="en",
                subtitles=["en"],
            ),
        ],
    )


def test_interpret_request_round_trip() -> None:
    """InterpretRequest should serialize and deserialize without data loss."""
    catalog = _sample_catalog()
    request = InterpretRequest(utterance="Turn on the kitchen lights", catalog=catalog)

    raw = request.model_dump()
    parsed = InterpretRequest.model_validate(raw)

    assert parsed == request


def test_interpret_response_confidence_required() -> None:
    """InterpretResponse must require confidence to be present."""
    with pytest.raises(ValidationError):
        InterpretResponse.model_validate(
            {
                "intent": "noop",
                "area": None,
                "targets": None,
                "params": {"reason": "Unknown"},
            }
        )


def test_catalog_entity_requires_domain() -> None:
    """Catalog entities should fail validation when required fields are missing."""
    with pytest.raises(ValidationError):
        CatalogEntity.model_validate(
            {
                "entity_id": "light.missing_domain",
                "friendly_name": "Missing Domain",
            }
        )
