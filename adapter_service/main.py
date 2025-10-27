"""FastAPI application exposing the adapter interpret endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Final, Mapping, Sequence

import httpx
from fastapi import FastAPI, HTTPException, Request
from jsonschema import Draft7Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError
from starlette import status

from .embeddings import EmbeddingService
from .model import ModelClient
from .schema import CatalogPayload, InterpretRequest, InterpretResponse

SIGNATURE_HEADER = "X-Entangled-Signature"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """Adapter configuration derived from environment variables."""

    model: str | None
    qdrant_host: str | None
    qdrant_api_key: str | None
    confidence_threshold: float
    model_timeout_s: float
    qdrant_timeout_s: float
    adapter_timeout_s: float
    catalog_cache_size: int
    shared_secret: str | None


def _parse_float(value: str | None, default: float, *, minimum: float | None = None) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if minimum is not None and parsed <= minimum:
        return default
    return parsed


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _parse_timeout(value: str | None, default: float) -> float:
    return _parse_float(value, default, minimum=0.0)


def _load_settings() -> Settings:
    """Load adapter configuration from environment variables."""

    return Settings(
        model=os.getenv("ADAPTER_MODEL"),
        qdrant_host=os.getenv("QDRANT_HOST"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        confidence_threshold=_parse_float(os.getenv("CONFIDENCE_THRESHOLD"), 0.75),
        model_timeout_s=_parse_timeout(os.getenv("MODEL_TIMEOUT_S"), 1.5),
        qdrant_timeout_s=_parse_timeout(os.getenv("QDRANT_TIMEOUT_S"), 0.4),
        adapter_timeout_s=_parse_timeout(os.getenv("ADAPTER_TIMEOUT_S"), 2.0),
        catalog_cache_size=_parse_int(os.getenv("CATALOG_CACHE_SIZE"), 256),
        shared_secret=os.getenv("ADAPTER_SHARED_SECRET"),
    )


def _now() -> float:
    """Obtain a monotonic timestamp for duration measurements."""

    return time.perf_counter()


def _normalize_utterance(utterance: str) -> str:
    """Normalize utterances for cache lookups."""

    return " ".join(utterance.lower().split())


def _fingerprint_catalog(catalog: CatalogPayload) -> str:
    """Derive a stable fingerprint for catalog payload caching."""

    serialized = catalog.model_dump_json()
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_catalog_slice(catalog: CatalogPayload) -> dict:
    """Produce a lightweight catalog slice for the model prompt."""

    return {
        "areas": [_filter_area(area.model_dump(exclude_none=True)) for area in catalog.areas],
        "entities": [
            _filter_entity(entity.model_dump(exclude_none=True)) for entity in catalog.entities
        ],
        "scenes": [_filter_scene(scene.model_dump(exclude_none=True)) for scene in catalog.scenes],
        "plex_media": [
            _filter_plex_item(item.model_dump(exclude_none=True)) for item in catalog.plex_media
        ],
    }


def _serialize_intents(
    intents: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Convert mapping-based intents into JSON-serializable dicts."""

    return {intent: dict(config) for intent, config in (intents or {}).items()}


def _fallback_response(utterance: str, *, reason: str) -> InterpretResponse:
    """Construct a noop response with the provided reason."""

    return InterpretResponse(
        intent="noop",
        params={"reason": reason, "utterance": utterance},
        confidence=0.0,
        adapter_error=reason,
    )


INTERPRET_RESPONSE_SCHEMA: Final[dict[str, Any]] = InterpretResponse.model_json_schema(
    mode="validation"
)
RESPONSE_VALIDATOR = Draft7Validator(INTERPRET_RESPONSE_SCHEMA)


def _extract_retrieved_ids(retrieved: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Return collection IDs from retrieved payloads for logging."""

    ids: dict[str, list[Any]] = {}
    for collection in ("ha_entities", "plex_media"):
        entries = retrieved.get(collection, []) if isinstance(retrieved, Mapping) else []
        if isinstance(entries, Sequence):
            ids[collection] = [
                item.get("id")
                for item in entries
                if isinstance(item, Mapping) and item.get("id") is not None
            ]
        else:
            ids[collection] = []
    return ids


_ENTITY_FIELDS: Final[tuple[str, ...]] = (
    "entity_id",
    "friendly_name",
    "domain",
    "area_id",
    "device_id",
    "aliases",
    "capabilities",
)
_AREA_FIELDS: Final[tuple[str, ...]] = ("area_id", "name", "aliases")
_SCENE_FIELDS: Final[tuple[str, ...]] = ("entity_id", "name", "aliases")
_PLEX_FIELDS: Final[tuple[str, ...]] = (
    "rating_key",
    "title",
    "type",
    "year",
    "collection",
    "genres",
    "actors",
    "audio_language",
    "subtitles",
)


def _filter_area(area: Mapping[str, Any]) -> dict[str, Any]:
    filtered = {key: area.get(key) for key in _AREA_FIELDS if area.get(key) is not None}
    aliases = area.get("aliases")
    if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)):
        filtered["aliases"] = [str(alias) for alias in aliases if str(alias)]
    filtered.setdefault("aliases", [])
    filtered["summary"] = _summarize_area(filtered)
    return filtered


def _filter_scene(scene: Mapping[str, Any]) -> dict[str, Any]:
    filtered = {key: scene.get(key) for key in _SCENE_FIELDS if scene.get(key) is not None}
    aliases = scene.get("aliases")
    if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)):
        filtered["aliases"] = [str(alias) for alias in aliases if str(alias)]
    filtered.setdefault("aliases", [])
    filtered["summary"] = _summarize_scene(filtered)
    return filtered


def _filter_entity(entity: Mapping[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for key in _ENTITY_FIELDS:
        value = entity.get(key)
        if value is None:
            continue
        if key == "aliases":
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                filtered[key] = [str(alias) for alias in value if str(alias)]
            continue
        if key == "capabilities":
            if isinstance(value, Mapping):
                filtered[key] = dict(value)
            continue
        filtered[key] = str(value)
    filtered.setdefault("aliases", [])
    filtered.setdefault("capabilities", {})
    filtered["summary"] = _summarize_entity(filtered)
    return filtered


def _filter_plex_item(item: Mapping[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for key in _PLEX_FIELDS:
        value = item.get(key)
        if value is None:
            continue
        if key in {"collection", "genres", "actors", "subtitles"}:
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                filtered[key] = [str(entry) for entry in value if str(entry)]
            continue
        if key == "year":
            try:
                filtered[key] = int(value)
            except (TypeError, ValueError):
                continue
            continue
        filtered[key] = str(value)
    for field in ("collection", "genres", "actors", "subtitles"):
        filtered.setdefault(field, [])
    filtered["summary"] = _summarize_plex(filtered)
    return filtered


def _summarize_area(area: Mapping[str, Any]) -> str:
    name = str(area.get("name") or area.get("area_id") or "Area")
    area_id = area.get("area_id")
    parts = [name]
    if area_id and str(area_id) != name:
        parts.append(f"({area_id})")
    summary = " ".join(parts).strip()
    aliases = area.get("aliases") or []
    if aliases:
        summary = f"{summary} • aliases: {', '.join(str(alias) for alias in aliases)}"
    return summary


def _summarize_scene(scene: Mapping[str, Any]) -> str:
    name = str(scene.get("name") or scene.get("entity_id") or "Scene")
    entity_id = scene.get("entity_id")
    parts = [name]
    if entity_id and str(entity_id) != name:
        parts.append(f"({entity_id})")
    summary = " ".join(parts).strip()
    aliases = scene.get("aliases") or []
    if aliases:
        summary = f"{summary} • aliases: {', '.join(str(alias) for alias in aliases)}"
    return summary


def _summarize_entity(entity: Mapping[str, Any]) -> str:
    name = str(entity.get("friendly_name") or entity.get("entity_id") or "Entity")
    domain = entity.get("domain")
    area = entity.get("area_id")
    aliases = entity.get("aliases") or []
    parts = [name]
    if domain:
        parts.append(f"domain:{domain}")
    if area:
        parts.append(f"area:{area}")
    if aliases:
        parts.append(f"aliases: {', '.join(str(alias) for alias in aliases)}")
    return " | ".join(parts)


def _summarize_plex(item: Mapping[str, Any]) -> str:
    title = str(item.get("title") or item.get("rating_key") or "Item")
    media_type = item.get("type")
    year = item.get("year")
    parts = [title]
    if media_type:
        parts.append(str(media_type))
    if year:
        parts.append(str(year))
    collections = item.get("collection") or []
    if collections:
        parts.append(f"collections: {', '.join(str(name) for name in collections)}")
    genres = item.get("genres") or []
    if genres:
        parts.append(f"genres: {', '.join(str(genre) for genre in genres)}")
    return " | ".join(parts)


def _normalize_retrieved(
    collection: str, items: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        payload_obj = item.get("payload")
        if not isinstance(payload_obj, Mapping):
            continue
        if collection == "ha_entities":
            filtered = _filter_entity(payload_obj)
        elif collection == "plex_media":
            filtered = _filter_plex_item(payload_obj)
        else:
            continue
        payload = dict(filtered)
        summary = str(payload.pop("summary", ""))
        normalized.append(
            {
                "id": item.get("id"),
                "score": float(item.get("score", 0.0)),
                "payload": payload,
                "summary": summary,
            }
        )
    return normalized


class CatalogSliceCache:
    """LRU cache keyed by normalized utterances and catalog fingerprints."""

    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._data: OrderedDict[tuple[str, str], dict] = OrderedDict()

    def get(self, key: str, fingerprint: str, builder: Callable[[], dict]) -> dict:
        cache_key = (key, fingerprint)
        if cache_key in self._data:
            value = self._data.pop(cache_key)
            self._data[cache_key] = value
            return value

        value = builder()
        self._data[cache_key] = value
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        self._data.clear()


class QdrantClient:
    """Thin HTTP client for querying Qdrant collections."""

    def __init__(
        self,
        *,
        host: str | None,
        api_key: str | None,
        timeout: float,
    ) -> None:
        self._host = host
        self._api_key = api_key
        self._timeout = timeout

    async def search(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        limit: int,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        if not self._host or not vector:
            return []

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key

        payload = {
            "vector": list(vector),
            "limit": limit,
            "with_payload": True,
            "with_vectors": False,
        }

        try:
            async with httpx.AsyncClient(
                base_url=self._host,
                timeout=timeout or self._timeout,
            ) as client:
                response = await client.post(
                    f"/collections/{collection}/points/search",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return []

        data = response.json()
        result = data.get("result")
        if not isinstance(result, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "id": item.get("id"),
                    "score": float(item.get("score", 0.0)),
                    "payload": item.get("payload", {}),
                }
            )
        return normalized


class StreamingModel:
    """Streaming adapter backed by embeddings, Qdrant, and a model client."""

    def __init__(
        self,
        *,
        settings: Settings,
        embedding_service: EmbeddingService | None = None,
        qdrant_client: QdrantClient | None = None,
        model_client: ModelClient | None = None,
        embedding_model: str | None = None,
        top_k: int = 32,
    ) -> None:
        self._settings = settings
        self._top_k = top_k
        self._embedding_service = embedding_service or EmbeddingService(
            model=embedding_model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        )
        self._qdrant = qdrant_client or QdrantClient(
            host=settings.qdrant_host,
            api_key=settings.qdrant_api_key,
            timeout=settings.qdrant_timeout_s,
        )
        self._model = model_client or ModelClient(
            model=settings.model or "",
            timeout=settings.model_timeout_s,
        )
        self._validator = Draft7Validator(INTERPRET_RESPONSE_SCHEMA)
        self._last_prompt: dict[str, Any] | None = None

    async def stream(
        self,
        utterance: str,
        catalog_slice: dict,
        intents: Mapping[str, Mapping[str, Any]] | None,
        settings: Settings,
    ) -> AsyncIterator[InterpretResponse]:
        self._last_prompt = None
        try:
            vector = await self._embed_utterance(utterance)
            retrieved = await self._retrieve_catalog(vector)
            prompt = {
                "utterance": utterance,
                "catalog": catalog_slice,
                "retrieved": retrieved,
                "intents": _serialize_intents(intents),
            }
            self._last_prompt = prompt
        except Exception:
            LOGGER.exception("interpret_stream_setup_failed utterance=%s", utterance)
            return

        try:
            async for candidate in self._model.stream(
                utterance=utterance,
                prompt=prompt,
                threshold=settings.confidence_threshold,
            ):
                response = await self._coerce_to_response(
                    candidate,
                    utterance=utterance,
                    prompt=prompt,
                )
                if response is None:
                    continue
                yield response
        except Exception:
            LOGGER.exception("interpret_stream_failed utterance=%s", utterance)
            return

    def describe_last_prompt(self) -> dict[str, Any] | None:
        return self._last_prompt

    async def _coerce_to_response(
        self,
        raw: Any,
        *,
        utterance: str,
        prompt: dict[str, Any],
        allow_repair: bool = True,
    ) -> InterpretResponse | None:
        if isinstance(raw, InterpretResponse):
            return raw

        if isinstance(raw, Mapping):
            data = dict(raw)
        else:
            LOGGER.warning(
                "interpret_validation_failed reason=non_mapping payload=%r",
                raw,
            )
            if allow_repair:
                return await self._attempt_repair(utterance=utterance, prompt=prompt, raw=raw)
            return None

        try:
            self._validator.validate(data)
        except ValidationError as exc:
            LOGGER.warning(
                "interpret_validation_failed reason=jsonschema error=%s payload=%s",
                exc,
                data,
            )
            if allow_repair:
                return await self._attempt_repair(utterance=utterance, prompt=prompt, raw=data)
            return None

        try:
            return InterpretResponse.model_validate(data)
        except PydanticValidationError as exc:
            LOGGER.warning(
                "interpret_validation_failed reason=pydantic error=%s payload=%s",
                exc,
                data,
            )
            if allow_repair:
                return await self._attempt_repair(utterance=utterance, prompt=prompt, raw=data)
            return None

    async def _attempt_repair(
        self,
        *,
        utterance: str,
        prompt: dict[str, Any],
        raw: Any,
    ) -> InterpretResponse | None:
        try:
            repaired = await self._model.repair(
                utterance=utterance,
                prompt=prompt,
                raw=raw,
            )
        except Exception:
            LOGGER.exception(
                "interpret_repair_failed utterance=%s payload=%r",
                utterance,
                raw,
            )
            return None

        if repaired is None:
            return None

        return await self._coerce_to_response(
            repaired,
            utterance=utterance,
            prompt=prompt,
            allow_repair=False,
        )

    async def _embed_utterance(self, utterance: str) -> list[float]:
        try:
            vectors = await self._embedding_service.embed([utterance])
        except Exception:
            return []
        if not vectors:
            return []
        return list(vectors[0])

    async def _retrieve_catalog(self, vector: Sequence[float]) -> dict[str, list[dict[str, Any]]]:
        if not vector:
            return {"ha_entities": [], "plex_media": []}

        tasks = []
        timeout = self._settings.qdrant_timeout_s
        for collection in ("ha_entities", "plex_media"):
            tasks.append(
                self._qdrant.search(
                    collection,
                    vector,
                    limit=self._top_k,
                    timeout=timeout,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        payload: dict[str, list[dict[str, Any]]] = {"ha_entities": [], "plex_media": []}
        for collection, result in zip(("ha_entities", "plex_media"), results):
            if isinstance(result, Exception):
                continue
            payload[collection] = _normalize_retrieved(collection, result)
        return payload


SETTINGS: Final[Settings] = _load_settings()
CATALOG_CACHE = CatalogSliceCache(SETTINGS.catalog_cache_size)
METRICS: dict[str, list[dict[str, float]]] = {"interpret": []}
_MODEL_STREAMER: StreamingModel = StreamingModel(settings=SETTINGS)
app = FastAPI()


def _record_metric(total_ms: float, stream_ms: float) -> None:
    """Record an interpret duration sample."""

    METRICS.setdefault("interpret", []).append(
        {
            "total_ms": total_ms,
            "stream_ms": stream_ms,
        }
    )


@app.post("/interpret", response_model=InterpretResponse)
async def interpret(request: Request, payload: InterpretRequest) -> InterpretResponse:
    """Stream model responses with caching and duration metrics."""

    if SETTINGS.shared_secret:
        body = await request.body()
        _enforce_signature(body, request.headers.get(SIGNATURE_HEADER))

    normalized = _normalize_utterance(payload.utterance)
    catalog_fingerprint = _fingerprint_catalog(payload.catalog)
    catalog_slice = CATALOG_CACHE.get(
        normalized,
        catalog_fingerprint,
        lambda: _build_catalog_slice(payload.catalog),
    )

    LOGGER.info(
        "interpret_start utterance=%s fingerprint=%s",
        payload.utterance,
        catalog_fingerprint,
    )

    overall_start = _now()
    stream_start: float | None = None
    latest_response: InterpretResponse | None = None
    chunks: list[InterpretResponse] = []

    async for chunk in _MODEL_STREAMER.stream(
        payload.utterance,
        catalog_slice,
        payload.intents,
        SETTINGS,
    ):
        if stream_start is None:
            stream_start = _now()
        latest_response = chunk
        chunks.append(chunk)
        if chunk.confidence >= SETTINGS.confidence_threshold:
            break

    end_time = _now()

    if latest_response is None:
        latest_response = _fallback_response(
            payload.utterance, reason="Adapter produced no response"
        )

    stream_duration_ms = 0.0
    if stream_start is not None:
        stream_duration_ms = max((end_time - stream_start) * 1000, 0.0)

    total_duration_ms = max((end_time - overall_start) * 1000, 0.0)
    _record_metric(total_duration_ms, stream_duration_ms)

    prompt_snapshot = _MODEL_STREAMER.describe_last_prompt() or {}
    retrieved_map = (
        prompt_snapshot.get("retrieved", {}) if isinstance(prompt_snapshot, Mapping) else {}
    )
    retrieved_ids = _extract_retrieved_ids(retrieved_map)
    chunk_payloads = [chunk.model_dump(mode="json") for chunk in chunks]
    final_payload = latest_response.model_dump(mode="json")

    LOGGER.info(
        "interpret_complete utterance=%s fingerprint=%s duration_ms=%.3f stream_ms=%.3f retrieved=%s model_chunks=%s final=%s",
        payload.utterance,
        catalog_fingerprint,
        total_duration_ms,
        stream_duration_ms,
        retrieved_ids,
        chunk_payloads,
        final_payload,
    )

    return latest_response


def _enforce_signature(body: bytes, provided: str | None) -> None:
    secret = SETTINGS.shared_secret or ""
    if not secret:
        return
    if not provided:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
