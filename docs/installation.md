# Installation

DietCode supports three install paths. **Drag-and-drop** is recommended for most users.

---

## Method 1: One-step install script (recommended)

From this package root:

```bash
./scripts/install-to-hermes.sh
```

The script:

1. Rsyncs `dietcode/` → `~/.hermes/plugins/dietcode/` (excludes `node_modules`)
2. Runs `install.py` to merge Hermes config defaults
3. Runs `npm ci` in `broccolidb/` when Node is available

Environment overrides:

| Variable | Effect |
|----------|--------|
| `HERMES_HOME` | Target Hermes profile directory (default `~/.hermes`) |
| `DIETCODE_HOME` | Alias for `HERMES_HOME` |
| `DIETCODE_SKIP_NPM=1` | Skip automatic `npm ci` |

Restart Hermes after install.

---

## Method 2: Manual drag-and-drop

```bash
cp -R dietcode ~/.hermes/plugins/dietcode
python3 ~/.hermes/plugins/dietcode/install.py
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci
```

### What happens automatically

**On first Hermes startup** after copy:

- Hermes discovers `~/.hermes/plugins/dietcode/plugin.yaml`
- `auto_enable: true` loads the plugin without manual `hermes plugins enable`
- Enablement is persisted to `plugins.enabled` in `config.yaml`

**On plugin register** (`register()` in `__init__.py`):

- `install.apply_seamless_defaults()` merges:
  - `dietcode` into `plugins.enabled`
  - removal from `plugins.disabled` if present
  - `dietcode` into `toolsets`
  - `joyzoning.governance.enabled: true` if unset

**Namespace bootstrap** (`_bootstrap.py`):

Hermes loads user plugins as `hermes_plugins.dietcode`, but all DietCode source imports
use `plugins.dietcode.*`. Bootstrap aliases the loaded module onto `plugins.dietcode`
before any other plugin code runs — no pip shim required.

---

## Method 3: pip install (optional)

For developers or CI environments that prefer a Python package:

```bash
pip install -e /path/to/dietcode-plugin
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci   # if broccolidb not yet built
```

The package registers via entry point:

```toml
[project.entry-points."hermes_agent.plugins"]
dietcode = "plugins.dietcode"
```

Pip uses `shim/plugins/` for the `plugins` namespace; drag-and-drop uses `_bootstrap.py` instead.

After pip install you still need BroccoliDB Node deps unless you copy the full `dietcode/` tree
with bundled `broccolidb/`.

---

## Hermes profiles

Each Hermes profile has its own `HERMES_HOME`:

```bash
hermes -p myprofile plugins list
HERMES_HOME=~/.hermes/profiles/myprofile ./scripts/install-to-hermes.sh
```

Install the plugin into **each profile** that should use DietCode:

```
~/.hermes/plugins/dietcode/              # default profile
~/.hermes/profiles/<name>/plugins/dietcode/   # named profile
```

Or symlink the plugin directory if you want one copy shared across profiles.

---

## BroccoliDB Node runtime

BroccoliDB ships as TypeScript inside `dietcode/broccolidb/`. Install dependencies once:

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

Skip auto-install during wizard:

```bash
python3 ~/.hermes/plugins/dietcode/install.py --skip-npm
```

After Node upgrades, rebuild native modules:

```bash
cd ~/.hermes/plugins/dietcode/broccolidb && npm rebuild better-sqlite3
```

---

## Verification checklist

| Step | Command | Expected |
|------|---------|----------|
| Plugin listed | `hermes plugins list` | `dietcode` enabled, no error |
| Health report | `/dietcode doctor` | contract ok, broccolidb rpc available |
| Tool load | `/dietcode tools` | 5 modules loaded, 0 registry missing |
| Governance | `/joyzoning status` | structural audit runs (needs npm) |

Example doctor output sections:

- Plugin registered on PluginManager
- Contract checks pass
- BroccoliDB root resolved, `node_modules_installed: true`, `rpc_available: true`
- JoyZoning governance enforcement active

---

## Uninstall

```bash
rm -rf ~/.hermes/plugins/dietcode
```

Edit `~/.hermes/config.yaml` to remove `dietcode` from `plugins.enabled` and `toolsets` if desired.
Governance hooks stop when the plugin is not loaded.

---

## Upgrade

```bash
./scripts/install-to-hermes.sh
# or
./scripts/sync-from-fork.sh /path/to/diet-hermes-fork   # maintainers
./scripts/install-to-hermes.sh
```

Restart Hermes. Run `/dietcode doctor` to confirm tool contract and RPC version alignment.
