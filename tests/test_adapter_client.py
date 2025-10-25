from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
import pytest

from httpx import Timeout

from custom_components.entangledhome.adapter_client import (
    AdapterClient,
    AdapterClientError,
)
from custom_components.entangledhome.models import CatalogPayload


pytestmark = pytest.mark.asyncio


async def test_adapter_client_signs_payload_with_shared_secret() -> None:
    """Requests to the adapter must include an HMAC signature header."""

    secret = "super-secret"
    captured_signature: str | None = None
    captured_body: bytes | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_signature, captured_body
        captured_signature = request.headers.get("X-Entangled-Signature")
        captured_body = request.content
        return httpx.Response(
            200,
            json={
                "intent": "noop",
                "params": {},
                "confidence": 0.0,
                "sensitive": False,
                "required_secondary_signals": [],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AdapterClient("https://adapter.invalid/interpret", client=http_client)
        client._shared_secret = secret  # type: ignore[attr-defined]
        await client.interpret("turn on the lights", CatalogPayload())

    assert captured_body is not None
    expected = hmac.new(secret.encode("utf-8"), captured_body, hashlib.sha256).hexdigest()
    assert captured_signature == expected


async def test_adapter_client_raises_when_signature_invalid() -> None:
    """Invalid signatures should surface as adapter client errors."""

    expected_secret = "expected-secret"
    provided_secret = "wrong-secret"
    captured_signature: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_signature
        captured_signature = request.headers.get("X-Entangled-Signature")
        expected = hmac.new(
            expected_secret.encode("utf-8"), request.content, hashlib.sha256
        ).hexdigest()
        if captured_signature != expected:
            return httpx.Response(401, json={"detail": "Invalid signature"})
        return httpx.Response(
            200,
            json={
                "intent": "noop",
                "params": {},
                "confidence": 0.0,
                "sensitive": False,
                "required_secondary_signals": [],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AdapterClient("https://adapter.invalid/interpret", client=http_client)
        client._shared_secret = provided_secret  # type: ignore[attr-defined]
        with pytest.raises(AdapterClientError):
            await client.interpret("open the garage", CatalogPayload())

    assert captured_signature is not None


async def test_adapter_client_uses_tight_timeout_when_building_client(monkeypatch):
    """The default client should use a ~1.5s Timeout envelope."""

    captured_timeout: Timeout | None = None

    class DummyAsyncClient:
        def __init__(self, *, timeout: Timeout | float | None = None, **kwargs) -> None:
            nonlocal captured_timeout
            assert kwargs == {}
            assert timeout is not None
            assert isinstance(timeout, Timeout)
            captured_timeout = timeout

        async def post(self, *_: Any, **__: Any) -> httpx.Response:  # type: ignore[override]
            return httpx.Response(
                200,
                json={
                    "intent": "noop",
                    "params": {},
                    "confidence": 0.0,
                    "sensitive": False,
                    "required_secondary_signals": [],
                },
                request=httpx.Request("POST", "https://adapter.invalid/interpret"),
            )

        async def aclose(self) -> None:  # pragma: no cover - nothing to close
            return None

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    client = AdapterClient("https://adapter.invalid/interpret")
    await client.interpret("dim the lights", CatalogPayload())

    assert captured_timeout is not None
    assert captured_timeout.connect == pytest.approx(1.5, rel=0.05)
    assert captured_timeout.read == pytest.approx(1.5, rel=0.05)
    assert captured_timeout.write == pytest.approx(1.5, rel=0.05)
    assert captured_timeout.pool == pytest.approx(1.5, rel=0.05)


async def test_adapter_client_returns_noop_on_http_failures_and_logs(caplog):
    """HTTPX failures should yield noop responses with adapter_error metadata."""

    class ExplodingClient:
        async def post(self, *_: Any, **__: Any) -> httpx.Response:  # type: ignore[override]
            raise httpx.ReadTimeout("boom")

        async def aclose(self) -> None:  # pragma: no cover
            return None

    caplog.set_level("INFO")
    client = AdapterClient(
        "https://adapter.invalid/interpret",
        client=ExplodingClient(),
    )

    catalog = CatalogPayload(
        areas=[],
        entities=[],
        scenes=[],
        plex_media=[],
    )

    response = await client.interpret("open the pod bay doors", catalog)

    assert response.intent == "noop"
    assert response.params.get("reason") == "Adapter request failed"
    assert response.adapter_error is not None
    assert "open the pod bay doors" in response.params.get("utterance", "")

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "open the pod bay doors" in log_text
    assert "adapter_failed" in log_text
