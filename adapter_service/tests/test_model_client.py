"""Tests for the adapter service model client."""

from __future__ import annotations

import asyncio

import pytest

from adapter_service.model import ModelClient
from adapter_service.schema import InterpretResponse


class FakeRequester:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.calls: list[dict] = []

    async def __call__(self, payload: dict):
        self.calls.append(payload)
        for chunk in self._chunks:
            yield chunk


def test_model_client_repairs_json_and_clamps_confidence(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    chunks = [
        'data: {"intent": "noop", "confidence": 0.2, "params": {}}\n\n',
        'data: {"intent": "lights_on", "confidence": 1.4, "area": "living_room", "params": {}}\n\n',
        "data: [DONE]\n\n",
    ]
    requester = FakeRequester(chunks)

    client = ModelClient(
        model="mock-model",
        timeout=5.0,
        requester=requester,
    )

    async def _run() -> list[InterpretResponse]:
        results: list[InterpretResponse] = []
        async for response in client.stream(
            utterance="Turn on the living room lights",
            prompt={
                "catalog": {"areas": ["Living Room"]},
                "retrieved": {"ha_entities": [], "plex_media": []},
            },
            threshold=0.75,
        ):
            results.append(response)
        return results

    responses = asyncio.run(_run())

    assert [response.intent for response in responses] == ["noop", "lights_on"]
    assert responses[0].confidence == pytest.approx(0.2)
    assert responses[1].confidence == pytest.approx(1.0)
    assert responses[1].area == "living_room"

    assert len(requester.calls) == 1
    payload = requester.calls[0]
    assert payload["model"] == "mock-model"
    assert payload["stream"] is True
    assert payload["messages"][1]["role"] == "user"
