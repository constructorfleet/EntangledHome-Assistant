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


async def _yield_chunks(responses):
    for response in responses:
        yield response


def test_interpret_streaming_cache_and_metrics(monkeypatch):
    import importlib

    from adapter_service.schema import InterpretRequest, InterpretResponse

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

    class FakeStreamer:
        def __init__(self):
            self.calls = []

        async def stream(self, utterance, catalog_slice, settings):
            self.calls.append((utterance, catalog_slice, settings))
            async for chunk in _yield_chunks(
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
                    InterpretResponse(
                        intent="should_not_emit",
                        params={"stage": 3},
                        confidence=0.9,
                    ),
                ]
            ):
                yield chunk
            pytest.fail("stream consumed beyond confidence threshold")

    fake_streamer = FakeStreamer()
    monkeypatch.setattr(main, "_MODEL_STREAMER", fake_streamer, raising=False)

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

    first_response = client.post(
        "/interpret", json=request_payload.model_dump(mode="json")
    )

    assert first_response.status_code == 200
    body = InterpretResponse.model_validate(first_response.json())
    assert body.intent == "lights_on"
    assert body.area == "living_room"
    assert body.params == {"stage": 2}
    assert len(fake_streamer.calls) == 1

    assert len(build_calls) == 1
    assert main.METRICS["interpret"][-1]["total_ms"] == pytest.approx(5.0)
    assert main.SETTINGS.model_timeout_s == pytest.approx(3.5)

    second_payload = request_payload.model_copy()
    second_payload.catalog = request_payload.catalog.model_copy()
    second_payload.catalog.areas[0].name = "Upstairs"

    second_response = client.post(
        "/interpret", json=second_payload.model_dump(mode="json")
    )

    assert second_response.status_code == 200
    assert len(build_calls) == 1

    for idx, utterance in enumerate(["movie time", "play some jazz"]):
        extra_payload = InterpretRequest(
            utterance=utterance,
            catalog=request_payload.catalog,
        )
        result = client.post(
            "/interpret", json=extra_payload.model_dump(mode="json")
        )
        assert result.status_code == 200
        assert len(build_calls) == idx + 2

    third_response = client.post(
        "/interpret", json=request_payload.model_dump(mode="json")
    )

    assert third_response.status_code == 200
    assert len(build_calls) == 4
