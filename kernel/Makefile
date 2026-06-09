CXX := clang++

INC_FLAGS := -I./src \
             -I./src/kernel \
             -I./src/kernel/workspace \
             -I./src/platform/macos \
             -I./src/platform/macos/control \
             -I./src/platform/macos/control/categories \
             -I./src/platform/macos/control/services \
             -I./src/platform/macos/control/utils \
             -I./src/platform/macos/services

CXXFLAGS := -std=c++20 -Wall -Wextra -Wpedantic $(INC_FLAGS)
OBJCXXFLAGS := -std=c++20 -Wall -Wextra $(INC_FLAGS) -fobjc-arc

BUILD_DIR := build
KERNEL_NAME := dietcode-kernel
KERNEL_BINARY := $(BUILD_DIR)/$(KERNEL_NAME)
KERNEL_RESOURCES := $(BUILD_DIR)/resources
KERNEL_BIN := $(KERNEL_RESOURCES)/bin

KERNEL_WORKSPACE_CPP := \
	src/kernel/workspace/WorkspaceFileOps.cpp \
	src/kernel/workspace/WorkspacePatchOps.cpp \
	src/kernel/workspace/WorkspaceVerifyOps.cpp \
	src/kernel/workspace/WorkspaceIndex.cpp \
	src/kernel/workspace/WorkspaceSession.cpp

KERNEL_RUNTIME_MM := \
	src/kernel/KernelAppDelegate.mm \
	src/kernel/KernelRuntime.mm \
	src/kernel/workspace/WorkspaceSessionBridge.mm

KERNEL_APP_MM := \
	src/kernel/main.mm \
	$(KERNEL_RUNTIME_MM)

CONTROL_MM := \
	src/platform/macos/control/MacControlServer.mm \
	src/platform/macos/control/categories/MacControlServer+File.mm \
	src/platform/macos/control/categories/MacControlServer+Editor.mm \
	src/platform/macos/control/categories/MacControlServer+Git.mm \
	src/platform/macos/control/categories/MacControlServer+Terminal.mm \
	src/platform/macos/control/categories/MacControlServer+Context.mm \
	src/platform/macos/control/utils/MacControlSupport.mm \
	src/platform/macos/control/utils/MacControlPathSecurity.mm \
	src/platform/macos/control/utils/MacControlSerialization.mm \
	src/platform/macos/control/utils/MacControlRuntimeDiagnostics.mm \
	src/platform/macos/control/utils/MacControlSocketSafety.mm \
	src/platform/macos/control/utils/MacControlReleaseVersions.mm \
	src/platform/macos/control/utils/MacControlDiffParsing.mm \
	src/platform/macos/control/services/MacControlRecoveryStore.mm \
	src/platform/macos/control/services/MacControlSearchService.mm \
	src/platform/macos/control/services/MacControlPatchService.mm \
	src/platform/macos/control/services/MacControlWorkspaceState.mm \
	src/platform/macos/control/services/MacControlCoherenceTokens.mm \
	src/platform/macos/control/services/MacControlMemoryService.mm \
	src/platform/macos/control/services/MacControlApprovalService.mm \
	src/platform/macos/control/categories/MacControlServer+Approval.mm \
	src/platform/macos/control/categories/MacControlServer+WorkspaceDrift.mm \
	src/platform/macos/control/categories/MacControlServer+Coherence.mm \
	src/platform/macos/control/categories/MacControlServer+VerifyGate.mm \
	src/platform/macos/control/categories/MacControlServer+Memory.mm \
	src/platform/macos/control/categories/MacControlServer+Runtime.mm \
	src/platform/macos/control/services/MacControlTaskRuntime.mm \
	src/platform/macos/control/services/MacControlComboRuntime.mm \
	src/platform/macos/control/services/MacControlRoutingPolicy.mm \
	src/platform/macos/control/services/MacControlMethodCatalog.mm \
	src/platform/macos/control/services/MacControlToolRegistry.mm \
	src/platform/macos/control/services/MacControlShellService.mm \
	src/platform/macos/control/categories/MacControlServer+Shell.mm \
	src/platform/macos/control/services/MacControlWindowBridge.mm \
	src/platform/macos/services/SymbolIndexService.mm \
	src/platform/macos/services/DiffAnalysisService.mm \
	src/platform/macos/services/WorkspaceAnalysisService.mm \
	src/platform/macos/services/BufferStateService.mm \
	src/platform/macos/services/SubprocessRunner.mm \
	src/filesystem/GitService.mm

KERNEL_OBJCXXFLAGS := $(OBJCXXFLAGS) -DDIETCODE_KERNEL_BUILD
KERNEL_SOURCES := $(KERNEL_WORKSPACE_CPP) src/filesystem/FileService.cpp $(CONTROL_MM) $(KERNEL_APP_MM)
KERNEL_OBJ_DIR := $(BUILD_DIR)/obj
KERNEL_CPP_OBJECTS := $(patsubst %.cpp,$(KERNEL_OBJ_DIR)/%.o,$(filter %.cpp,$(KERNEL_SOURCES)))
KERNEL_MM_OBJECTS := $(patsubst %.mm,$(KERNEL_OBJ_DIR)/%.o,$(filter %.mm,$(KERNEL_SOURCES)))
KERNEL_OBJECTS := $(KERNEL_CPP_OBJECTS) $(KERNEL_MM_OBJECTS)

.PHONY: all kernel app headless ensure-socket restart-agent-server restart-agent-server-fast \
	agent-ready agent-status agent-ping agent-methods agent-capabilities agent-self-test \
	test-agent-offline control-smoke test-task-health test-rpc-transaction test-ergonomics \
	test-grep-diff-tooling test-runtime-determinism test-transaction-kernel test-harness-realism \
	test-deterministic-retrieval test-agent-workflow-smoke test-agent-shell-tooling \
	test-agent-shell-tooling-fast test-agent-shell-workflows test-agent-shell-workflows-fast \
	test-authority-boundaries test-authority-boundaries-fast test-cli-agent-failures \
	test-docs-code-drift test-partial-success-closure test-broccoliq-runtime-memory \
	test-broccoliq-runtime-memory-fast test-runtime-native-integration \
	test-runtime-native-integration-fast test-coherence-tokens test-coherence-tokens-fast \
	coherence-recovery-smoke coherence-recovery-smoke-fast coherence-core-v0.1 validate \
	agent-integration test-agent-integration verify-agent-runtime verify-agent-runtime-fast \
	verify-agent-runtime-full verify-agent-runtime-full-fast release-check-agent-runtime \
	test-mutation-authority test-diff-authority test-verification-authority test test-editor clean

all: kernel

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(KERNEL_RESOURCES):
	mkdir -p $(KERNEL_RESOURCES)

$(KERNEL_BIN):
	mkdir -p $(KERNEL_BIN)

$(KERNEL_OBJ_DIR)/%.o: %.cpp | $(BUILD_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DDIETCODE_KERNEL_BUILD -c $< -o $@

$(KERNEL_OBJ_DIR)/%.o: %.mm | $(BUILD_DIR)
	@mkdir -p $(dir $@)
	$(CXX) $(KERNEL_OBJCXXFLAGS) -c $< -o $@

$(KERNEL_BINARY): $(KERNEL_OBJECTS) | $(BUILD_DIR)
	$(CXX) $(KERNEL_OBJECTS) -framework Cocoa -lsqlite3 -o $(KERNEL_BINARY)

kernel: $(KERNEL_BINARY)

app: kernel

headless: kernel
	$(KERNEL_BINARY)

ensure-socket: kernel
	$(KERNEL_BINARY) --ensure-socket

restart-agent-server: kernel
	-pkill -f "$(KERNEL_BINARY)" 2>/dev/null || true
	sleep 0.5
	DIETCODE_REPO_ROOT=$(CURDIR) $(KERNEL_BINARY) --ensure-socket

restart-agent-server-fast:
	-pkill -f "$(KERNEL_BINARY)" 2>/dev/null || true
	sleep 0.5
	DIETCODE_REPO_ROOT=$(CURDIR) $(KERNEL_BINARY) --ensure-socket

agent-ready: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json

agent-status: kernel
	python3 scripts/dietcode_agent_client.py --status --compact --error-json

agent-ping: kernel
	python3 scripts/dietcode_agent_client.py --compact --error-json rpc.ping

agent-methods: kernel
	python3 scripts/dietcode_agent_client.py --list-methods --compact --error-json

agent-capabilities: kernel
	python3 scripts/dietcode_agent_client.py --capabilities --compact --error-json

agent-self-test:
	python3 scripts/dietcode_agent_client.py --self-test --compact

test-agent-offline: agent-self-test
	python3 scripts/test_contract_lockdown.py --compact

control-smoke: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/control_smoke_test.py --compact

test-task-health: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_task_server_health.py --compact

test-rpc-transaction: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_rpc_transaction_health.py --compact

test-operator-diagnostics: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_operator_diagnostics.py --compact

test-runtime-safety: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_runtime_safety.py --compact

test-grep-diff-tooling: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_grep_diff_tooling.py --compact

test-runtime-determinism: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_runtime_determinism.py --compact

test-transaction-kernel: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_transaction_kernel.py --compact

test-harness-realism: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_harness_realism.py --compact

test-deterministic-retrieval: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_deterministic_retrieval.py --compact

test-agent-workflow-smoke: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_agent_workflow_smoke.py --compact

test-agent-shell-tooling: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_agent_shell_tooling.py --compact

test-agent-shell-tooling-fast:
	python3 scripts/test_agent_shell_tooling.py --compact

test-agent-shell-workflows: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_agent_shell_workflows.py --compact

test-agent-shell-workflows-fast:
	python3 scripts/test_agent_shell_workflows.py --compact

test-authority-boundaries: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_authority_boundaries.py --compact

test-authority-boundaries-fast:
	python3 scripts/test_authority_boundaries.py --compact

test-cli-agent-failures: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_cli_agent_failures.py --compact

test-docs-code-drift:
	python3 scripts/test_docs_code_drift.py --compact

test-partial-success-closure: restart-agent-server
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_partial_success_closure.py --compact

test-broccoliq-runtime-memory: restart-agent-server
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_broccoliq_runtime_memory.py --compact

test-broccoliq-runtime-memory-fast:
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_broccoliq_runtime_memory.py --compact

test-runtime-native-integration: restart-agent-server
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_runtime_native_integration.py --compact

test-runtime-native-integration-fast:
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_runtime_native_integration.py --compact

test-coherence-tokens: kernel restart-agent-server-fast
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_coherence_tokens.py --compact

test-coherence-tokens-fast:
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/test_coherence_tokens.py --compact

coherence-recovery-smoke: restart-agent-server
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	DIETCODE_REPO_ROOT=$(CURDIR) PYTHONUNBUFFERED=1 python3 scripts/coherence_recovery_smoke.py --compact

coherence-recovery-smoke-fast:
	DIETCODE_REPO_ROOT=$(CURDIR) PYTHONUNBUFFERED=1 python3 scripts/coherence_recovery_smoke.py --compact

coherence-core-v0.1: kernel
	$(MAKE) restart-agent-server-fast
	DIETCODE_REPO_ROOT=$(CURDIR) python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	$(MAKE) test-coherence-tokens-fast
	$(MAKE) coherence-recovery-smoke-fast
	@echo "coherence-core-v0.1 — kernel coherence tokens + recovery smoke: OK"

validate:
	$(MAKE) coherence-core-v0.1
	$(MAKE) test-docs-code-drift
	@echo "validate — coherence-core-v0.1 + docs drift: OK"

test-ergonomics: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/test_ergonomics.py --compact

test-mutation-authority:
	python3 scripts/test_mutation_authority.py

test-diff-authority:
	python3 scripts/test_diff_authority.py

test-verification-authority:
	python3 scripts/test_verification_authority.py

agent-integration: kernel
	python3 scripts/dietcode_agent_client.py --wait-ready --compact --error-json --quiet
	python3 scripts/run_agent_integration_tests.py --compact

test-agent-integration: agent-integration

verify-agent-runtime:
	python3 scripts/verify_agent_runtime.py --compact

verify-agent-runtime-fast:
	python3 scripts/verify_agent_runtime.py --compact --assume-server-ready

verify-agent-runtime-full:
	python3 scripts/verify_agent_runtime_full.py --compact

verify-agent-runtime-full-fast:
	python3 scripts/verify_agent_runtime_full.py --compact --assume-server-ready

release-check-agent-runtime:
	python3 scripts/release_check_agent_runtime.py --compact

test: agent-self-test

test-editor:
	@echo "Editor C++ unit tests removed — use make coherence-core-v0.1 for the kernel baseline." >&2
	@exit 1

clean:
	rm -rf $(BUILD_DIR)
