"""Tests enforcing repository lint expectations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("ruff")


def _run_ruff(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_imports_are_sorted() -> None:
    """Import blocks should be formatted according to Ruff's I rules."""

    result = _run_ruff("check", "--select", "I")

    assert result.returncode == 0, result.stdout + result.stderr


def test_code_is_ruff_formatted() -> None:
    """Source files should already satisfy Ruff's formatter."""

    result = _run_ruff("format", "--check")

    assert result.returncode == 0, result.stdout + result.stderr
