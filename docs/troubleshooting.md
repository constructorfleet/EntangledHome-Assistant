# Troubleshooting

Use this guide to diagnose common runtime issues with the EntangledHome integration, adapter
service, and Qdrant pipeline.

## Common issues
- **Integration fails to load** &ndash; Confirm the adapter URL and Qdrant host are reachable from the
  Home Assistant container. Review `home-assistant.log` for configuration validation errors.
- **Options flow rejects JSON** &ndash; Validate that the `Intent routing configuration` JSON is a mapping
  of intent IDs to objects. Quotes around keys and trailing commas are the usual culprits.

## Adapter connectivity
- Run `uv run python scripts/ingest_entities.py --dry-run` to verify credentials without mutating
  Qdrant data.
- Use `curl -X POST http://adapter:8080/interpret` with a sample payload from
  `tests/stubs/catalog.json` to ensure the adapter responds within the expected timeout.
- Enable HTTP logging on the adapter to capture signature validation failures.

## Qdrant ingestion
- **Rejected payloads** &ndash; Compare the payload schema to the definitions in `adapter_service/README.md`.
  Qdrant errors will include the offending field name.
- **Missing vectors** &ndash; Ensure the environment exposes the embedding model (e.g., `BGE_SMALL_MODEL`).
  The ingestion scripts fallback to zero vectors only during initial scaffolding.
- **Stale catalog data** &ndash; Schedule the ingestion scripts via cron or Home Assistant Automations to
  keep entities synchronized.
