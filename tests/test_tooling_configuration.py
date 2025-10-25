"""Tests for contributor tooling expectations."""

from __future__ import annotations

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
LOCKFILE = REPO_ROOT / "uv.lock"
LOCK_PACKAGES = {"fastapi", "uvicorn"}


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

    requirements_path = REPO_ROOT / "requirements-test.txt"
    assert requirements_path.exists(), "requirements-test.txt should be present for pip users"

    entries = {
        _normalize_requirement(line)
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    missing = EXPECTED_TEST_PACKAGES - entries
    assert not missing, f"requirements-test.txt missing: {sorted(missing)}"


def test_uv_lock_includes_required_packages() -> None:
    """uv.lock should record fastapi and uvicorn resolutions for adapter and HA tests."""

    lock_text = LOCKFILE.read_text()
    for package in LOCK_PACKAGES:
        needle = f'"{package}"'
        assert needle in lock_text, f"uv.lock missing entry for {package}"
