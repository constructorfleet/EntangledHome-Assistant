"""Documentation guardrail tests."""
from __future__ import annotations

import json
from pathlib import Path


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
