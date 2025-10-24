# """Smoke tests for loading the EntangledHome integration."""

# from __future__ import annotations

# import pytest


# pytestmark = pytest.mark.asyncio


# @pytest.mark.parametrize("expected_lingering_tasks", [True])
# @pytest.mark.parametrize("expected_lingering_timers", [True])
# async def test_setup_entry_initializes_domain_data(
#     hass, mock_config_entry, setup_integration_with_mocks
# ) -> None:
#     """Integration setup should create the coordinator entry in hass.data."""
#     entry = mock_config_entry()

#     await setup_integration_with_mocks(hass, entry)

#     domain_data = hass.data["entangledhome"][entry.entry_id]
#     assert "coordinator" in domain_data

#     await hass.config_entries.async_unload(entry.entry_id)
#     await hass.async_block_till_done()
#     await hass.async_stop()
#     await hass.async_block_till_done()


# @pytest.mark.parametrize("expected_lingering_tasks", [True])
# @pytest.mark.parametrize("expected_lingering_timers", [True])
# async def test_setup_entry_populates_default_options(
#     hass, mock_config_entry, setup_integration_with_mocks
# ) -> None:
#     """Integration setup should populate default options when missing."""
#     entry = mock_config_entry(options={})

#     await setup_integration_with_mocks(hass, entry)

#     assert entry.options["enable_catalog_sync"] is True
#     assert entry.options["enable_confidence_gate"] is False

#     await hass.config_entries.async_unload(entry.entry_id)
#     await hass.async_block_till_done()
#     await hass.async_stop()
#     await hass.async_block_till_done()


# @pytest.mark.parametrize("expected_lingering_tasks", [True])
# @pytest.mark.parametrize("expected_lingering_timers", [True])
# async def test_catalog_fixture_provides_qdrant_payload(sample_qdrant_search_response) -> None:
#     """Fixture should supply representative Qdrant search results."""
#     payload = sample_qdrant_search_response

#     assert payload[0]["payload"]["entity_id"] == "light.kitchen"
#     assert payload[1]["payload"]["title"] == "Inception"
