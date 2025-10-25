"""HTTP client for the EntangledHome adapter service."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

import httpx

from .models import CatalogPayload, InterpretRequest, InterpretResponse

SIGNATURE_HEADER = "X-Entangled-Signature"


class AdapterClientError(RuntimeError):
    """Raised when the adapter call fails."""


class AdapterClient:
    """Wrapper around the adapter HTTP endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float | httpx.Timeout | None = 10.0,
        client: httpx.AsyncClient | None = None,
        shared_secret: str | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._client = client
        self._shared_secret = shared_secret or ""

    async def interpret(
        self,
        utterance: str,
        catalog: CatalogPayload,
        *,
        intents: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> InterpretResponse:
        """Send the utterance and catalog to the adapter and parse the response."""
        request_model = InterpretRequest(
            utterance=utterance,
            catalog=catalog,
            intents=self._normalize_intents(intents),
        )
        payload = request_model.model_dump(mode="json")

        client = self._client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        signature = self._build_signature(body)
        if signature is not None:
            headers[SIGNATURE_HEADER] = signature

        try:
            response = await client.post(self._endpoint, content=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterClientError("Adapter request failed") from exc
        finally:
            if close_client:
                await client.aclose()

        data: Any = response.json()
        return InterpretResponse.model_validate(data)

    def _build_signature(self, body: bytes) -> str | None:
        if not self._shared_secret:
            return None
        digest = hmac.new(
            self._shared_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return digest

    @staticmethod
    def _normalize_intents(
        intents: Mapping[str, Mapping[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in (intents or {}).items()}

    def set_shared_secret(self, shared_secret: str | None) -> None:
        """Update the shared secret used for signing requests."""

        self._shared_secret = shared_secret or ""
