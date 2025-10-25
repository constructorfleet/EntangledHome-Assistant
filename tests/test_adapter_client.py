from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

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
