# DietCode Hermes Plugin

**v1.11.0 — Native mutation (LUMI strategy)**

DietCode is a standalone Hermes Agent plugin: one installable directory that gives
agents **governed mutation**, **repository intelligence**, and **per-project
long-horizon steering** — without forcing a single runtime path.

BroccoliDB indexes your repo. JoyZoning owns the mutation lifecycle.
JSDP plans bounded delivery loops. The **roadmap** tool keeps `ROADMAP.md` as a
living steering surface unique to *your* project — not the plugin checkout.
**`dietcode_kernel`** provides native governed patch/verify with coherence tokens
(same strategy as codemarie-new / LUMI).

```text
Point workspace at YOUR project → fingerprint → evidence → ROADMAP.md steering
intent → patch → receipt → journal → verify → convergence → kanban (when gates open)
```

---

## Strategy

DietCode separates three authorities that other setups often collapse:

| Authority | Owner | Question it answers |
| --- | --- | --- |
| **Physical mutation** | `dietcode_kernel` (native) or raw Hermes tools | What changed on disk, with receipts? |
| **Lifecycle & completion** | JoyZoning + convergence gates | Is this mutation reviewed, verified, converged? |
| **Long-horizon steering** | Roadmap (`ROADMAP.md`) | What is the project becoming; what matters now? |

Nothing auto-completes kanban. Raw Hermes writes remain allowed. Governed patches
use `dietcode_kernel(action='patch')` with coherence tokens when `task_id` is set.
Roadmap gates can block
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

### Mutation loop (JoyZoning + native runtime)

```text
joyzoning(action='context')  → scope, convergence, roadmap brief, next_actions
dietcode_kernel(action='status') → coherence token when task_id set
begin → patch → verify → request_review → convergence → kanban_complete (if gates open)
```

Native path: governed patch/verify via `dietcode_kernel` with drift detection and
`.dietcode/mutation-state.json` (codemarie-new / LUMI strategy).

---

## What you get

| Component | Role |
| --- | --- |
| **Roadmap** | Native `roadmap` toolset — checkpoint, validate, autofill, cockpit, gates |
| **BroccoliDB** | Knowledge graph, audit, refactor, structural analysis, hive sync |
| **JoyZoning** | Mutation lifecycle, convergence, runtime journal |
| **JSDP** | Rolling-horizon autonomous delivery helpers |
| **Native mutation** | `dietcode_kernel` tool — patch, verify, coherence, drift detection |
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

### Native mutation

```text
/dietcode mutation status       Workspace revision, drift, coherence state
dietcode_kernel(action='status')   Same via tool
```

### Everything else

```text
/dietcode tools
/dietcode broccolidb
/broccolidb status
/joyzoning status
```

---

## Configuration essentials

Safe defaults are seeded by `install.py`:

```yaml
dietcode:
  workspace:
    workspace_root_source: hermes_project
  roadmap:
    enabled: true
    auto_install_skills: true
    warn_on_stale_before_complete: true
    block_kanban_on_validation_pending: true
    stale_checkpoint_days: 7
```

Full keys: [docs/roadmap.md#configuration-reference](docs/roadmap.md#configuration-reference) · [docs/dietcode-plugin.md](docs/dietcode-plugin.md)

---

## Verify (development)

Plugin checkout production gate:

```bash
make verify
```

Runs roadmap smoke, production audit, operator smoke, and unit tests
(roadmap + native mutation).

Inside Hermes after install:

```text
/dietcode doctor
/dietcode mutation status
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

Works on macOS and Linux — native mutation uses Python + git (no macOS binary).

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
│   │   ├── native_mutation.py  Governed patch, verify, coherence tokens
│   │   └── joyzoning/          Lifecycle, convergence, JSDP
│   ├── workspace_root.py       Project workspace resolution
│   ├── runtime/                roadmap_hooks, joyzoning_hooks, mutation_hooks
│   └── tools/                  roadmap, dietcode_kernel, broccolidb, joyzoning
├── optional-skills/dietcode/auto-rolling-roadmap/   ROADMAP skill (auto-installed)
├── broccolidb/                 Bundled TypeScript package
├── scripts/                    Deploy, audit, smoke
├── tests/                      Roadmap + native mutation unit tests
└── docs/                       Operator and developer documentation
```

Workspace artifacts (in **your** project, not the plugin):

```text
/path/to/your/project/
├── ROADMAP.md                  Living steering surface (12-section contract)
├── .dietcode/roadmap-state.json   Validate/checkpoint memory
└── .dietcode/mutation-state.json  Native mutation coherence state
```

---

## Documentation

| Start here | Document |
| --- | --- |
| **Roadmap steering (read first for agents)** | [docs/roadmap.md](docs/roadmap.md) |
| Install, config, workflow | [docs/dietcode-plugin.md](docs/dietcode-plugin.md) |
| Hook wiring, authority split | [docs/architecture.md](docs/architecture.md) |
| Slash commands + tools | [docs/tools-reference.md](docs/tools-reference.md) |
| BroccoliDB runtime | [docs/broccolidb.md](docs/broccolidb.md) |
| Doc index | [docs/README.md](docs/README.md) |
| Release history | [CHANGELOG.md](CHANGELOG.md) |

Agent skill (installed to workspace):  
`optional-skills/dietcode/auto-rolling-roadmap/SKILL.md`

---

## License

MIT — see [LICENSE](LICENSE).
