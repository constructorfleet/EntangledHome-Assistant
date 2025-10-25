"""Shared data models for EntangledHome adapter communication."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


__all__ = [
    "CatalogArea",
    "CatalogEntity",
    "CatalogScene",
    "PlexMediaItem",
    "CatalogPayload",
    "InterpretRequest",
    "InterpretResponse",
]

class CatalogArea(BaseModel):
    """Descriptor for a Home Assistant area."""

    model_config = ConfigDict(extra="forbid")

    area_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class CatalogEntity(BaseModel):
    """Descriptor for an individual Home Assistant entity."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    domain: str
    area_id: str | None = None
    device_id: str | None = None
    friendly_name: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)


class CatalogScene(BaseModel):
    """Descriptor for a Home Assistant scene."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class PlexMediaItem(BaseModel):
    """Descriptor for a Plex media library item."""

    model_config = ConfigDict(extra="forbid")

    rating_key: str
    title: str
    type: str
    year: int | None = None
    collection: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    audio_language: str | None = None
    subtitles: list[str] = Field(default_factory=list)


class CatalogPayload(BaseModel):
    """Aggregated catalog payload provided to the adapter."""

    model_config = ConfigDict(extra="forbid")

    areas: list[CatalogArea] = Field(default_factory=list)
    entities: list[CatalogEntity] = Field(default_factory=list)
    scenes: list[CatalogScene] = Field(default_factory=list)
    plex_media: list[PlexMediaItem] = Field(default_factory=list)


class InterpretRequest(BaseModel):
    """Request payload sent to the adapter service."""

    model_config = ConfigDict(extra="forbid")

    utterance: str
    catalog: CatalogPayload
    intents: dict[str, dict[str, Any]] = Field(default_factory=dict)


class InterpretResponse(BaseModel):
    """Structured interpretation returned from the adapter service."""

    model_config = ConfigDict(extra="forbid")

    intent: str
    area: str | None = None
    targets: list[str] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    sensitive: bool = False
    required_secondary_signals: list[str] = Field(default_factory=list)
    qdrant_terms: list[str] = Field(default_factory=list)
    adapter_error: str | None = None
