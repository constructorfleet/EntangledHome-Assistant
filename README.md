# EntangledHome - Assistant

Development scaffold for the EntangledHome Home Assistant custom component.

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
