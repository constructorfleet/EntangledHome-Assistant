"""Tests for contributor tooling expectations."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TEST_PACKAGES = {
    "pytest",
    "pytest-cov",
    "pytest-homeassistant-custom-component",
    "fastapi",
    "uvicorn[standard]",
}
PYTEST_HACC_MIN_VERSION = "0.13.205"
REQUIREMENTS_TEST_FILE = REPO_ROOT / "requirements-test.txt"
LOCKFILE = REPO_ROOT / "uv.lock"
LOCK_PACKAGES = {"fastapi", "uvicorn"}
EXPECTED_HACS_METADATA = {
    "name": "EntangledHome - Assistant",
    "content_in_root": False,
    "filename": "",
    "render_readme": True,
    "domains": ["entangledhome"],
}
EXPECTED_HACS_SNIPPETS = (
    "HACS → Integrations",
    "Custom repositories",
    "EntangledHome - Assistant",
)
HASSFEST_COMMAND = "python3 -m script.hassfest"
BRANDING_FILES = (
    REPO_ROOT / "custom_components" / "entangledhome" / "icon.svg",
    REPO_ROOT / "custom_components" / "entangledhome" / "logo.png",
)
TROUBLESHOOTING_DOC = REPO_ROOT / "docs" / "troubleshooting.md"


def _normalize_requirement(entry: str) -> str:
    return entry.strip().split("==")[0].split(">=")[0]


def test_dev_dependency_groups_cover_test_stack() -> None:
    """The dev dependency group should include required test stack packages."""

    pyproject = tomllib.loads(REPO_ROOT.joinpath("pyproject.toml").read_text())
    dev_group = {_normalize_requirement(item) for item in pyproject["dependency-groups"]["dev"]}
    expected = EXPECTED_TEST_PACKAGES | {"coverage[toml]"}
    missing = expected - dev_group
    assert not missing, f"Missing dev dependencies: {sorted(missing)}"


def test_requirements_file_exists_for_pip_workflow() -> None:
    """requirements-test.txt should mirror the dev dependency stack."""

    assert REQUIREMENTS_TEST_FILE.exists(), "requirements-test.txt should be present for pip users"

    entries = {
        _normalize_requirement(line)
        for line in REQUIREMENTS_TEST_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    missing = EXPECTED_TEST_PACKAGES - entries
    assert not missing, f"requirements-test.txt missing: {sorted(missing)}"


def test_pytest_hacc_version_supports_python312() -> None:
    """Ensure pytest-homeassistant-custom-component constraint supports Python 3.12 coverage wheels."""

    requirement_lines = REQUIREMENTS_TEST_FILE.read_text().splitlines()
    matching_lines = [
        line.strip()
        for line in requirement_lines
        if line.strip().startswith("pytest-homeassistant-custom-component")
    ]
    assert matching_lines, "pytest-homeassistant-custom-component entry missing from requirements-test.txt"

    requirement_line = matching_lines[0]
    assert (
        f">={PYTEST_HACC_MIN_VERSION}" in requirement_line
    ), (
        "pytest-homeassistant-custom-component should require"
        f" >= {PYTEST_HACC_MIN_VERSION} to pull Python 3.12 compatible coverage wheels"
    )


def test_uv_lock_includes_required_packages() -> None:
    """uv.lock should record fastapi and uvicorn resolutions for adapter and HA tests."""

    lock_text = LOCKFILE.read_text()
    for package in LOCK_PACKAGES:
        needle = f'"{package}"'
        assert needle in lock_text, f"uv.lock missing entry for {package}"


def test_hacs_metadata_exists_with_required_fields() -> None:
    """hacs.json should advertise the integration with expected metadata."""

    hacs_file = REPO_ROOT / "hacs.json"
    assert hacs_file.exists(), "hacs.json must exist at the repository root"

    metadata = json.loads(hacs_file.read_text())
    for key, value in EXPECTED_HACS_METADATA.items():
        assert metadata.get(key) == value, f"hacs.json missing {key}: expected {value!r}"


def test_readme_documents_hacs_installation_flow() -> None:
    """README should contain explicit HACS installation guidance."""

    readme_text = REPO_ROOT.joinpath("README.md").read_text()
    assert "## Installation (HACS)" in readme_text, "README must expose a HACS installation section"

    for snippet in EXPECTED_HACS_SNIPPETS:
        assert snippet in readme_text, f"README HACS instructions missing snippet: {snippet!r}"


def test_troubleshooting_documents_hassfest_validation() -> None:
    """Troubleshooting guide should point contributors to hassfest validation."""

    troubleshooting_text = TROUBLESHOOTING_DOC.read_text()
    assert HASSFEST_COMMAND in troubleshooting_text, (
        "Troubleshooting guide must include hassfest command"
    )


def test_branding_assets_exist_for_hacs() -> None:
    """Branding assets should be present for HACS presentation."""

    missing = [path for path in BRANDING_FILES if not path.exists()]
    assert not missing, "Missing branding assets: " + ", ".join(
        str(path.relative_to(REPO_ROOT)) for path in missing
    )


def test_troubleshooting_highlights_hassfest_dependencies() -> None:
    """Troubleshooting doc should mention hassfest dependency installation hints."""

    troubleshooting_text = TROUBLESHOOTING_DOC.read_text()
    assert "Validating ... done" in troubleshooting_text
    assert "habluetooth" in troubleshooting_text
