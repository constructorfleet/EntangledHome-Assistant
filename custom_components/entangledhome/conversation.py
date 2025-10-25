"""Conversation handler with guardrail enforcement for EntangledHome."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import inspect
import json
from typing import Any, Awaitable, Callable, Iterable, Mapping
import time

from homeassistant.components import conversation as conversation_domain
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .adapter_client import AdapterClient
from .const import (
    CONF_ADAPTER_URL,
    DATA_TELEMETRY,
    DEFAULT_CONFIDENCE_GATE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DEDUPLICATION_WINDOW,
    DEFAULT_NIGHT_MODE_ENABLED,
    DEFAULT_NIGHT_MODE_END_HOUR,
    DEFAULT_NIGHT_MODE_START_HOUR,
    DOMAIN,
    OPT_ADAPTER_SHARED_SECRET,
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DEDUPLICATION_WINDOW,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_NIGHT_MODE_ENABLED,
    OPT_NIGHT_MODE_END_HOUR,
    OPT_NIGHT_MODE_START_HOUR,
)
from .intent_handlers import IntentHandlingError, async_execute_intent
from .models import CatalogPayload, InterpretResponse
from .telemetry import TelemetryRecorder


CatalogProvider = Callable[[], CatalogPayload | Awaitable[CatalogPayload]]


@dataclass
class ConversationResult:
    """Minimal result structure returned from guardrail decisions."""

    success: bool
    response: str


class EntangledHomeConversationHandler:
    """Handle conversation requests while enforcing guardrails."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        *,
        adapter_client,
        catalog_provider: CatalogProvider,
        intent_executor: Callable[..., Awaitable[None]],
        monotonic_source: Callable[[], float] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        secondary_signal_provider: Callable[[], Iterable[str]] | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._adapter = adapter_client
        self._catalog_provider = catalog_provider
        self._intent_executor = intent_executor
        self._monotonic = monotonic_source or time.monotonic
        self._now = now_provider or datetime.now
        self._dedupe: dict[str, float] = {}
        self._secondary_signal_provider = secondary_signal_provider or (lambda: ())
        self._last_shared_secret: str | None = None
        self._telemetry = telemetry_recorder

    async def async_handle(self, utterance: str) -> ConversationResult:
        """Interpret and execute ``utterance`` applying configured guardrails."""

        options: Mapping[str, Any] = getattr(self._entry, "options", {})
        start_time = self._monotonic()

        self._apply_adapter_shared_secret(options)

        if self._night_mode_active(options):
            return ConversationResult(False, "Night mode is active. Try again later.")

        catalog = await self._resolve_catalog()
        response = await self._adapter.interpret(utterance, catalog)

        if self._confidence_blocked(response, options):
            return ConversationResult(False, "Confidence too low to execute safely.")

        dedupe_window = float(
            options.get(OPT_DEDUPLICATION_WINDOW, DEFAULT_DEDUPLICATION_WINDOW)
        )
        token = self._response_token(response)
        now_value = self._monotonic()
        self._prune_dedupe(now_value, dedupe_window)

        if dedupe_window > 0 and self._is_recent_duplicate(token, now_value, dedupe_window):
            return ConversationResult(False, "Duplicate command suppressed.")

        missing_signals = self._missing_secondary_signals(response)
        if missing_signals:
            return ConversationResult(False, self._format_secondary_signal_message(missing_signals))

        try:
            result = self._intent_executor(self._hass, response, catalog=catalog)
            if inspect.isawaitable(result):
                await result
        except IntentHandlingError as exc:
            message = (
                f"Intent execution failed: {exc}"
                if str(exc)
                else "Intent execution failed."
            )
            return self._executor_failure_result(
                utterance=utterance,
                response=response,
                start_time=start_time,
                message=message,
            )
        except Exception:  # pragma: no cover - defensive guardrail
            return self._executor_failure_result(
                utterance=utterance,
                response=response,
                start_time=start_time,
                message="Intent execution failed due to an unexpected error.",
            )

        if dedupe_window > 0:
            self._dedupe[token] = now_value

        end_time = self._monotonic()
        duration_ms = max(0.0, (end_time - start_time) * 1000.0)

        self._record_telemetry(
            utterance=utterance,
            response=response,
            duration_ms=duration_ms,
            outcome="executed",
        )

        return ConversationResult(True, "Intent executed successfully.")

    async def _resolve_catalog(self) -> CatalogPayload:
        provider_result = self._catalog_provider()
        if inspect.isawaitable(provider_result):
            return await provider_result  # type: ignore[return-value]
        return provider_result  # type: ignore[return-value]

    def _confidence_blocked(
        self, response: InterpretResponse, options: Mapping[str, Any]
    ) -> bool:
        if not options.get(OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE):
            return False
        threshold = float(options.get(OPT_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD))
        return response.confidence < threshold

    def _night_mode_active(self, options: Mapping[str, Any]) -> bool:
        if not options.get(OPT_NIGHT_MODE_ENABLED, DEFAULT_NIGHT_MODE_ENABLED):
            return False

        start = int(options.get(OPT_NIGHT_MODE_START_HOUR, DEFAULT_NIGHT_MODE_START_HOUR))
        end = int(options.get(OPT_NIGHT_MODE_END_HOUR, DEFAULT_NIGHT_MODE_END_HOUR))
        hour = self._now().hour

        if start == end:
            return True
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _response_token(self, response: InterpretResponse) -> str:
        payload = {
            "intent": response.intent,
            "area": response.area,
            "targets": list(response.targets or []),
            "params": dict(response.params),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _prune_dedupe(self, current: float, window: float) -> None:
        if window <= 0:
            self._dedupe.clear()
            return
        expired: list[str] = [
            token for token, timestamp in self._dedupe.items() if current - timestamp >= window
        ]
        for token in expired:
            self._dedupe.pop(token, None)

    def _is_recent_duplicate(self, token: str, current: float, window: float) -> bool:
        timestamp = self._dedupe.get(token)
        if timestamp is None:
            return False
        return current - timestamp < window

    def _missing_secondary_signals(self, response: InterpretResponse) -> list[str]:
        required = list(response.required_secondary_signals)
        if not required:
            return []
        provided_raw = self._secondary_signal_provider()
        provided = {signal.lower() for signal in provided_raw}
        return [signal for signal in required if signal.lower() not in provided]

    def _format_secondary_signal_message(self, missing: list[str]) -> str:
        detail = ", ".join(missing)
        if not detail:
            return "Secondary signals required."
        return f"Secondary signals required: {detail}."

    def _apply_adapter_shared_secret(self, options: Mapping[str, Any]) -> None:
        secret = str(options.get(OPT_ADAPTER_SHARED_SECRET, "") or "")
        if self._last_shared_secret == secret:
            return
        setter = getattr(self._adapter, "set_shared_secret", None)
        if callable(setter):
            setter(secret)
        elif hasattr(self._adapter, "_shared_secret"):
            setattr(self._adapter, "_shared_secret", secret)
        self._last_shared_secret = secret

    def _record_telemetry(
        self,
        *,
        utterance: str,
        response: InterpretResponse,
        duration_ms: float,
        outcome: str,
    ) -> None:
        recorder = self._telemetry
        if recorder is None:
            return

        try:
            recorder.record_event(
                utterance=utterance,
                qdrant_terms=list(getattr(response, "qdrant_terms", [])),
                response=response,
                duration_ms=duration_ms,
                outcome=outcome,
            )
        except Exception:  # pragma: no cover - telemetry should not disrupt handling
            pass

    def _executor_failure_result(
        self,
        *,
        utterance: str,
        response: InterpretResponse,
        start_time: float,
        message: str,
    ) -> ConversationResult:
        end_time = self._monotonic()
        duration_ms = max(0.0, (end_time - start_time) * 1000.0)
        self._record_telemetry(
            utterance=utterance,
            response=response,
            duration_ms=duration_ms,
            outcome="failed",
        )
        return ConversationResult(False, message)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the EntangledHome conversation agent for ``entry``."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    entry_data: dict[str, Any] = domain_data.setdefault(entry.entry_id, {})

    adapter = _resolve_adapter(entry, entry_data)
    catalog_provider = _resolve_catalog_provider(entry, entry_data)
    telemetry = entry_data.get(DATA_TELEMETRY)

    handler = EntangledHomeConversationHandler(
        hass,
        entry,
        adapter_client=adapter,
        catalog_provider=catalog_provider,
        intent_executor=async_execute_intent,
        telemetry_recorder=telemetry,
    )

    entry_data["conversation_handler"] = handler

    await conversation_domain.async_set_agent(hass, DOMAIN, handler)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the conversation agent when the config entry unloads."""

    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry.entry_id)
    if isinstance(entry_data, dict):
        entry_data.pop("conversation_handler", None)

    await conversation_domain.async_unset_agent(hass, DOMAIN)
    return True


def _resolve_adapter(entry: ConfigEntry, entry_data: dict[str, Any]) -> AdapterClient:
    adapter = entry_data.get("adapter_client")
    if isinstance(adapter, AdapterClient):
        return adapter

    data = getattr(entry, "data", {}) or {}
    endpoint = data.get(CONF_ADAPTER_URL) or ""
    adapter = AdapterClient(endpoint)
    entry_data["adapter_client"] = adapter

    secret = (getattr(entry, "options", {}) or {}).get(OPT_ADAPTER_SHARED_SECRET)
    if secret:
        adapter.set_shared_secret(secret)

    return adapter


def _resolve_catalog_provider(
    entry: ConfigEntry, entry_data: dict[str, Any]
) -> CatalogProvider:
    provider = entry_data.get("catalog_provider")
    if callable(provider):
        return provider  # type: ignore[return-value]

    coordinator = entry_data.get("coordinator")
    if coordinator is not None:
        async def _coordinator_catalog() -> CatalogPayload:
            exporter = coordinator._build_exporter(getattr(entry, "options", {}))
            return await exporter.run_once()

        entry_data["catalog_provider"] = _coordinator_catalog
        return _coordinator_catalog

    async def _empty_catalog() -> CatalogPayload:
        return CatalogPayload()

    entry_data["catalog_provider"] = _empty_catalog
    return _empty_catalog
