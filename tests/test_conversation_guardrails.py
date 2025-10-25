from __future__ import annotations

from collections import deque
from datetime import datetime
from types import SimpleNamespace
from typing import Callable, Iterable, Sequence
import sys


try:  # pragma: no cover - import guard for optional dependency
    import httpx  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in test environment
    class _StubAsyncClient:
        """Minimal httpx.AsyncClient stand-in for tests."""

        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - trivial stub
            pass

        async def post(self, *args, **kwargs):
            raise NotImplementedError

        async def aclose(self) -> None:
            return None

    sys.modules["httpx"] = SimpleNamespace(
        AsyncClient=_StubAsyncClient,
        Timeout=object,
        HTTPError=Exception,
    )

import pytest

from custom_components.entangledhome import const as eh_const
from custom_components.entangledhome.conversation import (
    ConversationResult,
    EntangledHomeConversationHandler,
)
from custom_components.entangledhome.intent_handlers import IntentHandlingError
from custom_components.entangledhome.models import CatalogPayload, InterpretResponse


pytestmark = pytest.mark.asyncio


class DummyAdapter:
    """Adapter stub that yields predefined responses."""

    def __init__(self, responses: Iterable[InterpretResponse]) -> None:
        self._responses = deque(responses)
        self.calls: list[str] = []
        self.shared_secret: str | None = None

    async def interpret(self, utterance: str, catalog: CatalogPayload) -> InterpretResponse:
        self.calls.append(utterance)
        try:
            return self._responses.popleft()
        except IndexError:  # pragma: no cover - defensive guard
            raise AssertionError("Adapter interpret called more than expected")

    def set_shared_secret(self, secret: str | None) -> None:
        self.shared_secret = secret


class DummyExecutor:
    """Intent executor stub capturing invocation arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[SimpleNamespace, InterpretResponse, CatalogPayload]] = []

    async def __call__(
        self,
        hass: SimpleNamespace,
        response: InterpretResponse,
        *,
        catalog: CatalogPayload,
        **kwargs: object,
    ) -> None:
        self.calls.append((hass, response, catalog))


class FailingExecutor:
    """Executor stub that raises a provided exception."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[tuple[SimpleNamespace, InterpretResponse, CatalogPayload]] = []

    async def __call__(
        self,
        hass: SimpleNamespace,
        response: InterpretResponse,
        *,
        catalog: CatalogPayload,
        **kwargs: object,
    ) -> None:
        self.calls.append((hass, response, catalog))
        raise self.error


class TelemetryStub:
    """Telemetry recorder stub capturing record_event payloads."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_event(self, **payload: object):
        self.events.append(payload)
        return SimpleNamespace(**payload)


class MonotonicStub:
    """Deterministic monotonic clock for dedupe tests."""

    def __init__(self, values: Sequence[float]) -> None:
        self._values = deque(values)

    def __call__(self) -> float:
        if not self._values:
            raise AssertionError("Monotonic clock exhausted")
        return self._values.popleft()


def _handler(
    *,
    adapter: DummyAdapter,
    executor: DummyExecutor,
    options: dict[str, object],
    guardrail_config: dict[str, object] | None = None,
    monotonic_values: Sequence[float] | None = None,
    now: datetime | None = None,
    telemetry: TelemetryStub | None = None,
    secondary_signals: Callable[[], Iterable[str]] | None = None,
) -> EntangledHomeConversationHandler:
    hass = SimpleNamespace()
    entry = SimpleNamespace(options=options)
    monotonic = MonotonicStub(monotonic_values or [0.0, 10.0, 20.0])
    now_provider = (lambda: now) if now is not None else (lambda: datetime(2024, 1, 1, 12, 0, 0))

    handler_kwargs: dict[str, object] = {}
    if guardrail_config is not None:
        handler_kwargs["guardrail_config"] = guardrail_config

    return EntangledHomeConversationHandler(
        hass,
        entry,
        adapter_client=adapter,
        catalog_provider=lambda: CatalogPayload(),
        intent_executor=executor,
        monotonic_source=monotonic,
        now_provider=now_provider,
        secondary_signal_provider=secondary_signals,
        telemetry_recorder=telemetry,
        **handler_kwargs,
    )


async def test_confidence_gate_blocks_low_confidence_intents() -> None:
    """When confidence is below the configured threshold the intent should not execute."""

    response = InterpretResponse(
        intent="turn_on",
        area=None,
        targets=None,
        params={},
        confidence=0.25,
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: True,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.8,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
    )

    result = await handler.async_handle("please turn on the lights")

    assert isinstance(result, ConversationResult)
    assert result.success is False
    assert "confidence" in result.response.lower()
    assert executor.calls == []


async def test_night_mode_suppresses_adapter_call() -> None:
    """Night mode should prevent contacting the adapter when within the quiet window."""

    adapter = DummyAdapter([])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: False,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: True,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 22,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        now=datetime(2024, 1, 1, 23, 45, 0),
    )

    result = await handler.async_handle("dim the living room")

    assert result.success is False
    assert "night" in result.response.lower()
    assert adapter.calls == []
    assert executor.calls == []


async def test_recent_duplicate_commands_are_suppressed() -> None:
    """Identical payloads within the dedupe window should only execute once."""

    response = InterpretResponse(
        intent="turn_off",
        area="kitchen",
        targets=["light.kitchen"],
        params={"reason": "bedtime"},
        confidence=0.92,
    )
    adapter = DummyAdapter([response, response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: True,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.6,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        monotonic_values=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
    )

    first = await handler.async_handle("lights off")
    second = await handler.async_handle("lights off")

    assert first.success is True
    assert second.success is False
    assert "duplicate" in second.response.lower()
    assert len(executor.calls) == 1


async def test_sensitive_intents_require_secondary_signals() -> None:
    """Sensitive intents should require secondary signals before execution."""

    response = InterpretResponse(
        intent="unlock_door",
        area="front_door",
        targets=["lock.front_door"],
        params={},
        confidence=0.91,
        required_secondary_signals=["presence"],
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: True,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.6,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        secondary_signals=lambda: set(),
    )

    result = await handler.async_handle("unlock the front door")

    assert result.success is False
    assert "secondary" in result.response.lower()
    assert executor.calls == []


async def test_sensitive_intents_execute_when_signals_present() -> None:
    """Sensitive intents should execute when all required secondary signals exist."""

    response = InterpretResponse(
        intent="unlock_door",
        area="front_door",
        targets=["lock.front_door"],
        params={},
        confidence=0.91,
        required_secondary_signals=["presence"],
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: True,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.6,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        secondary_signals=lambda: {"presence"},
    )

    result = await handler.async_handle("unlock the front door")

    assert result.success is True
    assert "success" in result.response.lower()
    assert len(executor.calls) == 1


async def test_adapter_client_receives_shared_secret_from_options() -> None:
    """Conversation handler should propagate the shared secret to the adapter."""

    response = InterpretResponse(
        intent="turn_on",
        area="garage",
        targets=["switch.garage"],
        params={},
        confidence=0.95,
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    shared_secret = "hmac-secret"
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: False,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
            eh_const.OPT_ADAPTER_SHARED_SECRET: shared_secret,
        },
    )

    result = await handler.async_handle("turn on the garage switch")

    assert result.success is True
    assert adapter.shared_secret == shared_secret


async def test_executor_errors_return_failure_and_record_telemetry() -> None:
    """Executor failures should bubble up as graceful responses without dedupe."""

    response = InterpretResponse(
        intent="scene_activate",
        area="living_room",
        targets=["scene.living_room_movie"],
        params={"scene": "movie"},
        confidence=0.95,
    )
    adapter = DummyAdapter([response, response])
    error = IntentHandlingError("adapter refused")
    executor = FailingExecutor(error)
    telemetry = TelemetryStub()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: False,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        monotonic_values=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        telemetry=telemetry,
    )

    first = await handler.async_handle("activate movie scene")
    second = await handler.async_handle("activate movie scene")

    assert first.success is False
    assert second.success is False
    assert "failed" in first.response.lower()
    assert "failed" in second.response.lower()
    assert handler._dedupe == {}
    assert len(executor.calls) == 2
    assert len(adapter.calls) == 2
    assert len(telemetry.events) == 2
    assert all(event["outcome"] == "failed" for event in telemetry.events)


async def test_guardrail_threshold_override_blocks_low_confidence() -> None:
    """Per-intent threshold overrides should block low confidence responses."""

    response = InterpretResponse(
        intent="turn_on",
        area="office",
        targets=["light.office"],
        params={},
        confidence=0.72,
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: True,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        guardrail_config={
            eh_const.OPT_INTENT_THRESHOLDS: {"turn_on": 0.9},
        },
    )

    result = await handler.async_handle("Turn on the office light")

    assert result.success is False
    assert "confidence" in result.response.lower()
    assert executor.calls == []


async def test_guardrail_dedupe_window_override_blocks_duplicates() -> None:
    """Per-intent dedupe overrides should honor the configured window."""

    response = InterpretResponse(
        intent="turn_on",
        area="kitchen",
        targets=["light.kitchen"],
        params={},
        confidence=0.96,
    )
    adapter = DummyAdapter([response, response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: False,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 0.5,
        },
        guardrail_config={
            eh_const.OPT_RECENT_COMMAND_WINDOW_OVERRIDES: {"turn_on": 3.0},
        },
        monotonic_values=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
    )

    first = await handler.async_handle("Activate kitchen lights")
    second = await handler.async_handle("Activate kitchen lights")

    assert first.success is True
    assert second.success is False
    assert "duplicate" in second.response.lower()
    assert len(executor.calls) == 1


async def test_guardrail_blocks_dangerous_intents_after_hours() -> None:
    """Dangerous intents should be rejected outside their allowed hours."""

    response = InterpretResponse(
        intent="unlock_door",
        area="front",
        targets=["lock.front"],
        params={},
        confidence=0.94,
    )
    adapter = DummyAdapter([response])
    executor = DummyExecutor()
    handler = _handler(
        adapter=adapter,
        executor=executor,
        options={
            eh_const.OPT_ENABLE_CONFIDENCE_GATE: False,
            eh_const.OPT_CONFIDENCE_THRESHOLD: 0.5,
            eh_const.OPT_NIGHT_MODE_ENABLED: False,
            eh_const.OPT_NIGHT_MODE_START_HOUR: 23,
            eh_const.OPT_NIGHT_MODE_END_HOUR: 6,
            eh_const.OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        guardrail_config={
            eh_const.OPT_DANGEROUS_INTENTS: ["unlock_door"],
            eh_const.OPT_ALLOWED_HOURS: {"unlock_door": [7, 21]},
        },
        now=datetime(2024, 1, 1, 22, 30, 0),
    )

    result = await handler.async_handle("unlock the front door")

    assert result.success is False
    assert "hours" in result.response.lower()
    assert executor.calls == []
