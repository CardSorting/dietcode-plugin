#!/usr/bin/env bash
# Sync plugin + broccolidb from diet-hermes fork into this drag-and-drop package.
set -euo pipefail

FORK="${1:-${DIET_HERMES_ROOT:-}}"
if [[ -z "${FORK}" || ! -d "${FORK}/plugins/dietcode" ]]; then
  echo "Usage: $0 /path/to/diet-hermes-main-master" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_SRC="${FORK}/plugins/dietcode"
BDB_SRC="${FORK}/broccolidb"
PLUGIN_DST="${ROOT}/dietcode"

mkdir -p "${ROOT}/shim/plugins"
[[ -f "${ROOT}/shim/plugins/__init__.py" ]] || echo "# Hermes plugins namespace (pip shim)" > "${ROOT}/shim/plugins/__init__.py"

rsync -a --delete --exclude broccolidb "${PLUGIN_SRC}/" "${PLUGIN_DST}/"
rsync -a --delete \
  --exclude node_modules \
  --exclude scratch \
  --exclude '*.db' \
  --exclude '*.db-wal' \
  --exclude '*.db-shm' \
  --exclude '.DS_Store' \
  "${BDB_SRC}/" "${PLUGIN_DST}/broccolidb/"

echo "Synced to ${PLUGIN_DST}"
echo "Drag-and-drop: copy ${PLUGIN_DST} → ~/.hermes/plugins/dietcode"
echo "Optional pip: pip install -e ${ROOT} && cd ${PLUGIN_DST}/broccolidb && npm ci"
