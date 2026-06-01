"""
BroccoliDB Tools Package — Separation of Concerns

Throughput / native RPC architecture:
  docs/broccolidb-native-execution-throughput.md

This package organizes BroccoliDB agent tool integrations into focused modules:
  - runner.py        → Subprocess execution layer (shared infrastructure)
  - db_gateway.py    → Native BroccoliDB/BroccoliQ RPC (persistent tsx worker)
  - db_native.py     → RPC method registry, version, warm_db_rpc()
  - agent_rpc.py     → AgentContext graph tools via agent_invoke RPC
  - exec.py          → Unified import facade (run_db_rpc, warm_db_rpc, …)
  - core_tools.py    → Init, status, audit, refactor (CLI-based)
  - joyzoning_tools.py → JoyZoning-specific validation & refactoring
  - graph_tools.py   → Knowledge graph CRUD & search
  - structural_tools.py → Blast radius, entropy, cycles, integrity
"""
