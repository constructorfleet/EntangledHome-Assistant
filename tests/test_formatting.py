"""Formatting guard tests for lint-critical paths."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TARGET_FILES = [
    Path("tests/test_config_options_flow.py"),
    Path("tests/test_options_defaults.py"),
]


def test_source_files_are_ruff_formatted() -> None:
    """Ensure targeted sources stay formatted according to Ruff."""

    ruff_executable = shutil.which("ruff")
    if not ruff_executable:  # pragma: no cover - environment guard
        pytest.skip("ruff is not installed in the execution environment")

    repo_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        *map(str, TARGET_FILES),
    ]
    process = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr
