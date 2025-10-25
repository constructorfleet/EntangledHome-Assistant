"""Telemetry recording and structured logging helpers for EntangledHome."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Iterator, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .models import InterpretResponse


class TelemetryEvent(BaseModel):
    """Normalized telemetry payload for conversation traces."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    utterance: str
    qdrant_terms: list[str] = Field(default_factory=list)
    response: InterpretResponse
    duration_ms: float
    outcome: str

    def summary(self) -> dict[str, Any]:
        """Return a compact summary suitable for structured logging."""

        return {
            "timestamp": self.timestamp.isoformat(),
            "utterance": self.utterance,
            "qdrant_terms": list(self.qdrant_terms),
            "intent": self.response.intent,
            "confidence": float(self.response.confidence),
            "duration_ms": float(self.duration_ms),
            "outcome": self.outcome,
        }


class TelemetryRecorder:
    """Ring buffer of the most recent telemetry events."""

    def __init__(
        self,
        *,
        max_events: int = 50,
        clock: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._events: deque[TelemetryEvent] = deque(maxlen=max(1, max_events))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._logger = logger or logging.getLogger("custom_components.entangledhome.telemetry")

    def record_event(
        self,
        *,
        utterance: str,
        qdrant_terms: Sequence[str] | None,
        response: InterpretResponse | dict,
        duration_ms: float,
        outcome: str,
    ) -> TelemetryEvent:
        """Validate and append a telemetry event."""

        response_model = (
            response
            if isinstance(response, InterpretResponse)
            else InterpretResponse.model_validate(response)
        )

        event = TelemetryEvent(
            utterance=utterance,
            qdrant_terms=list(qdrant_terms or []),
            response=response_model,
            duration_ms=float(duration_ms),
            outcome=outcome,
            timestamp=self._clock(),
        )
        self._events.append(event)
        self._emit_log(event)
        return event

    def iter_recent(self) -> Iterator[TelemetryEvent]:
        """Yield stored events from oldest to newest."""

        return iter(tuple(self._events))

    def as_dicts(self) -> list[dict]:
        """Return the stored events serialized for diagnostics."""

        return [event.model_dump(mode="json") for event in self._events]

    def _emit_log(self, event: TelemetryEvent) -> None:
        """Emit a structured log entry for ``event``."""

        if not self._logger:
            return

        try:
            summary = event.summary()
            payload = event.model_dump(mode="json")
            self._logger.info(
                "entangledhome.conversation",
                extra={
                    "entangled_command": summary,
                    "entangled_full_event": payload,
                },
            )
        except Exception:  # pragma: no cover - logging failures should not break execution
            self._logger.debug("Failed to emit telemetry log", exc_info=True)
