#pragma once

// RELEASE: Runtime contract version surfaces (grep: rg 'RELEASE:|kContract' src/ scripts/ docs/).
// Keep in sync with scripts/release_versions.py (verified by test_release_readiness.py).

namespace dietcode::domain::control {

inline constexpr const char* kControlProtocolVersion = "1.6";
inline constexpr const char* kTransactionSchemaVersion = "1.6.2";
inline constexpr const char* kContractInventoryVersion = "1.0.0";
inline constexpr const char* kRpcEnvelopeSchemaVersion = "1.0";
inline constexpr const char* kErrorTaxonomyVersion = "1.0";
inline constexpr const char* kDiagnosticsSchemaVersion = "1.0";
inline constexpr const char* kSafetyLimitsSchemaVersion = "1.0";
inline constexpr const char* kHarnessSummarySchemaVersion = "1.0";

} // namespace dietcode::domain::control
