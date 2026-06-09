#!/usr/bin/env python3
"""
RELEASE: Runtime contract version surfaces — grep with `rg 'RELEASE:|CONTRACT_VERSION' scripts/ docs/`.

Keep in sync with src/domain/control/ControlReleaseVersions.hpp.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_HEADER = REPO_ROOT / "src/domain/control/ControlReleaseVersions.hpp"
SURFACE_CLASSIFICATION_PATH = REPO_ROOT / "scripts/fixtures/release/surface_classification.json"

# RELEASE: Canonical version IDs exposed via rpc.version, --emit-config, --diagnose.
CLIENT_SCHEMA_VERSION = "1.6.2"
CONTROL_PROTOCOL_VERSION = "1.6"
TRANSACTION_SCHEMA_VERSION = "1.6.2"
CONTRACT_INVENTORY_VERSION = "1.0.0"
RPC_ENVELOPE_SCHEMA_VERSION = "1.0"
ERROR_TAXONOMY_VERSION = "1.0"
DIAGNOSTICS_SCHEMA_VERSION = "1.0"
SAFETY_LIMITS_SCHEMA_VERSION = "1.0"
HARNESS_SUMMARY_SCHEMA_VERSION = "1.0"

RUNTIME_VERSIONS: dict[str, str] = {
    "controlProtocol": CONTROL_PROTOCOL_VERSION,
    "transactionSchema": TRANSACTION_SCHEMA_VERSION,
    "clientSchema": CLIENT_SCHEMA_VERSION,
    "contractInventory": CONTRACT_INVENTORY_VERSION,
    "rpcEnvelope": RPC_ENVELOPE_SCHEMA_VERSION,
    "errorTaxonomy": ERROR_TAXONOMY_VERSION,
    "diagnostics": DIAGNOSTICS_SCHEMA_VERSION,
    "safetyLimits": SAFETY_LIMITS_SCHEMA_VERSION,
    "harnessSummary": HARNESS_SUMMARY_SCHEMA_VERSION,
}

STABILITY_LABELS = frozenset({"stable", "experimental", "internal", "deprecated"})


def runtime_versions_payload() -> dict[str, Any]:
    return {
        "contractVersions": dict(RUNTIME_VERSIONS),
        "contractInventoryVersion": CONTRACT_INVENTORY_VERSION,
    }


def parse_versions_from_header(path: Path = VERSIONS_HEADER) -> dict[str, str]:
    import re

    text = path.read_text(encoding="utf-8")
    mapping = {
        "kControlProtocolVersion": "controlProtocol",
        "kTransactionSchemaVersion": "transactionSchema",
        "kContractInventoryVersion": "contractInventory",
        "kRpcEnvelopeSchemaVersion": "rpcEnvelope",
        "kErrorTaxonomyVersion": "errorTaxonomy",
        "kDiagnosticsSchemaVersion": "diagnostics",
        "kSafetyLimitsSchemaVersion": "safetyLimits",
        "kHarnessSummarySchemaVersion": "harnessSummary",
    }
    parsed: dict[str, str] = {}
    for const_name, key in mapping.items():
        match = re.search(rf'{re.escape(const_name)}\s*=\s*"([^"]+)"', text)
        if not match:
            raise AssertionError(f"missing {const_name} in {path}")
        parsed[key] = match.group(1)
    return parsed


def load_surface_classification(path: Path = SURFACE_CLASSIFICATION_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_versions_synced() -> None:
    header = parse_versions_from_header()
    for key, value in header.items():
        assert RUNTIME_VERSIONS.get(key) == value, f"version drift for {key}: py={RUNTIME_VERSIONS.get(key)} cpp={value}"
