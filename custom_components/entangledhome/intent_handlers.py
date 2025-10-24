"""Intent execution helpers for EntangledHome."""

from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import re
from typing import Any, Iterable, Mapping, Sequence

from homeassistant.core import HomeAssistant

from .helpers.color_maps import COLOR_HS
from .models import CatalogArea, CatalogEntity, CatalogPayload, CatalogScene, InterpretResponse

__all__ = [
    "IntentHandlingError",
    "async_execute_intent",
    "render_sensor_report",
    "resolve_scene_entity_id",
]

CONFIDENCE_THRESHOLD = 0.6
DEFAULT_UNKNOWN_REASON = "Unknown intent failure"
DEFAULT_SENSOR_AREA = "General"


class IntentHandlingError(RuntimeError):
    """Raised when an interpreted intent cannot be executed."""


async def async_execute_intent(
    hass: HomeAssistant,
    response: InterpretResponse,
    *,
    catalog: CatalogPayload,
) -> None:
    """Execute the interpreted intent via Home Assistant services."""

    intent_name = response.intent
    confidence = response.confidence
    area = response.area
    targets = response.targets
    params = dict(response.params)

    if confidence < CONFIDENCE_THRESHOLD:
        raise IntentHandlingError(params.get("reason") or "Low confidence")

    target = _build_service_target(area, targets)

    if intent_name == "set_light_color":
        color = params.get("color")
        data: dict[str, Any] = {}
        if color:
            mapped = COLOR_HS.get(color.lower())
            data["hs_color"] = mapped or COLOR_HS.get("warm", [35, 60])
        await _async_call_service(hass, "light", "turn_on", data, target=target)

    elif intent_name == "turn_on":
        await _async_call_service(hass, "homeassistant", "turn_on", {}, target=target)

    elif intent_name == "turn_off":
        await _async_call_service(hass, "homeassistant", "turn_off", {}, target=target)

    elif intent_name == "set_brightness":
        brightness = params.get("brightness")
        if brightness is None:
            raise IntentHandlingError("Missing brightness")
        await _async_call_service(
            hass,
            "light",
            "turn_on",
            {"brightness_pct": brightness},
            target=target,
        )

    elif intent_name == "scene_activate":
        scene_name = params.get("scene")
        if not scene_name:
            raise IntentHandlingError("Missing scene")
        entity_id = resolve_scene_entity_id(scene_name, catalog)
        if entity_id is None:
            raise IntentHandlingError(f"Unknown scene: {scene_name}")
        await _async_call_service(hass, "scene", "turn_on", {"entity_id": entity_id})

    elif intent_name == "report_sensor":
        sensor_ids = list(targets or params.get("sensors", []))
        if not sensor_ids:
            raise IntentHandlingError("No sensors provided")
        summary = render_sensor_report(hass, sensor_ids, catalog)
        if not summary:
            raise IntentHandlingError("Unable to summarize sensors")
        await _async_call_service(
            hass,
            "conversation",
            "process",
            {"text": summary},
        )

    elif intent_name == "media_play":
        await _async_call_service(hass, "media_player", "media_play", {}, target=target)

    elif intent_name == "media_pause":
        await _async_call_service(hass, "media_player", "media_pause", {}, target=target)

    elif intent_name == "play_title":
        rating_key = params.get("rating_key") or params.get("media_id")
        server = params.get("server") or params.get("server_name")
        media_type = params.get("media_type") or params.get("type") or "plex"
        if not rating_key:
            raise IntentHandlingError("Missing rating_key for play_title")
        if not server:
            raise IntentHandlingError("Missing server for play_title")

        data = {
            "media_content_type": media_type,
            "media_content_id": str(rating_key),
            "extra": {
                "plex_server": server,
                "plex_rating_key": str(rating_key),
            },
        }
        if "shuffle" in params:
            data["extra"]["plex_shuffle"] = bool(params["shuffle"])
        await _async_call_service(
            hass,
            "media_player",
            "play_media",
            data,
            target=target,
        )

    elif intent_name == "noop":
        raise IntentHandlingError(params.get("reason") or DEFAULT_UNKNOWN_REASON)

    else:
        raise IntentHandlingError(f"Unknown intent: {intent_name}")


def resolve_scene_entity_id(
    name: str,
    catalog: CatalogPayload | Sequence[CatalogScene],
) -> str | None:
    """Resolve ``name`` to a scene entity_id using fuzzy matching and aliases."""

    scenes: Sequence[CatalogScene]
    if isinstance(catalog, CatalogPayload):
        scenes = catalog.scenes
    else:
        scenes = catalog

    if not scenes:
        return None

    target_norm = _normalize_text(name)
    best_score = 0.0
    best_match: str | None = None

    for scene in scenes:
        for candidate in _iter_scene_candidates(scene):
            candidate_norm = _normalize_text(candidate)
            if not candidate_norm:
                continue
            if candidate_norm == target_norm:
                return scene.entity_id
            score = SequenceMatcher(None, target_norm, candidate_norm).ratio()
            if score > best_score:
                best_score = score
                best_match = scene.entity_id

    return best_match if best_score >= 0.6 else None


def render_sensor_report(
    hass: HomeAssistant,
    sensor_ids: Sequence[str],
    catalog: CatalogPayload,
) -> str:
    """Render a spoken summary for sensors grouped by area."""

    area_lookup = _build_area_lookup(catalog.areas)
    entity_lookup = {entity.entity_id: entity for entity in catalog.entities}
    grouped: "OrderedDict[str, list[str]]" = OrderedDict()

    state_machine = getattr(hass, "states", None)
    if state_machine is None:
        def _get_state(_: str) -> Any:
            return None
    else:
        _get_state = state_machine.get  # type: ignore[assignment]

    for sensor_id in sensor_ids:
        entity = entity_lookup.get(sensor_id)
        area_name = _resolve_area_name(entity, area_lookup)

        state = _get_state(sensor_id)
        reading = _format_sensor_reading(state)
        friendly = entity.friendly_name if entity and entity.friendly_name else sensor_id

        grouped.setdefault(area_name, []).append(f"{friendly} is {reading}")

    lines = [f"{area}: {', '.join(readings)}" for area, readings in grouped.items()]
    return "\n".join(lines)


async def _async_call_service(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: Mapping[str, Any],
    *,
    target: Mapping[str, Any] | None = None,
) -> None:
    """Invoke ``hass.services.async_call`` with common defaults."""

    kwargs: dict[str, Any] = {"blocking": True}
    if target:
        kwargs["target"] = target
    payload = data if isinstance(data, dict) else dict(data)
    await hass.services.async_call(domain, service, payload, **kwargs)


def _build_service_target(
    area: str | None,
    targets: Sequence[str] | None,
) -> dict[str, Any] | None:
    target: dict[str, Any] = {}
    if area:
        target["area_id"] = area
    if targets:
        target["entity_id"] = list(targets)
    return target or None


def _iter_scene_candidates(scene: CatalogScene) -> Iterable[str]:
    for raw in (scene.name, *scene.aliases):
        value = raw.strip()
        if value:
            yield value
    entity_suffix = scene.entity_id.split(".", 1)[-1]
    yield entity_suffix
    suffix_words = entity_suffix.replace("_", " ").strip()
    if suffix_words and suffix_words != entity_suffix:
        yield suffix_words


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return normalized


def _build_area_lookup(areas: Sequence[CatalogArea]) -> dict[str, str]:
    return {area.area_id: area.name for area in areas}


def _resolve_area_name(entity: CatalogEntity | None, areas: Mapping[str, str]) -> str:
    if entity and entity.area_id and entity.area_id in areas:
        return areas[entity.area_id]
    return DEFAULT_SENSOR_AREA


def _format_sensor_reading(state: Any) -> str:
    if state is None:
        return "unavailable"
    value = state.state
    unit = getattr(state, "attributes", {}).get("unit_of_measurement")
    if unit:
        return f"{value} {unit}"
    return str(value)
