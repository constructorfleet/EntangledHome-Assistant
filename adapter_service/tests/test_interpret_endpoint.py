import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("ADAPTER_MODEL", "mock-model")
    monkeypatch.setenv("QDRANT_HOST", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")


def test_interpret_endpoint_returns_valid_response():
    from adapter_service.main import app
    from adapter_service.schema import InterpretRequest, InterpretResponse

    client = TestClient(app)

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

    response = client.post("/interpret", json=request_payload.model_dump())

    assert response.status_code == 200

    body = InterpretResponse.model_validate(response.json())
    assert body.intent == "noop"
    assert body.params
