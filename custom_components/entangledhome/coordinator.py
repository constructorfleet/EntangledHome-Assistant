"""Data update coordinator for EntangledHome."""

from __future__ import annotations

from datetime import timedelta
import asyncio
import logging
from typing import Any, Mapping, Sequence

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DEFAULT_CATALOG_SYNC,
    DEFAULT_PLEX_SYNC,
    DEFAULT_REFRESH_INTERVAL_MINUTES,
    DOMAIN,
    OPT_ENABLE_CATALOG_SYNC,
    OPT_ENABLE_PLEX_SYNC,
    OPT_REFRESH_INTERVAL_MINUTES,
)
from .catalog import build_catalog_payload, serialize_catalog_for_qdrant
from .exporter import CatalogExporter

_LOGGER = logging.getLogger(__name__)


class EntangledHomeCoordinator(DataUpdateCoordinator[None]):
    """Trivial coordinator placeholder for configuration updates."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        refresh_minutes = entry.options.get(
            OPT_REFRESH_INTERVAL_MINUTES, DEFAULT_REFRESH_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name="EntangledHome Coordinator",
            update_interval=timedelta(minutes=refresh_minutes),
        )
        self.config_entry = entry

    async def _async_update_data(self) -> None:
        """Perform a no-op refresh for now."""
        options: Mapping[str, Any] = getattr(self.config_entry, "options", {})

        refresh_minutes = options.get(
            OPT_REFRESH_INTERVAL_MINUTES, DEFAULT_REFRESH_INTERVAL_MINUTES
        )
        self.update_interval = timedelta(minutes=refresh_minutes)

        if not options.get(OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC):
            return None

        exporter = self._build_exporter(options)
        await exporter.run_once()
        return None

    def _build_exporter(self, options: Mapping[str, Any]) -> CatalogExporter:
        enable_plex = options.get(OPT_ENABLE_PLEX_SYNC, DEFAULT_PLEX_SYNC)

        return CatalogExporter(
            hass=self.hass,
            embed_texts=self._embed_texts,
            upsert_points=self._upsert_points,
            metrics_logger=self._log_metrics,
            area_source=self._collect_area_descriptions,
            entity_source=self._collect_entity_descriptions,
            scene_source=self._collect_scene_descriptions,
            plex_source=self._collect_plex_media,
            enable_plex_sync=enable_plex,
        )

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        provider = self._domain_data().get("embed_texts")
        if provider is None:
            return [[0.0] * 1 for _ in texts]
        result = provider(texts)
        if asyncio.iscoroutine(result):
            return await result
        return list(result)

    async def _upsert_points(self, collection: str, points: list[dict[str, Any]]) -> None:
        client = self._domain_data().get("qdrant_upsert")
        if client is None:
            return
        result = client(collection, points)
        if asyncio.iscoroutine(result):
            await result

    def _log_metrics(self, event: str, **fields: Any) -> None:
        self.logger.debug("%s", event, extra={"catalog_metrics": fields})

    def _collect_area_descriptions(self) -> Sequence[Mapping[str, Any]]:
        try:
            from homeassistant.helpers import area_registry as ar  # type: ignore
        except ImportError:  # pragma: no cover - runtime environment only
            return []

        registry = getattr(ar, "async_get", None)
        if registry is None:
            return []
        area_registry = registry(self.hass)
        areas = getattr(area_registry, "areas", {})
        return [
            {
                "area_id": area.id,
                "name": area.name,
                "aliases": sorted(getattr(area, "aliases", []) or []),
            }
            for area in getattr(areas, "values", lambda: [])()
        ]

    def _collect_entity_descriptions(self) -> Sequence[Mapping[str, Any]]:
        try:
            from homeassistant.helpers import entity_registry as er  # type: ignore
        except ImportError:  # pragma: no cover
            return []

        registry = getattr(er, "async_get", None)
        if registry is None:
            return []
        entity_registry = registry(self.hass)
        entities = getattr(entity_registry, "entities", {})
        descriptions: list[dict[str, Any]] = []
        for entry in getattr(entities, "values", lambda: [])():
            domain = getattr(entry, "domain", None)
            entity_id = getattr(entry, "entity_id", None)
            if domain is None and isinstance(entity_id, str):
                domain = entity_id.split(".", 1)[0]
            data = {
                "entity_id": entity_id,
                "domain": domain,
                "area_id": getattr(entry, "area_id", None),
                "device_id": getattr(entry, "device_id", None),
                "friendly_name": getattr(entry, "original_name", None),
                "aliases": sorted(getattr(entry, "aliases", []) or []),
                "capabilities": getattr(entry, "capabilities", {}) or {},
            }
            descriptions.append({k: v for k, v in data.items() if v not in (None, [], {})})
        return descriptions

    def _collect_scene_descriptions(self) -> Sequence[Mapping[str, Any]]:
        scenes: list[dict[str, Any]] = []
        for entity in self._collect_entity_descriptions():
            if entity.get("domain") == "scene":
                scenes.append(
                    {
                        "entity_id": entity["entity_id"],
                        "name": entity.get("friendly_name", entity["entity_id"]),
                        "aliases": entity.get("aliases", []),
                    }
                )
        return scenes

    async def _collect_plex_media(self) -> Sequence[Mapping[str, Any]]:
        client = self._domain_data().get("plex_client")
        if client is None:
            return []

        fetcher = getattr(client, "async_get_catalog", None)
        if callable(fetcher):
            result = fetcher()
            if asyncio.iscoroutine(result):
                return list(await result)
            return list(result)
        fetcher = getattr(client, "get_catalog", None)
        if callable(fetcher):
            return list(fetcher())
        return []

    def _domain_data(self) -> dict[str, Any]:
        stored = self.hass.data.get(DOMAIN)
        return stored if isinstance(stored, dict) else {}
