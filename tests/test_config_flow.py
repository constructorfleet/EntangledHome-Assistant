"""Localization coverage tests for the config and options flows."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from pathlib import Path

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

    overrides = {
        const.OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED: False,
        const.OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES: [],
        const.OPT_SECONDARY_SIGNAL_VOICE_ENABLED: False,
        const.OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS: 30.0,
    }
    user_input = _build_user_input(**overrides)
    result = asyncio.run(_async_run_user_step(**overrides))

    assert result["type"] == "create_entry"
    assert result["data"][const.CONF_ADAPTER_URL] == user_input[const.CONF_ADAPTER_URL]


def test_config_flow_module_exports_configflow_alias() -> None:
    """Home Assistant expects the module to export ConfigFlow."""

    assert hasattr(config_flow_module, "ConfigFlow"), "ConfigFlow alias should be exported"
    assert config_flow_module.ConfigFlow is config_flow_module.ConfigFlowHandler, (
        "ConfigFlow should reference ConfigFlowHandler"
    )
