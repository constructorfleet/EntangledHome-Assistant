"""Constants for the EntangledHome integration."""

DOMAIN = "entangledhome"
TITLE = "EntangledHome"
DEFAULT_CATALOG_SYNC = True
DEFAULT_CONFIDENCE_GATE = False
DEFAULT_REFRESH_INTERVAL_MINUTES = 5
DEFAULT_PLEX_SYNC = True
DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_NIGHT_MODE_ENABLED = False
DEFAULT_NIGHT_MODE_START_HOUR = 23
DEFAULT_NIGHT_MODE_END_HOUR = 6
DEFAULT_DEDUPLICATION_WINDOW = 2.0
DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS = 30.0
DATA_TELEMETRY = "telemetry"

DEFAULT_INTENT_THRESHOLDS: dict[str, float] = {}
DEFAULT_DISABLED_INTENTS: tuple[str, ...] = ()
DEFAULT_DANGEROUS_INTENTS: tuple[str, ...] = ()
DEFAULT_ALLOWED_HOURS: dict[str, list[int]] = {}
DEFAULT_RECENT_COMMAND_WINDOW_OVERRIDES: dict[str, float] = {}
DEFAULT_INTENTS_CONFIG: dict[str, dict[str, object]] = {
    "turn_on": {"enabled": True, "slots": ["targets", "area"]},
    "turn_off": {"enabled": True, "slots": ["targets", "area"]},
    "scene_activate": {"enabled": True, "slots": ["scene", "area"]},
    "media_play": {"enabled": True, "slots": ["media", "targets"]},
    "set_brightness": {"enabled": True, "slots": ["targets", "brightness", "area"]},
}

CONF_ADAPTER_URL = "adapter_url"
CONF_QDRANT_HOST = "qdrant_host"
CONF_QDRANT_API_KEY = "qdrant_api_key"
OPT_ENABLE_CATALOG_SYNC = "enable_catalog_sync"
OPT_ENABLE_CONFIDENCE_GATE = "enable_confidence_gate"
OPT_REFRESH_INTERVAL_MINUTES = "refresh_interval_minutes"
OPT_ENABLE_PLEX_SYNC = "enable_plex_sync"
OPT_CONFIDENCE_THRESHOLD = "confidence_threshold"
OPT_NIGHT_MODE_ENABLED = "night_mode_enabled"
OPT_NIGHT_MODE_START_HOUR = "night_mode_start_hour"
OPT_NIGHT_MODE_END_HOUR = "night_mode_end_hour"
OPT_DEDUPLICATION_WINDOW = "deduplication_window_seconds"
OPT_ADAPTER_SHARED_SECRET = "adapter_shared_secret"
OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED = "secondary_signals_presence_enabled"
OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES = "secondary_signals_presence_entities"
OPT_SECONDARY_SIGNAL_VOICE_ENABLED = "secondary_signals_voice_enabled"
OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS = "secondary_signals_voice_ttl_seconds"
OPT_INTENT_THRESHOLDS = "intent_thresholds"
OPT_DISABLED_INTENTS = "disabled_intents"
OPT_DANGEROUS_INTENTS = "dangerous_intents"
OPT_ALLOWED_HOURS = "intent_allowed_hours"
OPT_RECENT_COMMAND_WINDOW_OVERRIDES = "intent_recent_command_windows"
OPT_INTENTS_CONFIG = "intents_config"

DEFAULT_OPTION_VALUES = (
    (OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC),
    (OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE),
    (OPT_REFRESH_INTERVAL_MINUTES, DEFAULT_REFRESH_INTERVAL_MINUTES),
    (OPT_ENABLE_PLEX_SYNC, DEFAULT_PLEX_SYNC),
    (OPT_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD),
    (OPT_NIGHT_MODE_ENABLED, DEFAULT_NIGHT_MODE_ENABLED),
    (OPT_NIGHT_MODE_START_HOUR, DEFAULT_NIGHT_MODE_START_HOUR),
    (OPT_NIGHT_MODE_END_HOUR, DEFAULT_NIGHT_MODE_END_HOUR),
    (OPT_DEDUPLICATION_WINDOW, DEFAULT_DEDUPLICATION_WINDOW),
    (OPT_ADAPTER_SHARED_SECRET, ""),
    (OPT_INTENT_THRESHOLDS, DEFAULT_INTENT_THRESHOLDS),
    (OPT_DISABLED_INTENTS, DEFAULT_DISABLED_INTENTS),
    (OPT_DANGEROUS_INTENTS, DEFAULT_DANGEROUS_INTENTS),
    (OPT_ALLOWED_HOURS, DEFAULT_ALLOWED_HOURS),
    (OPT_RECENT_COMMAND_WINDOW_OVERRIDES, DEFAULT_RECENT_COMMAND_WINDOW_OVERRIDES),
    (OPT_INTENTS_CONFIG, DEFAULT_INTENTS_CONFIG),
)
