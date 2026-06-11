# DietCode Hermes Plugin

**v1.9.4 — Sonic Kernel UX**

DietCode is a standalone Hermes Agent plugin: one installable directory that gives
agents **governed mutation**, **repository intelligence**, and **per-project
long-horizon steering** — without forcing a single runtime path.

BroccoliDB indexes your repo. JoyZoning owns the mutation lifecycle.
JSDP plans bounded delivery loops. The **roadmap** tool keeps `ROADMAP.md` as a
living steering surface unique to *your* project — not the plugin checkout.
An optional **macOS kernel bridge** adds coherent physical patch and verify when
you opt in.

```text
Point workspace at YOUR project → fingerprint → evidence → ROADMAP.md steering
intent → patch → receipt → journal → verify → convergence → kanban (when gates open)
```

---

## Strategy

DietCode separates three authorities that other setups often collapse:

| Authority | Owner | Question it answers |
| --- | --- | --- |
| **Physical mutation** | Kernel bridge (optional) or raw Hermes tools | What changed on disk, with receipts? |
| **Lifecycle & completion** | JoyZoning + convergence gates | Is this mutation reviewed, verified, converged? |
| **Long-horizon steering** | Roadmap (`ROADMAP.md`) | What is the project becoming; what matters now? |

Nothing auto-completes kanban. Raw writes stay allowed by default. The kernel
patch gate is **closed until you enable it**. Roadmap gates can block
`kanban_complete` when the steering surface is stale, invalid, or unvalidated —
mirroring how production teams treat architecture docs and CI green before merge.

### Per-project identity (roadmap)

Every roadmap tool response is scoped to **`HERMES_KANBAN_WORKSPACE`** (your project
root), never `~/.hermes/plugins/dietcode`. The plugin builds a **project
fingerprint** from README, Makefile, CI, agent rules, and repo layout — then
attaches it everywhere agents look:

```text
project_fingerprint → evidence bundle → project_steering_digest → project_identity_line
```

| Field | What agents read first |
| --- | --- |
| `project_identity_line` | One line: brief · stack · verify command |
| `project_steering_digest` | Entity card: CI, quality tools, governance, bootstrap status |
| `bootstrap_fill_plan` | Evidence-backed replacements when template phrases remain |

Bootstrap skeletons ship schema-complete; **evidence autofill** replaces generic
placeholder text with README/git/fingerprint facts before you treat the roadmap
as production-ready.

**Deep reference:** [docs/roadmap.md](docs/roadmap.md)

### Mutation loop (JoyZoning + optional kernel)

```text
joyzoning(action='context')  → scope, convergence, roadmap brief, next_actions
begin → patch → verify → request_review → convergence → kanban_complete (if gates open)
```

Kernel-enabled path adds governed RPC patch/verify with coherence receipts and
progress telemetry (`/dietcode kernel cockpit`, watch, explain-gate).

---

## What you get

| Component | Role |
| --- | --- |
| **Roadmap** | Native `roadmap` toolset — checkpoint, validate, autofill, cockpit, gates |
| **BroccoliDB** | Knowledge graph, audit, refactor, structural analysis |
| **BroccoliQ** | Queue status, shard health, integrity |
| **JoyZoning** | Mutation lifecycle, convergence, runtime journal |
| **JSDP** | Rolling-horizon autonomous delivery helpers |
| **Kernel bridge** | Optional macOS `dietcode_kernel` patch/verify + raw-write policy |
| **Hooks** | Session start, pre/post tool call, write transforms, gate enforcement |

---

## Quick start

### 1. Install

```bash
mkdir -p ~/.hermes/plugins
cp -R dietcode-plugin ~/.hermes/plugins/dietcode
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci
python ../install.py
```

Or from a dev checkout: `make deploy` (see [Deploy](#deploy)).

### 2. Point at your project

```bash
export HERMES_KANBAN_WORKSPACE=/path/to/your/project
```

Add to Hermes config (`~/.hermes/config.yaml`):

```yaml
kanban:
  workspace: /path/to/your/project

dietcode:
  roadmap:
    enabled: true
    auto_install_skills: true
```

`ROADMAP.md` lives at **`{workspace}/ROADMAP.md`** — writes elsewhere are blocked.

### 3. Verify inside Hermes

```text
/dietcode doctor
/roadmap cockpit
/roadmap doctor
/joyzoning status
```

### 4. First roadmap pass (agent or operator)

```text
roadmap(action='guide')                              → phase + project_identity_line
roadmap(action='checkpoint')                         → evidence + algorithm
roadmap(action='apply_bootstrap_fill', context='write')   → if placeholders remain
roadmap(action='validate')                           → schema + bootstrap gates
```

Prime directive: *did the latest work strengthen or weaken the project's center of gravity?*

---

## Operator consoles

### Roadmap (project steering)

```text
/roadmap cockpit              One-screen health, identity, schema, next action
/roadmap doctor               Skill install + production checks
/roadmap explain-gate         Closed gates blocking kanban_complete
/roadmap checkpoint [context] Evidence briefing before edits
/rm validate                  Alias for validate flow
/dietcode roadmap             JSON health with project_identity_line
```

Decision tree when stuck: [docs/roadmap.md#decision-tree](docs/roadmap.md#decision-tree-which-call-next)

### Kernel (optional, macOS)

```text
/dietcode kernel cockpit          State, gates, roadmap steering merge
/dietcode kernel watch --follow   Live operation line
/dietcode kernel explain-gate     Patch gate diagnostics
/dietcode kernel progress         Human summary + phase hints
```

### Everything else

```text
/dietcode tools
/dietcode broccolidb
/broccolidb status
/broccoliq queue
/joyzoning status
```

---

## Configuration essentials

Safe defaults are seeded by `install.py`:

```yaml
dietcode:
  kernel:
    bridge:
      enabled: true
      mutations_enabled: false    # opt in to open patch gate
      raw_write_policy: warn
  roadmap:
    enabled: true
    auto_install_skills: true
    warn_on_stale_before_complete: true
    block_kanban_on_validation_pending: true
    stale_checkpoint_days: 7
```

Enable kernel mutation (macOS, after build + socket):

```yaml
dietcode:
  kernel:
    bridge:
      mutations_enabled: true
```

Full keys: [docs/roadmap.md#configuration-reference](docs/roadmap.md#configuration-reference) · [docs/dietcode-plugin.md](docs/dietcode-plugin.md)

---

## Verify (development)

Plugin checkout production gate:

```bash
make verify
```

Runs roadmap smoke, production audit, operator smoke, and 121 unit tests
(roadmap + kernel cockpit).

Inside Hermes after install:

```text
/dietcode doctor
```

Kernel integration (macOS):

```bash
make -C kernel kernel && make -C kernel restart-agent-server-fast
python scripts/kernel_bridge_e2e.py
```

BroccoliDB:

```bash
cd broccolidb && npm run build && npm test
```

---

## Deploy

```bash
./scripts/hermes_deploy.sh              # sync → reinstall Hermes → enable → verify
make deploy                             # same via Makefile
make deploy-fast                        # skip Hermes pip reinstall
```

| Variable | Purpose |
| --- | --- |
| `HERMES_SRC` | Hermes checkout for `pip install -e` |
| `HERMES_HOME` | Plugin install root (`~/.hermes`) |
| `DIETCODE_PLUGIN_SRC` | Dev checkout path when deploying from Hermes root |

---

## Requirements

- Hermes Agent with plugin support
- Python (Hermes runtime)
- Node.js 18+ and npm (`broccolidb/`)
- **Kernel bridge (optional):** macOS, built `kernel/build/dietcode-kernel`, socket at `~/.dietcode/control.sock`

Linux: full BroccoliDB, JoyZoning, JSDP, and roadmap; kernel bridge degrades gracefully.

---

## Project layout

```text
.
├── plugin.yaml                 Hermes manifest
├── hooks.py                    Session, pre/post tool, write transforms
├── install.py                  Config defaults, npm bootstrap
├── health.py                   /dietcode doctor and status
├── slash_commands.py           /dietcode, /roadmap, /broccolidb, …
├── lib/
│   ├── agent/
│   │   ├── roadmap/            Fingerprint, evidence, autofill, gates, cockpit
│   │   ├── joyzoning/          Lifecycle, convergence, JSDP
│   │   └── kernel_*            Bridge client, progress, cockpit
│   ├── runtime/                roadmap_hooks, joyzoning_hooks, kernel_hooks
│   └── tools/                  roadmap, dietcode_kernel, broccolidb, joyzoning
├── optional-skills/dietcode/auto-rolling-roadmap/   ROADMAP skill (auto-installed)
├── kernel/                     Quarantined macOS kernel subtree
├── broccolidb/                 Bundled TypeScript package
├── scripts/                    Deploy, audit, smoke, kernel e2e
├── tests/                      Roadmap + kernel cockpit unit tests
└── docs/                       Operator and developer documentation
```

Workspace artifacts (in **your** project, not the plugin):

```text
/path/to/your/project/
├── ROADMAP.md                  Living steering surface (12-section contract)
└── .dietcode/roadmap-state.json   Validate/checkpoint memory
```

---

## Documentation

| Start here | Document |
| --- | --- |
| **Roadmap steering (read first for agents)** | [docs/roadmap.md](docs/roadmap.md) |
| Install, config, workflow | [docs/dietcode-plugin.md](docs/dietcode-plugin.md) |
| Hook wiring, authority split | [docs/architecture.md](docs/architecture.md) |
| Kernel bridge operations | [docs/kernel-bridge-operations.md](docs/kernel-bridge-operations.md) |
| Slash commands + tools | [docs/tools-reference.md](docs/tools-reference.md) |
| Kernel + roadmap operator UX | [docs/agent-ergonomics.md](docs/agent-ergonomics.md) |
| BroccoliDB runtime | [docs/broccolidb.md](docs/broccolidb.md) |
| Doc index | [docs/README.md](docs/README.md) |
| Kernel build + RPC | [kernel/README.md](kernel/README.md) |
| Release history | [CHANGELOG.md](CHANGELOG.md) |

Agent skill (installed to workspace):  
`optional-skills/dietcode/auto-rolling-roadmap/SKILL.md`

---

## License

MIT — see [LICENSE](LICENSE).
