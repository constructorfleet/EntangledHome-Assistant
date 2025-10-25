import logging
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Iterable

import pytest

from custom_components.entangledhome.conversation import EntangledHomeConversationHandler
from custom_components.entangledhome.models import CatalogPayload, InterpretResponse
from custom_components.entangledhome.telemetry import TelemetryRecorder

pytestmark = pytest.mark.asyncio


class DummyAdapter:
    """Adapter stub returning a fixed response."""

    def __init__(self, response: InterpretResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, CatalogPayload]] = []

    async def interpret(self, utterance: str, catalog: CatalogPayload) -> InterpretResponse:
        self.calls.append((utterance, catalog))
        return self.response


class DummyExecutor:
    """Executor stub capturing invocations."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, hass, response: InterpretResponse, *, catalog: CatalogPayload) -> None:
        self.calls.append((hass, response, catalog))


class MonotonicStub:
    """Deterministic monotonic clock returning predefined values."""

    def __init__(self, values: Iterable[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class ClockStub:
    """Deterministic datetime provider."""

    def __init__(self, base: datetime, step: timedelta) -> None:
        self._current = base
        self._step = step

    def __call__(self) -> datetime:
        current = self._current
        self._current = current + self._step
        return current


async def test_structured_logging_records_conversation(caplog: pytest.LogCaptureFixture) -> None:
    """Handler should emit telemetry logs and store traces."""

    response = InterpretResponse(
        intent="turn_on",
        area="hallway",
        targets=["light.hallway"],
        params={"reason": "movie"},
        confidence=0.93,
        qdrant_terms=["hallway", "lights"],
    )
    adapter = DummyAdapter(response)
    executor = DummyExecutor()
    recorder = TelemetryRecorder(
        max_events=4,
        clock=ClockStub(datetime(2024, 1, 1, tzinfo=timezone.utc), timedelta(milliseconds=5)),
    )
    handler = EntangledHomeConversationHandler(
        SimpleNamespace(),
        SimpleNamespace(options={}),
        adapter_client=adapter,
        catalog_provider=lambda: CatalogPayload(),
        intent_executor=executor,
        monotonic_source=MonotonicStub([10.0, 10.1, 10.2]),
        telemetry_recorder=recorder,
    )

    with caplog.at_level(logging.INFO, logger="custom_components.entangledhome.telemetry"):
        result = await handler.async_handle("Turn on the hallway lights")

    assert result.success is True
    events = list(recorder.iter_recent())
    assert len(events) == 1
    event = events[0]
    assert event.utterance == "Turn on the hallway lights"
    assert event.qdrant_terms == ["hallway", "lights"]
    assert event.response.intent == "turn_on"
    assert event.response.confidence == pytest.approx(0.93)
    assert event.duration_ms == pytest.approx(200.0)
    assert event.outcome == "executed"

    records = [rec for rec in caplog.records if rec.message == "entangledhome.conversation"]
    assert len(records) == 1
    record = records[0]
    payload = record.entangled_command
    assert payload["utterance"] == "Turn on the hallway lights"
    assert payload["qdrant_terms"] == ["hallway", "lights"]
    assert payload["intent"] == "turn_on"
    assert payload["confidence"] == pytest.approx(0.93)
    assert payload["duration_ms"] == pytest.approx(200.0)
    assert payload["outcome"] == "executed"
