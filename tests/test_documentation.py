"""Documentation guardrail tests."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from tests.stubs.homeassistant.config_entries import ConfigEntry
from tests.stubs.homeassistant.core import HomeAssistant


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains(text: str, markers: list[str]) -> None:
    for marker in markers:
        assert marker in text


def test_readme_and_adapter_docs_cover_required_sections() -> None:
    readme = _read_text(REPO_ROOT / "README.md")
    _assert_contains(
        readme,
        [
            "## Architecture Overview",
            "## Setup",
            "### Home Assistant Configuration",
            "### Adapter Service Deployment",
            "### Qdrant Requirements",
            "## Guardrails and Security",
            "## Testing",
            "## Conversation Sentences",
            "catch-all intent",
            "sentence overrides",
        ],
    )

    adapter_readme_path = REPO_ROOT / "adapter_service" / "README.md"
    assert adapter_readme_path.exists()
    adapter_readme = _read_text(adapter_readme_path)
    _assert_contains(
        adapter_readme,
        [
            "## Environment Variables",
            "## Running the Adapter Service",
            "## Expected Qdrant Schema",
            "## Signature Configuration",
        ],
    )

    documentation_manifest = json.loads(
        _read_text(
            REPO_ROOT
            / "custom_components"
            / "entangledhome"
            / "manifest.json"
        )
    )
    assert (
        documentation_manifest.get("documentation")
        == "https://github.com/ConstructorFleet/EntangledHome-Assistant"
    )

    example_config = REPO_ROOT / "docs" / "examples" / "homeassistant_configuration.yaml"
    assert example_config.exists()
    assert "entangledhome:" in _read_text(example_config)

    sentences_doc = REPO_ROOT / "docs" / "sentences.md"
    assert sentences_doc.exists()
    sentences_copy = _read_text(sentences_doc)
    _assert_contains(
        sentences_copy,
        [
            "override templates",
            "catch-all",
            "custom_components/entangledhome/sentences/en",
        ],
    )


def test_readme_documents_configurable_intents_and_guardrails() -> None:
    readme = _read_text(REPO_ROOT / "README.md")
    _assert_contains(
        readme,
        [
            "## Configurable intents",
            "### YAML configuration example",
            "### UI configuration walkthrough",
            "## Sentence customization",
            "## Guardrail thresholds and dangerous intents",
            "## Qdrant ingestion scripts",
            "## Adapter deployment",
            "## Migration notes",
            "## Troubleshooting",
        ],
    )

    examples_dir = REPO_ROOT / "docs" / "examples"
    for example_path in (examples_dir / "intents.yaml", examples_dir / "sentences.en.yaml"):
        assert example_path.exists()

    doc_checks = {
        REPO_ROOT / "docs" / "migration.md": [
            "# Migration notes",
            "Deprecated",
            "Breaking changes",
        ],
        REPO_ROOT / "docs" / "troubleshooting.md": [
            "# Troubleshooting",
            "Common issues",
            "Adapter connectivity",
            "Qdrant ingestion",
        ],
    }

    for path, markers in doc_checks.items():
        _assert_contains(_read_text(path), markers)


def test_sentence_override_wins_on_reload(tmp_path: Path) -> None:
    """Custom sentence templates should override packaged defaults after reload."""

    DOMAIN = "entangledhome"
    class _HttpxAsyncClient:  # pragma: no cover - stub methods unused in test
        def __init__(self, *args, **kwargs) -> None:
            self._closed = False

        async def post(self, *args, **kwargs):  # pragma: no cover - defensive stub
            raise RuntimeError("httpx.AsyncClient.post should not be called in this test")

        async def aclose(self) -> None:
            self._closed = True

    sys.modules.setdefault(
        "httpx",
        SimpleNamespace(AsyncClient=_HttpxAsyncClient, Timeout=object, HTTPError=Exception),
    )

    import custom_components.entangledhome as integration

    hass = HomeAssistant()
    hass.config = SimpleNamespace(
        path=lambda *parts: str(tmp_path.joinpath(*parts))
    )
    hass.config_entries = SimpleNamespace(
        async_update_entry=lambda entry, options: entry.__setattr__("options", options)
    )

    entry = ConfigEntry(entry_id="doc-guard", data={}, options={})

    async def _run() -> None:
        await integration.async_setup_entry(hass, entry)

        domain_entry = hass.data[DOMAIN][entry.entry_id]
        templates = domain_entry.get("sentence_templates")
        assert templates is not None
        default_turn_on = templates.get("turn_on", "")
        assert "turn on" in default_turn_on.lower()

        override_dir = (
            tmp_path
            / "custom_components"
            / "entangledhome"
            / "sentences"
            / "en"
        )
        override_dir.mkdir(parents=True, exist_ok=True)
        override_turn_on = override_dir / "turn_on.yaml"
        override_turn_on.write_text(
            """language: en
intents:
  entangledhome.turn_on:
    data:
      - sentences:
          - override the lights in {area}
""",
            encoding="utf-8",
        )

        await integration.async_unload_entry(hass, entry)
        await integration.async_setup_entry(hass, entry)

        reloaded = hass.data[DOMAIN][entry.entry_id]["sentence_templates"]
        assert "override the lights" in reloaded["turn_on"]

    asyncio.run(_run())
