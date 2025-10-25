"""HTTP client for the EntangledHome adapter service."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Mapping

import httpx
from httpx import Timeout
from jsonschema import ValidationError, validate

from .models import CatalogPayload, InterpretRequest, InterpretResponse

SIGNATURE_HEADER = "X-Entangled-Signature"
LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT = Timeout(1.5)
RESPONSE_SCHEMA = InterpretResponse.model_json_schema(mode="validation")


class AdapterClientError(RuntimeError):
    """Raised when the adapter call fails."""


class AdapterClient:
    """Wrapper around the adapter HTTP endpoint."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float | httpx.Timeout | None = None,
        client: httpx.AsyncClient | None = None,
        shared_secret: str | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout or DEFAULT_TIMEOUT
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

        fingerprint = self._fingerprint_catalog(catalog)
        LOGGER.info(
            "adapter_request_start utterance=%s fingerprint=%s",
            utterance,
            fingerprint,
        )

        client = self._client
        close_client = False
        if client is None:
            timeout = self._timeout
            if not isinstance(timeout, Timeout):
                timeout = Timeout(timeout)
            client = httpx.AsyncClient(timeout=timeout)
            close_client = True

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        signature = self._build_signature(body)
        if signature is not None:
            headers[SIGNATURE_HEADER] = signature

        try:
            response = await client.post(self._endpoint, content=body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == httpx.codes.UNAUTHORIZED:
                raise AdapterClientError("Adapter rejected signature") from exc
            self._log_failure(
                utterance,
                fingerprint,
                error=exc,
                status=status,
            )
            return self._failure_response(
                utterance,
                fingerprint,
                reason="Adapter request failed",
                adapter_error=str(exc),
            )
        except httpx.HTTPError as exc:
            self._log_failure(utterance, fingerprint, error=exc)
            return self._failure_response(
                utterance,
                fingerprint,
                reason="Adapter request failed",
                adapter_error=str(exc),
            )
        finally:
            if close_client:
                await client.aclose()

        data: Any
        try:
            data = response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - httpx already validates JSON
            self._log_failure(utterance, fingerprint, error=exc)
            return self._failure_response(
                utterance,
                fingerprint,
                reason="Adapter returned invalid JSON",
                adapter_error=str(exc),
            )

        try:
            validate(data, RESPONSE_SCHEMA)
        except (ValidationError, TypeError) as exc:
            self._log_failure(
                utterance,
                fingerprint,
                error=exc,
                payload=data,
            )
            return self._failure_response(
                utterance,
                fingerprint,
                reason="Adapter response failed validation",
                adapter_error=str(exc),
            )

        validated = InterpretResponse.model_validate(data)
        LOGGER.info(
            "adapter_request_complete utterance=%s fingerprint=%s outcome=%s",
            utterance,
            fingerprint,
            validated.intent,
        )
        return validated

    def _build_signature(self, body: bytes) -> str | None:
        if not self._shared_secret:
            return None
        digest = hmac.new(
            self._shared_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return digest

    @staticmethod
    def _fingerprint_catalog(catalog: CatalogPayload) -> str:
        serialized = catalog.model_dump_json()
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _failure_response(
        self,
        utterance: str,
        fingerprint: str,
        *,
        reason: str,
        adapter_error: str,
    ) -> InterpretResponse:
        LOGGER.info(
            "adapter_request_complete utterance=%s fingerprint=%s outcome=noop adapter_error=%s",
            utterance,
            fingerprint,
            adapter_error,
        )
        return InterpretResponse(
            intent="noop",
            params={
                "reason": reason,
                "utterance": utterance,
            },
            confidence=0.0,
            adapter_error=adapter_error,
        )

    @staticmethod
    def _log_failure(
        utterance: str,
        fingerprint: str,
        *,
        error: Exception | str,
        status: int | None = None,
        payload: Any | None = None,
    ) -> None:
        parts = [
            f"adapter_failed utterance={utterance}",
            f"fingerprint={fingerprint}",
        ]
        if status is not None:
            parts.append(f"status={status}")
        parts.append(f"error={error}")
        if payload is not None:
            parts.append(f"payload={payload}")
        LOGGER.warning(" ".join(parts))

    @staticmethod
    def _normalize_intents(
        intents: Mapping[str, Mapping[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in (intents or {}).items()}

    def set_shared_secret(self, shared_secret: str | None) -> None:
        """Update the shared secret used for signing requests."""

        self._shared_secret = shared_secret or ""
