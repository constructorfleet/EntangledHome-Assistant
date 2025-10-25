# EntangledHome Adapter Service

The adapter microservice converts natural language utterances into structured intents that Home
Assistant can execute safely. It runs as a FastAPI application exposing `POST /interpret`.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ADAPTER_MODEL` | Identifier used by the model client (e.g., Ollama model name). |
| `QDRANT_HOST` | Qdrant host or hostname reachable from the adapter container. |
| `QDRANT_PORT` | Optional port override (defaults to `6333`). |
| `QDRANT_API_KEY` | API key with read/write access to required collections. |
| `QDRANT_GRPC` | Set to `true` to use the gRPC client, otherwise HTTP is used. |
| `EMBEDDING_MODEL` | Embedding model name for generating search vectors. |
| `OPENAI_BASE_URL` | Optional override for OpenAI-compatible endpoints. |
| `OPENAI_API_KEY` | API key used when calling OpenAI-compatible services. |
| `ADAPTER_SIGNATURE_SECRET` | Shared secret for signing responses back to Home Assistant. |

## Running the Adapter Service

```bash
uvicorn adapter_service.app:app \
  --host 0.0.0.0 \
  --port 8080
```

- Docker: `docker run --env-file .env -p 8080:8080 your-image`.
- Home Assistant communicates via HTTP; ensure firewalls expose port `8080` (or whichever you set).
- When running locally for development, install dependencies via `pip install -e .[adapter]` and use
  the provided pytest fixtures in `tests/stubs/` to feed sample catalogs.

## Expected Qdrant Schema

Create the following collections before deploying:

### `ha_entities`
- **Vector size**: match embedding output (e.g., 384).
- **Payload fields**:
  - `entity_id` (string)
  - `domain` (string)
  - `area_id` (string | null)
  - `device_id` (string | null)
  - `friendly_name` (string)
  - `capabilities` (object: booleans for `on_off`, `color`, `brightness`, etc.)
  - `aliases` (array of strings)

### `plex_media`
- **Vector size**: same as embedding model.
- **Payload fields**:
  - `rating_key` (string)
  - `title` (string)
  - `type` (string: `movie`, `episode`, `artist`, ...)
  - `year` (int | null)
  - `collection` (string | null)
  - `genres` (array of strings)
  - `actors` (array of strings)
  - `audio_language` (string | null)
  - `subtitles` (array of strings)

## Signature Configuration

When `ADAPTER_SIGNATURE_SECRET` is provided, Home Assistant signs outbound requests using an
HMAC-SHA256 digest of the payload. The adapter must:

1. Read the `X-Entangled-Signature` header and verify the digest before processing the request.
2. Sign the JSON response and include the same header so Home Assistant can validate it before
   executing actions.
3. Reject requests with missing or invalid signatures and emit audit logs.

This shared-secret scheme prevents tampering when the adapter is deployed on a different host.
