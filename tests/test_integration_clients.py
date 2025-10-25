from __future__ import annotations

from types import ModuleType

import pytest

from homeassistant.config_entries import ConfigEntry


@pytest.mark.asyncio
@pytest.mark.usefixtures("monkeypatch")
async def test_build_embedder_uses_embedding_service(monkeypatch) -> None:
    """Embedder wrapper should delegate to EmbeddingService and return vectors."""

    import custom_components.entangledhome as integration

    created: dict[str, object] = {}

    class FakeEmbeddingService:
        def __init__(self, *, model: str, cache_size: int = 256, backend=None) -> None:
            created["model"] = model
            created["cache_size"] = cache_size
            created["backend"] = backend

        async def embed(self, texts: list[str]) -> list[list[float]]:
            created["texts"] = list(texts)
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setenv("EMBEDDING_MODEL", "custom-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "custom_components.entangledhome.embeddings.EmbeddingService",
        FakeEmbeddingService,
    )

    entry = ConfigEntry(entry_id="embed-entry", options={})
    entry.data = {}

    embed_texts = integration._build_embedder(entry)
    result = await embed_texts(["hello world"])

    assert created["model"] == "custom-model"
    assert created["cache_size"] == 256
    assert created["backend"] is None
    assert created["texts"] == ["hello world"]
    assert result == [[0.1, 0.2, 0.3]]


@pytest.mark.asyncio
@pytest.mark.usefixtures("monkeypatch")
async def test_build_qdrant_upsert_posts_batches(monkeypatch, caplog) -> None:
    """Qdrant upsert helper should post batches to the configured endpoint."""

    import custom_components.entangledhome as integration
    from custom_components.entangledhome.const import CONF_QDRANT_API_KEY, CONF_QDRANT_HOST

    requests: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *, base_url: str, headers: dict[str, str], timeout: float) -> None:
            requests.append(("__init__", {"base_url": base_url, "headers": headers, "timeout": timeout}))

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            await self.aclose()

        async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
            requests.append((path, json))
            return FakeResponse()

        async def aclose(self) -> None:
            requests.append(("close", {}))

    monkeypatch.setenv("QDRANT_MAX_RETRIES", "1")
    httpx_stub = ModuleType("httpx")
    httpx_stub.AsyncClient = FakeClient
    httpx_stub.HTTPError = Exception
    monkeypatch.setattr(integration, "httpx", httpx_stub)

    entry = ConfigEntry(entry_id="qdrant-entry", options={})
    entry.data = {CONF_QDRANT_HOST: "https://qdrant.example", CONF_QDRANT_API_KEY: "token"}

    upsert = integration._build_qdrant_upsert(entry)

    points = [
        {"id": 1, "vector": [0.4, 0.5], "payload": {"name": "one"}},
        {"id": 2, "vector": [0.6, 0.7], "payload": {"name": "two"}},
    ]

    await upsert("ha_entities", points)

    assert requests[0] == (
        "__init__",
        {
            "base_url": "https://qdrant.example",
            "headers": {"api-key": "token"},
            "timeout": pytest.approx(10.0),
        },
    )
    assert requests[1][0] == "/collections/ha_entities/points/upsert"
    payload = requests[1][1]
    assert payload["points"][0]["vector"] == [0.4, 0.5]
    assert payload["points"][1]["vector"] == [0.6, 0.7]
    assert any(record.levelname == "ERROR" for record in caplog.records) is False
