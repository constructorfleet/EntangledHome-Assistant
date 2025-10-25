"""Tests for guardrail configuration normalization edge cases."""

from __future__ import annotations

import json

from custom_components.entangledhome.conversation import GuardrailBundle
from custom_components.entangledhome.const import (
    OPT_ALLOWED_HOURS,
    OPT_DANGEROUS_INTENTS,
    OPT_DISABLED_INTENTS,
    OPT_INTENT_THRESHOLDS,
    OPT_RECENT_COMMAND_WINDOW_OVERRIDES,
)


def test_guardrail_bundle_parses_json_strings() -> None:
    """JSON-encoded guardrail fields should be parsed into native structures."""

    bundle = GuardrailBundle.from_mapping(
        {
            OPT_INTENT_THRESHOLDS: json.dumps({"scene_activate": "0.9", "media_play": 0.8}),
            OPT_DISABLED_INTENTS: json.dumps(["noop", "media_pause"]),
            OPT_DANGEROUS_INTENTS: json.dumps(["unlock_door"]),
            OPT_ALLOWED_HOURS: json.dumps({"scene_activate": {"start": 22, "end": 6}}),
            OPT_RECENT_COMMAND_WINDOW_OVERRIDES: json.dumps({"scene_activate": "2.5"}),
        }
    )

    assert bundle.intent_thresholds == {"scene_activate": 0.9, "media_play": 0.8}
    assert bundle.disabled_intents == {"noop", "media_pause"}
    assert bundle.dangerous_intents == {"unlock_door"}
    assert bundle.allowed_hours == {"scene_activate": (22, 6)}
    assert bundle.recent_command_windows == {"scene_activate": 2.5}
