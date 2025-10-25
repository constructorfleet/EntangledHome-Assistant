from __future__ import annotations

from collections import deque
from datetime import datetime
from types import SimpleNamespace
from typing import Iterable, Sequence

import pytest

from custom_components.entangledhome.const import (
    OPT_CONFIDENCE_THRESHOLD,
    OPT_DEDUPLICATION_WINDOW,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_NIGHT_MODE_ENABLED,
    OPT_NIGHT_MODE_END_HOUR,
    OPT_NIGHT_MODE_START_HOUR,
    OPT_ADAPTER_SHARED_SECRET,
)
from custom_components.entangledhome.conversation import (
    ConversationResult,
    EntangledHomeConversationHandler,
)
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
    ) -> None:
        self.calls.append((hass, response, catalog))


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
    monotonic_values: Sequence[float] | None = None,
    now: datetime | None = None,
) -> EntangledHomeConversationHandler:
    hass = SimpleNamespace()
    entry = SimpleNamespace(options=options)
    monotonic = MonotonicStub(monotonic_values or [0.0, 10.0, 20.0])
    now_provider = (lambda: now) if now is not None else (lambda: datetime(2024, 1, 1, 12, 0, 0))

    return EntangledHomeConversationHandler(
        hass,
        entry,
        adapter_client=adapter,
        catalog_provider=lambda: CatalogPayload(),
        intent_executor=executor,
        monotonic_source=monotonic,
        now_provider=now_provider,
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
            OPT_ENABLE_CONFIDENCE_GATE: True,
            OPT_CONFIDENCE_THRESHOLD: 0.8,
            OPT_NIGHT_MODE_ENABLED: False,
            OPT_NIGHT_MODE_START_HOUR: 23,
            OPT_NIGHT_MODE_END_HOUR: 6,
            OPT_DEDUPLICATION_WINDOW: 2.0,
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
            OPT_ENABLE_CONFIDENCE_GATE: False,
            OPT_CONFIDENCE_THRESHOLD: 0.5,
            OPT_NIGHT_MODE_ENABLED: True,
            OPT_NIGHT_MODE_START_HOUR: 22,
            OPT_NIGHT_MODE_END_HOUR: 6,
            OPT_DEDUPLICATION_WINDOW: 2.0,
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
            OPT_ENABLE_CONFIDENCE_GATE: True,
            OPT_CONFIDENCE_THRESHOLD: 0.6,
            OPT_NIGHT_MODE_ENABLED: False,
            OPT_NIGHT_MODE_START_HOUR: 23,
            OPT_NIGHT_MODE_END_HOUR: 6,
            OPT_DEDUPLICATION_WINDOW: 2.0,
        },
        monotonic_values=[0.0, 1.0],
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
            OPT_ENABLE_CONFIDENCE_GATE: True,
            OPT_CONFIDENCE_THRESHOLD: 0.6,
            OPT_NIGHT_MODE_ENABLED: False,
            OPT_NIGHT_MODE_START_HOUR: 23,
            OPT_NIGHT_MODE_END_HOUR: 6,
            OPT_DEDUPLICATION_WINDOW: 2.0,
        },
    )
    handler._secondary_signal_provider = lambda: set()

    result = await handler.async_handle("unlock the front door")

    assert result.success is False
    assert "secondary" in result.response.lower()
    assert executor.calls == []


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
            OPT_ENABLE_CONFIDENCE_GATE: False,
            OPT_CONFIDENCE_THRESHOLD: 0.5,
            OPT_NIGHT_MODE_ENABLED: False,
            OPT_NIGHT_MODE_START_HOUR: 23,
            OPT_NIGHT_MODE_END_HOUR: 6,
            OPT_DEDUPLICATION_WINDOW: 2.0,
            OPT_ADAPTER_SHARED_SECRET: shared_secret,
        },
    )

    result = await handler.async_handle("turn on the garage switch")

    assert result.success is True
    assert adapter.shared_secret == shared_secret
