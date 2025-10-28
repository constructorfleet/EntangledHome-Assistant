"""Tests for contributor tooling expectations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from sitecustomize import PYTEST_AUTOLOAD_ENV_VAR

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TEST_PACKAGES = {
    "pytest",
    "pytest-cov",
    "pytest-homeassistant-custom-component",
    "fastapi",
    "uvicorn[standard]",
}
EXPECTED_LINT_PACKAGES = {"ruff"}
DEPENDENCY_PIN_MARKERS = ("==", ">=", "<=", "~=", "!=")
REQUIREMENTS_TEST_FILE = REPO_ROOT / "requirements-test.txt"
TOOLING_TEST_FILE = Path(__file__).resolve()
LOCKFILE = REPO_ROOT / "uv.lock"
LOCK_PACKAGES = {"fastapi", "uvicorn"}
RELEASE_WORKFLOW_FILE = REPO_ROOT / ".github" / "workflows" / "release.yml"
RELEASE_WORKFLOW_PYTHON_VERSION = "3.13"
REQUIRED_PYTHON_SPEC = ">=3.13,<3.14"
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


def _has_version_pin(entry: str) -> bool:
    stripped = entry.strip()
    if not stripped or stripped.startswith("#"):
        return False
    return any(marker in stripped for marker in DEPENDENCY_PIN_MARKERS)


def _iter_requirement_entries(path: Path) -> list[str]:
    return [
        line for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")
    ]


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(REPO_ROOT.joinpath("pyproject.toml").read_text())


def _load_dev_dependency_group() -> set[str]:
    pyproject = _load_pyproject()
    return {_normalize_requirement(item) for item in pyproject["dependency-groups"]["dev"]}


def _load_release_workflow_text() -> str:
    return RELEASE_WORKFLOW_FILE.read_text()


def _assert_sorted(entries: list[str], *, message: str) -> None:
    assert entries == sorted(entries), message


def _assert_ruff_format_clean(path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tooling_configuration_module_is_ruff_formatted() -> None:
    """The tooling tests should remain formatted according to Ruff."""

    _assert_ruff_format_clean(TOOLING_TEST_FILE)


def test_pytest_disables_plugin_autoload() -> None:
    """pytest should disable third-party plugin auto-loading to avoid import crashes."""

    flag_value = os.environ.get(PYTEST_AUTOLOAD_ENV_VAR)
    assert flag_value == "1", (
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD must be set to '1' to prevent third-party plugin crashes"
    )


def test_dev_dependency_groups_cover_test_stack() -> None:
    """The dev dependency group should include required test stack packages."""

    dev_group = _load_dev_dependency_group()
    expected = EXPECTED_TEST_PACKAGES | {"coverage[toml]"}
    missing = expected - dev_group
    assert not missing, f"Missing dev dependencies: {sorted(missing)}"


def test_dev_dependency_groups_include_lint_tooling() -> None:
    """The dev dependency group should install lint tooling for contributors."""

    dev_group = _load_dev_dependency_group()
    missing = EXPECTED_LINT_PACKAGES - dev_group
    assert not missing, f"Missing lint dependencies: {sorted(missing)}"


def test_requirements_file_exists_for_pip_workflow() -> None:
    """requirements-test.txt should mirror the dev dependency stack."""

    assert REQUIREMENTS_TEST_FILE.exists(), "requirements-test.txt should be present for pip users"

    entries = {
        _normalize_requirement(line) for line in _iter_requirement_entries(REQUIREMENTS_TEST_FILE)
    }
    missing = EXPECTED_TEST_PACKAGES - entries
    assert not missing, f"requirements-test.txt missing: {sorted(missing)}"


def test_dependency_manifests_do_not_pin_versions() -> None:
    """Project manifests should avoid pinning dependency versions."""

    pyproject = _load_pyproject()
    manifests = {
        "project.dependencies": pyproject["project"].get("dependencies", []),
        "project.optional-dependencies.dev": pyproject["project"]
        .get("optional-dependencies", {})
        .get("dev", []),
        "dependency-groups.dev": pyproject["dependency-groups"].get("dev", []),
        "requirements-test.txt": _iter_requirement_entries(REQUIREMENTS_TEST_FILE),
    }

    violating = {
        name: [entry for entry in entries if _has_version_pin(entry)]
        for name, entries in manifests.items()
    }

    offenders = {name: entries for name, entries in violating.items() if entries}
    assert not offenders, f"Pinned dependencies detected: {offenders}"


def test_pyproject_requires_python_313() -> None:
    """Ensure the package metadata advertises Python 3.13 runtime support."""

    pyproject = _load_pyproject()
    requires_python = pyproject["project"]["requires-python"]
    assert requires_python == REQUIRED_PYTHON_SPEC, (
        "pyproject.toml must pin Python compatibility to >=3.13,<3.14 for release pipeline"
    )


def test_release_workflow_targets_python_313() -> None:
    """Release workflow should install dependencies under Python 3.13."""

    assert RELEASE_WORKFLOW_FILE.exists(), "release workflow file must exist"

    workflow_text = _load_release_workflow_text()
    expected_snippet = f'python-version: "{RELEASE_WORKFLOW_PYTHON_VERSION}"'
    assert expected_snippet in workflow_text, (
        "release workflow should use python-version '3.13' to match project metadata"
    )


def test_pyproject_dependency_lists_are_sorted() -> None:
    """Pyproject dependency lists should be sorted for readability."""

    pyproject = _load_pyproject()
    dependencies = pyproject["project"].get("dependencies", [])
    optional_dev = pyproject["project"].get("optional-dependencies", {}).get("dev", [])
    dependency_group_dev = pyproject["dependency-groups"].get("dev", [])

    _assert_sorted(dependencies, message="project.dependencies must be sorted")
    _assert_sorted(
        optional_dev,
        message="project.optional-dependencies.dev must be sorted",
    )
    _assert_sorted(
        dependency_group_dev,
        message="dependency-groups.dev must be sorted",
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
