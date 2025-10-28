"""Tests covering options flow defaults for new integration settings."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_options_flow_provides_refresh_and_plex_defaults() -> None:
    """Options flow should expose refresh cadence and Plex toggle."""

    from custom_components.entangledhome.config_flow import OptionsFlowHandler
    from custom_components.entangledhome.const import (
        DEFAULT_INTENTS_CONFIG,
        DEFAULT_PLEX_SYNC,
        DEFAULT_REFRESH_INTERVAL_MINUTES,
        DEFAULT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
        DEFAULT_SECONDARY_SIGNAL_VOICE_ENABLED,
        DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
        OPT_ENABLE_PLEX_SYNC,
        OPT_INTENTS_CONFIG,
        OPT_REFRESH_INTERVAL_MINUTES,
        OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
        OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES,
        OPT_SECONDARY_SIGNAL_VOICE_ENABLED,
        OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
    )

    entry = SimpleNamespace(options={})

    async def _run() -> None:
        flow = OptionsFlowHandler(entry)
        form = await flow.async_step_init()
        defaults = form["data_schema"]({})

        assert defaults[OPT_REFRESH_INTERVAL_MINUTES] == DEFAULT_REFRESH_INTERVAL_MINUTES
        assert defaults[OPT_ENABLE_PLEX_SYNC] is DEFAULT_PLEX_SYNC
        assert defaults[OPT_INTENTS_CONFIG] == DEFAULT_INTENTS_CONFIG
        assert (
            defaults[OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED]
            is DEFAULT_SECONDARY_SIGNAL_PRESENCE_ENABLED
        )
        assert defaults[OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES] == []
        assert (
            defaults[OPT_SECONDARY_SIGNAL_VOICE_ENABLED] is DEFAULT_SECONDARY_SIGNAL_VOICE_ENABLED
        )
        assert (
            defaults[OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS]
            == DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS
        )

    asyncio.run(_run())


def test_options_flow_returns_form_structure() -> None:
    """Options flow should return a Home Assistant form response."""

    from custom_components.entangledhome.config_flow import OptionsFlowHandler

    entry = SimpleNamespace(options={})

    async def _run() -> None:
        flow = OptionsFlowHandler(entry)
        result = await flow.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    asyncio.run(_run())


def test_config_flow_import_does_not_require_httpx() -> None:
    """Importing the config flow should not depend on httpx availability."""

    import importlib
    import sys

    module_keys = [
        "custom_components.entangledhome",
        "custom_components.entangledhome.config_flow",
        "httpx",
    ]
    previous = {key: sys.modules.get(key) for key in module_keys}

    for key in module_keys:
        sys.modules.pop(key, None)

    try:
        module = importlib.import_module("custom_components.entangledhome.config_flow")
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    assert hasattr(module, "OptionsFlowHandler")


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
