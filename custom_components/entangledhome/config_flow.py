"""Config flow for the EntangledHome integration."""

from __future__ import annotations

from typing import Any, Mapping

import json
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
    DEFAULT_DISABLED_INTENTS,
    DEFAULT_DANGEROUS_INTENTS,
    DEFAULT_ALLOWED_HOURS,
    DEFAULT_INTENTS_CONFIG,
    DEFAULT_INTENT_THRESHOLDS,
    DEFAULT_NIGHT_MODE_END_HOUR,
    DEFAULT_NIGHT_MODE_ENABLED,
    DEFAULT_NIGHT_MODE_START_HOUR,
    DEFAULT_RECENT_COMMAND_WINDOW_OVERRIDES,
    DEFAULT_PLEX_SYNC,
    DEFAULT_REFRESH_INTERVAL_MINUTES,
    DOMAIN,
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DEDUPLICATION_WINDOW,
    OPT_ADAPTER_SHARED_SECRET,
    OPT_ENABLE_CATALOG_SYNC,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_ENABLE_PLEX_SYNC,
    OPT_INTENTS_CONFIG,
    OPT_INTENT_THRESHOLDS,
    OPT_DISABLED_INTENTS,
    OPT_DANGEROUS_INTENTS,
    OPT_ALLOWED_HOURS,
    OPT_RECENT_COMMAND_WINDOW_OVERRIDES,
    OPT_NIGHT_MODE_ENABLED,
    OPT_NIGHT_MODE_END_HOUR,
    OPT_NIGHT_MODE_START_HOUR,
    OPT_REFRESH_INTERVAL_MINUTES,
    TITLE,
)


def _coerce_json_object(
    value: object, *, default: Mapping[str, object] | None = None
) -> dict[str, object]:
    if value in (None, ""):
        return dict(default or {})
    if isinstance(value, dict):
        return {str(key): val for key, val in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError as exc:  # pragma: no cover - validation path
            raise vol.Invalid(f"Invalid JSON mapping: {exc}")
        if isinstance(parsed, dict):
            return {str(key): val for key, val in parsed.items()}
    raise vol.Invalid("Expected a JSON object mapping intents to values")


def _coerce_string_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [item for item in (part.strip() for part in stripped.split(",")) if item]
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]
    raise vol.Invalid("Expected a JSON array or comma separated string of intents")


def _validate_intent_thresholds(value: object) -> dict[str, float]:
    data = _coerce_json_object(value)
    thresholds: dict[str, float] = {}
    for intent, raw in data.items():
        try:
            threshold = float(raw)
        except (TypeError, ValueError) as exc:
            raise vol.Invalid(f"Invalid threshold for {intent}: {raw}") from exc
        if not 0.0 <= threshold <= 1.0:
            raise vol.Invalid(f"Threshold for {intent} must be between 0 and 1")
        thresholds[intent] = threshold
    return thresholds


def _validate_allowed_hours(value: object) -> dict[str, list[int]]:
    data = _coerce_json_object(value)
    hours: dict[str, list[int]] = {}
    for intent, raw in data.items():
        if isinstance(raw, Mapping):
            start = raw.get("start")
            end = raw.get("end")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            start, end = raw
        else:
            raise vol.Invalid(
                f"Allowed hours for {intent} must be [start, end] or an object with start/end"
            )
        try:
            start_hour = int(start)
            end_hour = int(end)
        except (TypeError, ValueError) as exc:
            raise vol.Invalid(f"Invalid allowed hours for {intent}") from exc
        if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
            raise vol.Invalid(f"Allowed hours for {intent} must be between 0 and 23")
        hours[intent] = [start_hour, end_hour]
    return hours


def _validate_recent_windows(value: object) -> dict[str, float]:
    data = _coerce_json_object(value)
    windows: dict[str, float] = {}
    for intent, raw in data.items():
        try:
            window = float(raw)
        except (TypeError, ValueError) as exc:
            raise vol.Invalid(f"Invalid dedupe window for {intent}: {raw}") from exc
        if window < 0:
            raise vol.Invalid(f"Dedupe window for {intent} must be non-negative")
        windows[intent] = window
    return windows


def _validate_intents_config(value: object) -> dict[str, dict[str, object]]:
    data = _coerce_json_object(value, default=DEFAULT_INTENTS_CONFIG)
    intents: dict[str, dict[str, object]] = {}
    for intent, raw in data.items():
        if not isinstance(raw, Mapping):
            raise vol.Invalid(f"Intent configuration for {intent} must be a mapping")
        intents[intent] = {str(key): val for key, val in raw.items()}
    return intents


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

GUARDRAIL_COMPLEX_OPTION_FIELDS: tuple[tuple[str, object, Any], ...] = (
    (OPT_INTENT_THRESHOLDS, DEFAULT_INTENT_THRESHOLDS, _validate_intent_thresholds),
    (OPT_DISABLED_INTENTS, list(DEFAULT_DISABLED_INTENTS), _coerce_string_list),
    (OPT_DANGEROUS_INTENTS, list(DEFAULT_DANGEROUS_INTENTS), _coerce_string_list),
    (OPT_ALLOWED_HOURS, DEFAULT_ALLOWED_HOURS, _validate_allowed_hours),
    (
        OPT_RECENT_COMMAND_WINDOW_OVERRIDES,
        DEFAULT_RECENT_COMMAND_WINDOW_OVERRIDES,
        _validate_recent_windows,
    ),
)

INTENTS_OPTION_FIELD: tuple[str, object, Any] = (
    OPT_INTENTS_CONFIG,
    DEFAULT_INTENTS_CONFIG,
    _validate_intents_config,
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
        **{
            vol.Required(option_key, default=default): validator
            for option_key, default, validator in GUARDRAIL_COMPLEX_OPTION_FIELDS
        },
        vol.Required(
            OPT_REFRESH_INTERVAL_MINUTES,
            default=DEFAULT_REFRESH_INTERVAL_MINUTES,
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        vol.Required(
            OPT_ENABLE_PLEX_SYNC,
            default=DEFAULT_PLEX_SYNC,
        ): vol.Boolean(),
        vol.Required(
            INTENTS_OPTION_FIELD[0],
            default=INTENTS_OPTION_FIELD[1],
        ): INTENTS_OPTION_FIELD[2],
    }
)


class ConfigFlowHandler(config_entries.ConfigFlow):
    """Handle the initial configuration flow."""

    VERSION = 1
    domain = DOMAIN

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
            OPT_INTENTS_CONFIG: user_input[OPT_INTENTS_CONFIG],
        }

        for option_key, _default, _validator in GUARDRAIL_COMPLEX_OPTION_FIELDS:
            options[option_key] = user_input[option_key]

        return self.async_create_entry(title=TITLE, data=data, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> config_entries.ConfigFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Manage the options flow for feature toggles."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    def async_show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: dict[str, str] | None = None,
    ) -> OptionsFlowResult:
        base_handler = getattr(super(), "async_show_form", None)
        if callable(base_handler):  # pragma: no branch - depends on HA version
            try:
                return base_handler(
                    step_id=step_id,
                    data_schema=data_schema,
                    errors=errors,
                    description_placeholders=description_placeholders,
                )
            except TypeError:  # pragma: no cover - legacy Home Assistant stubs
                return base_handler(step_id=step_id, data_schema=data_schema)

        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
            "description_placeholders": description_placeholders,
        }

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> OptionsFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=self._options_schema())

    def _options_schema(self) -> vol.Schema:
        base_schema: dict[vol.Schema, object] = {
            vol.Required(
                OPT_ENABLE_CATALOG_SYNC,
                default=self._bool_option(OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC),
            ): vol.Boolean(),
            vol.Required(
                OPT_ENABLE_CONFIDENCE_GATE,
                default=self._bool_option(OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE),
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
            vol.Required(
                INTENTS_OPTION_FIELD[0],
                default=self._current_complex_default(
                    INTENTS_OPTION_FIELD[0], INTENTS_OPTION_FIELD[1]
                ),
            ): INTENTS_OPTION_FIELD[2],
        }

        base_schema.update(self._guardrail_option_schema())
        base_schema.update(self._complex_guardrail_schema())
        return vol.Schema(base_schema)

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

    def _complex_guardrail_schema(self) -> dict[vol.Schema, object]:
        schema: dict[vol.Schema, object] = {}
        for option_key, default, validator in GUARDRAIL_COMPLEX_OPTION_FIELDS:
            schema[
                vol.Required(
                    option_key,
                    default=self._current_complex_default(option_key, default),
                )
            ] = validator
        return schema

    def _current_complex_default(self, key: str, default: object) -> object:
        value = self._config_entry.options.get(key, default)
        if isinstance(default, dict):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = default
            return dict(value)
        if isinstance(default, (list, tuple)):
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    parsed = [part.strip() for part in value.split(",") if part.strip()]
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [str(item).strip() for item in value] if value else []
        return value
