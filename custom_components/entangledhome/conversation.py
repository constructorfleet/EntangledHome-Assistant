"""Conversation handler with guardrail enforcement for EntangledHome."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import inspect
import json
from typing import Any, Awaitable, Callable, Iterable, Mapping
import time

from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_CONFIDENCE_GATE,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DEDUPLICATION_WINDOW,
    DEFAULT_NIGHT_MODE_ENABLED,
    DEFAULT_NIGHT_MODE_END_HOUR,
    DEFAULT_NIGHT_MODE_START_HOUR,
    OPT_ADAPTER_SHARED_SECRET,
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DEDUPLICATION_WINDOW,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_NIGHT_MODE_ENABLED,
    OPT_NIGHT_MODE_END_HOUR,
    OPT_NIGHT_MODE_START_HOUR,
)
from .models import CatalogPayload, InterpretResponse


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

    async def async_handle(self, utterance: str) -> ConversationResult:
        """Interpret and execute ``utterance`` applying configured guardrails."""

        options: Mapping[str, Any] = getattr(self._entry, "options", {})

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

        result = self._intent_executor(self._hass, response, catalog=catalog)
        if inspect.isawaitable(result):
            await result

        if dedupe_window > 0:
            self._dedupe[token] = now_value

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
