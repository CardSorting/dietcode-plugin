#!/usr/bin/env bash
# Deploy dietcode from the Hermes repo root:
#   cd /path/to/hermes-agent && ./scripts/hermes_deploy.sh
#
# Installed automatically into HERMES_SRC/scripts/ by dietcode deploy.
# Override plugin source: DIETCODE_PLUGIN_SRC=/path/to/dietcode-plugin ./scripts/hermes_deploy.sh
#
set -euo pipefail

HERMES_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HERMES_SRC="${HERMES_SRC:-$HERMES_ROOT}"

PLUGIN_DEPLOY="$HERMES_ROOT/plugins/dietcode-plugin/scripts/hermes_deploy.sh"
if [[ ! -f "$PLUGIN_DEPLOY" ]]; then
  echo "dietcode plugin not found: $HERMES_ROOT/plugins/dietcode-plugin" >&2
  echo "Run deploy once from your dev checkout:" >&2
  echo "  cd ~/Desktop/dietcode-plugin && ./scripts/hermes_deploy.sh" >&2
  exit 1
fi

PLUGIN_SRC_ARGS=()
if [[ -n "${DIETCODE_PLUGIN_SRC:-}" ]]; then
  PLUGIN_SRC_ARGS=(--plugin-src "$DIETCODE_PLUGIN_SRC")
elif [[ -f "${HOME}/Desktop/dietcode-plugin/install.py" ]]; then
  PLUGIN_SRC_ARGS=(--plugin-src "${HOME}/Desktop/dietcode-plugin")
fi

exec "$PLUGIN_DEPLOY" "${PLUGIN_SRC_ARGS[@]}" "$@"
