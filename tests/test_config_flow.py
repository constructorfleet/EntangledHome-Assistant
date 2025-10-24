"""Tests for the EntangledHome config and options flows."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

TEST_FILE_PATH = Path(__file__)
REPO_ROOT = TEST_FILE_PATH.resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT))

DOMAIN = "entangledhome"
STRINGS_PATH = REPO_ROOT / "custom_components/entangledhome/strings.json"
TRANSLATIONS_EN_PATH = REPO_ROOT / "custom_components/entangledhome/translations/en.json"


@pytest.mark.asyncio
async def test_user_flow_creates_entry(hass):
    """The user step should collect adapter and Qdrant settings."""
    flow = _get_flow_handler(hass)

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    user_input = {
        "adapter_url": "http://adapter:8080/interpret",
        "qdrant_host": "qdrant.internal",
        "qdrant_api_key": "secret",
        "enable_catalog_sync": True,
        "enable_confidence_gate": False,
    }

    result = await flow.async_step_user(user_input=user_input)
    assert result["type"] == "create_entry"
    assert result["title"] == "EntangledHome"
    assert result["data"] == {
        "adapter_url": "http://adapter:8080/interpret",
        "qdrant_host": "qdrant.internal",
        "qdrant_api_key": "secret",
    }
    assert result["options"] == {
        "enable_catalog_sync": True,
        "enable_confidence_gate": False,
    }


@pytest.mark.asyncio
async def test_options_flow_updates_entry_and_refreshes_coordinator():
    """Options updates should persist and trigger coordinator refresh."""
    hass = _fake_hass()
    config_entry = _fake_config_entry(
        data={
            "adapter_url": "http://adapter:8080/interpret",
            "qdrant_host": "qdrant.internal",
            "qdrant_api_key": "secret",
        },
        options={
            "enable_catalog_sync": True,
            "enable_confidence_gate": False,
        },
    )

    module = _load_module()

    with patch("custom_components.entangledhome.coordinator.EntangledHomeCoordinator") as coordinator_cls:
        coordinator = coordinator_cls.return_value
        coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
        coordinator.async_request_refresh = AsyncMock(return_value=None)

        hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
            "coordinator": coordinator
        }

        options_flow = _get_options_flow(config_entry)
        form = await options_flow.async_step_init()
        assert form["type"] == "form"
        assert form["step_id"] == "init"

        result = await options_flow.async_step_init(
            user_input={
                "enable_catalog_sync": False,
                "enable_confidence_gate": True,
            }
        )

    assert result["type"] == "create_entry"
    config_entry.options = result["data"]

    await module.async_update_options(hass, config_entry)

    assert config_entry.options == {
        "enable_catalog_sync": False,
        "enable_confidence_gate": True,
    }
    coordinator.async_request_refresh.assert_awaited()


def test_strings_and_translations_contain_expected_content():
    """Ensure the UI prompts and translations are populated."""
    assert STRINGS_PATH.exists(), "Expected strings.json to exist"
    assert TRANSLATIONS_EN_PATH.exists(), "Expected English translation file to exist"

    strings_content = STRINGS_PATH.read_text(encoding="utf-8")
    translations_content = TRANSLATIONS_EN_PATH.read_text(encoding="utf-8")

    for snippet in [
        '"step"',
        '"user"',
        '"adapter_url"',
        '"qdrant_host"',
        '"enable_catalog_sync"',
        '"enable_confidence_gate"',
    ]:
        assert snippet in strings_content, f"strings.json missing {snippet}"

    for snippet in [
        '"title"',
        '"EntangledHome - Assistant"',
        '"adapter_url"',
    ]:
        assert snippet in translations_content, f"en.json missing {snippet}"


def test_config_flow_tests_avoid_direct_homeassistant_imports():
    """Guard against unnecessary homeassistant dependencies in tests."""
    content = TEST_FILE_PATH.read_text(encoding="utf-8")
    needle = "from " + "homeassistant"
    assert needle not in content, "Tests should not import homeassistant directly"


def _get_flow_handler(hass):
    """Instantiate the config flow handler for tests."""
    flow_module = _load_config_flow()
    flow = flow_module.ConfigFlowHandler()
    flow.hass = hass
    return flow


def _get_options_flow(config_entry):
    flow_module = _load_config_flow()
    return flow_module.OptionsFlowHandler(config_entry)


def _fake_config_entry(*, data, options):
    return _FakeConfigEntry(data=data, options=options)


def _fake_hass():
    class FakeConfigEntries:
        def __init__(self, hass):
            self.hass = hass

        def async_update_entry(self, entry, *, options=None, data=None):
            if options is not None:
                entry.options = options

    hass = SimpleNamespace()
    hass.data = {}
    hass.config_entries = FakeConfigEntries(hass)
    return hass


class _FakeConfigEntry:
    def __init__(self, *, data, options):
        self.domain = DOMAIN
        self.entry_id = "test-entry"
        self.data = data
        self.options = options
        self._unload_callbacks = []
        self._update_listeners = []

    def add_update_listener(self, listener):
        self._update_listeners.append(listener)
        return listener

    def async_on_unload(self, callback):
        self._unload_callbacks.append(callback)


def _load_module():
    import importlib

    return importlib.import_module("custom_components.entangledhome")


def _load_config_flow():
    import importlib

    return importlib.import_module("custom_components.entangledhome.config_flow")
