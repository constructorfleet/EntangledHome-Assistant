"""Color lookup tables for light control."""

from __future__ import annotations

COLOR_HS: dict[str, list[int]] = {
    "red": [0, 100],
    "green": [120, 100],
    "blue": [240, 100],
    "warm": [35, 60],
    "cool": [210, 60],
}

__all__ = ["COLOR_HS"]
