"""Pytest startup environment customization."""

from __future__ import annotations

import os
from typing import Final

PYTEST_AUTOLOAD_ENV_VAR: Final = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"

os.environ.setdefault(PYTEST_AUTOLOAD_ENV_VAR, "1")
