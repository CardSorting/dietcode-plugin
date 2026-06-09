# File structure

Repository map for the **kernel/coherence-core archive**.

[ARCHIVE.md](../ARCHIVE.md) · [architecture.md](architecture.md)

---

## Top level

```text
DietCode-IDE/
├── ARCHIVE.md                   # Retained vs removed index
├── README.md                    # Project entry
├── Makefile                     # kernel, validate, coherence gates
├── .github/workflows/           # CI: make validate on macOS
├── build/
│   ├── dietcode-kernel          # Headless kernel binary
│   └── obj/                     # Incremental compile cache
├── src/
│   ├── kernel/                  # Entry, WorkspaceSession bridge
│   ├── kernel/workspace/        # File/patch/verify ops
│   ├── platform/macos/control/  # JSON-RPC + coherence + gates
│   ├── platform/macos/services/   # Subprocess, diff, symbol analysis
│   ├── filesystem/              # FileService, GitService, PathUtils
│   └── domain/control/          # Shared control-plane types
├── scripts/
│   ├── dietcode_agent_client.py # Python RPC CLI
│   ├── dietcode_coherence.py    # Coherence recovery helpers
│   ├── test_coherence_tokens.py # Live coherence tests
│   ├── coherence_recovery_smoke.py
│   ├── agent_contracts.py       # Frozen contract key sets
│   ├── test_docs_code_drift.py  # Docs ↔ code lock
│   └── fixtures/
│       ├── coherence_recovery/  # Recovery smoke workspace
│       ├── recovery/            # Error recovery hint fixtures
│       └── release/             # Internal namespace fixtures
├── benchmarks/                  # Frozen research (bridge-dependent runners)
├── docs/                        # This documentation tree
└── resources/
    ├── logo.svg
    └── bin/dietcode-agent-client  # Python CLI wrapper
```

---

## Kernel control plane

```text
src/platform/macos/control/
├── MacControlServer.mm           # RPC dispatch, auth, autonomy
├── categories/
│   ├── MacControlServer+File.mm
│   ├── MacControlServer+Editor.mm
│   ├── MacControlServer+Git.mm
│   ├── MacControlServer+Context.mm
│   ├── MacControlServer+Approval.mm
│   ├── MacControlServer+WorkspaceDrift.mm
│   ├── MacControlServer+Coherence.mm
│   └── MacControlServer+VerifyGate.mm
└── services/
    ├── MacControlMethodCatalog.mm
    ├── MacControlApprovalService.mm
    ├── MacControlCoherenceTokens.mm
    ├── MacControlPatchService.mm
    └── MacControlWorkspaceState.mm
```

---

## Key scripts

| Script | Purpose |
|--------|---------|
| `dietcode_agent_client.py` | JSON-RPC CLI — primary integration surface |
| `dietcode_coherence.py` | Token helpers, drift completion, recovery retry |
| `test_coherence_tokens.py` | Live kernel coherence enforcement |
| `coherence_recovery_smoke.py` | End-to-end recovery vertical |
| `test_docs_code_drift.py` | Docs ↔ contracts alignment |
| `control_smoke_test.py` | Control plane smoke |
| `agent_contracts.py` | Frozen key sets for harness validators |

---

## Local runtime state

| Path | Purpose |
|------|---------|
| `~/.dietcode/control.sock` | Kernel Unix socket |
| `~/.dietcode/session.token` | RPC auth (mode `0600`) |
| `~/.dietcode/session/` | Recovery store (`DIETCODE_SESSION_DIR`) |

---

## Not in tree

| Removed | Notes |
|---------|-------|
| `cockpit/`, `legacy_ui/`, `agent-bridge/`, `integrations/` | Product surfaces — see [archive-note.md](archive-note.md) |
| `src/editor/`, `src/ui/`, etc. | Editor scaffold — pass 4 |
| `DietCode.app`, `Info.plist` | App bundle packaging |

---

## Related

- [testing.md](testing.md) — validation commands
- [kernel-rpc.md](kernel-rpc.md) — RPC reference
- [agent-environment.md](agent-environment.md) — env vars
