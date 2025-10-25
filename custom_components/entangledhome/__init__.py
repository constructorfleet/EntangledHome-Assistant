"""Home Assistant integration setup for EntangledHome."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable, Mapping, Sequence

import httpx

# Re-export embeddings module so patching helpers can resolve dotted paths.
from . import embeddings as embeddings  # noqa: F401

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

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EntangledHome from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    from .coordinator import EntangledHomeCoordinator
    from .secondary_signals import build_secondary_signal_provider
    from .telemetry import TelemetryRecorder

    domain_entry: dict[str, Any] = {}
    coordinator = EntangledHomeCoordinator(hass, entry)
    telemetry = TelemetryRecorder()
    adapter_client = _build_adapter_client(entry)

    domain_entry["coordinator"] = coordinator
    domain_entry[DATA_TELEMETRY] = telemetry
    domain_entry["adapter_client"] = adapter_client
    domain_entry["embed_texts"] = _build_embedder(entry)
    domain_entry["qdrant_upsert"] = _build_qdrant_upsert(entry)
    domain_entry["catalog_provider"] = _build_catalog_provider(coordinator)
    domain_entry["secondary_signal_provider"] = build_secondary_signal_provider(hass, entry)

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


def _build_embedder(entry: ConfigEntry) -> Callable[[list[str]], Awaitable[list[list[float]]]]:
    from .embeddings import EmbeddingService, EmbeddingServiceError

    options = getattr(entry, "options", {}) or {}

    model = str(
        _option_or_env(options, "embedding_model", "EMBEDDING_MODEL", "text-embedding-3-small")
    )
    cache_size = _coerce_int(
        _option_or_env(options, "embedding_cache_size", "EMBEDDING_CACHE_SIZE", 256),
        default=256,
        minimum=0,
    )

    fallback_backend = None
    if _allow_fallback_embeddings(options) and not os.getenv("OPENAI_API_KEY"):
        fallback_backend = _DeterministicEmbeddingBackend()
        _LOGGER.info(
            "OPENAI_API_KEY missing; using deterministic embedding fallback backend"
        )

    service = EmbeddingService(model=model, cache_size=cache_size, backend=fallback_backend)

    async def _embed(texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = await service.embed(texts)
        except EmbeddingServiceError as exc:
            _LOGGER.error("Embedding service failed for %s texts: %s", len(texts), exc)
            raise
        except Exception:  # pragma: no cover - defensive logging
            _LOGGER.exception("Unexpected error while embedding %s texts", len(texts))
            raise

        if any(_is_zero_vector(vector) for vector in vectors):
            _LOGGER.warning("Embedding service returned zero vector for some inputs")

        return [list(vector) for vector in vectors]

    return _embed


def _build_qdrant_upsert(entry: ConfigEntry) -> Callable[[str, list[dict[str, Any]]], Awaitable[None]]:
    from .const import CONF_QDRANT_API_KEY, CONF_QDRANT_HOST

    data = getattr(entry, "data", {}) or {}
    options = getattr(entry, "options", {}) or {}

    host = str(data.get(CONF_QDRANT_HOST) or os.getenv("QDRANT_HOST", "")).rstrip("/")
    if not host:
        _LOGGER.warning("Qdrant host not configured; catalog sync upserts disabled")

        async def _noop(collection: str, points: list[dict[str, Any]]) -> None:
            _LOGGER.debug(
                "Dropping %s points for %s because Qdrant host is missing",
                len(points),
                collection,
            )

        return _noop

    api_key = data.get(CONF_QDRANT_API_KEY) or os.getenv("QDRANT_API_KEY")
    timeout = _coerce_float(
        _option_or_env(options, "qdrant_timeout", "QDRANT_TIMEOUT", 10.0),
        default=10.0,
        minimum=0.1,
    )
    batch_size = _coerce_int(
        _option_or_env(options, "qdrant_batch_size", "QDRANT_BATCH_SIZE", 64),
        default=64,
        minimum=1,
    )
    max_retries = _coerce_int(
        _option_or_env(options, "qdrant_max_retries", "QDRANT_MAX_RETRIES", 3),
        default=3,
        minimum=1,
    )

    headers = {"api-key": api_key} if api_key else {}

    async def _upsert(collection: str, points: list[dict[str, Any]]) -> None:
        if not points:
            return

        async with httpx.AsyncClient(
            base_url=host,
            timeout=timeout,
            headers=headers or None,
        ) as client:
            for batch in _chunk_list(points, batch_size):
                attempt = 0
                delay = 0.2
                while True:
                    attempt += 1
                    try:
                        response = await client.post(
                            f"/collections/{collection}/points/upsert",
                            json={"points": batch},
                        )
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        _LOGGER.warning(
                            "Qdrant upsert attempt %s/%s failed for %s: %s",
                            attempt,
                            max_retries,
                            collection,
                            exc,
                        )
                        if attempt >= max_retries:
                            raise
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 2.0)
                        continue
                    break

    return _upsert


def _build_catalog_provider(
    coordinator: EntangledHomeCoordinator,
) -> Callable[[], Awaitable[CatalogPayload]]:
    async def _provider() -> CatalogPayload:
        exporter = coordinator._build_exporter(getattr(coordinator.config_entry, "options", {}))
        return await exporter.run_once()

    return _provider


def _coerce_int(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, minimum)


def _coerce_float(value: Any, *, default: float, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else minimum


def _chunk_list(points: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    chunk_size = max(1, size)
    for start in range(0, len(points), chunk_size):
        yield list(points[start : start + chunk_size])


def _is_zero_vector(vector: Sequence[float]) -> bool:
    return all(float(component) == 0.0 for component in vector)


def _option_or_env(
    options: Mapping[str, Any], option_key: str, env_name: str, default: Any
) -> Any:
    value = options.get(option_key)
    if value not in (None, ""):
        return value
    env_value = os.getenv(env_name)
    if env_value not in (None, ""):
        return env_value
    return default


class _DeterministicEmbeddingBackend:
    async def generate(self, model: str, texts: list[str]) -> list[list[float]]:  # pragma: no cover - deterministic fallback
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [
                int.from_bytes(digest[offset : offset + 4], "big") / 2**32
                for offset in (0, 4, 8)
            ]
            vectors.append(vector)
        return vectors


def _allow_fallback_embeddings(options: Mapping[str, Any]) -> bool:
    flag = _option_or_env(options, "embedding_fallback", "ENTANGLEDHOME_EMBEDDINGS_FALLBACK", "1")
    if isinstance(flag, bool):
        return flag
    text = str(flag).strip().lower()
    return text not in {"0", "false", "no", "off"}
