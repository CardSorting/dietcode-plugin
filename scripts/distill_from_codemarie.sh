#!/usr/bin/env bash
# Distill substrate updates from codemarie-new (LUMI monorepo) into dietcode-plugin.
# Preserves Hermes-only infrastructure (RPC worker, kanban hive, queue, dashboard).
set -euo pipefail

SRC="${CODEMARIE_SRC:-/Users/bozoegg/Downloads/codemarie-new}"
DEST="${DIETCODE_PLUGIN_DEST:-$(cd "$(dirname "$0")/.." && pwd)}"
BDB_SRC="$SRC/broccolidb"
BDB_DEST="$DEST/broccolidb"

if [[ ! -d "$BDB_SRC" ]]; then
  echo "error: broccolidb not found at $BDB_SRC" >&2
  exit 1
fi

echo "Distilling broccolidb from $BDB_SRC → $BDB_DEST"

# Hermes-only overlays — never overwrite from codemarie.
PRESERVE=(
  "infrastructure/hermes"
  "infrastructure/kanban"
  "infrastructure/queue"
  "infrastructure/util"
  "infrastructure/dashboard"
  "infrastructure/index.ts"
  "infrastructure/SOVEREIGN_INFRASTRUCTURE.md"
  "infrastructure/db/Config.ts"
  "infrastructure/db/DatabaseSchema.ts"
  "infrastructure/db/BufferedDbPool.ts"
  "infrastructure/db/pool"
  "infrastructure/db/Benchmark.ts"
  "infrastructure/db/IntegrityWorker.ts"
  "infrastructure/db/VerifySharding.ts"
)

TMP_BACKUP="$(mktemp -d)"
trap 'rm -rf "$TMP_BACKUP"' EXIT

mkdir -p "$TMP_BACKUP/tests"
for test in reembed_all.test.ts semantic_search.test.ts; do
  if [[ -f "$BDB_DEST/tests/$test" ]]; then
    cp "$BDB_DEST/tests/$test" "$TMP_BACKUP/tests/$test"
  fi
done

for rel in "${PRESERVE[@]}"; do
  if [[ -e "$BDB_DEST/$rel" ]]; then
    mkdir -p "$TMP_BACKUP/$(dirname "$rel")"
    cp -R "$BDB_DEST/$rel" "$TMP_BACKUP/$rel"
  fi
done

rsync -a --delete \
  --exclude node_modules \
  --exclude dist \
  --exclude '*.db' \
  --exclude 'broccolidb-failed-flush-*.json' \
  --exclude 'workspaces/' \
  "$BDB_SRC/" "$BDB_DEST/"

for rel in "${PRESERVE[@]}"; do
  if [[ -e "$TMP_BACKUP/$rel" ]]; then
    mkdir -p "$BDB_DEST/$(dirname "$rel")"
    rm -rf "$BDB_DEST/$rel"
    cp -R "$TMP_BACKUP/$rel" "$BDB_DEST/$rel"
  fi
done

for test in reembed_all.test.ts semantic_search.test.ts; do
  if [[ -f "$TMP_BACKUP/tests/$test" ]]; then
    cp "$TMP_BACKUP/tests/$test" "$BDB_DEST/tests/$test"
  fi
done

echo "Done. Run: cd broccolidb && npm ci && npm run build && npm test"
