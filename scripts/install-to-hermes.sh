#!/usr/bin/env bash
# One-step DietCode install: copy plugin + merge Hermes config + npm ci.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/dietcode"
HERMES_HOME="${HERMES_HOME:-${DIETCODE_HOME:-$HOME/.hermes}}"
DEST="${HERMES_HOME}/plugins/dietcode"

if [[ ! -f "${SRC}/plugin.yaml" ]]; then
  echo "Missing ${SRC}/plugin.yaml" >&2
  exit 1
fi

mkdir -p "${HERMES_HOME}/plugins"
rsync -a --delete \
  --exclude broccolidb/node_modules \
  --exclude broccolidb/scratch \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "${SRC}/" "${DEST}/"

echo "→ Copied plugin to ${DEST}"

# Bootstrap namespace + merge config (works without Hermes on PYTHONPATH if hermes installed)
if python3 -c "import hermes_cli" 2>/dev/null; then
  python3 "${DEST}/install.py" ${DIETCODE_SKIP_NPM:+--skip-npm} || true
else
  echo "→ Hermes not in this Python env — config merge skipped."
  echo "  After installing Hermes, run: python3 ${DEST}/install.py"
fi

if [[ -z "${DIETCODE_SKIP_NPM:-}" ]] && command -v npm >/dev/null; then
  if [[ ! -d "${DEST}/broccolidb/node_modules" ]]; then
    echo "→ Running npm ci in broccolidb/ ..."
    (cd "${DEST}/broccolidb" && npm ci)
  fi
fi

echo ""
echo "Done. Restart Hermes — DietCode auto-enables via plugin.yaml (auto_enable: true)."
echo "Verify: hermes plugins list   and   /dietcode doctor"
