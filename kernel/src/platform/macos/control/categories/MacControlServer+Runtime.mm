#import "MacControlServer+Private.hpp"
#import "MacControlMemoryService.hpp"
#import "MacControlSupport.hpp"

@implementation DietCodeControlServer (Runtime)

- (NSDictionary*)runtimeTimelineResult:(NSDictionary*)params activityOnly:(BOOL)activityOnly {
    [self ensureMemoryServiceForWorkspace];
    NSMutableDictionary* query = [params mutableCopy] ?: [NSMutableDictionary dictionary];
    if (activityOnly) {
        query[@"eventTypes"] = @[@"mutation_applied", @"revision_recorded", @"rollback_applied", @"replay_cached"];
    }
    NSDictionary* timeline = [_memoryService timelineWithParams:query];
    BOOL truncated = [timeline[@"truncated"] boolValue];
    return MacControlEnrichRuntimeListResult(timeline, @"runtime_timeline", @"runtime.timeline", truncated);
}

- (void)executeRuntimeMethod:(NSString*)method
                      params:(NSDictionary*)params
                   outResult:(NSDictionary**)outResult
                  outErrCode:(NSString**)outErrCode
                     outErrMsg:(NSString**)outErrMsg
                    outPaths:(NSString**)outPaths {
    (void)outPaths;
    [self ensureMemoryServiceForWorkspace];

    if ([method isEqualToString:@"runtime.diagnostics"] || [method isEqualToString:@"runtime.status"]) {
        *outResult = MacControlEnrichRuntimeSurface([_memoryService runtimeDiagnosticsPayload], @"runtime_diagnostics", @"runtime.timeline");
        return;
    }

    if ([method isEqualToString:@"runtime.timeline"] || [method isEqualToString:@"runtime.history"]) {
        *outResult = [self runtimeTimelineResult:params activityOnly:NO];
        return;
    }

    if ([method isEqualToString:@"workspace.activity"]) {
        *outResult = [self runtimeTimelineResult:params activityOnly:YES];
        return;
    }

    if ([method isEqualToString:@"runtime.operation.recent"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        BOOL compact = [params[@"compact"] boolValue];
        if (compact) {
            *outResult = MacControlEnrichRuntimeSurface([_memoryService compactOperationSummaries:limit], @"runtime_operation_summary", @"runtime.timeline");
            return;
        }
        NSDictionary* list = @{
            @"operations": [_memoryService recentOperations:limit],
            @"mode": @"runtime_operation_list",
        };
        *outResult = MacControlEnrichRuntimeListResult(list, @"runtime_operation_list", @"runtime.timeline", NO);
        return;
    }

    if ([method isEqualToString:@"runtime.warnings.recent"]) {
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 20;
        *outResult = MacControlEnrichRuntimeListResult(@{
            @"warnings": [_memoryService recentWarnings:limit],
            @"mode": @"runtime_warnings",
        }, @"runtime_warnings", @"runtime.timeline", NO);
        return;
    }

    if ([method isEqualToString:@"runtime.correlate"]) {
        NSString* operationId = params[@"operationId"];
        NSString* idempotencyKey = params[@"idempotencyKey"];
        NSMutableDictionary* correlation = [NSMutableDictionary dictionary];
        if (operationId.length > 0) {
            correlation[@"operation"] = [_memoryService operationForId:operationId];
        }
        if (idempotencyKey.length > 0) {
            correlation[@"operationByIdempotency"] = [_memoryService operationForIdempotencyKey:idempotencyKey];
            correlation[@"replay"] = [_memoryService replayCacheForKey:idempotencyKey];
        }
        if (params[@"revisionId"]) {
            NSInteger revId = [params[@"revisionId"] integerValue];
            correlation[@"revision"] = [_memoryService revisionForId:revId];
            correlation[@"operationsAtRevision"] = [_memoryService operationsForRevision:revId limit:20];
        }
        if (params[@"workflowId"]) {
            correlation[@"workflow"] = [_memoryService workflowForId:params[@"workflowId"]];
        }
        NSDictionary* timeline = [_memoryService timelineWithParams:@{
            @"operationId": operationId ?: @"",
            @"workflowId": params[@"workflowId"] ?: @"",
            @"limit": @50,
            @"compact": @YES,
        }];
        correlation[@"timeline"] = timeline[@"events"] ?: @[];
        correlation[@"mode"] = @"runtime_correlation";
        correlation[@"correlation"] = MacControlOperationIdentity(correlation[@"operation"] ?: correlation[@"operationByIdempotency"] ?: @{});
        *outResult = MacControlEnrichRuntimeSurface(correlation, @"runtime_correlation", @"runtime.timeline");
        return;
    }

    if (!_memoryService.available) {
        *outErrCode = @"runtime_journal_degraded";
        *outErrMsg = @"Runtime journal unavailable; mutation kernel remains authoritative.";
        *outResult = MacControlEnrichRuntimeSurface(@{
            @"degraded": @YES,
            @"checkpointStatus": _memoryService.checkpointStatus ?: @"unavailable",
            @"recoveryHint": @"retry_runtime_diagnostics",
            @"nextRecommendedCommand": @"runtime.diagnostics",
            @"mutationAuthority": @"cpp_kernel",
        }, @"runtime_degraded", @"runtime.diagnostics");
        return;
    }

    *outErrCode = @"method_not_found";
    *outErrMsg = [NSString stringWithFormat:@"The method '%@' is not defined.", method];
}

@end
