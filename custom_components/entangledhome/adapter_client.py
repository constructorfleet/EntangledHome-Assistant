"""HTTP client for the EntangledHome adapter service."""

from __future__ import annotations

from typing import Any

import httpx

from .models import CatalogPayload, InterpretRequest, InterpretResponse


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
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._client = client

    async def interpret(self, utterance: str, catalog: CatalogPayload) -> InterpretResponse:
        """Send the utterance and catalog to the adapter and parse the response."""
        request_model = InterpretRequest(utterance=utterance, catalog=catalog)
        payload = request_model.model_dump(mode="json")

        client = self._client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            close_client = True

        try:
            response = await client.post(self._endpoint, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterClientError("Adapter request failed") from exc
        finally:
            if close_client:
                await client.aclose()

        data: Any = response.json()
        return InterpretResponse.model_validate(data)
