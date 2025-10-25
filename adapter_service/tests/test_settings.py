"""Tests for adapter service settings loading."""

from __future__ import annotations

import importlib


def test_load_settings_rejects_non_positive_timeouts(monkeypatch) -> None:
    """Timeout environment variables should fall back when non-positive."""

    monkeypatch.setenv("MODEL_TIMEOUT_S", "-1")
    monkeypatch.setenv("QDRANT_TIMEOUT_S", "0")
    monkeypatch.setenv("ADAPTER_TIMEOUT_S", "-3")
    monkeypatch.setenv("CATALOG_CACHE_SIZE", "-10")

    import adapter_service.main as main

    importlib.reload(main)
    settings = main._load_settings()

    assert settings.model_timeout_s == 1.5
    assert settings.qdrant_timeout_s == 0.4
    assert settings.adapter_timeout_s == 2.0
    assert settings.catalog_cache_size == 256
