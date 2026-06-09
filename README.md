# DietCode Hermes Plugin

**v1.9.3 — Kernel Cockpit Responsiveness**

DietCode is a standalone Hermes Agent plugin that bundles BroccoliDB, BroccoliQ,
JoyZoning governance, JSDP rolling-horizon planning, and an **optional macOS
kernel authority bridge** into one installable directory.

The plugin provides:

- **BroccoliDB** — knowledge graph, repository indexing, structural audit, refactor planning.
- **BroccoliQ** — sharded SQLite queue status, shard health, integrity tools.
- **JoyZoning** — governed mutation lifecycle hooks, convergence gates, slash commands.
- **JSDP** — autonomous planning helpers for bounded, reviewable delivery loops.
- **Kernel bridge (macOS, opt-in)** — coherent patching and verification via
  `dietcode_kernel`, with JoyZoning journaling and gated raw-write interception.
- **Hermes hooks** — session start/end, tool call gating, and tool result transformation.

## Strategy

DietCode separates **physical mutation authority** from **lifecycle and completion
authority**. The kernel is optional; BroccoliDB, JoyZoning, and governance work
without it. Linux installs degrade gracefully (no binary, no socket, no blocking).

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

| Layer | Role |
| --- | --- |
| **Kernel** | Physical `patch` and `verify.run` (when bridge enabled) |
| **JoyZoning** | Lifecycle journal (`mutation_record_patch`, `mutation_verify`) |
| **Convergence gate** | Completion authority — kanban is never auto-completed |
| **Raw Hermes writes** | Allowed by default; warn/block is opt-in |

Safe install defaults:

```yaml
dietcode:
  kernel:
    bridge:
      enabled: true
      mutations_enabled: false   # patch gate closed until you opt in
      raw_write_policy: warn
```

Raw writes are hard-blocked only when **both** `raw_write_policy: block` and
`DIETCODE_KERNEL_RAW_WRITE_BLOCK=1` are set with the patch gate fully open.

## Requirements

- Hermes Agent with plugin support.
- Python runtime used by Hermes.
- Node.js 18+ and npm for the bundled `broccolidb/` package.
- **Kernel bridge (optional):** macOS, Xcode CLT, built `kernel/build/dietcode-kernel`,
  running control socket at `~/.dietcode/control.sock`.

## Install

Copy this folder to the Hermes plugin directory:

```bash
mkdir -p ~/.hermes/plugins
cp -R dietcode-plugin ~/.hermes/plugins/dietcode
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

Apply Hermes config defaults (includes safe kernel bridge settings):

```bash
python install.py
```

Use `python install.py --skip-npm` when dependencies are already installed.
Use `python install.py --build-kernel` on macOS to build the quarantined kernel binary.

## Verify

Inside Hermes:

```text
/dietcode doctor
/dietcode kernel status
```

Kernel operator checklist:

```text
/dietcode kernel cockpit          # one-screen state, gates, next action
/dietcode kernel watch            # compact live operation line
/dietcode kernel perf --ux        # responsiveness budgets
/dietcode kernel progress         # human summary + next phase
/dietcode kernel explain-gate     # closed gates and fixes
```

Other checks:

```text
/dietcode tools
/dietcode broccolidb
/dietcode kernel status
/broccolidb status
/broccoliq queue
/joyzoning status
```

From the shell (macOS kernel integration):

```bash
make -C kernel kernel
make -C kernel restart-agent-server-fast
python scripts/kernel_phase3_rehearsal.py
python scripts/kernel_bridge_e2e.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

BroccoliDB package checks:

```bash
cd broccolidb
npm run build
npm test
```

## Enable kernel authority (optional)

1. Build and start the kernel on macOS (see [kernel/README.md](kernel/README.md)).
2. Point workspace at your project: `export HERMES_KANBAN_WORKSPACE=/path/to/project`
3. Opt in: set `dietcode.kernel.bridge.mutations_enabled: true` in Hermes config.
4. Confirm: `/dietcode kernel status` → `patch_allowed=true`

Operator guide: [docs/kernel-bridge-operations.md](docs/kernel-bridge-operations.md)

## Project layout

```text
.
|-- plugin.yaml                 # Hermes manifest (v1.9.3)
|-- hooks.py                    # Hook registration (kernel + JoyZoning + governance)
|-- install.py                  # Config defaults, npm bootstrap, kernel build check
|-- health.py                   # /dietcode status, doctor, kernel status
|-- slash_commands.py           # /dietcode, /broccolidb, /broccoliq, /joyzoning
|-- lib/
|   |-- agent/                  # JoyZoning, kernel bridge client, journals, raw-write router
|   |-- runtime/                # kernel_hooks, joyzoning_hooks, governance_hooks
|   `-- tools/                  # dietcode_kernel, broccolidb, joyzoning, convergence
|-- kernel/                     # Quarantined macOS kernel + coherence harnesses
|-- broccolidb/                 # Bundled TypeScript BroccoliDB package
|-- scripts/                    # kernel_phase3_rehearsal.py, kernel_bridge_e2e.py
|-- tests/                      # Kernel bridge unit tests
`-- docs/                       # Operator and developer documentation
```

## Documentation

| Document | Purpose |
| --- | --- |
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/dietcode-plugin.md](docs/dietcode-plugin.md) | Plugin overview, config, workflow |
| [docs/architecture.md](docs/architecture.md) | Runtime layers, hook flow, authority split |
| [docs/kernel-bridge-operations.md](docs/kernel-bridge-operations.md) | Kernel bridge operator manual |
| [docs/tools-reference.md](docs/tools-reference.md) | Slash commands and Hermes tools |
| [docs/broccolidb.md](docs/broccolidb.md) | BroccoliDB runtime and RPC |
| [kernel/MIGRATION.md](kernel/MIGRATION.md) | Kernel integration phase history |
| [kernel/README.md](kernel/README.md) | Kernel build, validate, RPC reference |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |
| [docs/releases/v1.9.3.md](docs/releases/v1.9.3.md) | v1.9.3 cockpit release note |
| [docs/releases/v1.9.2.md](docs/releases/v1.9.2.md) | v1.9.2 performance pass |
| [docs/releases/v1.9.1.md](docs/releases/v1.9.1.md) | v1.9.1 release note |
| [docs/releases/v1.9.0.md](docs/releases/v1.9.0.md) | v1.9.0 release note |

## License

MIT. See [LICENSE](LICENSE).
