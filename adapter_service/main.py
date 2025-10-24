"""FastAPI application exposing the adapter interpret endpoint."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI

from .schema import InterpretRequest, InterpretResponse


@dataclass(frozen=True)
class Settings:
    """Adapter configuration derived from environment variables."""

    model: str | None
    qdrant_host: str | None
    qdrant_api_key: str | None


def _load_settings() -> Settings:
    """Load adapter configuration from environment variables."""

    return Settings(
        model=os.getenv("ADAPTER_MODEL"),
        qdrant_host=os.getenv("QDRANT_HOST"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
    )


SETTINGS: Final[Settings] = _load_settings()
app = FastAPI()


@app.post("/interpret", response_model=InterpretResponse)
async def interpret(payload: InterpretRequest) -> InterpretResponse:
    """Return a placeholder interpretation until the adapter is implemented."""

    return InterpretResponse(
        intent="noop",
        area=None,
        targets=None,
        params={"reason": "Adapter not implemented", "utterance": payload.utterance},
        confidence=0.0,
    )
