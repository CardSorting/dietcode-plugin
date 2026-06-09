#pragma once

#include <cstddef>
#include <sys/stat.h>

namespace dietcode::domain::control {

constexpr size_t kMaxRequestBytes = 1024 * 1024;
constexpr size_t kMaxResponseBytes = 4 * 1024 * 1024;
constexpr int kMaxGrepResults = 500;
constexpr size_t kMaxFileTextBytes = 1024 * 1024;
constexpr size_t kMaxPatchBytesBeforeConfirmation = 10 * 1024;
constexpr size_t kMaxPatchBytes = 1024 * 1024;
constexpr int kMaxBatchPatchCount = 10;
constexpr size_t kMaxChunkPreviewLength = 180;
constexpr int kMaxSearchDepth = 10;
constexpr int kMaxSearchScanFiles = 10000;
constexpr size_t kMaxSearchFileBytes = 2 * 1024 * 1024;
constexpr int kMaxPlanSteps = 30;
constexpr int kMaxActiveCombos = 4;

// SHELL: Agent shell wrapper limits (Pass IX — grep: rg 'kShell' src/domain/control/).
constexpr size_t kShellCatSmallMaxBytes = 64 * 1024;
constexpr int kShellCatSmallMaxLines = 500;
constexpr int kShellHeadTailDefaultLines = 80;
constexpr int kShellHeadTailMaxLines = 300;
constexpr int kShellRgMaxResults = 200;
constexpr int kShellRgTimeoutSeconds = 30;
constexpr size_t kShellMaxReadFileBytes = 2 * 1024 * 1024;
constexpr int kShellRgMaxScanFiles = 10000;

// SAFETY: Local abuse-resistance guardrails (grep: rg 'kMaxActiveConnections|SAFETY:' src/ docs/).
constexpr int kMaxActiveConnections = 8;
constexpr int kMaxPendingRequestsPerConnection = 32;
constexpr int kMaxMalformedRequestsPerConnection = 16;
constexpr int kMaxNestedCallWaitSeconds = 120;
constexpr int kSocketListenBacklog = 5;
constexpr size_t kMaxRuntimeDiagnosticLogBytes = 5 * 1024 * 1024;
constexpr size_t kMaxAuditLogBytes = 5 * 1024 * 1024;
constexpr size_t kMaxFailureBundleBytes = 2 * 1024 * 1024;
constexpr mode_t kSocketFileMode = 0600;
constexpr mode_t kDietcodeDirMode = 0700;

} // namespace dietcode::domain::control
