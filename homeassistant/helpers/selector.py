"""Minimal selector stubs mimicking Home Assistant interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import voluptuous as vol


class Selector:
    """Base selector providing a callable contract."""

    config: object | None

    def __call__(self, value: Any) -> Any:  # pragma: no cover - simple passthrough
        return value


@dataclass(frozen=True, slots=True)
class TextSelectorConfig:
    """Configuration for textual selectors."""

    multiline: bool = False
    type: str | None = None


class TextSelector(Selector):
    """Selector representing textual input."""

    def __init__(self, config: TextSelectorConfig | None = None) -> None:
        self.config = config or TextSelectorConfig()

    def __call__(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)


class BooleanSelector(Selector):
    """Selector that coerces values into booleans."""

    def __init__(self) -> None:
        self.config = None

    def __call__(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "on", "yes"}:
                return True
            if normalized in {"false", "0", "off", "no"}:
                return False
        return bool(value)


class NumberSelectorMode(str, Enum):
    """Modes for numeric selectors."""

    BOX = "box"
    SLIDER = "slider"


@dataclass(frozen=True, slots=True)
class NumberSelectorConfig:
    """Configuration payload for numeric selectors."""

    min: float | None = None
    max: float | None = None
    step: float | None = None
    mode: NumberSelectorMode | None = None
    unit_of_measurement: str | None = None


class NumberSelector(Selector):
    """Selector enforcing numeric bounds."""

    def __init__(self, config: NumberSelectorConfig | None = None) -> None:
        self.config = config or NumberSelectorConfig()

    def __call__(self, value: Any) -> float:
        if isinstance(value, bool):
            raise vol.Invalid("Boolean is not a valid number")
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise vol.Invalid("Expected a numeric value")
            try:
                number = float(stripped)
            except ValueError as exc:  # pragma: no cover - validation path
                raise vol.Invalid("Expected a numeric value") from exc
        else:
            raise vol.Invalid("Expected a numeric value")

        minimum = self.config.min
        maximum = self.config.max
        if minimum is not None and number < minimum:
            raise vol.Invalid("Value is below the allowed minimum")
        if maximum is not None and number > maximum:
            raise vol.Invalid("Value is above the allowed maximum")
        return number


__all__ = [
    "BooleanSelector",
    "NumberSelector",
    "NumberSelectorConfig",
    "NumberSelectorMode",
    "Selector",
    "TextSelector",
    "TextSelectorConfig",
]
