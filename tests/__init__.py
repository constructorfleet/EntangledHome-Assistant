"""Test package configuration for EntangledHome."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUBS = ROOT / "tests" / "stubs"

for path in (STUBS, ROOT):
    str_path = str(path)
    if str_path not in sys.path:
        sys.path.insert(0, str_path)
