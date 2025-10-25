"""FastAPI application exposing the adapter interpret endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Final, Mapping, Sequence

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette import status

from .embeddings import EmbeddingService
from .model import ModelClient
from .schema import CatalogPayload, InterpretRequest, InterpretResponse

SIGNATURE_HEADER = "X-Entangled-Signature"


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


def _parse_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _load_settings() -> Settings:
    """Load adapter configuration from environment variables."""

    return Settings(
        model=os.getenv("ADAPTER_MODEL"),
        qdrant_host=os.getenv("QDRANT_HOST"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        confidence_threshold=_parse_float(os.getenv("CONFIDENCE_THRESHOLD"), 0.75),
        model_timeout_s=_parse_float(os.getenv("MODEL_TIMEOUT_S"), 1.5),
        qdrant_timeout_s=_parse_float(os.getenv("QDRANT_TIMEOUT_S"), 0.4),
        adapter_timeout_s=_parse_float(os.getenv("ADAPTER_TIMEOUT_S"), 2.0),
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
        "areas": [area.model_dump(exclude_none=True) for area in catalog.areas],
        "entities": [entity.model_dump(exclude_none=True) for entity in catalog.entities],
        "scenes": [scene.model_dump(exclude_none=True) for scene in catalog.scenes],
        "plex_media": [item.model_dump(exclude_none=True) for item in catalog.plex_media],
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
    )


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

    async def stream(
        self,
        utterance: str,
        catalog_slice: dict,
        intents: Mapping[str, Mapping[str, Any]] | None,
        settings: Settings,
    ) -> AsyncIterator[InterpretResponse]:
        try:
            vector = await self._embed_utterance(utterance)
            retrieved = await self._retrieve_catalog(vector)
            prompt = {
                "utterance": utterance,
                "catalog": catalog_slice,
                "retrieved": retrieved,
                "intents": _serialize_intents(intents),
            }
            async for response in self._model.stream(
                utterance=utterance,
                prompt=prompt,
                threshold=settings.confidence_threshold,
            ):
                yield response
        except Exception:
            return

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
            payload[collection] = result
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

    overall_start = _now()
    stream_start: float | None = None
    latest_response: InterpretResponse | None = None

    async for chunk in _MODEL_STREAMER.stream(
        payload.utterance,
        catalog_slice,
        payload.intents,
        SETTINGS,
    ):
        if stream_start is None:
            stream_start = _now()
        latest_response = chunk
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

    return latest_response


def _enforce_signature(body: bytes, provided: str | None) -> None:
    secret = SETTINGS.shared_secret or ""
    if not secret:
        return
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature"
        )
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )
