#import "MacControlTaskRuntime.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlPatchService.hpp"
#import "MacControlSearchService.hpp"
#import "MacControlSupport.hpp"
#import "MacControlRoutingPolicy.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"

@implementation MacControlTaskRuntime {
    DietCodeControlWindowBridge* _windowBridge;
    MacControlPatchService* _patchService;
    MacControlSearchService* _searchService;
    MacControlMethodExecutor _executor;
    
    NSMutableDictionary<NSString*, NSMutableDictionary*>* _tasks;
    NSInteger _taskCounter;
    NSMutableDictionary<NSString*, NSDictionary*>* _editPlans;
    NSInteger _editPlanCounter;
}

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge
                        patchService:(MacControlPatchService*)patchService
                       searchService:(MacControlSearchService*)searchService
                            executor:(MacControlMethodExecutor)executor {
    self = [super init];
    if (self) {
        _windowBridge = bridge;
        _patchService = patchService;
        _searchService = searchService;
        _executor = [executor copy];
        _tasks = [NSMutableDictionary dictionary];
        _taskCounter = 0;
        _editPlans = [NSMutableDictionary dictionary];
        _editPlanCounter = 0;
    }
    return self;
}

- (NSDictionary*)startTask:(NSDictionary*)params 
                outErrCode:(NSString**)outErrCode 
                 outErrMsg:(NSString**)outErrMsg {
    NSString* goal = params[@"goal"] ?: @"";
    if (goal.length == 0) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"goal parameter required.";
        return nil;
    }
    NSString* taskId = [NSString stringWithFormat:@"task-%ld", (long)++_taskCounter];
    NSMutableDictionary* task = [@{
        @"taskId": taskId,
        @"goal": goal,
        @"scope": params[@"scope"] ?: @{},
        @"budget": params[@"budget"] ?: @{},
        @"verify": params[@"verify"] ?: @[],
        @"status": @"active",
        @"startedAt": ISODateString([NSDate date]),
        @"steps": [NSMutableArray array],
        @"results": [NSMutableArray array],
        @"patchBatchesUsed": @0,
        @"verifyRunsUsed": @0,
        @"filesTouched": [NSMutableArray array]
    } mutableCopy];
    task[@"startedAtDate"] = [NSDate date];
    task[@"filesTouchedSet"] = [NSMutableSet set];
    _tasks[taskId] = task;
    return @{ @"taskId": taskId, @"task": [self serializableTask:task] };
}

- (NSDictionary*)taskStatus:(NSDictionary*)params 
                     result:(BOOL)isResult
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg {
    NSString* taskId = params[@"taskId"];
    NSMutableDictionary* task = taskId ? _tasks[taskId] : nil;
    if (!task) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"Unknown taskId.";
        return nil;
    }
    NSDictionary* snapshot = [self serializableTask:task];
    if (isResult) {
        NSDictionary* currentChanges = nil;
        NSDictionary* verifyStatus = nil;
        _executor(@"changes.current", @{}, &currentChanges, nil, nil, nil);
        _executor(@"verify.status", @{}, &verifyStatus, nil, nil, nil);
        
        return @{ 
            @"result": snapshot, 
            @"finalDiff": currentChanges ?: @{}, 
            @"verify": verifyStatus ?: @{} 
        };
    } else {
        return @{ @"task": snapshot };
    }
}

- (NSDictionary*)cancelTask:(NSDictionary*)params 
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg {
    NSString* taskId = params[@"taskId"];
    NSMutableDictionary* task = taskId ? _tasks[taskId] : nil;
    if (!task) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"Unknown taskId.";
        return nil;
    }
    NSString* status = task[@"status"] ?: @"";
    if (![status isEqualToString:@"active"]) {
        *outErrCode = @"task_not_active";
        *outErrMsg = [NSString stringWithFormat:@"Task is not active (status: %@).", status];
        return nil;
    }
    task[@"status"] = @"cancelled";
    task[@"cancelledAt"] = ISODateString([NSDate date]);
    return @{ @"cancelled": @YES, @"task": [self serializableTask:task] };
}

- (NSDictionary*)taskStep:(NSDictionary*)params 
               outErrCode:(NSString**)outErrCode 
                outErrMsg:(NSString**)outErrMsg {
    NSString* taskId = params[@"taskId"];
    NSMutableDictionary* task = taskId ? _tasks[taskId] : nil;
    NSDictionary* step = params[@"step"];
    if (!task || ![step isKindOfClass:[NSDictionary class]]) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"taskId and step object required.";
        return nil;
    }
    NSDictionary* stepResult = [self executeWorkbenchStep:step task:task];
    [task[@"steps"] addObject:step];
    [task[@"results"] addObject:stepResult];
    if (![stepResult[@"ok"] boolValue] && [task[@"status"] isEqualToString:@"active"]) {
        task[@"status"] = @"blocked";
    }
    return @{ @"stepResult": stepResult, @"task": [self serializableTask:task] };
}

- (NSDictionary*)taskRunLoop:(NSDictionary*)params 
                  outErrCode:(NSString**)outErrCode 
                   outErrMsg:(NSString**)outErrMsg {
    NSString* taskId = params[@"taskId"];
    NSMutableDictionary* task = taskId ? _tasks[taskId] : nil;
    NSArray* steps = params[@"steps"] ?: @[];
    if (!task || ![steps isKindOfClass:[NSArray class]] || steps.count > (NSUInteger)kMaxPlanSteps) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"taskId and bounded steps array required.";
        return nil;
    }
    NSMutableArray* results = [NSMutableArray array];
    for (NSDictionary* step in steps) {
        if (![step isKindOfClass:[NSDictionary class]]) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Every runLoop step must be an object.";
            return nil;
        }
        NSDictionary* stepResult = [self executeWorkbenchStep:step task:task];
        [task[@"steps"] addObject:step];
        [task[@"results"] addObject:stepResult];
        [results addObject:stepResult];
        if (![stepResult[@"ok"] boolValue]) {
            if ([task[@"status"] isEqualToString:@"active"]) {
                task[@"status"] = @"blocked";
            }
            break;
        }
        if ([step[@"type"] isEqualToString:@"verify"]) {
            NSDictionary* status = nil;
            _executor(@"verify.status", @{}, &status, nil, nil, nil);
            if ([status[@"state"] isEqualToString:@"complete"] && ![status[@"passed"] boolValue]) {
                task[@"status"] = @"verify_failed";
                break;
            }
        }
    }
    if ([task[@"status"] isEqualToString:@"active"]) {
        task[@"status"] = @"complete";
        task[@"completedAt"] = ISODateString([NSDate date]);
    }
    
    NSDictionary* currentChanges = nil;
    NSDictionary* verifyStatus = nil;
    _executor(@"changes.current", @{}, &currentChanges, nil, nil, nil);
    _executor(@"verify.status", @{}, &verifyStatus, nil, nil, nil);

    return @{ 
        @"results": results, 
        @"task": [self serializableTask:task], 
        @"finalDiff": currentChanges ?: @{}, 
        @"verify": verifyStatus ?: @{} 
    };
}

- (NSDictionary*)editPlan:(NSDictionary*)params 
               outErrCode:(NSString**)outErrCode 
                outErrMsg:(NSString**)outErrMsg {
    NSArray* steps = params[@"steps"];
    if (![steps isKindOfClass:[NSArray class]] || steps.count == 0 || steps.count > (NSUInteger)kMaxPlanSteps) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"steps array required and must be bounded.";
        return nil;
    }
    for (NSDictionary* step in steps) {
        if (![step isKindOfClass:[NSDictionary class]] || [self primitiveForWorkbenchStep:step].count == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Plan contains unknown step type.";
            return nil;
        }
    }
    NSString* planId = [NSString stringWithFormat:@"plan-%ld", (long)++_editPlanCounter];
    NSDictionary* plan = @{ @"planId": planId, @"steps": steps, @"createdAt": ISODateString([NSDate date]) };
    _editPlans[planId] = plan;
    return @{ @"planId": planId, @"plan": plan };
}

- (NSDictionary*)editExecutePlan:(NSDictionary*)params 
                      outErrCode:(NSString**)outErrCode 
                       outErrMsg:(NSString**)outErrMsg {
    NSString* planId = params[@"planId"];
    NSDictionary* plan = planId ? _editPlans[planId] : nil;
    NSArray* steps = params[@"steps"] ?: plan[@"steps"];
    NSString* taskId = params[@"taskId"];
    NSMutableDictionary* task = taskId ? _tasks[taskId] : nil;
    if (![steps isKindOfClass:[NSArray class]] || steps.count == 0 || steps.count > (NSUInteger)kMaxPlanSteps) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"planId or bounded steps array required.";
        return nil;
    }
    NSMutableArray* results = [NSMutableArray array];
    for (NSDictionary* step in steps) {
        NSDictionary* stepResult = [self executeWorkbenchStep:step task:task];
        [results addObject:stepResult];
        if (task) {
            [task[@"steps"] addObject:step];
            [task[@"results"] addObject:stepResult];
        }
        if (![stepResult[@"ok"] boolValue]) break;
    }
    
    NSDictionary* currentChanges = nil;
    NSDictionary* verifyStatus = nil;
    _executor(@"changes.current", @{}, &currentChanges, nil, nil, nil);
    _executor(@"verify.status", @{}, &verifyStatus, nil, nil, nil);

    return @{ 
        @"results": results, 
        @"finalDiff": currentChanges ?: @{}, 
        @"verify": verifyStatus ?: @{} 
    };
}

- (BOOL)task:(NSMutableDictionary*)task canConsumeStep:(NSDictionary*)step error:(NSString**)errorOut errorCode:(NSString**)errorCodeOut {
    NSString* taskStatus = task[@"status"] ?: @"";
    if (![taskStatus isEqualToString:@"active"]) {
        if (errorCodeOut) *errorCodeOut = @"task_not_active";
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Task is not active (status: %@).", taskStatus];
        return NO;
    }
    NSDictionary* budget = task[@"budget"] ?: @{};
    NSDate* startedAt = task[@"startedAtDate"];
    NSInteger maxDuration = budget[@"maxDurationMs"] ? [budget[@"maxDurationMs"] integerValue] : 300000;
    if (startedAt && [[NSDate date] timeIntervalSinceDate:startedAt] * 1000.0 > maxDuration) {
        task[@"status"] = @"budget_exceeded";
        if (errorCodeOut) *errorCodeOut = @"budget_exceeded";
        if (errorOut) *errorOut = @"Task exceeded maxDurationMs.";
        return NO;
    }
    NSString* type = step[@"type"] ?: @"";
    if ([type isEqualToString:@"patch"] || [type isEqualToString:@"patchBatch"]) {
        NSInteger maxPatchBatches = budget[@"maxPatchBatches"] ? [budget[@"maxPatchBatches"] integerValue] : 3;
        if ([task[@"patchBatchesUsed"] integerValue] >= maxPatchBatches) {
            if (errorCodeOut) *errorCodeOut = @"budget_exceeded";
            if (errorOut) *errorOut = @"Task exceeded maxPatchBatches.";
            return NO;
        }
    }
    if ([type isEqualToString:@"verify"]) {
        NSInteger maxVerifyRuns = budget[@"maxVerifyRuns"] ? [budget[@"maxVerifyRuns"] integerValue] : 3;
        if ([task[@"verifyRunsUsed"] integerValue] >= maxVerifyRuns) {
            if (errorCodeOut) *errorCodeOut = @"budget_exceeded";
            if (errorOut) *errorOut = @"Task exceeded maxVerifyRuns.";
            return NO;
        }
    }
    NSDictionary* scope = task[@"scope"] ?: @{};
    NSMutableSet* touched = task[@"filesTouchedSet"];
    NSMutableArray* candidatePaths = [NSMutableArray array];
    NSMutableArray* candidateAbsPaths = [NSMutableArray array];
    if (step[@"path"]) [candidatePaths addObject:step[@"path"]];
    for (NSDictionary* item in step[@"patches"] ?: @[]) {
        if (item[@"path"]) [candidatePaths addObject:item[@"path"]];
    }
    for (NSString* candidate in candidatePaths) {
        if (![self path:candidate isAllowedByScope:scope]) {
            if (errorCodeOut) *errorCodeOut = @"outside_scope";
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Path is outside task scope: %@", candidate];
            return NO;
        }
        [candidateAbsPaths addObject:AbsolutePathForRPCPath(candidate, [_windowBridge workspacePath]) ?: candidate];
    }
    NSInteger maxFilesTouched = budget[@"maxFilesTouched"] ? [budget[@"maxFilesTouched"] integerValue] : 4;
    NSMutableSet* projectedTouched = [touched mutableCopy];
    for (NSString* candidateAbs in candidateAbsPaths) {
        [projectedTouched addObject:candidateAbs];
    }
    if (projectedTouched.count > (NSUInteger)maxFilesTouched) {
        if (errorCodeOut) *errorCodeOut = @"budget_exceeded";
        if (errorOut) *errorOut = @"Task exceeded maxFilesTouched.";
        return NO;
    }
    [touched unionSet:projectedTouched];
    return YES;
}

- (NSDictionary*)serializableTask:(NSMutableDictionary*)task {
    NSMutableDictionary* copy = [task mutableCopy];
    NSMutableArray* touched = [NSMutableArray array];
    for (NSString* pathValue in task[@"filesTouchedSet"] ?: [NSSet set]) {
        [touched addObject:pathValue];
    }
    copy[@"filesTouched"] = touched;
    [copy removeObjectForKey:@"filesTouchedSet"];
    [copy removeObjectForKey:@"startedAtDate"];
    return [NSDictionary dictionaryWithDictionary:copy];
}

- (NSDictionary*)primitiveForWorkbenchStep:(NSDictionary*)step {
    NSString* type = step[@"type"] ?: @"";
    if ([type isEqualToString:@"readAround"]) return @{ @"method": @"file.readAround", @"params": step };
    if ([type isEqualToString:@"readRange"]) return @{ @"method": @"file.readRange", @"params": step };
    if ([type isEqualToString:@"searchFiles"]) return @{ @"method": @"search.files", @"params": step };
    if ([type isEqualToString:@"searchText"]) return @{ @"method": @"search.text", @"params": step };
    if ([type isEqualToString:@"patch"]) return @{ @"method": @"patch.apply", @"params": step };
    if ([type isEqualToString:@"patchBatch"]) return @{ @"method": @"patch.applyBatch", @"params": step };
    if ([type isEqualToString:@"write"]) return @{ @"method": @"file.write", @"params": step };
    if ([type isEqualToString:@"create"]) return @{ @"method": @"file.create", @"params": step };
    if ([type isEqualToString:@"verify"]) return @{ @"method": @"verify.run", @"params": step };
    if ([type isEqualToString:@"diffSummary"]) return @{ @"method": @"diff.summary", @"params": @{} };
    if ([type isEqualToString:@"failures"]) return @{ @"method": @"verify.failures", @"params": @{} };
    if ([type isEqualToString:@"contextSnapshot"]) return @{ @"method": @"context.snapshot", @"params": @{} };
    return @{};
}

- (NSDictionary*)executeWorkbenchStep:(NSDictionary*)step task:(NSMutableDictionary*)task {
    if ([step[@"confirm"] boolValue]) {
        return @{ @"ok": @NO, @"error": @{ @"code": @"confirmation_required", @"message": @"Combo steps cannot perform confirmed destructive operations." } };
    }
    NSString* err = nil;
    NSString* rejectCode = nil;
    if (task && ![self task:task canConsumeStep:step error:&err errorCode:&rejectCode]) {
        return @{ @"ok": @NO, @"error": @{ @"code": rejectCode ?: @"task_rejected", @"message": err ?: @"Task rejected step." } };
    }
    NSDictionary* primitive = [self primitiveForWorkbenchStep:step];
    NSString* method = primitive[@"method"];
    if (method.length == 0) {
        return @{ @"ok": @NO, @"error": @{ @"code": @"invalid_params", @"message": @"Unknown step type." } };
    }
    __block NSDictionary* result = nil;
    __block NSString* errCode = nil;
    __block NSString* errMsg = nil;
    __block NSString* paths = @"";
    
    BOOL isBackground = [method isEqualToString:@"verify.run"] || MacControlIsReadQueueMethod(method);
    
    if (isBackground) {
        _executor(method, primitive[@"params"] ?: @{}, &result, &errCode, &errMsg, &paths);
    } else {
        dispatch_semaphore_t execSem = dispatch_semaphore_create(0);
        dispatch_async(dispatch_get_main_queue(), ^{
            _executor(method, primitive[@"params"] ?: @{}, &result, &errCode, &errMsg, &paths);
            dispatch_semaphore_signal(execSem);
        });
        dispatch_semaphore_wait(execSem, DISPATCH_TIME_FOREVER);
    }
    
    if (errCode) {
        return @{ @"ok": @NO, @"method": method, @"error": @{ @"code": errCode, @"message": errMsg ?: @"" } };
    }
    if (task) {
        if ([method isEqualToString:@"patch.apply"] || [method isEqualToString:@"patch.applyBatch"]) {
            task[@"patchBatchesUsed"] = @([task[@"patchBatchesUsed"] integerValue] + 1);
        } else if ([method isEqualToString:@"verify.run"]) {
            task[@"verifyRunsUsed"] = @([task[@"verifyRunsUsed"] integerValue] + 1);
        }
    }
    return @{ @"ok": @YES, @"method": method, @"result": result ?: @{} };
}

- (BOOL)path:(NSString*)path isAllowedByScope:(NSDictionary*)scope {
    NSString* ws = [_windowBridge workspacePath];
    NSString* absPath = AbsolutePathForRPCPath(path, ws);
    if (!PathIsInsideWorkspace(absPath, ws)) return NO;
    std::error_code ec;
    std::filesystem::path rel = std::filesystem::relative(std::filesystem::path(StdStringFromNSString(absPath)), std::filesystem::path(StdStringFromNSString(ws)), ec);
    if (ec) return NO;
    std::string relPath = rel.string();
    std::string filename = std::filesystem::path(relPath).filename().string();
    NSArray* includes = scope[@"include"] ?: @[];
    NSArray* excludes = scope[@"exclude"] ?: @[];
    if (AnyPatternMatches(excludes, relPath, filename)) return NO;
    if (includes.count > 0 && !AnyPatternMatches(includes, relPath, filename)) return NO;
    return YES;
}

@end
