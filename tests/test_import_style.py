"""Tests enforcing repository lint expectations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("ruff")


def test_imports_are_sorted() -> None:
    """Import blocks should be formatted according to Ruff's I rules."""

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "I", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
