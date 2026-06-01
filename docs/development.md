# Development

Guide for maintaining the DietCode plugin package and syncing from the diet-hermes fork.

---

## Repository relationship

```
diet-hermes-main-master/          Fork (full Hermes + plugins/dietcode)
dietcode-plugin/                  Standalone drag-and-drop package (this repo)
  dietcode/                       Copy of plugins/dietcode + bundled broccolidb/
  shim/plugins/                   Pip namespace for plugins.dietcode
```

The fork may symlink `plugins/dietcode/broccolidb → ../../broccolidb`.
The standalone package **ships a real `broccolidb/` directory**.

---

## Sync from fork

```bash
./scripts/sync-from-fork.sh /path/to/diet-hermes-main-master
```

This script:

1. Rsyncs `plugins/dietcode/` → `dietcode/` (excludes nested broccolidb)
2. Rsyncs repo-root `broccolidb/` → `dietcode/broccolidb/`

Then reinstall locally:

```bash
./scripts/install-to-hermes.sh
/dietcode doctor
```

---

## Package structure

| Path | Role |
|------|------|
| `dietcode/` | Plugin source installed to `~/.hermes/plugins/dietcode/` |
| `shim/plugins/` | Empty `plugins` package for setuptools |
| `pyproject.toml` | `hermes-dietcode-plugin` pip metadata |
| `MANIFEST.in` | Include broccolidb tree in sdist |
| `scripts/install-to-hermes.sh` | User install |
| `scripts/sync-from-fork.sh` | Maintainer sync |

Entry point:

```toml
[project.entry-points."hermes_agent.plugins"]
dietcode = "plugins.dietcode"
```

Version: keep `dietcode/plugin.yaml`, `pyproject.toml`, and git tags aligned.

---

## Local pip editable install

```bash
cd /path/to/dietcode-plugin
pip install -e .
python -c "import plugins.dietcode; print(plugins.dietcode.__file__)"
```

Setuptools maps:

```toml
[tool.setuptools]
package-dir = { "plugins" = "shim/plugins", "plugins.dietcode" = "dietcode" }
```

---

## Running tests (fork checkout)

Tests live in the **diet-hermes fork**, not this package:

```bash
cd /path/to/diet-hermes-main-master
scripts/run_tests.sh tests/plugins/test_dietcode*.py
scripts/run_tests.sh tests/hermes_cli/test_dietcode*.py
```

Key test files:

| File | Coverage |
|------|----------|
| `test_dietcode_plugin.py` | Registration, tools, hooks |
| `test_dietcode_install.py` | Seamless defaults, auto_enable |
| `test_dietcode_drag_drop_bootstrap.py` | Namespace bootstrap |
| `test_dietcode_audit.py` | Forbidden imports, layout |
| `test_dietcode_hooks_hardening.py` | Fail-closed behavior |

Static audit: `plugins/dietcode/audit.py` (run via test_dietcode_audit).

---

## BroccoliDB development

```bash
cd dietcode/broccolidb
npm ci
npm test                    # if configured
npx tsx tests/benchmark.ts
```

RPC smoke test — see [broccolidb.md](./broccolidb.md).

Fork benchmarks:

```bash
python scripts/benchmark_broccolidb_native_rpc.py -n 9
```

---

## Contract and audit

Before release:

1. `./scripts/sync-from-fork.sh`
2. Run fork test suite (dietcode tests)
3. `./scripts/install-to-hermes.sh` on clean `HERMES_HOME`
4. `/dietcode doctor` — contract ok, RPC ok
5. Bump version in `plugin.yaml` + `pyproject.toml`

`audit.py` checks:

- Required runtime files present
- Legacy shim plugin dirs absent
- No duplicate dietcode hook registration
- Fork tree free of forbidden direct imports (when run in fork context)

---

## Release checklist

- [ ] Version bump (`plugin.yaml`, `pyproject.toml`)
- [ ] `sync-from-fork.sh` from tested fork commit
- [ ] Fork `test_dietcode*.py` green
- [ ] `broccolidb/` excludes `node_modules`, `*.db`, `scratch`
- [ ] README + docs/ updated
- [ ] `install-to-hermes.sh` tested on macOS/Linux
- [ ] Tag release / distribute zip of `dietcode-plugin/`

---

## Contributing to core facades

If you need Hermes core to call DietCode behavior, **add a generic facade** in the fork —
never import `plugins.dietcode.*` from `run_agent.py`, `cli.py`, or `gateway/run.py` directly.

Existing facades: `dietcode_bridge`, `governance_bridge`, `joy_zoning_bridge`, `prompt_bridge`.

Vanilla Hermes users rely on plugin hooks/tools only; facades are fork enhancements.
