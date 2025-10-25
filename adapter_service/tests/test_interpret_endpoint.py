import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapter_service.schema import InterpretResponse


SHARED_SECRET = "test-shared-secret"


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.25 for _ in range(3)]]


class FakeQdrantClient:
    def __init__(self, results: dict[str, list[dict[str, Any]]]) -> None:
        self._results = results
        self.search_calls: list[tuple[str, list[float], int, float]] = []

    async def search(
        self,
        collection: str,
        vector: list[float],
        *,
        limit: int,
        timeout: float,
    ) -> list[dict[str, Any]]:
        self.search_calls.append((collection, list(vector), limit, timeout))
        return list(self._results.get(collection, []))


class FakeModelClient:
    def __init__(self, responses: list[InterpretResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any], float]] = []

    async def stream(
        self,
        *,
        utterance: str,
        prompt: dict[str, Any],
        threshold: float,
    ):
        self.calls.append((utterance, prompt, threshold))
        for response in self._responses:
            yield response


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("ADAPTER_MODEL", "mock-model")
    monkeypatch.setenv("QDRANT_HOST", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")
    monkeypatch.setenv("ADAPTER_SHARED_SECRET", SHARED_SECRET)


def _post_with_signature(client: TestClient, payload: dict, secret: str):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Entangled-Signature": signature,
    }
    return client.post("/interpret", data=body, headers=headers)


def test_interpret_endpoint_returns_valid_response(monkeypatch):
    import importlib

    from adapter_service.schema import InterpretRequest

    import adapter_service.main as main

    importlib.reload(main)

    fake_embeddings = FakeEmbeddingService()
    fake_qdrant = FakeQdrantClient({"ha_entities": [], "plex_media": []})
    fallback = InterpretResponse(
        intent="noop",
        params={"reason": "adapter unavailable"},
        confidence=0.12,
    )
    fake_model = FakeModelClient([fallback])

    monkeypatch.setattr(
        main,
        "_MODEL_STREAMER",
        main.StreamingModel(
            settings=main.SETTINGS,
            embedding_service=fake_embeddings,
            qdrant_client=fake_qdrant,
            model_client=fake_model,
            top_k=4,
        ),
        raising=False,
    )

    client = TestClient(main.app)

    request_payload = InterpretRequest(
        utterance="turn on the living room lights",
        catalog={
            "areas": [
                {
                    "area_id": "living_room",
                    "name": "Living Room",
                    "aliases": ["lounge"],
                }
            ],
            "entities": [],
            "scenes": [],
            "plex_media": [],
        },
    )

    response = _post_with_signature(
        client, request_payload.model_dump(mode="json"), SHARED_SECRET
    )

    assert response.status_code == 200

    body = InterpretResponse.model_validate(response.json())
    assert body.intent == "noop"
    assert body.params["reason"] == "adapter unavailable"
    assert fake_embeddings.calls == [["turn on the living room lights"]]
    assert [call[0] for call in fake_qdrant.search_calls] == ["ha_entities", "plex_media"]


def test_interpret_streaming_cache_and_metrics(monkeypatch):
    import importlib

    from adapter_service.schema import InterpretRequest

    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.8")
    monkeypatch.setenv("MODEL_TIMEOUT_S", "3.5")
    monkeypatch.setenv("CATALOG_CACHE_SIZE", "2")

    import adapter_service.main as main

    importlib.reload(main)

    build_calls = []

    def fake_build_catalog_slice(catalog):
        build_calls.append(catalog)
        return {"areas": [area.name for area in catalog.areas]}

    monkeypatch.setattr(
        main,
        "_build_catalog_slice",
        fake_build_catalog_slice,
        raising=False,
    )

    fake_embeddings = FakeEmbeddingService()
    fake_qdrant = FakeQdrantClient(
        {
            "ha_entities": [
                {
                    "payload": {
                        "entity_id": "light.living_room_lamp",
                        "friendly_name": "Living Room Lamp",
                        "area_id": "living_room",
                    }
                }
            ],
            "plex_media": [
                {
                    "payload": {
                        "rating_key": "movie-night",
                        "title": "Movie Night",
                        "type": "movie",
                    }
                }
            ],
        }
    )
    fake_model = FakeModelClient(
        [
            InterpretResponse(
                intent="noop",
                params={"stage": 1},
                confidence=0.5,
            ),
            InterpretResponse(
                intent="lights_on",
                area="living_room",
                params={"stage": 2},
                confidence=0.86,
            ),
        ]
    )

    monkeypatch.setattr(
        main,
        "_MODEL_STREAMER",
        main.StreamingModel(
            settings=main.SETTINGS,
            embedding_service=fake_embeddings,
            qdrant_client=fake_qdrant,
            model_client=fake_model,
            top_k=4,
        ),
        raising=False,
    )

    durations = [10.0, 10.002, 10.005]

    def fake_now():
        if durations:
            return durations.pop(0)
        return 10.005

    monkeypatch.setattr(main, "_now", fake_now, raising=False)

    client = TestClient(main.app)

    request_payload = InterpretRequest(
        utterance="  Turn ON   the Living Room Lights  ",
        catalog={
            "areas": [
                {
                    "area_id": "living_room",
                    "name": "Living Room",
                    "aliases": ["lounge"],
                }
            ],
            "entities": [],
            "scenes": [],
            "plex_media": [],
        },
    )

    first_response = _post_with_signature(
        client, request_payload.model_dump(mode="json"), SHARED_SECRET
    )

    assert first_response.status_code == 200
    body = InterpretResponse.model_validate(first_response.json())
    assert body.intent == "lights_on"
    assert body.area == "living_room"
    assert body.params == {"stage": 2}

    assert len(fake_embeddings.calls) == 1
    assert [call[0] for call in fake_qdrant.search_calls] == [
        "ha_entities",
        "plex_media",
    ]
    assert fake_model.calls[0][0] == "  Turn ON   the Living Room Lights  "
    prompt = fake_model.calls[0][1]
    assert prompt["catalog"] == {"areas": ["Living Room"]}
    assert prompt["retrieved"]["ha_entities"][0]["payload"]["friendly_name"] == "Living Room Lamp"
    assert prompt["retrieved"]["plex_media"][0]["payload"]["title"] == "Movie Night"
    assert fake_model.calls[0][2] == pytest.approx(0.8)

    assert len(build_calls) == 1
    assert main.METRICS["interpret"][-1]["total_ms"] == pytest.approx(5.0)
    assert main.SETTINGS.model_timeout_s == pytest.approx(3.5)

    second_payload = request_payload.model_copy()
    second_payload.catalog = request_payload.catalog.model_copy()
    second_payload.catalog.areas[0].name = "Upstairs"

    second_response = _post_with_signature(
        client, second_payload.model_dump(mode="json"), SHARED_SECRET
    )

    assert second_response.status_code == 200
    assert len(build_calls) == 1
    assert len(fake_qdrant.search_calls) == 4

    for idx, utterance in enumerate(["movie time", "play some jazz"]):
        extra_payload = InterpretRequest(
            utterance=utterance,
            catalog=request_payload.catalog,
        )
        result = _post_with_signature(
            client, extra_payload.model_dump(mode="json"), SHARED_SECRET
        )
        assert result.status_code == 200
        assert len(build_calls) == idx + 2

    third_response = _post_with_signature(
        client, request_payload.model_dump(mode="json"), SHARED_SECRET
    )

    assert third_response.status_code == 200
    assert len(build_calls) == 4


def test_interpret_endpoint_rejects_invalid_signature():
    from adapter_service.main import app
    from adapter_service.schema import InterpretRequest

    client = TestClient(app)

    request_payload = InterpretRequest(
        utterance="unlock the door",
        catalog={
            "areas": [],
            "entities": [],
            "scenes": [],
            "plex_media": [],
        },
    )

    body = json.dumps(
        request_payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    headers = {
        "Content-Type": "application/json",
        "X-Entangled-Signature": "deadbeef",
    }

    response = client.post("/interpret", data=body, headers=headers)

    assert response.status_code == 401
