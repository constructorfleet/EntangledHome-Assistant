"""Config flow for the EntangledHome integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry

try:  # pragma: no cover - fallback for older Home Assistant stubs
    from homeassistant.config_entries import ConfigFlowResult, OptionsFlowResult
except ImportError:  # pragma: no cover
    from typing import Any as ConfigFlowResult  # type: ignore[assignment]
    from typing import Any as OptionsFlowResult  # type: ignore[assignment]
from homeassistant.core import callback

from .const import (
    CONF_ADAPTER_URL,
    CONF_QDRANT_API_KEY,
    CONF_QDRANT_HOST,
    DEFAULT_CATALOG_SYNC,
    DEFAULT_CONFIDENCE_GATE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DEDUPLICATION_WINDOW,
    DEFAULT_NIGHT_MODE_END_HOUR,
    DEFAULT_NIGHT_MODE_ENABLED,
    DEFAULT_NIGHT_MODE_START_HOUR,
    DEFAULT_PLEX_SYNC,
    DEFAULT_REFRESH_INTERVAL_MINUTES,
    DOMAIN,
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DEDUPLICATION_WINDOW,
    OPT_ADAPTER_SHARED_SECRET,
    OPT_ENABLE_CATALOG_SYNC,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_ENABLE_PLEX_SYNC,
    OPT_NIGHT_MODE_ENABLED,
    OPT_NIGHT_MODE_END_HOUR,
    OPT_NIGHT_MODE_START_HOUR,
    OPT_REFRESH_INTERVAL_MINUTES,
    TITLE,
)

GUARDRAIL_OPTION_FIELDS: tuple[tuple[str, str, float | int | bool, vol.Schema], ...] = (
    (
        "float",
        OPT_CONFIDENCE_THRESHOLD,
        DEFAULT_CONFIDENCE_THRESHOLD,
        vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
    ),
    (
        "bool",
        OPT_NIGHT_MODE_ENABLED,
        DEFAULT_NIGHT_MODE_ENABLED,
        vol.Boolean(),
    ),
    (
        "int",
        OPT_NIGHT_MODE_START_HOUR,
        DEFAULT_NIGHT_MODE_START_HOUR,
        vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
    ),
    (
        "int",
        OPT_NIGHT_MODE_END_HOUR,
        DEFAULT_NIGHT_MODE_END_HOUR,
        vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
    ),
    (
        "float",
        OPT_DEDUPLICATION_WINDOW,
        DEFAULT_DEDUPLICATION_WINDOW,
        vol.All(vol.Coerce(float), vol.Range(min=0.0, max=30.0)),
    ),
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADAPTER_URL): str,
        vol.Required(CONF_QDRANT_HOST): str,
        vol.Optional(CONF_QDRANT_API_KEY, default=""): str,
        vol.Required(OPT_ADAPTER_SHARED_SECRET, default=""): str,
        vol.Required(OPT_ENABLE_CATALOG_SYNC, default=DEFAULT_CATALOG_SYNC): vol.Boolean(),
        vol.Required(
            OPT_ENABLE_CONFIDENCE_GATE,
            default=DEFAULT_CONFIDENCE_GATE,
        ): vol.Boolean(),
        **{
            vol.Required(option_key, default=default): validator
            for _, option_key, default, validator in GUARDRAIL_OPTION_FIELDS
        },
        vol.Required(
            OPT_REFRESH_INTERVAL_MINUTES,
            default=DEFAULT_REFRESH_INTERVAL_MINUTES,
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        vol.Required(
            OPT_ENABLE_PLEX_SYNC,
            default=DEFAULT_PLEX_SYNC,
        ): vol.Boolean(),
    }
)


class ConfigFlowHandler(config_entries.ConfigFlow):
    """Handle the initial configuration flow."""

    VERSION = 1
    domain = DOMAIN

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            OPT_CONFIDENCE_THRESHOLD: user_input[OPT_CONFIDENCE_THRESHOLD],
            OPT_NIGHT_MODE_ENABLED: user_input[OPT_NIGHT_MODE_ENABLED],
            OPT_NIGHT_MODE_START_HOUR: user_input[OPT_NIGHT_MODE_START_HOUR],
            OPT_NIGHT_MODE_END_HOUR: user_input[OPT_NIGHT_MODE_END_HOUR],
            OPT_DEDUPLICATION_WINDOW: user_input[OPT_DEDUPLICATION_WINDOW],
            OPT_REFRESH_INTERVAL_MINUTES: user_input[OPT_REFRESH_INTERVAL_MINUTES],
            OPT_ENABLE_PLEX_SYNC: user_input[OPT_ENABLE_PLEX_SYNC],
            OPT_ADAPTER_SHARED_SECRET: user_input[OPT_ADAPTER_SHARED_SECRET],
        }

        return self.async_create_entry(title=TITLE, data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> config_entries.ConfigFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Manage the options flow for feature toggles."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> OptionsFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        base_schema: dict[vol.Schema, object] = {
            vol.Required(
                OPT_ENABLE_CATALOG_SYNC,
                default=self._bool_option(OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC),
            ): vol.Boolean(),
            vol.Required(
                OPT_ENABLE_CONFIDENCE_GATE,
                default=self._bool_option(
                    OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE
                ),
            ): vol.Boolean(),
            vol.Required(
                OPT_REFRESH_INTERVAL_MINUTES,
                default=self._int_option(
                    OPT_REFRESH_INTERVAL_MINUTES, DEFAULT_REFRESH_INTERVAL_MINUTES
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Required(
                OPT_ENABLE_PLEX_SYNC,
                default=self._bool_option(OPT_ENABLE_PLEX_SYNC, DEFAULT_PLEX_SYNC),
            ): vol.Boolean(),
            vol.Required(
                OPT_ADAPTER_SHARED_SECRET,
                default=self._current_option(OPT_ADAPTER_SHARED_SECRET, ""),
            ): str,
        }

        base_schema.update(self._guardrail_option_schema())

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(base_schema)
        )

    def _current_option(self, key: str, default: object) -> object:
        return self._config_entry.options.get(key, default)

    def _bool_option(self, key: str, default: bool) -> bool:
        return bool(self._current_option(key, default))

    def _int_option(self, key: str, default: int) -> int:
        return int(self._current_option(key, default))

    def _float_option(self, key: str, default: float) -> float:
        return float(self._current_option(key, default))

    def _option_value(self, option_type: str, key: str, default: object) -> object:
        if option_type == "bool":
            return self._bool_option(key, bool(default))
        if option_type == "int":
            return self._int_option(key, int(default))
        if option_type == "float":
            return self._float_option(key, float(default))
        return self._current_option(key, default)

    def _guardrail_option_schema(self) -> dict[vol.Schema, object]:
        schema: dict[vol.Schema, object] = {}
        for option_type, option_key, default, validator in GUARDRAIL_OPTION_FIELDS:
            schema[
                vol.Required(
                    option_key,
                    default=self._option_value(option_type, option_key, default),
                )
            ] = validator
        return schema
