from custom_components.entangledhome.telemetry import TelemetryRecorder


class TestTelemetryRecorder:
    """TelemetryRecorder behaviors."""

    def test_validates_payloads_and_truncates(self) -> None:
        """Recorded events should validate via models and enforce max size."""

        recorder = TelemetryRecorder(max_events=2)

        first = recorder.record_event(
            utterance="turn on the lights",
            qdrant_terms=["light", "living room"],
            response={
                "intent": "turn_on",
                "area": "living_room",
                "targets": ["light.living_room"],
                "params": {"reason": "party"},
                "confidence": 0.91,
            },
            duration_ms=123.4,
            outcome="executed",
        )
        assert first.response.intent == "turn_on"
        assert first.response.confidence == 0.91

        recorder.record_event(
            utterance="dim the hallway",
            qdrant_terms=["dimmer"],
            response={
                "intent": "set_brightness",
                "area": "hallway",
                "targets": ["light.hallway"],
                "params": {"brightness": 25},
                "confidence": 0.76,
            },
            duration_ms=87.0,
            outcome="executed",
        )

        recorder.record_event(
            utterance="stop music",
            qdrant_terms=["media", "pause"],
            response={
                "intent": "media_pause",
                "area": None,
                "targets": ["media_player.living_room"],
                "params": {},
                "confidence": 0.84,
            },
            duration_ms=64.5,
            outcome="executed",
        )

        events = list(recorder.iter_recent())
        assert len(events) == 2
        assert [event.utterance for event in events] == [
            "dim the hallway",
            "stop music",
        ]
        assert events[-1].duration_ms == 64.5
        assert events[-1].response.intent == "media_pause"
