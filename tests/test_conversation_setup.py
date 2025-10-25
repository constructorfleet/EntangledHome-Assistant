"""Integration-style tests for conversation setup and teardown."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import custom_components.entangledhome as integration
from custom_components.entangledhome import conversation as conv
from custom_components.entangledhome.const import (
    CONF_ADAPTER_URL,
    CONF_QDRANT_API_KEY,
    CONF_QDRANT_HOST,
    DOMAIN,
    OPT_ADAPTER_SHARED_SECRET,
)
from custom_components.entangledhome.models import CatalogPayload, InterpretResponse
from custom_components.entangledhome.telemetry import TelemetryRecorder

from tests.stubs.homeassistant.config_entries import ConfigEntry
from tests.stubs.homeassistant.core import HomeAssistant


pytestmark = pytest.mark.asyncio


def _build_hass_and_entry() -> tuple[HomeAssistant, ConfigEntry]:
    """Return a stubbed Home Assistant instance and config entry."""

    hass = HomeAssistant()
    hass.config_entries = SimpleNamespace(
        async_update_entry=lambda entry, options: entry.__setattr__("options", options)
    )

    entry = ConfigEntry(
        entry_id="entry-id",
        data={
            CONF_ADAPTER_URL: "http://adapter.local/interpret",
            CONF_QDRANT_HOST: "qdrant.local",
            CONF_QDRANT_API_KEY: "super-secret",
        },
        options={OPT_ADAPTER_SHARED_SECRET: "initial-token"},
    )

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
    assert vectors == [[0.0], [0.0]]

    qdrant_upsert = domain_data.get("qdrant_upsert")
    assert callable(qdrant_upsert)
    assert await qdrant_upsert("ha_entities", []) is None

    # Coordinator should expose a catalog exporter factory via the domain data.
    catalog_provider = domain_data.get("catalog_provider")
    assert callable(catalog_provider)
    payload = await catalog_provider()
    assert isinstance(payload, CatalogPayload)


async def test_conversation_setup_registers_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conversation setup should register the handler and execute intents."""

    hass, entry = _build_hass_and_entry()
    await integration.async_setup_entry(hass, entry)

    domain_data = hass.data[DOMAIN][entry.entry_id]
    telemetry = TelemetryRecorder()
    domain_data["telemetry"] = telemetry

    captured_agent: list[tuple[HomeAssistant, str, object]] = []

    async def fake_set_agent(hass_obj: HomeAssistant, agent_id: str, agent: object) -> None:
        captured_agent.append((hass_obj, agent_id, agent))

    async def fake_catalog_provider() -> CatalogPayload:
        return CatalogPayload()

    domain_data["catalog_provider"] = fake_catalog_provider

    interpret_calls: list[tuple[str, CatalogPayload]] = []

    async def fake_interpret(utterance: str, catalog: CatalogPayload) -> InterpretResponse:
        interpret_calls.append((utterance, catalog))
        return InterpretResponse(intent="turn_on", params={}, confidence=0.9)

    domain_data["adapter_client"].interpret = fake_interpret  # type: ignore[assignment]

    execute_calls: list[tuple[HomeAssistant, InterpretResponse, CatalogPayload]] = []

    async def fake_execute(
        hass_obj: HomeAssistant, response: InterpretResponse, *, catalog: CatalogPayload
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
    assert getattr(domain_data["adapter_client"], "_shared_secret") == "initial-token"


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
