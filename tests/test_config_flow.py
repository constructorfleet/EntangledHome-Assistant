"""Localization coverage tests for the config and options flows."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
STRINGS_PATH = REPO_ROOT / "custom_components/entangledhome/strings.json"
TRANSLATIONS_EN_PATH = (
    REPO_ROOT / "custom_components/entangledhome/translations/en.json"
)

LOCALIZATION_PATHS = [
    pytest.param(STRINGS_PATH, id="strings"),
    pytest.param(TRANSLATIONS_EN_PATH, id="en"),
]

_CONST_SPEC = importlib.util.spec_from_file_location(
    "entangledhome_const", REPO_ROOT / "custom_components/entangledhome/const.py"
)
assert _CONST_SPEC and _CONST_SPEC.loader
const = importlib.util.module_from_spec(_CONST_SPEC)
_CONST_SPEC.loader.exec_module(const)

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
    const.OPT_INTENTS_CONFIG,
}

GUARDRAIL_DESCRIPTION_FIELDS = {
    const.OPT_CONFIDENCE_THRESHOLD,
    const.OPT_NIGHT_MODE_START_HOUR,
    const.OPT_NIGHT_MODE_END_HOUR,
    const.OPT_DEDUPLICATION_WINDOW,
    const.OPT_REFRESH_INTERVAL_MINUTES,
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
