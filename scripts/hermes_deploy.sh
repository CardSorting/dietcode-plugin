#!/usr/bin/env bash
# Sync dietcode-plugin → ~/.hermes/plugins/dietcode, reinstall Hermes, enable, verify.
#
# Usage (from dietcode-plugin dev checkout):
#   ./scripts/hermes_deploy.sh
#   HERMES_SRC="/path/to/hermes-agent" ./scripts/hermes_deploy.sh
#   ./scripts/hermes_deploy.sh --skip-tests --skip-hermes-reinstall
#
# From Hermes repo root (after first deploy installs the wrapper):
#   cd /path/to/hermes-agent && ./scripts/hermes_deploy.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_VENV="${HERMES_VENV:-$HOME/.hermes/hermes-agent/venv}"
PYTHON="${HERMES_VENV}/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Hermes venv python not found: $PYTHON" >&2
  echo "Set HERMES_VENV or install Hermes first." >&2
  exit 1
fi

unset PYTHONPATH PYTHONHOME
exec "$PYTHON" "$ROOT/install.py" --deploy-hermes "$@"
