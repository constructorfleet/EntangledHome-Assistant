#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

python3.13 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install -e '.[dev]'

echo "Environment ready. Activate with: source ${VENV_DIR}/bin/activate"
