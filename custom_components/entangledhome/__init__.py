"""Home Assistant integration setup for EntangledHome."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADAPTER_URL,
    DATA_TELEMETRY,
    DEFAULT_OPTION_VALUES,
    DOMAIN,
    OPT_ADAPTER_SHARED_SECRET,
)
if TYPE_CHECKING:
    from .adapter_client import AdapterClient
    from .coordinator import EntangledHomeCoordinator
    from .models import CatalogPayload

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EntangledHome from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    from .coordinator import EntangledHomeCoordinator
    from .telemetry import TelemetryRecorder

    domain_entry: dict[str, Any] = {}
    coordinator = EntangledHomeCoordinator(hass, entry)
    telemetry = TelemetryRecorder()
    adapter_client = _build_adapter_client(entry)

    domain_entry["coordinator"] = coordinator
    domain_entry[DATA_TELEMETRY] = telemetry
    domain_entry["adapter_client"] = adapter_client
    domain_entry["embed_texts"] = _build_embedder()
    domain_entry["qdrant_upsert"] = _build_qdrant_upsert()
    domain_entry["catalog_provider"] = _build_catalog_provider(coordinator)

    hass.data[DOMAIN][entry.entry_id] = domain_entry

    await coordinator.async_config_entry_first_refresh()

    _ensure_default_options(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update to refresh the coordinator."""
    coordinator = _get_coordinator(hass, entry.entry_id)
    if coordinator is not None:
        await coordinator.async_request_refresh()


def _ensure_default_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ensure options have defaults populated."""
    options: dict[str, Any] = dict(entry.options)
    updated = False

    for option_key, default_value in DEFAULT_OPTION_VALUES:
        if option_key not in options:
            options[option_key] = default_value
            updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, options=options)


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> EntangledHomeCoordinator | None:
    domain_data = hass.data.get(DOMAIN, {})
    stored = domain_data.get(entry_id)
    if not stored:
        return None
    return stored.get("coordinator")


def _build_adapter_client(entry: ConfigEntry) -> AdapterClient:
    from .adapter_client import AdapterClient

    data = getattr(entry, "data", {}) or {}
    options = getattr(entry, "options", {}) or {}

    endpoint = data.get(CONF_ADAPTER_URL) or ""
    shared_secret = options.get(OPT_ADAPTER_SHARED_SECRET)

    client = AdapterClient(endpoint)
    if shared_secret:
        client.set_shared_secret(shared_secret)
    return client


def _build_embedder() -> Callable[[list[str]], Awaitable[list[list[float]]]]:
    async def _embed(texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    return _embed


def _build_qdrant_upsert() -> Callable[[str, list[dict[str, Any]]], Awaitable[None]]:
    async def _upsert(_: str, __: list[dict[str, Any]]) -> None:
        return None

    return _upsert


def _build_catalog_provider(
    coordinator: EntangledHomeCoordinator,
) -> Callable[[], Awaitable[CatalogPayload]]:
    async def _provider() -> CatalogPayload:
        exporter = coordinator._build_exporter(getattr(coordinator.config_entry, "options", {}))
        return await exporter.run_once()

    return _provider
