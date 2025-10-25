"""Model client responsible for streaming interpret responses."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
from pydantic import ValidationError

from .schema import InterpretResponse


Requester = Callable[[dict[str, Any]], AsyncIterator[str]]
Repairer = Callable[[dict[str, Any]], Awaitable[InterpretResponse | dict[str, Any] | None]]


class ModelClient:
    """Stream InterpretResponse objects from an LLM backend."""

    def __init__(
        self,
        *,
        model: str,
        timeout: float = 1.5,
        base_url: str | None = None,
        api_key: str | None = None,
        requester: Requester | None = None,
        repairer: Repairer | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._requester = requester
        self._repairer = repairer

    async def stream(
        self,
        *,
        utterance: str,
        prompt: dict[str, Any],
        threshold: float,
    ) -> AsyncIterator[InterpretResponse]:
        if not self._model:
            return

        payload = self._build_payload(utterance, prompt)
        async for response in self._collect(payload):
            yield response
            if response.confidence >= threshold:
                break

    async def repair(
        self,
        *,
        utterance: str,
        prompt: dict[str, Any],
        raw: Any,
    ) -> InterpretResponse | dict[str, Any] | None:
        if self._repairer is None:
            return None

        payload = {
            "utterance": utterance,
            "prompt": prompt,
            "raw": raw,
        }
        return await self._repairer(payload)

    def _build_payload(self, utterance: str, prompt: dict[str, Any]) -> dict[str, Any]:
        serialized_prompt = json.dumps(
            {"utterance": utterance, "context": prompt},
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return {
            "model": self._model,
            "stream": True,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Home Assistant adapter. Respond with JSON that "
                        "matches the InterpretResponse schema."
                    ),
                },
                {
                    "role": "user",
                    "content": serialized_prompt,
                },
            ],
        }

    async def _collect(
        self, payload: dict[str, Any]
    ) -> AsyncIterator[InterpretResponse | None]:
        buffer = ""
        async for chunk in self._request(payload):
            buffer += chunk
            lines = buffer.split("\n")
            buffer = lines.pop() if lines else ""
            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    continue
                parsed = self._parse_json(line)
                if parsed is None:
                    continue
                validated = self._validate_response(parsed)
                if validated is not None:
                    yield validated

    async def _request(self, payload: dict[str, Any]) -> AsyncIterator[str]:
        if self._requester is not None:
            async for chunk in self._requester(payload):
                yield chunk
            return

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    "/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for text in response.aiter_text():
                        yield text
        except httpx.HTTPError:
            return

    def _parse_json(self, data: str) -> dict[str, Any] | None:
        candidate = data.strip()
        if not candidate:
            return None

        for _ in range(2):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                start = candidate.find("{")
                end = candidate.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    return None
                candidate = candidate[start : end + 1]
        return None

    def _validate_response(self, payload: dict[str, Any]) -> InterpretResponse | None:
        normalized = dict(payload)
        confidence = normalized.get("confidence", 0.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        normalized["confidence"] = max(0.0, min(1.0, confidence_value))

        params = normalized.get("params")
        if not isinstance(params, dict):
            normalized["params"] = {}

        try:
            return InterpretResponse.model_validate(normalized)
        except ValidationError:
            return None
