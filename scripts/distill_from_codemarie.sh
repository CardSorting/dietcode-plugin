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
  "core/agent-context/InvariantEngine.ts"
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
  --exclude '*.db-wal' \
  --exclude '*.db-shm' \
  --exclude 'benchmark.db' \
  --exclude 'test-production.db' \
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

if [[ "${BUILD:-1}" != "0" ]]; then
  echo "Building broccolidb..."
  (cd "$BDB_DEST" && npm ci && npm run build)
  if command -v diff >/dev/null 2>&1; then
    CORE_DRIFT=$(diff -rq "$BDB_SRC/core" "$BDB_DEST/core" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$CORE_DRIFT" != "0" ]]; then
      echo "warn: core/ still differs after distill ($CORE_DRIFT lines) — check PRESERVE overlays" >&2
    else
      echo "core/ mirrored OK"
    fi
  fi
fi

# Optional skills (shared between LUMI and Hermes plugin).
SKILL_SRC="$SRC/optional-skills/dietcode"
SKILL_DEST="$DEST/optional-skills/dietcode"
if [[ -d "$SKILL_SRC" ]]; then
  echo "Distilling optional-skills/dietcode from $SKILL_SRC → $SKILL_DEST"
  rsync -a --delete \
    --exclude '.DS_Store' \
    "$SKILL_SRC/" "$SKILL_DEST/"
fi

# Monorepo docs required by broccolidb guardrail tests (capabilities, intent tracing).
DOC_API_SRC="$SRC/docs/api"
DOC_API_DEST="$DEST/docs/api"
if [[ -d "$DOC_API_SRC" ]]; then
  echo "Distilling docs/api from $DOC_API_SRC → $DOC_API_DEST"
  rsync -a \
    "$DOC_API_SRC/" "$DOC_API_DEST/" \
    --exclude '.DS_Store'
fi

ARCH_HIST_SRC="$SRC/docs/history/architecture"
ARCH_HIST_DEST="$DEST/docs/history/architecture"
if [[ -d "$ARCH_HIST_SRC" ]]; then
  echo "Distilling docs/history/architecture from $ARCH_HIST_SRC → $ARCH_HIST_DEST"
  mkdir -p "$ARCH_HIST_DEST"
  rsync -a "$ARCH_HIST_SRC/" "$ARCH_HIST_DEST/"
fi
