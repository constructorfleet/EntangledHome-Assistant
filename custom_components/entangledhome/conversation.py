"""Conversation handler with guardrail enforcement for EntangledHome."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import inspect
import json
import logging
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
    OPT_ALLOWED_HOURS,
    OPT_DANGEROUS_INTENTS,
    OPT_DISABLED_INTENTS,
    OPT_INTENT_THRESHOLDS,
    OPT_RECENT_COMMAND_WINDOW_OVERRIDES,
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

_LOGGER = logging.getLogger(__name__)


@dataclass
class GuardrailBundle:
    """Normalized guardrail configuration for conversation decisions."""

    intent_thresholds: dict[str, float] = field(default_factory=dict)
    disabled_intents: set[str] = field(default_factory=set)
    dangerous_intents: set[str] = field(default_factory=set)
    allowed_hours: dict[str, tuple[int, int]] = field(default_factory=dict)
    recent_command_windows: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | "GuardrailBundle" | None) -> "GuardrailBundle":
        if isinstance(data, GuardrailBundle):
            return data

        mapping: Mapping[str, Any] = data or {}

        thresholds: dict[str, float] = {}
        raw_thresholds = mapping.get(OPT_INTENT_THRESHOLDS, {})
        if isinstance(raw_thresholds, Mapping):
            for intent, value in raw_thresholds.items():
                try:
                    thresholds[str(intent)] = float(value)
                except (TypeError, ValueError):
                    continue

        disabled = cls._coerce_str_set(mapping.get(OPT_DISABLED_INTENTS, ()))
        dangerous = cls._coerce_str_set(mapping.get(OPT_DANGEROUS_INTENTS, ()))

        allowed: dict[str, tuple[int, int]] = {}
        raw_allowed = mapping.get(OPT_ALLOWED_HOURS, {})
        if isinstance(raw_allowed, Mapping):
            for intent, value in raw_allowed.items():
                hours = cls._coerce_hours(value)
                if hours is not None:
                    allowed[str(intent)] = hours

        windows: dict[str, float] = {}
        raw_windows = mapping.get(OPT_RECENT_COMMAND_WINDOW_OVERRIDES, {})
        if isinstance(raw_windows, Mapping):
            for intent, value in raw_windows.items():
                try:
                    window = float(value)
                except (TypeError, ValueError):
                    continue
                if window >= 0:
                    windows[str(intent)] = window

        return cls(
            intent_thresholds=thresholds,
            disabled_intents=disabled,
            dangerous_intents=dangerous,
            allowed_hours=allowed,
            recent_command_windows=windows,
        )

    def threshold_for(self, intent: str) -> float | None:
        return self.intent_thresholds.get(intent)

    def dedupe_window_for(self, intent: str) -> float | None:
        return self.recent_command_windows.get(intent)

    def allowed_hours_for(self, intent: str) -> tuple[int, int] | None:
        return self.allowed_hours.get(intent)

    def is_disabled(self, intent: str) -> bool:
        return intent in self.disabled_intents

    def is_dangerous(self, intent: str) -> bool:
        return intent in self.dangerous_intents

    def intent_config(self, intent: str) -> dict[str, Any]:
        config: dict[str, Any] = {}
        threshold = self.threshold_for(intent)
        if threshold is not None:
            config["confidence_threshold"] = threshold
        window = self.dedupe_window_for(intent)
        if window is not None:
            config["recent_command_window"] = window
        hours = self.allowed_hours_for(intent)
        if hours is not None:
            config["allowed_hours"] = hours
        if self.is_dangerous(intent):
            config["dangerous"] = True
        if self.is_disabled(intent):
            config["disabled"] = True
        return config

    @staticmethod
    def _coerce_str_set(value: Any) -> set[str]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return set(items)
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if str(item).strip()}
        return set()

    @staticmethod
    def _coerce_hours(value: Any) -> tuple[int, int] | None:
        if isinstance(value, Mapping):
            start = value.get("start")
            end = value.get("end")
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            start, end = value
        else:
            return None
        try:
            start_hour = int(start)
            end_hour = int(end)
        except (TypeError, ValueError):
            return None
        if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23:
            return None
        return start_hour, end_hour

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
        guardrail_config: Mapping[str, Any] | GuardrailBundle | None = None,
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
        self._guardrails = GuardrailBundle.from_mapping(guardrail_config)

    def set_guardrail_config(
        self, guardrail_config: Mapping[str, Any] | GuardrailBundle | None
    ) -> None:
        """Update the active guardrail configuration."""

        self._guardrails = GuardrailBundle.from_mapping(guardrail_config)

    async def async_handle(self, utterance: str) -> ConversationResult:
        """Interpret and execute ``utterance`` applying configured guardrails."""

        options: Mapping[str, Any] = getattr(self._entry, "options", {})
        start_time = self._monotonic()

        self._apply_adapter_shared_secret(options)

        if self._night_mode_active(options):
            return self._guardrail_block(
                utterance=utterance,
                message="Night mode is active. Try again later.",
                reason="night_mode_active",
            )

        catalog = await self._resolve_catalog()
        response = await self._adapter.interpret(utterance, catalog)

        guardrails = self._guardrails
        intent = response.intent
        intent_config = guardrails.intent_config(intent)
        threshold_override = intent_config.get("confidence_threshold")
        dedupe_window = intent_config.get("recent_command_window")
        allowed_hours = intent_config.get("allowed_hours")
        is_dangerous = bool(intent_config.get("dangerous"))
        if dedupe_window is None:
            dedupe_window = float(
                options.get(OPT_DEDUPLICATION_WINDOW, DEFAULT_DEDUPLICATION_WINDOW)
            )

        if guardrails.is_disabled(intent):
            return self._guardrail_block(
                utterance=utterance,
                response=response,
                message="This intent is disabled by configuration.",
                reason="intent_disabled",
            )

        if threshold_override is not None and response.confidence < threshold_override:
            return self._guardrail_block(
                utterance=utterance,
                response=response,
                message="Confidence too low to execute safely.",
                reason="intent_threshold",
                detail={"threshold": threshold_override},
            )

        if self._confidence_blocked(response, options):
            configured_threshold = float(
                options.get(OPT_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD)
            )
            return self._guardrail_block(
                utterance=utterance,
                response=response,
                message="Confidence too low to execute safely.",
                reason="confidence_gate",
                detail={
                    "threshold": configured_threshold,
                    "gate_enabled": bool(
                        options.get(OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE)
                    ),
                },
            )

        token = self._response_token(response)
        now_value = self._monotonic()
        self._prune_dedupe(now_value, dedupe_window)

        if dedupe_window > 0 and self._is_recent_duplicate(token, now_value, dedupe_window):
            return self._guardrail_block(
                utterance=utterance,
                response=response,
                message="Duplicate command suppressed.",
                reason="duplicate_suppressed",
                detail={"dedupe_window": dedupe_window},
            )

        missing_signals = self._missing_secondary_signals(response)
        if missing_signals:
            return self._guardrail_block(
                utterance=utterance,
                response=response,
                message=self._format_secondary_signal_message(missing_signals),
                reason="missing_secondary_signals",
                detail={"missing_secondary_signals": list(missing_signals)},
            )

        if is_dangerous:
            if allowed_hours is not None and not self._within_allowed_hours(allowed_hours):
                return self._guardrail_block(
                    utterance=utterance,
                    response=response,
                    message="Intent is restricted to allowed hours.",
                    reason="dangerous_intent_after_hours",
                    detail={"allowed_hours": list(allowed_hours)},
                )
            if not self._has_verification_flags(response):
                return self._guardrail_block(
                    utterance=utterance,
                    response=response,
                    message="Additional verification required before executing this intent.",
                    reason="dangerous_intent_missing_verification",
                )

        try:
            result = self._intent_executor(
                self._hass,
                response,
                catalog=catalog,
                intent_config=intent_config,
            )
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

        execution_detail: dict[str, Any] = {"dedupe_window": dedupe_window}
        if threshold_override is not None:
            execution_detail["confidence_threshold"] = threshold_override
        if allowed_hours is not None:
            execution_detail["allowed_hours"] = list(allowed_hours)
        if is_dangerous:
            execution_detail["dangerous"] = True

        self._emit_guardrail_log(
            utterance=utterance,
            response=response,
            reason="intent_executed",
            outcome="executed",
            detail=execution_detail,
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

    def _guardrail_block(
        self,
        *,
        utterance: str,
        message: str,
        reason: str,
        response: InterpretResponse | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> ConversationResult:
        self._emit_guardrail_log(
            utterance=utterance,
            response=response,
            reason=reason,
            outcome="blocked",
            detail=detail,
        )
        return ConversationResult(False, message)

    def _emit_guardrail_log(
        self,
        *,
        utterance: str,
        response: InterpretResponse | None,
        reason: str,
        outcome: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "utterance": utterance,
            "reason": reason,
            "outcome": outcome,
        }
        if response is not None:
            payload.update(
                {
                    "intent": response.intent,
                    "confidence": float(response.confidence),
                    "area": response.area,
                }
            )
        if detail:
            payload.update(detail)
        try:
            _LOGGER.info(
                "entangledhome.guardrail",
                extra={"entangled_guardrail": payload},
            )
        except Exception:  # pragma: no cover - logging should not break execution
            _LOGGER.debug("Failed to emit guardrail log", exc_info=True)

    def _within_allowed_hours(self, hours: tuple[int, int]) -> bool:
        start, end = hours
        current = self._now().hour
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end

    def _has_verification_flags(self, response: InterpretResponse) -> bool:
        params = getattr(response, "params", {}) or {}
        if isinstance(params, Mapping):
            flags = params.get("verification_flags")
            if isinstance(flags, str) and flags.strip():
                return True
            if isinstance(flags, (list, tuple, set)):
                if any(str(flag).strip() for flag in flags):
                    return True
            verification = params.get("verification")
            if isinstance(verification, Mapping):
                nested_flags = verification.get("flags")
                if isinstance(nested_flags, str) and nested_flags.strip():
                    return True
                if isinstance(nested_flags, (list, tuple, set)):
                    if any(str(flag).strip() for flag in nested_flags):
                        return True
                confirmed = verification.get("confirmed") or verification.get("verified")
                if isinstance(confirmed, bool) and confirmed:
                    return True
            confirmed = params.get("verified")
            if isinstance(confirmed, bool):
                return confirmed
        return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the EntangledHome conversation agent for ``entry``."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    entry_data: dict[str, Any] = domain_data.setdefault(entry.entry_id, {})

    adapter = _resolve_adapter(entry, entry_data)
    catalog_provider = _resolve_catalog_provider(entry, entry_data)
    secondary_signals = _resolve_secondary_signal_provider(entry_data)
    telemetry = entry_data.get(DATA_TELEMETRY)

    handler = EntangledHomeConversationHandler(
        hass,
        entry,
        adapter_client=adapter,
        catalog_provider=catalog_provider,
        intent_executor=async_execute_intent,
        secondary_signal_provider=secondary_signals,
        telemetry_recorder=telemetry,
        guardrail_config=entry_data.get("guardrail_config"),
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


def _resolve_secondary_signal_provider(
    entry_data: dict[str, Any],
) -> Callable[[], Iterable[str]]:
    provider = entry_data.get("secondary_signal_provider")
    if callable(provider):
        return provider  # type: ignore[return-value]
    return lambda: ()
