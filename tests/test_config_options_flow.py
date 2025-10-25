"""Tests covering options flow defaults for new integration settings."""

from __future__ import annotations

from types import SimpleNamespace

import asyncio


def test_options_flow_provides_refresh_and_plex_defaults() -> None:
    """Options flow should expose refresh cadence and Plex toggle."""

    from custom_components.entangledhome.config_flow import OptionsFlowHandler
    from custom_components.entangledhome.const import (
        DEFAULT_PLEX_SYNC,
        DEFAULT_REFRESH_INTERVAL_MINUTES,
        OPT_ENABLE_PLEX_SYNC,
        OPT_REFRESH_INTERVAL_MINUTES,
    )

    entry = SimpleNamespace(options={})

    async def _run() -> None:
        flow = OptionsFlowHandler(entry)
        form = await flow.async_step_init()
        defaults = form["data_schema"]({})

        assert defaults[OPT_REFRESH_INTERVAL_MINUTES] == DEFAULT_REFRESH_INTERVAL_MINUTES
        assert defaults[OPT_ENABLE_PLEX_SYNC] is DEFAULT_PLEX_SYNC

    asyncio.run(_run())


def test_config_flow_declares_domain_constant() -> None:
    """Config flow should expose the integration domain via class attribute."""

    from custom_components.entangledhome.config_flow import ConfigFlowHandler
    from custom_components.entangledhome.const import DOMAIN

    assert ConfigFlowHandler.domain == DOMAIN


def test_options_flow_uses_existing_values() -> None:
    """Existing option values should be surfaced as defaults in the form."""

    from custom_components.entangledhome.config_flow import OptionsFlowHandler
    from custom_components.entangledhome.const import (
        OPT_ENABLE_PLEX_SYNC,
        OPT_REFRESH_INTERVAL_MINUTES,
    )

    entry = SimpleNamespace(
        options={
            OPT_REFRESH_INTERVAL_MINUTES: 12,
            OPT_ENABLE_PLEX_SYNC: False,
        }
    )

    async def _run() -> None:
        flow = OptionsFlowHandler(entry)
        form = await flow.async_step_init()
        defaults = form["data_schema"]({})

        assert defaults[OPT_REFRESH_INTERVAL_MINUTES] == 12
        assert defaults[OPT_ENABLE_PLEX_SYNC] is False

    asyncio.run(_run())
