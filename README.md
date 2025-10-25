# EntangledHome - Assistant

Development scaffold for the EntangledHome Home Assistant custom component.

- Catch-all conversation agent for adapter-driven intents
- Optional catalog/Qdrant synchronisation utilities
- Secondary signal guardrails (person presence + recent voice profile)

## Development

1. Run the environment bootstrap script:
   ```bash
   scripts/setup_env.sh
   ```
2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
3. Run linters:
   ```bash
   ruff check
   ```
4. Execute the test suite:
   ```bash
   pytest
   ```

The development dependencies install pytest, pytest-homeassistant-custom-component, Ruff, and the FastAPI stack (FastAPI, Uvicorn, HTTPX) for adapter service work.

## Runtime dependencies

- `httpx>=0.28` is required for the integration runtime to talk to the Qdrant HTTP API and OpenAI-compatible embedding endpoints. It is installed automatically via `manifest.json`.

## Configuration

The integration reads service credentials from both the config entry and environment variables:

- `EMBEDDING_MODEL`, `EMBEDDING_CACHE_SIZE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `ENTANGLEDHOME_EMBEDDINGS_FALLBACK`
- `QDRANT_HOST`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT`, `QDRANT_BATCH_SIZE`, `QDRANT_MAX_RETRIES`

If a config option is absent or blank, the environment variable (when set) takes precedence. Missing Qdrant host configuration disables catalog upserts but logs a warning so the failure is visible in Home Assistant.

## Secondary signals

Sensitive intents (unlocking, opening, etc.) can demand extra signals before execution. The
conversation adapter advertises these by populating the `required_secondary_signals` list in its JSON
response. Two built-in signal names are available:

- `presence` &ndash; granted when at least one configured `person` entity is `home`. The provider also
  surfaces entity-scoped tokens such as `presence:person.alice` for fine-grained policies.
- `voice` &ndash; granted when a recently verified voice profile is recorded. Helpers emit
  `voice:<profile_id>` tokens so downstream code can confirm the recognized speaker.

### Adapter usage

When the adapter determines that additional proof is necessary it should set
`required_secondary_signals`, e.g. `{"required_secondary_signals": ["presence", "voice"]}`. The
conversation handler will block execution until all requested signals are present.

### Home Assistant configuration

Secondary signals are controlled via config entry options (UI or YAML overrides):

| Option key | Description |
|------------|-------------|
| `secondary_signals_presence_enabled` | Enable checks against `person.*` entities. |
| `secondary_signals_presence_entities` | List of entity IDs that prove presence. |
| `secondary_signals_voice_enabled` | Enable recent-voice detection guardrail. |
| `secondary_signals_voice_ttl_seconds` | Validity window for voice matches (default 30s). |

Voice profiles can be recorded by calling `record_voice_identifier(hass, entry_id, voice_id)` from
`custom_components.entangledhome.secondary_signals`. Integrations that process STT events can store
voice hits there so the guardrail becomes satisfied for the next few seconds.
