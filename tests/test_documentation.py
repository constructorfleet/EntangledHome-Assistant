"""Documentation guardrail tests."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from homeassistant.core import HomeAssistant

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_STATE_SETUP_IN_PROGRESS = "SETUP_IN_PROGRESS"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_contains(text: str, markers: list[str]) -> None:
    for marker in markers:
        assert marker in text


def _run_ruff_format_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ruff", "format", "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def _ensure_httpx_stub() -> None:
    if "httpx" in sys.modules:
        return

    class _HttpxAsyncClient:  # pragma: no cover - stub methods unused in test
        def __init__(self, *args, **kwargs) -> None:
            self._closed = False

        async def post(self, *args, **kwargs):  # pragma: no cover - defensive stub
            raise RuntimeError("httpx.AsyncClient.post should not be called in this test")

        async def aclose(self) -> None:
            self._closed = True

    class _Timeout:  # pragma: no cover - minimal stub
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    httpx_stub = ModuleType("httpx")
    httpx_stub.AsyncClient = _HttpxAsyncClient
    httpx_stub.Timeout = _Timeout
    httpx_stub.HTTPError = Exception
    sys.modules["httpx"] = httpx_stub


def _build_test_hass(tmp_path: Path) -> HomeAssistant:
    """Instantiate Home Assistant with minimal test harness support."""

    try:
        hass = HomeAssistant()
    except TypeError:
        hass = HomeAssistant.__new__(HomeAssistant, config_dir=str(tmp_path))
        try:
            HomeAssistant.__init__(hass)
        except TypeError:
            HomeAssistant.__init__(hass, str(tmp_path))
        hass.config_dir = str(tmp_path)

    hass.config = SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts)))
    hass.config_entries = SimpleNamespace(async_update_entry=lambda *_args, **_kwargs: None)

    try:
        from homeassistant.helpers import frame  # type: ignore
    except ImportError:
        frame = None
    if frame is not None:
        frame.report_usage = lambda *args, **kwargs: None  # type: ignore[attr-defined]

    return hass


def _imported_symbols() -> set[str]:
    return set(globals())


def test_readme_and_adapter_docs_cover_required_sections() -> None:
    readme = _read_text(REPO_ROOT / "README.md")
    _assert_contains(
        readme,
        [
            "## Architecture Overview",
            "## Setup",
            "### Home Assistant Configuration",
            "configured exclusively via Home Assistant's config flow",
            "Use the options flow to manage guardrails, adapter credentials, and catalog synchronization.",
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
        _read_text(REPO_ROOT / "custom_components" / "entangledhome" / "manifest.json")
    )
    assert (
        documentation_manifest.get("documentation")
        == "https://github.com/ConstructorFleet/EntangledHome-Assistant"
    )

    example_config = REPO_ROOT / "docs" / "examples" / "homeassistant_configuration.yaml"
    assert example_config.exists()
    example_config_text = _read_text(example_config)
    _assert_contains(
        example_config_text,
        [
            "# Reference values for the EntangledHome - Assistant options flow fields.",
            "adapter_url (required)",
            "qdrant_host (default: qdrant)",
            "qdrant_api_key (optional)",
            "enable_catalog_sync (default: true)",
            "enable_confidence_gate (default: false)",
            "confidence_threshold (default: 0.7)",
            "night_mode_start_hour (default: 23)",
            "night_mode_end_hour (default: 6)",
            "deduplication_window_seconds (default: 2.0)",
            "max_latency_ms (default: 2000.0)",
        ],
    )
    assert "entangledhome:" not in example_config_text

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
    guardrail_markers = [
        "`dangerous_intents`",
        "`intent_allowed_hours`",
        "`intent_secondary_signals`",
        "`intent_thresholds`",
        "`intent_recent_command_windows`",
    ]

    readme_markers = [
        "## Configurable intents",
        "`intents_config` supports the following keys",
        "`enabled`",
        "`slots`",
        "`threshold`",
        "Use the guardrail options",
        "### Options flow reference data",
        "### UI configuration walkthrough",
        "## Sentence customization",
        "## Qdrant ingestion scripts",
        "## Adapter deployment",
        "## Migration notes",
        "## Troubleshooting",
    ]

    _assert_contains(readme, readme_markers + guardrail_markers)

    examples_dir = REPO_ROOT / "docs" / "examples"
    intents_example = examples_dir / "intents.yaml"
    sentences_example = examples_dir / "sentences.en.yaml"
    for example_path in (intents_example, sentences_example):
        assert example_path.exists()

    intents_example_text = _read_text(intents_example)
    _assert_contains(
        intents_example_text,
        [
            "# Reference mapping for the options flow",
            "Intent routing configuration",
        ],
    )

    intents_example_text = _read_text(intents_example)
    intents_example_markers = [
        "enabled:",
        "slots:",
        "threshold:",
        "# Guardrail options such as",
        "dangerous_intents",
        "intent_thresholds",
    ]
    _assert_contains(intents_example_text, intents_example_markers)

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


def test_release_notes_anchor_latest_version_history() -> None:
    readme = _read_text(REPO_ROOT / "README.md")
    _assert_contains(
        readme,
        [
            "## Version history",
            "### v0.5.0",
            "docs/releases/v0.5.0.md",
        ],
    )

    release_notes_path = REPO_ROOT / "docs" / "releases" / "v0.5.0.md"
    assert release_notes_path.exists()
    release_notes = _read_text(release_notes_path)
    _assert_contains(
        release_notes,
        [
            "# v0.5.0",
            "Guardrails",
            "Intent configuration",
            "Adapter",
            "Qdrant",
        ],
    )

    migration_notes = _read_text(REPO_ROOT / "docs" / "migration.md")
    _assert_contains(
        migration_notes,
        [
            "[v0.5.0]",
            "docs/releases/v0.5.0.md",
        ],
    )


@pytest.mark.parametrize(
    "symbol",
    ["ConfigEntry", "ConfigEntryState"],
)
def test_documentation_suite_does_not_import_config_entry_symbols(symbol: str) -> None:
    assert symbol not in _imported_symbols()


def test_documentation_test_module_is_ruff_formatted() -> None:
    result = _run_ruff_format_check(REPO_ROOT / "tests" / "test_documentation.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_sentence_override_wins_on_reload(tmp_path: Path) -> None:
    """Custom sentence templates should override packaged defaults after reload."""

    DOMAIN = "entangledhome"

    _ensure_httpx_stub()

    import custom_components.entangledhome as integration

    async def _run() -> None:
        hass = _build_test_hass(tmp_path)

        entry = SimpleNamespace(
            entry_id="doc-guard",
            options={},
            data={},
            add_update_listener=lambda callback: callback,
            async_on_unload=lambda _callback: None,
            state=ENTRY_STATE_SETUP_IN_PROGRESS,
        )

        def _update_entry(entry_to_update, *, options: dict[str, Any] | None = None) -> None:
            if options is not None:
                entry_to_update.options = dict(options)

        hass.config_entries.async_update_entry = _update_entry  # type: ignore[method-assign]

        await integration.async_setup_entry(hass, entry)

        domain_entry = hass.data[DOMAIN][entry.entry_id]
        templates = domain_entry.get("sentence_templates")
        assert templates is not None
        default_turn_on = templates.get("turn_on", "")
        assert "turn on" in default_turn_on.lower()

        override_dir = tmp_path / "custom_components" / "entangledhome" / "sentences" / "en"
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
