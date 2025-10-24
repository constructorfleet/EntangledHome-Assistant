"""Data update coordinator for EntangledHome."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Mapping, Sequence, TypeVar, Type

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .models import CatalogArea, CatalogEntity, CatalogPayload, CatalogScene, PlexMediaItem

_LOGGER = logging.getLogger(__name__)


class EntangledHomeCoordinator(DataUpdateCoordinator[None]):
    """Trivial coordinator placeholder for configuration updates."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="EntangledHome Coordinator",
            update_interval=timedelta(minutes=5),
        )
        self.config_entry = entry

    async def _async_update_data(self) -> None:
        """Perform a no-op refresh for now."""
        return None


def build_catalog_payload(
    *,
    areas: Sequence[CatalogArea | Mapping[str, object]],
    entities: Sequence[CatalogEntity | Mapping[str, object]],
    scenes: Sequence[CatalogScene | Mapping[str, object]],
    plex_media: Sequence[PlexMediaItem | Mapping[str, object]],
) -> CatalogPayload:
    """Construct a :class:`CatalogPayload` from raw registry inputs."""

    area_models = [_coerce_catalog_item(CatalogArea, area) for area in areas]
    entity_models = [_coerce_catalog_item(CatalogEntity, entity) for entity in entities]
    scene_models = [_coerce_catalog_item(CatalogScene, scene) for scene in scenes]
    plex_models = [_coerce_catalog_item(PlexMediaItem, item) for item in plex_media]

    return CatalogPayload(
        areas=list(area_models),
        entities=list(entity_models),
        scenes=list(scene_models),
        plex_media=list(plex_models),
    )


ModelT = TypeVar("ModelT", CatalogArea, CatalogEntity, CatalogScene, PlexMediaItem)


def _coerce_catalog_item(model: Type[ModelT], item: ModelT | Mapping[str, object]) -> ModelT:
    """Return ``item`` as an instance of ``model``."""

    if isinstance(item, model):
        return item

    if isinstance(item, Mapping):
        return model.model_validate(item)

    raise TypeError(f"Unsupported catalog item type: {type(item)!r}")


def serialize_catalog_for_qdrant(payload: CatalogPayload | Mapping[str, object]) -> dict[str, list[dict]]:
    """Validate and serialize catalog data before Qdrant upserts."""

    if isinstance(payload, CatalogPayload):
        model = payload
    else:
        model = CatalogPayload.model_validate(payload)

    return model.model_dump(mode="json")
