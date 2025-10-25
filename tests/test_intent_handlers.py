"""Golden tests for intent handler service routing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable
from unittest.mock import AsyncMock

import pytest

from custom_components.entangledhome.intent_handlers import (
    EXECUTORS,
    IntentHandlingError,
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
from homeassistant.core import HomeAssistant


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
def fake_hass() -> HomeAssistant:
    """Return a stub Home Assistant core object."""

    hass = HomeAssistant()
    hass.services = SimpleNamespace(async_call=AsyncMock())  # type: ignore[attr-defined]
    hass.states = FakeStates()  # type: ignore[attr-defined]
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


async def test_report_sensor_summarizes_by_area(fake_hass: HomeAssistant) -> None:
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

    await async_execute_intent(
        fake_hass,
        response,
        catalog=catalog,
        intent_config={"slots": ["targets", "area"]},
    )

    fake_hass.services.async_call.assert_awaited_once_with(
        "conversation",
        "process",
        {"text": "Living Room: Thermostat is 72 °F\nKitchen: Humidity is 40 %"},
        blocking=True,
    )


async def test_media_play_routes_to_media_player(fake_hass: HomeAssistant) -> None:
    """`media_play` should call the media_player domain with the interpreted target."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="media_play",
        area="living_room",
        targets=None,
        params={},
        confidence=0.81,
    )

    await async_execute_intent(
        fake_hass,
        response,
        catalog=catalog,
        intent_config={"slots": ["media", "targets", "area"]},
    )

    fake_hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "media_play",
        {},
        target={"area_id": "living_room"},
        blocking=True,
    )


async def test_media_pause_routes_to_media_player(fake_hass: HomeAssistant) -> None:
    """`media_pause` should call the media_player domain with the interpreted target."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="media_pause",
        area="living_room",
        targets=None,
        params={},
        confidence=0.83,
    )

    await async_execute_intent(
        fake_hass,
        response,
        catalog=catalog,
        intent_config={"slots": ["media", "targets", "area"]},
    )

    fake_hass.services.async_call.assert_awaited_once_with(
        "media_player",
        "media_pause",
        {},
        target={"area_id": "living_room"},
        blocking=True,
    )


async def test_play_title_invokes_media_player_with_plex_metadata(fake_hass: HomeAssistant) -> None:
    """`play_title` should call play_media with Plex metadata preserved."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="play_title",
        area=None,
        targets=["media_player.living_room_tv"],
        params={
            "media_id": "4242",
            "server_name": "PlexServer",
            "media_type": "movie",
            "shuffle": True,
        },
        confidence=0.9,
    )

    await async_execute_intent(
        fake_hass,
        response,
        catalog=catalog,
        intent_config={
            "slots": ["media_id", "server_name", "media_type", "shuffle", "targets"],
        },
    )

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


async def test_scene_activate_uses_fuzzy_resolution(fake_hass: HomeAssistant) -> None:
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
        params={"scene_name": "cinema mode"},
        confidence=0.92,
    )

    await async_execute_intent(
        fake_hass,
        response,
        catalog=catalog,
        intent_config={"slots": ["scene_name"]},
    )

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


def test_executor_registry_lists_supported_intents() -> None:
    """Executor registry should expose handlers for known intents."""

    expected = {
        "set_light_color",
        "turn_on",
        "turn_off",
        "set_brightness",
        "scene_activate",
        "report_sensor",
        "media_play",
        "media_pause",
        "play_title",
        "noop",
    }

    assert expected.issubset(EXECUTORS), "All expected intents must be registered"


async def test_async_execute_intent_errors_for_unknown_intent(
    fake_hass: HomeAssistant,
) -> None:
    """Unknown intents should raise a descriptive error."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="unsupported_intent",
        area=None,
        targets=None,
        params={},
        confidence=0.8,
    )

    with pytest.raises(IntentHandlingError) as excinfo:
        await async_execute_intent(fake_hass, response, catalog=catalog)

    assert (
        str(excinfo.value) == "No executor registered for intent 'unsupported_intent'"
    )


async def test_async_execute_intent_errors_when_intent_disabled(
    fake_hass: HomeAssistant,
) -> None:
    """Passing a disabled flag in intent metadata should abort execution."""

    catalog = _catalog_with_entities_and_scenes()
    response = InterpretResponse(
        intent="turn_on",
        area="living_room",
        targets=None,
        params={},
        confidence=0.9,
    )

    with pytest.raises(IntentHandlingError) as excinfo:
        await async_execute_intent(
            fake_hass,
            response,
            catalog=catalog,
            intent_config={"disabled": True},
        )

    assert str(excinfo.value) == "Intent 'turn_on' is disabled"
