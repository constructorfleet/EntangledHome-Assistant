# # PYTEST_DONT_REWRITE
# """Shared pytest fixtures for EntangledHome integration tests."""

# from __future__ import annotations

# from collections.abc import Awaitable, Callable
import pytest


@pytest.fixture
def enable_custom_integrations():
    """Minimal stub to satisfy pytest configuration when HA plugin isn't installed."""

    yield


# from datetime import timezone as dt_timezone
# from typing import Any
# from unittest.mock import AsyncMock, Mock, patch
# from homeassistant.helpers import area_registry as ar
# from homeassistant.helpers import entity_registry as er
# from pytest_homeassistant_custom_component.common import MockConfigEntry

# from custom_components.entangledhome.const import (
#     CONF_ADAPTER_URL,
#     CONF_QDRANT_API_KEY,
#     CONF_QDRANT_HOST,
#     DOMAIN,
# )
# from custom_components.entangledhome.models import InterpretResponse
# from homeassistant.util import dt as dt_util

# pytest_plugins = ["pytest_homeassistant_custom_component"]

# # Prevent registry cleanup timers from being scheduled during tests.
# ar.AreaRegistry._async_setup_cleanup = Mock(return_value=None)
# er._async_setup_cleanup = Mock(return_value=None)


# @pytest.fixture(autouse=True)
# def enforce_utc_timezone() -> None:
#     """Ensure the default timezone is restored to UTC for each test."""

#     dt_util.set_default_time_zone(dt_timezone.utc)
#     yield
#     dt_util.set_default_time_zone(dt_timezone.utc)

# DEFAULT_CONFIG_DATA = {
#     CONF_ADAPTER_URL: "http://adapter.internal/interpret",
#     CONF_QDRANT_HOST: "qdrant.internal",
#     CONF_QDRANT_API_KEY: "secret-key",
# }


# @pytest.fixture
# def mock_config_entry() -> Callable[..., MockConfigEntry]:
#     """Return a factory that builds mock config entries for the integration."""

#     def _factory(*, data: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> MockConfigEntry:
#         return MockConfigEntry(
#             domain=DOMAIN,
#             data=data or DEFAULT_CONFIG_DATA,
#             options=options or {},
#             title="EntangledHome",
#         )

#     return _factory


# @pytest.fixture
# def sample_adapter_response() -> InterpretResponse:
#     """Structured adapter response used by smoke tests."""

#     return InterpretResponse(
#         intent="set_light_color",
#         area="kitchen",
#         targets=["light.kitchen"],
#         params={"color": "red"},
#         confidence=0.88,
#     )


# @pytest.fixture
# def sample_qdrant_search_response() -> list[dict[str, Any]]:
#     """Representative Qdrant search response payload."""

#     return [
#         {
#             "id": "entity-light-kitchen",
#             "score": 0.92,
#             "payload": {
#                 "entity_id": "light.kitchen",
#                 "domain": "light",
#                 "area_id": "kitchen",
#                 "friendly_name": "Kitchen Light",
#                 "capabilities": {"color": True, "brightness": True},
#                 "aliases": ["cooking light"],
#             },
#         },
#         {
#             "id": "plex-movie-inception",
#             "score": 0.87,
#             "payload": {
#                 "rating_key": "1",
#                 "title": "Inception",
#                 "type": "movie",
#                 "year": 2010,
#                 "collection": ["Sci-Fi"],
#                 "genres": ["Sci-Fi"],
#                 "actors": ["Leonardo DiCaprio"],
#             },
#         },
#     ]


# @pytest.fixture
# def area_registry_builder(area_registry):
#     """Create areas in the Home Assistant area registry for tests."""

#     created_ids: list[str] = []

#     def _builder(*, name: str = "Kitchen", aliases: list[str] | None = None) -> Any:
#         entry = area_registry.async_create(name=name, aliases=set(aliases or []))
#         created_ids.append(entry.id)
#         return entry

#     yield _builder

#     for area_id in created_ids:
#         if area_registry.async_get_area(area_id) is not None:
#             area_registry.async_delete(area_id)


# @pytest.fixture
# def entity_registry_builder(entity_registry):
#     """Create entities in the Home Assistant entity registry for tests."""

#     created_entities: list[str] = []

#     def _builder(
#         *,
#         domain: str = "light",
#         platform: str = DOMAIN,
#         unique_id: str = "kitchen-light",
#         suggested_object_id: str | None = None,
#         **kwargs: Any,
#     ) -> Any:
#         entry = entity_registry.async_get_or_create(
#             domain,
#             platform,
#             unique_id,
#             suggested_object_id=suggested_object_id,
#             **kwargs,
#         )
#         created_entities.append(entry.entity_id)
#         return entry

#     yield _builder

#     for entity_id in created_entities:
#         if entity_registry.async_get(entity_id) is not None:
#             entity_registry.async_remove(entity_id)


# @pytest.fixture
# def setup_integration_with_mocks(
#     sample_adapter_response: InterpretResponse,
#     sample_qdrant_search_response: list[dict[str, Any]],
# ) -> Callable[[Any, MockConfigEntry], Awaitable[bool]]:
#     """Set up the integration while patching external dependencies."""

#     async def _setup(hass, entry: MockConfigEntry) -> bool:
#         entry.add_to_hass(hass)

#         with (
#             patch(
#                 "custom_components.entangledhome.coordinator.EntangledHomeCoordinator.async_config_entry_first_refresh",
#                 AsyncMock(return_value=sample_qdrant_search_response),
#             ),
#             patch(
#                 "custom_components.entangledhome.adapter_client.AdapterClient.interpret",
#                 AsyncMock(return_value=sample_adapter_response),
#             ),
#             patch(
#                 "homeassistant.helpers.storage.Store._async_schedule_callback_delayed_write",
#                 Mock(return_value=None),
#             ),
#             patch(
#                 "homeassistant.helpers.storage.Store._async_reschedule_delayed_write",
#                 Mock(return_value=None),
#             ),
#             patch(
#                 "homeassistant.helpers.area_registry.AreaRegistry._async_setup_cleanup",
#                 Mock(return_value=None),
#             ),
#             patch(
#                 "homeassistant.helpers.entity_registry._async_setup_cleanup",
#                 Mock(return_value=None),
#             ),
#         ):
#             assert await hass.config_entries.async_setup(entry.entry_id)
#             await hass.async_block_till_done()

#         return True

#     return _setup
