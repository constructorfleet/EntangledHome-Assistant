# Migration notes

This log highlights changes that require adjustments when upgrading the EntangledHome integration
or the adapter microservice.

## v0.5.0

### Breaking changes
- Guardrail defaults moved from YAML-only configuration to the options flow. Review the
  **Dangerous intents** and **Intent thresholds** fields after upgrading.
- Adapter requests now include an `intents` object. Ensure custom adapters accept the new field.

### Deprecated
- `guardrails.secondary_signals.voice_profiles` has been replaced with dynamic telemetry tokens.
  Update automations that referenced the legacy setting.
- The `scripts/bootstrap_qdrant.py` helper has been superseded by `scripts/ingest_entities.py` and
  `scripts/ingest_plex.py`.

### Recommended actions
- Re-run the ingestion scripts to repopulate payload metadata with the latest schema fields.
- Audit custom intents for `dangerous: true` flags and confirm they have matching secondary signals.
