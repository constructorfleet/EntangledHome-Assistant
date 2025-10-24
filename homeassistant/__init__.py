"""Minimal stubs for Home Assistant core interfaces used in tests."""

from .config_entries import ConfigEntry  # noqa: F401
from .core import HomeAssistant  # noqa: F401

__all__ = ["ConfigEntry", "HomeAssistant"]
