"""Integration-style tests for conversation setup and teardown."""

from __future__ import annotations

from typing import Any

import pytest

import custom_components.entangledhome as integration
from custom_components.entangledhome import conversation as conv
from custom_components.entangledhome.const import (
    CONF_ADAPTER_URL,
    CONF_QDRANT_API_KEY,
    CONF_QDRANT_HOST,
    DOMAIN,
    OPT_ADAPTER_SHARED_SECRET,
    OPT_INTENTS_CONFIG,
    DEFAULT_INTENTS_CONFIG,
)
from custom_components.entangledhome.models import CatalogPayload, InterpretResponse
from custom_components.entangledhome.telemetry import TelemetryRecorder
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


pytestmark = pytest.mark.asyncio


def _build_hass_and_entry() -> tuple[HomeAssistant, ConfigEntry]:
    """Return a stubbed Home Assistant instance and config entry."""

    hass = HomeAssistant()

    def _update_entry(entry: ConfigEntry, *, options: dict[str, Any] | None = None) -> None:
        if options is not None:
            entry.options = dict(options)

    hass.config_entries.async_update_entry = _update_entry  # type: ignore[method-assign]

    entry = ConfigEntry(entry_id="entry-id", options={OPT_ADAPTER_SHARED_SECRET: "initial-token"})
    entry.data = {  # type: ignore[attr-defined]
        CONF_ADAPTER_URL: "http://adapter.local/interpret",
        CONF_QDRANT_HOST: "qdrant.local",
        CONF_QDRANT_API_KEY: "super-secret",
    }

    hass.data.setdefault(DOMAIN, {})
    return hass, entry


async def test_setup_entry_stashes_shared_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration setup should expose shared services for downstream consumers."""

    hass, entry = _build_hass_and_entry()
    assert await integration.async_setup_entry(hass, entry)

    domain_data = hass.data[DOMAIN][entry.entry_id]

    adapter_client = domain_data.get("adapter_client")
    assert adapter_client is not None
    assert getattr(adapter_client, "_shared_secret", None) == "initial-token"

    embed_texts = domain_data.get("embed_texts")
    assert callable(embed_texts)
    vectors = await embed_texts(["kitchen light", "movie scene"])
    assert len(vectors) == 2
    assert all(len(vector) == 3 for vector in vectors)
    assert all(any(component != 0.0 for component in vector) for vector in vectors)

    qdrant_upsert = domain_data.get("qdrant_upsert")
    assert callable(qdrant_upsert)
    assert await qdrant_upsert("ha_entities", []) is None

    # Coordinator should expose a catalog exporter factory via the domain data.
    catalog_provider = domain_data.get("catalog_provider")
    assert callable(catalog_provider)
    payload = await catalog_provider()
    assert isinstance(payload, CatalogPayload)

    intents_config = domain_data.get("intents_config")
    assert isinstance(intents_config, dict)
    for intent, default_config in DEFAULT_INTENTS_CONFIG.items():
        assert intent in intents_config
        merged = intents_config[intent]
        assert merged["enabled"] == default_config.get("enabled", True)
        assert merged["slots"] == default_config.get("slots", [])


async def test_conversation_setup_registers_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conversation setup should register the handler and execute intents."""

    hass, entry = _build_hass_and_entry()
    await integration.async_setup_entry(hass, entry)

    domain_data = hass.data[DOMAIN][entry.entry_id]
    telemetry = TelemetryRecorder()
    domain_data["telemetry"] = telemetry

    captured_agent: list[tuple[HomeAssistant, str, conv.EntangledHomeConversationHandler]] = []

    async def fake_set_agent(hass_obj: HomeAssistant, agent_id: str, agent: object) -> None:
        captured_agent.append((hass_obj, agent_id, agent))

    async def fake_catalog_provider() -> CatalogPayload:
        return CatalogPayload()

    domain_data["catalog_provider"] = fake_catalog_provider

    interpret_calls: list[tuple[str, CatalogPayload, dict[str, dict[str, object]]]] = []

    async def fake_interpret(
        utterance: str, catalog: CatalogPayload, *, intents: dict[str, dict[str, object]]
    ) -> InterpretResponse:
        interpret_calls.append((utterance, catalog, intents))
        return InterpretResponse(intent="turn_on", params={}, confidence=0.9)

    domain_data["adapter_client"].interpret = fake_interpret  # type: ignore[assignment]

    domain_data["intents_config"] = {
        "turn_on": {"enabled": True, "slots": ["area", "targets"], "threshold": 0.65},
        "turn_off": {"enabled": False, "slots": ["area"]},
    }

    execute_calls: list[tuple[HomeAssistant, InterpretResponse, CatalogPayload]] = []

    async def fake_execute(
        hass_obj: HomeAssistant,
        response: InterpretResponse,
        *,
        catalog: CatalogPayload,
        **kwargs: object,
    ) -> None:
        execute_calls.append((hass_obj, response, catalog))

    monkeypatch.setattr(conv.conversation_domain, "async_set_agent", fake_set_agent)
    monkeypatch.setattr(conv, "async_execute_intent", fake_execute)

    assert await conv.async_setup_entry(hass, entry)

    assert captured_agent and captured_agent[0][1] == DOMAIN
    handler = captured_agent[0][2]
    result = await handler.async_handle("turn on the lights")
    assert result.success is True
    assert interpret_calls and interpret_calls[0][0] == "turn on the lights"
    assert execute_calls and execute_calls[0][2] is interpret_calls[0][1]
    intents_payload = interpret_calls[0][2]
    assert intents_payload == {"turn_on": {"slots": ["area", "targets"], "threshold": 0.65}}
    assert getattr(domain_data["adapter_client"], "_shared_secret") == "initial-token"


async def test_setup_entry_normalizes_intent_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Intents config should merge defaults and normalize overrides."""

    hass, entry = _build_hass_and_entry()
    entry.options[OPT_INTENTS_CONFIG] = {
        "turn_on": {"enabled": False, "slots": ["targets", "area", "area"], "threshold": "0.8"},
        "custom_intent": {"enabled": True, "slots": ["foo", "bar", "foo"], "threshold": 0.55},
    }

    assert await integration.async_setup_entry(hass, entry)

    intents_config = hass.data[DOMAIN][entry.entry_id]["intents_config"]
    assert intents_config["turn_on"]["enabled"] is False
    assert intents_config["turn_on"]["slots"] == DEFAULT_INTENTS_CONFIG["turn_on"]["slots"]
    assert intents_config["turn_on"]["threshold"] == pytest.approx(0.8)

    custom = intents_config["custom_intent"]
    assert custom["enabled"] is True
    assert custom["slots"] == ["foo", "bar"]
    assert custom["threshold"] == pytest.approx(0.55)


async def test_conversation_unload_removes_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Teardown should unregister the conversation agent."""

    hass, entry = _build_hass_and_entry()
    await integration.async_setup_entry(hass, entry)

    domain_data = hass.data[DOMAIN][entry.entry_id]
    domain_data["telemetry"] = TelemetryRecorder()

    async def fake_catalog_provider() -> CatalogPayload:
        return CatalogPayload()

    domain_data["catalog_provider"] = fake_catalog_provider

    async def noop_set_agent(*_: object, **__: object) -> None:
        return None

    async def capture_unset(_: HomeAssistant, agent_id: str) -> None:
        called.append(agent_id)

    called: list[str] = []

    monkeypatch.setattr(conv.conversation_domain, "async_set_agent", noop_set_agent)
    monkeypatch.setattr(conv.conversation_domain, "async_unset_agent", capture_unset)

    await conv.async_setup_entry(hass, entry)

    assert await conv.async_unload_entry(hass, entry)
    assert called == [DOMAIN]
