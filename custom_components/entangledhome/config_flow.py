"""Config flow for the EntangledHome integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback

from .const import (
    CONF_ADAPTER_URL,
    CONF_QDRANT_API_KEY,
    CONF_QDRANT_HOST,
    DEFAULT_CATALOG_SYNC,
    DEFAULT_CONFIDENCE_GATE,
    DOMAIN,
    OPT_ENABLE_CATALOG_SYNC,
    OPT_ENABLE_CONFIDENCE_GATE,
    TITLE,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADAPTER_URL): str,
        vol.Required(CONF_QDRANT_HOST): str,
        vol.Optional(CONF_QDRANT_API_KEY, default=""): str,
        vol.Required(OPT_ENABLE_CATALOG_SYNC, default=DEFAULT_CATALOG_SYNC): vol.Boolean(),
        vol.Required(
            OPT_ENABLE_CONFIDENCE_GATE,
            default=DEFAULT_CONFIDENCE_GATE,
        ): vol.Boolean(),
    }
)


class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Display the user form and create the entry."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        data = {
            CONF_ADAPTER_URL: user_input[CONF_ADAPTER_URL],
            CONF_QDRANT_HOST: user_input[CONF_QDRANT_HOST],
            CONF_QDRANT_API_KEY: user_input.get(CONF_QDRANT_API_KEY, ""),
        }
        options = {
            OPT_ENABLE_CATALOG_SYNC: user_input[OPT_ENABLE_CATALOG_SYNC],
            OPT_ENABLE_CONFIDENCE_GATE: user_input[OPT_ENABLE_CONFIDENCE_GATE],
        }

        return self.async_create_entry(title=TITLE, data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Manage the options flow for feature toggles."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPT_ENABLE_CATALOG_SYNC,
                        default=self._current_option(
                            OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC
                        ),
                    ): vol.Boolean(),
                    vol.Required(
                        OPT_ENABLE_CONFIDENCE_GATE,
                        default=self._current_option(
                            OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE
                        ),
                    ): vol.Boolean(),
                }
            ),
        )

    def _current_option(self, key: str, default: bool) -> bool:
        return bool(self._config_entry.options.get(key, default))
