"""Golden tests for intent handler service routing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable
from unittest.mock import AsyncMock

import pytest

from custom_components.entangledhome.intent_handlers import (
    async_execute_intent,
    resolve_scene_entity_id,
)
from custom_components.entangledhome.models import (
    CatalogArea,
    CatalogEntity,
    CatalogPayload,
    CatalogScene,
    InterpretResponse,
)


pytestmark = pytest.mark.asyncio


class FakeStates:
    """Minimal state registry stub mimicking Home Assistant."""

    def __init__(self) -> None:
        self._states: dict[str, SimpleNamespace] = {}

    def set(self, entity_id: str, state: str, attributes: dict[str, object] | None = None) -> None:
        self._states[entity_id] = SimpleNamespace(state=state, attributes=attributes or {})

    def get(self, entity_id: str) -> SimpleNamespace | None:  # noqa: D401 - mimic HA API
        return self._states.get(entity_id)


@pytest.fixture
def fake_hass() -> SimpleNamespace:
    """Return a stub Home Assistant core object."""

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = FakeStates()
    return hass


def _catalog_with_entities_and_scenes(
    *,
    scenes: Iterable[CatalogScene] | None = None,
) -> CatalogPayload:
    """Build a representative catalog payload for tests."""

    return CatalogPayload(
        areas=[
            CatalogArea(area_id="living_room", name="Living Room"),
            CatalogArea(area_id="kitchen", name="Kitchen"),
        ],
        entities=[
            CatalogEntity(
                entity_id="sensor.living_room_temp",
                domain="sensor",
                area_id="living_room",
                friendly_name="Thermostat",
            ),
            CatalogEntity(
                entity_id="sensor.kitchen_humidity",
                domain="sensor",
                area_id="kitchen",
                friendly_name="Humidity",
            ),
            CatalogEntity(
                entity_id="media_player.living_room_tv",
                domain="media_player",
                area_id="living_room",
                friendly_name="Living Room TV",
            ),
        ],
        scenes=list(scenes or []),
        plex_media=[],
    )


async def test_report_sensor_summarizes_by_area(fake_hass: SimpleNamespace) -> None:
    """`report_sensor` should produce grouped spoken summaries and call conversation service."""

    catalog = _catalog_with_entities_and_scenes()
    fake_hass.states.set("sensor.living_room_temp", "72", {"unit_of_measurement": "°F"})
    fake_hass.states.set("sensor.kitchen_humidity", "40", {"unit_of_measurement": "%"})

    response = InterpretResponse(
        intent="report_sensor",
        area=None,
        targets=["sensor.living_room_temp", "sensor.kitchen_humidity"],
        params={},
        confidence=0.94,
    )

    await async_execute_intent(fake_hass, response, catalog=catalog)

    fake_hass.services.async_call.assert_awaited_once_with(
        "conversation",
        "process",
        {"text": "Living Room: Thermostat is 72 °F\nKitchen: Humidity is 40 %"},
        blocking=True,
    )


async def test_media_play_routes_to_media_player(fake_hass: SimpleNamespace) -> None:
    """`media_play` should call the media_player domain with the interpreted target."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="media_play",
        area="living_room",
        targets=None,
        params={},
        confidence=0.81,
    )

    await async_execute_intent(fake_hass, response, catalog=catalog)

    fake_hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "media_play",
        {},
        target={"area_id": "living_room"},
        blocking=True,
    )


async def test_media_pause_routes_to_media_player(fake_hass: SimpleNamespace) -> None:
    """`media_pause` should call the media_player domain with the interpreted target."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="media_pause",
        area="living_room",
        targets=None,
        params={},
        confidence=0.83,
    )

    await async_execute_intent(fake_hass, response, catalog=catalog)

    fake_hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "media_pause",
        {},
        target={"area_id": "living_room"},
        blocking=True,
    )


async def test_play_title_invokes_media_player_with_plex_metadata(fake_hass: SimpleNamespace) -> None:
    """`play_title` should call play_media with Plex metadata preserved."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="play_title",
        area=None,
        targets=["media_player.living_room_tv"],
        params={
            "rating_key": "4242",
            "server": "PlexServer",
            "media_type": "movie",
            "shuffle": True,
        },
        confidence=0.9,
    )

    await async_execute_intent(fake_hass, response, catalog=catalog)

    fake_hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "play_media",
        {
            "media_content_type": "movie",
            "media_content_id": "4242",
            "extra": {
                "plex_server": "PlexServer",
                "plex_rating_key": "4242",
                "plex_shuffle": True,
            },
        },
        target={"entity_id": ["media_player.living_room_tv"]},
        blocking=True,
    )


async def test_scene_activate_uses_fuzzy_resolution(fake_hass: SimpleNamespace) -> None:
    """Scene activation should resolve human friendly names via fuzzy matching."""

    catalog = _catalog_with_entities_and_scenes(
        scenes=[
            CatalogScene(
                entity_id="scene.movie_night",
                name="Movie Night",
                aliases=["Cinema Mode"],
            )
        ]
    )
    response = InterpretResponse(
        intent="scene_activate",
        area=None,
        targets=None,
        params={"scene": "cinema mode"},
        confidence=0.92,
    )

    await async_execute_intent(fake_hass, response, catalog=catalog)

    fake_hass.services.async_call.assert_awaited_once_with(
        "scene",
        "turn_on",
        {"entity_id": "scene.movie_night"},
        blocking=True,
    )


def test_resolve_scene_entity_id_matches_alias() -> None:
    """Fuzzy scene resolution should map aliases to canonical entity IDs."""

    catalog = CatalogPayload(
        areas=[],
        entities=[],
        scenes=[
            CatalogScene(
                entity_id="scene.relax_evening",
                name="Relax Evening",
                aliases=["relax mode", "wind down"],
            )
        ],
        plex_media=[],
    )

    assert (
        resolve_scene_entity_id("Wind-Down", catalog) == "scene.relax_evening"
    ), "Alias should resolve via fuzzy matching"
