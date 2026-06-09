#import "MacControlServer+Private.hpp"
#import "MacControlMemoryService.hpp"
#import "MacControlSupport.hpp"

@implementation DietCodeControlServer (Memory)

- (void)ensureMemoryServiceForWorkspace {
    NSString* ws = [self safeWorkspacePath] ?: @"";
    if (_memoryService && [_memoryService.workspacePath isEqualToString:ws]) {
        _workspaceState.memoryService = _memoryService;
        return;
    }
    [_memoryService shutdown];
    _memoryService = [[MacControlMemoryService alloc] initWithWorkspacePath:ws];
    _workspaceState.memoryService = _memoryService;
}

- (void)executeMemoryMethod:(NSString*)method
                     params:(NSDictionary*)params
                  outResult:(NSDictionary**)outResult
                 outErrCode:(NSString**)outErrCode
                    outErrMsg:(NSString**)outErrMsg
                   outPaths:(NSString**)outPaths {
    (void)outPaths;
    [self ensureMemoryServiceForWorkspace];

    if ([method isEqualToString:@"memory.status"]) {
        *outResult = MacControlEnrichRuntimeSurface([_memoryService runtimeDiagnosticsPayload], @"runtime_diagnostics", @"runtime.timeline");
        return;
    }

    if (!_memoryService.available) {
        *outErrCode = @"runtime_journal_degraded";
        *outErrMsg = @"Runtime journal unavailable; mutation kernel remains authoritative.";
        *outResult = MacControlEnrichRuntimeSurface(@{
            @"degraded": @YES,
            @"checkpointStatus": _memoryService.checkpointStatus ?: @"unavailable",
            @"recoveryHint": @"retry_runtime_diagnostics_or_operation_status",
            @"nextRecommendedCommand": @"runtime.diagnostics",
            @"mutationAuthority": @"cpp_kernel",
        }, @"runtime_degraded", @"runtime.diagnostics");
        return;
    }

    if ([method isEqualToString:@"memory.operation.get"]) {
        NSString* opId = params[@"operationId"];
        NSDictionary* op = [_memoryService operationForId:opId];
        if (!op) {
            *outResult = @{ @"status": @"unknown", @"operationId": opId ?: @"" };
            return;
        }
        *outResult = MacControlEnrichRuntimeSurface(op, @"runtime_operation", @"runtime.correlate");
        return;
    }

    if ([method isEqualToString:@"memory.operation.list"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 50;
        NSInteger offset = params[@"offset"] ? [params[@"offset"] integerValue] : 0;
        *outResult = MacControlEnrichRuntimeListResult(@{
            @"operations": [_memoryService listOperations:limit offset:offset],
            @"mode": @"runtime_operation_list",
        }, @"runtime_operation_list", @"runtime.timeline", NO);
        return;
    }

    if ([method isEqualToString:@"memory.operation.findByIdempotencyKey"]) {
        NSString* key = params[@"idempotencyKey"];
        NSDictionary* op = [_memoryService operationForIdempotencyKey:key];
        *outResult = op ? MacControlEnrichRuntimeSurface(op, @"runtime_operation", @"runtime.correlate") : @{ @"status": @"unknown", @"idempotencyKey": key ?: @"" };
        return;
    }

    if ([method isEqualToString:@"memory.operation.findByRevision"]) {
        NSInteger revisionId = [params[@"revisionId"] integerValue];
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        *outResult = MacControlEnrichRuntimeListResult(@{
            @"revisionId": @(revisionId),
            @"operations": [_memoryService operationsForRevision:revisionId limit:limit],
            @"mode": @"runtime_operation_by_revision",
        }, @"runtime_operation_by_revision", @"runtime.timeline", NO);
        return;
    }

    if ([method isEqualToString:@"memory.operation.recent"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        if ([params[@"compact"] boolValue]) {
            *outResult = MacControlEnrichRuntimeSurface([_memoryService compactOperationSummaries:limit], @"runtime_operation_summary", @"runtime.timeline");
            return;
        }
        *outResult = MacControlEnrichRuntimeListResult(@{
            @"operations": [_memoryService recentOperations:limit],
            @"mode": @"runtime_operation_recent",
        }, @"runtime_operation_recent", @"runtime.timeline", NO);
        return;
    }

    if ([method isEqualToString:@"memory.replay.get"]) {
        NSString* key = params[@"idempotencyKey"];
        NSDictionary* replay = [_memoryService replayCacheForKey:key];
        if (!replay) {
            *outResult = @{
                @"status": @"unknown",
                @"idempotencyKey": key ?: @"",
                @"recoveryHint": @"retry_with_same_idempotencyKey_or_revalidate",
                @"nextRecommendedCommand": @"operation.status",
            };
            return;
        }
        if ([replay[@"expired"] boolValue]) {
            *outErrCode = @"replay_expired";
            *outErrMsg = @"Replay cache entry expired; re-validate before retry.";
            *outResult = replay;
            return;
        }
        *outResult = MacControlApplyJournalAuthorityLabels(replay);
        return;
    }

    if ([method isEqualToString:@"memory.revision.get"]) {
        NSInteger revisionId = [params[@"revisionId"] integerValue];
        NSDictionary* rev = [_memoryService revisionForId:revisionId];
        *outResult = MacControlApplyJournalAuthorityLabels(rev ?: @{ @"status": @"unknown", @"revisionId": @(revisionId) });
        return;
    }

    if ([method isEqualToString:@"memory.revision.list"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 50;
        *outResult = MacControlApplyJournalAuthorityLabels(@{
            @"revisions": [_memoryService listRevisions:limit],
            @"mode": @"memory_revision_list",
        });
        return;
    }

    if ([method isEqualToString:@"memory.revision.changedFiles"]) {
        NSInteger revisionId = [params[@"revisionId"] integerValue];
        NSDictionary* rev = [_memoryService revisionForId:revisionId];
        *outResult = MacControlApplyJournalAuthorityLabels(@{
            @"revisionId": @(revisionId),
            @"changedFiles": rev[@"changedFiles"] ?: @[],
            @"mode": @"memory_revision_changed_files",
        });
        return;
    }

    if ([method isEqualToString:@"memory.revision.lastMutation"]) {
        *outResult = MacControlApplyJournalAuthorityLabels([_memoryService lastMutationRevision] ?: @{ @"status": @"unknown" });
        return;
    }

    if ([method isEqualToString:@"memory.workflow.start"]) {
        NSString* err = nil;
        NSDictionary* wf = [_memoryService startWorkflow:params error:&err];
        if (!wf) {
            *outErrCode = @"memory_write_failed";
            *outErrMsg = err ?: @"Failed to start workflow.";
            return;
        }
        *outResult = wf;
        return;
    }

    if ([method isEqualToString:@"memory.workflow.step"]) {
        NSString* err = nil;
        NSDictionary* step = [_memoryService recordWorkflowStep:params error:&err];
        if (!step) {
            *outErrCode = @"memory_write_failed";
            *outErrMsg = err ?: @"Failed to record workflow step.";
            return;
        }
        *outResult = step;
        return;
    }

    if ([method isEqualToString:@"memory.workflow.complete"]) {
        NSString* workflowId = params[@"workflowId"];
        *outResult = [_memoryService completeWorkflow:workflowId error:nil] ?: @{ @"status": @"unknown", @"workflowId": workflowId ?: @"" };
        return;
    }

    if ([method isEqualToString:@"memory.workflow.fail"]) {
        *outResult = [_memoryService failWorkflow:params error:nil] ?: @{ @"status": @"unknown" };
        return;
    }

    if ([method isEqualToString:@"memory.workflow.get"]) {
        NSString* workflowId = params[@"workflowId"];
        *outResult = [_memoryService workflowForId:workflowId] ?: @{ @"status": @"unknown", @"workflowId": workflowId ?: @"" };
        return;
    }

    if ([method isEqualToString:@"memory.workflow.recent"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        *outResult = @{
            @"workflows": [_memoryService recentWorkflows:limit],
            @"mode": @"memory_workflow_recent",
        };
        return;
    }

    if ([method isEqualToString:@"memory.verify.record"]) {
        NSString* err = nil;
        if (![_memoryService recordVerificationRun:params error:&err]) {
            *outErrCode = @"memory_write_failed";
            *outErrMsg = err ?: @"Failed to record verification run.";
            return;
        }
        *outResult = @{ @"recorded": @YES, @"mode": @"memory_verification_recorded" };
        return;
    }

    if ([method isEqualToString:@"memory.verify.latest"]) {
        NSString* command = params[@"command"] ?: @"verify-agent-runtime-full";
        *outResult = MacControlApplyJournalAuthorityLabels([_memoryService latestVerificationForCommand:command] ?: @{ @"status": @"unknown", @"command": command });
        return;
    }

    if ([method isEqualToString:@"memory.verify.history"]) {
        NSString* command = params[@"command"] ?: @"verify-agent-runtime-full";
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        *outResult = MacControlApplyJournalAuthorityLabels(@{
            @"command": command,
            @"runs": [_memoryService verificationHistory:command limit:limit],
            @"mode": @"memory_verification_history",
        });
        return;
    }
}

- (void)persistMutationToMemory:(NSString*)method
                    idempotencyKey:(NSString*)idempotencyKey
                    paramsHash:(NSString*)paramsHash
                    receipt:(NSDictionary*)receipt
                    changedPaths:(NSArray<NSString*>*)paths
                    revisionBefore:(NSInteger)revisionBefore
                    revisionAfter:(NSInteger)revisionAfter
                    resultPayload:(NSDictionary*)resultPayload {
    [self ensureMemoryServiceForWorkspace];
    if (!_memoryService.available) return;

    NSString* opId = [[NSUUID UUID] UUIDString];
    NSString* receiptHash = StableHashForString(
        [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:receipt ?: @{} options:0 error:nil] encoding:NSUTF8StringEncoding] ?: @"");

    [_memoryService recordOperation:@{
        @"operationId": opId,
        @"method": method,
        @"paramsHash": paramsHash ?: @"",
        @"idempotencyKey": idempotencyKey ?: @"",
        @"status": @"completed",
        @"receipt": receipt ?: @{},
        @"receiptHash": receiptHash,
        @"revisionBefore": @(revisionBefore),
        @"revisionAfter": @(revisionAfter),
        @"completedAt": @([[NSDate date] timeIntervalSince1970]),
    } error:nil];

    [_memoryService recordRevision:@{
        @"revisionId": @(revisionAfter),
        @"changedFiles": paths ?: @[],
        @"mutationSource": @"agent",
        @"operationId": opId,
        @"receiptHash": receiptHash,
        @"previousRevisionId": @(revisionBefore),
    } error:nil];

    if (idempotencyKey.length > 0 && resultPayload) {
        [_memoryService storeReplayCache:@{
            @"idempotencyKey": idempotencyKey,
            @"method": method,
            @"paramsHash": paramsHash ?: @"",
            @"result": resultPayload,
            @"receiptHash": receiptHash,
        } error:nil];
    }

    [_memoryService recordTelemetryEvent:@"mutation_recorded" payload:@{
        @"method": method ?: @"",
        @"revisionAfter": @(revisionAfter),
        @"idempotencyKey": idempotencyKey ?: @"",
    }];
}

@end
