"""Localization coverage tests for the config and options flows."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STRINGS_PATH = REPO_ROOT / "custom_components/entangledhome/strings.json"
TRANSLATIONS_EN_PATH = REPO_ROOT / "custom_components/entangledhome/translations/en.json"

LOCALIZATION_PATHS = [
    pytest.param(STRINGS_PATH, id="strings"),
    pytest.param(TRANSLATIONS_EN_PATH, id="en"),
]

const = importlib.import_module("custom_components.entangledhome.const")
config_flow_module = importlib.import_module("custom_components.entangledhome.config_flow")


@pytest.fixture(autouse=True)
def _ensure_event_loop() -> None:  # pragma: no cover - test infrastructure
    """Ensure an event loop exists for Home Assistant plugin fixtures."""

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        yield
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        asyncio.set_event_loop(None)
        loop.close()


USER_SCHEMA_FIELDS = {
    const.CONF_ADAPTER_URL,
    const.CONF_QDRANT_HOST,
    const.CONF_QDRANT_API_KEY,
    const.OPT_ADAPTER_SHARED_SECRET,
    const.OPT_ENABLE_CATALOG_SYNC,
    const.OPT_ENABLE_CONFIDENCE_GATE,
    const.OPT_CONFIDENCE_THRESHOLD,
    const.OPT_NIGHT_MODE_ENABLED,
    const.OPT_NIGHT_MODE_START_HOUR,
    const.OPT_NIGHT_MODE_END_HOUR,
    const.OPT_DEDUPLICATION_WINDOW,
    const.OPT_REFRESH_INTERVAL_MINUTES,
    const.OPT_ENABLE_PLEX_SYNC,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES,
    const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
    const.OPT_INTENTS_CONFIG,
}

SELECTOR_EXPECTATIONS = {
    const.CONF_ADAPTER_URL: "TextSelector",
    const.CONF_QDRANT_HOST: "TextSelector",
    const.CONF_QDRANT_API_KEY: "TextSelector",
    const.OPT_ADAPTER_SHARED_SECRET: "TextSelector",
    const.OPT_ENABLE_CATALOG_SYNC: "BooleanSelector",
    const.OPT_ENABLE_CONFIDENCE_GATE: "BooleanSelector",
    const.OPT_CONFIDENCE_THRESHOLD: "NumberSelector",
    const.OPT_NIGHT_MODE_ENABLED: "BooleanSelector",
    const.OPT_NIGHT_MODE_START_HOUR: "NumberSelector",
    const.OPT_NIGHT_MODE_END_HOUR: "NumberSelector",
    const.OPT_DEDUPLICATION_WINDOW: "NumberSelector",
    const.OPT_REFRESH_INTERVAL_MINUTES: "NumberSelector",
    const.OPT_ENABLE_PLEX_SYNC: "BooleanSelector",
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED: "BooleanSelector",
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES: "TextSelector",
    const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED: "BooleanSelector",
    const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS: "NumberSelector",
    const.OPT_ALLOWED_HOURS: "TextSelector",
    const.OPT_RECENT_COMMAND_WINDOW_OVERRIDES: "TextSelector",
    const.OPT_VERIFIED_USERS: "TextSelector",
    const.OPT_DANGEROUS_INTENTS: "TextSelector",
    const.OPT_DISABLED_INTENTS: "TextSelector",
    const.OPT_INTENT_THRESHOLDS: "TextSelector",
    const.OPT_INTENTS_CONFIG: "TextSelector",
}

OPTIONS_SCHEMA_FIELDS = {
    const.OPT_ENABLE_CATALOG_SYNC,
    const.OPT_ENABLE_CONFIDENCE_GATE,
    const.OPT_REFRESH_INTERVAL_MINUTES,
    const.OPT_ENABLE_PLEX_SYNC,
    const.OPT_ADAPTER_SHARED_SECRET,
    const.OPT_CONFIDENCE_THRESHOLD,
    const.OPT_NIGHT_MODE_ENABLED,
    const.OPT_NIGHT_MODE_START_HOUR,
    const.OPT_NIGHT_MODE_END_HOUR,
    const.OPT_DEDUPLICATION_WINDOW,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES,
    const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
    const.OPT_INTENTS_CONFIG,
}

GUARDRAIL_DESCRIPTION_FIELDS = {
    const.OPT_CONFIDENCE_THRESHOLD,
    const.OPT_NIGHT_MODE_START_HOUR,
    const.OPT_NIGHT_MODE_END_HOUR,
    const.OPT_DEDUPLICATION_WINDOW,
    const.OPT_REFRESH_INTERVAL_MINUTES,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES,
    const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED,
    const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
}

SECONDARY_DISABLED_OVERRIDES = {
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED: False,
    const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES: [],
    const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED: False,
    const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS: 30.0,
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(mapping: dict, *keys: str) -> dict[str, str]:
    current: dict = mapping
    for key in keys:
        assert key in current, f"Expected key '{key}' in path {keys!r}"
        current = current[key]
    assert isinstance(current, dict), f"Expected mapping at {keys!r}"
    return current


def _build_user_input(**overrides: object) -> dict[str, object]:
    base = config_flow_module.USER_SCHEMA(
        {
            const.CONF_ADAPTER_URL: "http://adapter",
            const.CONF_QDRANT_HOST: "qdrant",
        }
    )
    base.update(overrides)
    return base


def _config_flow_alias() -> type:
    assert hasattr(config_flow_module, "ConfigFlow"), "ConfigFlow alias should be exported"
    return getattr(config_flow_module, "ConfigFlow")


def _extract_validator(schema: object, field: str):
    mapping = getattr(schema, "schema", {})
    for key, validator in mapping.items():
        key_name = getattr(key, "schema", key)
        if key_name == field:
            return validator
    raise AssertionError(f"Field {field} not found in schema")


def _selector_name(validator: object) -> str | None:
    name = getattr(getattr(validator, "__class__", None), "__name__", "")
    if name.endswith("Selector"):
        return name
    inner_validators = getattr(validator, "validators", [])
    for inner in inner_validators:
        inner_name = _selector_name(inner)
        if inner_name:
            return inner_name
    return None


async def _async_run_user_step(**overrides: object) -> dict[str, object]:
    """Run the config flow user step for the provided overrides."""

    flow = config_flow_module.ConfigFlow()
    return await flow.async_step_user(_build_user_input(**overrides))


@pytest.mark.parametrize("path", LOCALIZATION_PATHS)
def test_user_schema_fields_have_localized_labels(path: Path) -> None:
    """Every user schema field must expose a localized label."""

    mapping = _load_json(path)
    user_labels = _resolve(mapping, "config", "step", "user", "data")
    missing = USER_SCHEMA_FIELDS.difference(user_labels)
    assert not missing, f"Missing user labels in {path.name}: {sorted(missing)}"


@pytest.mark.parametrize("path", LOCALIZATION_PATHS)
def test_options_schema_fields_have_localized_labels(path: Path) -> None:
    """Every options flow field must expose a localized label."""

    mapping = _load_json(path)
    option_labels = _resolve(mapping, "options", "step", "init", "data")
    missing = OPTIONS_SCHEMA_FIELDS.difference(option_labels)
    assert not missing, f"Missing options labels in {path.name}: {sorted(missing)}"


@pytest.mark.parametrize("path", LOCALIZATION_PATHS)
def test_guardrail_fields_include_help_text(path: Path) -> None:
    """Guardrail controls should provide contextual help text."""

    mapping = _load_json(path)
    descriptions = _resolve(mapping, "config", "step", "user", "data_description")
    missing = GUARDRAIL_DESCRIPTION_FIELDS.difference(descriptions)
    assert not missing, f"Missing guardrail descriptions in {path.name}: {sorted(missing)}"


def test_user_flow_populates_secondary_signal_options() -> None:
    """User config flow should persist secondary signal guardrail fields."""

    user_input = _build_user_input(
        **{
            const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED: True,
            const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES: [
                "person.alice",
                "person.bob",
            ],
            const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED: True,
            const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS: 45.0,
        }
    )

    async def _run_flow() -> object:
        return await _async_run_user_step(**user_input)

    result = asyncio.run(_run_flow())
    assert not inspect.isawaitable(result)

    options = result["options"]
    assert options[const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED] is True
    assert options[const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES] == [
        "person.alice",
        "person.bob",
    ]
    assert options[const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED] is True
    assert options[const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS] == 45.0


def test_async_step_user_creates_entry() -> None:
    """The config flow should return a create_entry result."""

    user_input = _build_user_input(**SECONDARY_DISABLED_OVERRIDES)
    result = asyncio.run(_async_run_user_step(**SECONDARY_DISABLED_OVERRIDES))

    assert result["type"] == "create_entry"
    assert result["data"][const.CONF_ADAPTER_URL] == user_input[const.CONF_ADAPTER_URL]


def test_async_step_user_returns_sync_flow_result() -> None:
    """Flow results should be realized dictionaries, not bare coroutines."""

    result = asyncio.run(_async_run_user_step(**SECONDARY_DISABLED_OVERRIDES))

    assert not inspect.isawaitable(result)
    assert isinstance(result, dict)
    assert result["type"] == "create_entry"


def test_config_flow_module_exports_configflow_alias() -> None:
    """Home Assistant expects the module to export ConfigFlow."""

    assert _config_flow_alias() is config_flow_module.ConfigFlowHandler, (
        "ConfigFlow should reference ConfigFlowHandler"
    )


def test_config_flow_alias_exposes_domain_constant() -> None:
    """The ConfigFlow alias should expose the integration domain."""

    assert _config_flow_alias().domain == const.DOMAIN


def test_user_schema_fields_use_selectors() -> None:
    """User form controls should leverage Home Assistant selectors."""

    schema = config_flow_module.USER_SCHEMA
    for field, expected in SELECTOR_EXPECTATIONS.items():
        selector_name = _selector_name(_extract_validator(schema, field))
        assert selector_name == expected, f"Expected {field} to use {expected}, got {selector_name}"


def test_options_schema_fields_use_selectors() -> None:
    """Options flow schema should also rely on selectors for UI rendering."""

    entry = SimpleNamespace(options={})

    async def _build_schema() -> object:
        flow = config_flow_module.OptionsFlowHandler(entry)
        form = await flow.async_step_init()
        return form["data_schema"]

    schema = asyncio.run(_build_schema())

    option_expectations = {
        field: SELECTOR_EXPECTATIONS[field]
        for field in OPTIONS_SCHEMA_FIELDS
        if field in SELECTOR_EXPECTATIONS
    }

    for field, expected in option_expectations.items():
        selector_name = _selector_name(_extract_validator(schema, field))
        assert selector_name == expected, f"Expected {field} to use {expected}, got {selector_name}"
