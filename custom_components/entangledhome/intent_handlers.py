"""Intent execution helpers for EntangledHome."""

from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import re
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

from homeassistant.core import HomeAssistant

from .helpers.color_maps import COLOR_HS
from .models import CatalogArea, CatalogEntity, CatalogPayload, CatalogScene, InterpretResponse

__all__ = [
    "EXECUTORS",
    "IntentHandlingError",
    "async_execute_intent",
    "render_sensor_report",
    "resolve_scene_entity_id",
]

CONFIDENCE_THRESHOLD = 0.6
DEFAULT_UNKNOWN_REASON = "Unknown intent failure"
DEFAULT_SENSOR_AREA = "General"

IntentExecutor = Callable[
    [
        HomeAssistant,
        InterpretResponse,
        Mapping[str, Any] | None,
        CatalogPayload,
    ],
    Awaitable[None] | None,
]


class IntentHandlingError(RuntimeError):
    """Raised when an interpreted intent cannot be executed."""


async def async_execute_intent(
    hass: HomeAssistant,
    response: InterpretResponse,
    *,
    catalog: CatalogPayload,
    intent_config: Mapping[str, Any] | None = None,
) -> None:
    """Execute the interpreted intent via Home Assistant services."""

    intent_name = response.intent
    confidence = response.confidence
    params = dict(response.params)

    if confidence < CONFIDENCE_THRESHOLD:
        raise IntentHandlingError(params.get("reason") or "Low confidence")

    handler = EXECUTORS.get(intent_name)
    if handler is None:
        raise IntentHandlingError(f"No executor registered for intent '{intent_name}'")

    if _intent_disabled(intent_config):
        raise IntentHandlingError(f"Intent '{intent_name}' is disabled")

    result = handler(hass, response, intent_config, catalog)
    if result is not None:
        await result


async def _handle_set_light_color(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    color_candidates = ["color", "hs_color", *_unique(resolver.slot_candidates("color", "hs"))]
    color_raw = resolver.value(*color_candidates)
    data: dict[str, Any] = {}
    if isinstance(color_raw, str):
        mapped = COLOR_HS.get(color_raw.lower())
        data["hs_color"] = mapped or COLOR_HS.get("warm", [35, 60])
    elif isinstance(color_raw, Sequence):
        data["hs_color"] = list(color_raw)

    target = _resolve_service_target(response, resolver)
    await _async_call_service(hass, "light", "turn_on", data, target=target)


async def _handle_turn_on(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    target = _resolve_service_target(response, resolver)
    await _async_call_service(hass, "homeassistant", "turn_on", {}, target=target)


async def _handle_turn_off(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    target = _resolve_service_target(response, resolver)
    await _async_call_service(hass, "homeassistant", "turn_off", {}, target=target)


async def _handle_set_brightness(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    brightness_candidates = [
        "brightness",
        "brightness_pct",
        "level",
        *resolver.slot_candidates("bright", "level"),
    ]
    brightness = resolver.value(*brightness_candidates)
    brightness_pct = _coerce_percentage(brightness)
    if brightness_pct is None:
        raise IntentHandlingError("Missing brightness")

    target = _resolve_service_target(response, resolver)
    await _async_call_service(
        hass,
        "light",
        "turn_on",
        {"brightness_pct": brightness_pct},
        target=target,
    )


async def _handle_scene_activate(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    scene_candidates = [
        "scene",
        "scene_name",
        "scene_id",
        *resolver.slot_candidates("scene"),
    ]
    scene_name = resolver.value(*scene_candidates)
    if not scene_name:
        raise IntentHandlingError("Missing scene")
    entity_id = resolve_scene_entity_id(str(scene_name), catalog)
    if entity_id is None:
        raise IntentHandlingError(f"Unknown scene: {scene_name}")
    await _async_call_service(hass, "scene", "turn_on", {"entity_id": entity_id})


async def _handle_report_sensor(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    sensor_ids = _resolve_targets(response, resolver)
    if not sensor_ids:
        sensor_candidates = ["sensors", "sensor", *resolver.slot_candidates("sensor")]
        sensor_ids = _coerce_str_list(resolver.value(*sensor_candidates))
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


async def _handle_media_play(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    target = _resolve_service_target(response, resolver)
    await _async_call_service(hass, "media_player", "media_play", {}, target=target)


async def _handle_media_pause(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    target = _resolve_service_target(response, resolver)
    await _async_call_service(hass, "media_player", "media_pause", {}, target=target)


async def _handle_play_title(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    rating_key_candidates = [
        "rating_key",
        "media_id",
        "mediaId",
        "id",
        *resolver.slot_candidates("rating", "media_id", "media"),
    ]
    rating_key = resolver.value(*rating_key_candidates)
    server_candidates = [
        "server",
        "server_name",
        "plex_server",
        *resolver.slot_candidates("server"),
    ]
    server = resolver.value(*server_candidates)
    media_type_candidates = [
        "media_type",
        "media",
        "type",
        *resolver.slot_candidates("media", "type"),
    ]
    media_type = resolver.value(*media_type_candidates) or "plex"
    if not rating_key:
        raise IntentHandlingError("Missing rating_key for play_title")
    if not server:
        raise IntentHandlingError("Missing server for play_title")

    data = {
        "media_content_type": str(media_type),
        "media_content_id": str(rating_key),
        "extra": {
            "plex_server": str(server),
            "plex_rating_key": str(rating_key),
        },
    }
    shuffle = resolver.value("shuffle", "plex_shuffle", *resolver.slot_candidates("shuffle"))
    if shuffle is not None:
        data["extra"]["plex_shuffle"] = bool(shuffle)

    target = _resolve_service_target(response, resolver)
    await _async_call_service(
        hass,
        "media_player",
        "play_media",
        data,
        target=target,
    )


async def _handle_noop(
    hass: HomeAssistant,
    response: InterpretResponse,
    intent_config: Mapping[str, Any] | None,
    catalog: CatalogPayload,
) -> None:
    resolver = _SlotResolver(response, intent_config)
    reason = resolver.value("reason")
    raise IntentHandlingError(reason or DEFAULT_UNKNOWN_REASON)


EXECUTORS: dict[str, IntentExecutor] = {
    "set_light_color": _handle_set_light_color,
    "turn_on": _handle_turn_on,
    "turn_off": _handle_turn_off,
    "set_brightness": _handle_set_brightness,
    "scene_activate": _handle_scene_activate,
    "report_sensor": _handle_report_sensor,
    "media_play": _handle_media_play,
    "media_pause": _handle_media_pause,
    "play_title": _handle_play_title,
    "noop": _handle_noop,
}


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


def _intent_disabled(intent_config: Mapping[str, Any] | None) -> bool:
    if not isinstance(intent_config, Mapping):
        return False
    if intent_config.get("disabled"):
        return True
    if "enabled" in intent_config and not intent_config.get("enabled", True):
        return True
    return False


class _SlotResolver:
    """Helper that resolves parameter values using slot metadata."""

    __slots__ = ("_params", "_slots")

    def __init__(
        self, response: InterpretResponse, intent_config: Mapping[str, Any] | None
    ) -> None:
        params = getattr(response, "params", {}) or {}
        self._params: dict[str, Any] = dict(params) if isinstance(params, Mapping) else {}
        self._slots: tuple[str, ...] = tuple(_coerce_slots(intent_config))

    def value(self, *preferred: str, default: Any | None = None) -> Any | None:
        for key in self._ordered(preferred):
            if key in self._params:
                value = self._params[key]
                if value is not None:
                    return value
        return default

    def slot_candidates(self, *fragments: str) -> list[str]:
        if not fragments:
            return list(self._slots)
        lowered = [fragment.lower() for fragment in fragments if fragment]
        matches: list[str] = []
        for slot in self._slots:
            slot_lower = slot.lower()
            if any(fragment in slot_lower for fragment in lowered):
                matches.append(slot)
        return matches

    def _ordered(self, preferred: Sequence[str]) -> Iterable[str]:
        seen: set[str] = set()
        for key in preferred:
            normalized = str(key).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                yield normalized


def _resolve_area(response: InterpretResponse, resolver: _SlotResolver) -> str | None:
    if response.area:
        return response.area
    preferred = [
        "area",
        "area_id",
        "area_name",
        "room",
        "location",
    ]
    area = resolver.value(*preferred)
    if area:
        return str(area)
    for slot in resolver.slot_candidates("area", "room", "location"):
        value = resolver.value(slot)
        if value:
            return str(value)
    return None


def _resolve_targets(response: InterpretResponse, resolver: _SlotResolver) -> list[str] | None:
    if response.targets:
        return list(response.targets)
    candidates = [
        "targets",
        "entities",
        "entity_id",
    ]
    candidates.extend(resolver.slot_candidates("target", "entity"))
    value = resolver.value(*candidates)
    return _coerce_str_list(value)


def _resolve_service_target(
    response: InterpretResponse, resolver: _SlotResolver
) -> dict[str, Any] | None:
    return _build_service_target(
        _resolve_area(response, resolver),
        _resolve_targets(response, resolver),
    )


def _coerce_slots(intent_config: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(intent_config, Mapping):
        return []
    raw = intent_config.get("slots")
    candidates: list[str]
    if isinstance(raw, str):
        candidates = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, Mapping):
        candidates = [str(value).strip() for value in raw.values()]
    else:
        try:
            candidates = [str(value).strip() for value in raw or ()]
        except TypeError:
            candidates = []
    return [slot for slot in candidates if slot]


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, Mapping):
        return _coerce_str_list(list(value.values()))
    if isinstance(value, Sequence):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    text = str(value).strip()
    return [text] if text else []


def _coerce_percentage(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return 0
    if number > 100:
        return 100
    return int(round(number))


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_values.append(normalized)
    return unique_values


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
