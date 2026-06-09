#import "MacControlComboRuntime.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlRecoveryStore.hpp"
#import "MacControlPatchService.hpp"
#import "MacControlTaskRuntime.hpp"
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"
#import "MacControlDiffParsing.hpp"
#import "MacControlRoutingPolicy.hpp"
#import "MacControlMethodCatalog.hpp"

#include <filesystem>
#include <string>
#include <vector>

@implementation MacControlComboRuntime {
    DietCodeControlWindowBridge* _windowBridge;
    MacControlRecoveryStore* _recoveryStore;
    MacControlPatchService* _patchService;
    MacControlTaskRuntime* _taskRuntime;
    MacControlMethodExecutor _executor;
    
    NSMutableDictionary<NSString*, NSMutableDictionary*>* _combos;
    NSMutableDictionary<NSString*, NSString*>* _pathLocks;
    NSString* _lastComboId;
}

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge
                        recoveryStore:(MacControlRecoveryStore*)recoveryStore
                         patchService:(MacControlPatchService*)patchService
                          taskRuntime:(MacControlTaskRuntime*)taskRuntime
                             executor:(MacControlMethodExecutor)executor {
    self = [super init];
    if (self) {
        _windowBridge = bridge;
        _recoveryStore = recoveryStore;
        _patchService = patchService;
        _taskRuntime = taskRuntime;
        _executor = [executor copy];
        
        _combos = [NSMutableDictionary dictionary];
        _pathLocks = [NSMutableDictionary dictionary];
        _globalMutationLock = NO;
        _lastComboId = nil;
    }
    return self;
}

- (NSDictionary<NSString*, NSDictionary*>*)combos {
    return [_combos copy];
}

- (NSString*)lastComboId {
    return _lastComboId;
}

- (NSString*)chipNameForStep:(NSDictionary*)step {
    NSString* chip = step[@"chip"];
    if (chip.length > 0) return CanonicalChipName(chip);
    NSDictionary* primitive = [_taskRuntime primitiveForWorkbenchStep:step];
    return primitive[@"method"] ?: @"";
}

- (NSDictionary*)paramsForComboStep:(NSDictionary*)step {
    NSDictionary* params = step[@"params"];
    if ([params isKindOfClass:[NSDictionary class]]) return params;
    NSMutableDictionary* copy = [step mutableCopy];
    [copy removeObjectForKey:@"id"];
    [copy removeObjectForKey:@"chip"];
    [copy removeObjectForKey:@"type"];
    [copy removeObjectForKey:@"needs"];
    [copy removeObjectForKey:@"expects"];
    return copy;
}

- (NSArray<NSString*>*)pathsDeclaredByParams:(NSDictionary*)params chip:(NSString*)chip {
    NSMutableArray<NSString*>* paths = [NSMutableArray array];
    NSString* path = params[@"path"];
    if (path.length > 0) [paths addObject:path];
    NSString* cwd = params[@"cwd"];
    if (cwd.length > 0) [paths addObject:cwd];
    for (NSDictionary* item in params[@"patches"] ?: @[]) {
        NSString* patchPath = item[@"path"];
        if (patchPath.length > 0) [paths addObject:patchPath];
    }
    for (NSDictionary* file in params[@"files"] ?: @[]) {
        NSString* filePath = file[@"path"];
        if (filePath.length > 0) [paths addObject:filePath];
    }
    return paths;
}

- (NSArray<NSString*>*)mutationPathsForChip:(NSString*)chip params:(NSDictionary*)params {
    NSString* ws = [_windowBridge workspacePath];
    if ([chip isEqualToString:@"patch.apply"]) {
        NSString* path = params[@"path"];
        return path.length > 0 ? @[AbsolutePathForRPCPath(path, ws) ?: path] : @[];
    }
    if ([chip isEqualToString:@"patch.applyBatch"]) {
        NSMutableArray* paths = [NSMutableArray array];
        for (NSDictionary* item in params[@"patches"] ?: @[]) {
            NSString* path = item[@"path"];
            if (path.length > 0) [paths addObject:AbsolutePathForRPCPath(path, ws) ?: path];
        }
        return paths;
    }
    return @[];
}

- (BOOL)comboPolicy:(NSDictionary*)policy allowsPermission:(NSString*)permission {
    NSArray* permissions = policy[@"permissions"];
    if (![permissions isKindOfClass:[NSArray class]] || permissions.count == 0) {
        permissions = @[@"read"];
    }
    NSInteger needed = PermissionRank(permission);
    for (NSString* allowed in permissions) {
        if (PermissionRank(allowed) >= needed) return YES;
    }
    return NO;
}

- (BOOL)validateCombo:(NSDictionary*)combo normalizedPlan:(NSDictionary**)planOut errors:(NSArray<NSDictionary*>**)errorsOut {
    NSMutableArray<NSDictionary*>* errors = [NSMutableArray array];
    
    NSString* planVersion = combo[@"schemaVersion"];
    if (!planVersion || ![planVersion isEqualToString:@"1.6.2"]) {
        [errors addObject:RuntimeError(@"invalid_combo", @"Plan must declare schemaVersion '1.6.2'.", nil, nil, @"validate", YES)];
    }
    
    NSArray* steps = combo[@"steps"];
    NSDictionary* budget = combo[@"budget"] ?: @{};
    NSDictionary* policy = combo[@"policy"] ?: @{};
    NSDictionary* scope = combo[@"scope"] ?: @{};
    NSInteger maxSteps = budget[@"maxSteps"] ? [budget[@"maxSteps"] integerValue] : kMaxPlanSteps;
    maxSteps = MIN(maxSteps, kMaxPlanSteps);

    if (![steps isKindOfClass:[NSArray class]] || steps.count == 0 || steps.count > (NSUInteger)maxSteps) {
        [errors addObject:RuntimeError(@"invalid_combo", @"steps must be a non-empty bounded array.", nil, nil, @"validate", YES)];
    }

    NSMutableSet<NSString*>* stepIds = [NSMutableSet set];
    NSMutableArray* normalizedSteps = [NSMutableArray array];
    NSMutableSet<NSString*>* completedIds = [NSMutableSet set];
    NSUInteger index = 0;
    for (NSDictionary* step in steps ?: @[]) {
        if (![step isKindOfClass:[NSDictionary class]]) {
            [errors addObject:RuntimeError(@"invalid_combo", @"Every step must be an object.", nil, nil, @"validate", YES)];
            index++;
            continue;
        }
        NSString* stepId = step[@"id"] ?: [NSString stringWithFormat:@"step-%lu", (unsigned long)index + 1];
        if ([stepIds containsObject:stepId]) {
            [errors addObject:RuntimeError(@"invalid_combo", @"Duplicate step id.", stepId, nil, @"validate", YES)];
        }
        [stepIds addObject:stepId];

        NSString* chip = [self chipNameForStep:step];
        NSDictionary* meta = MacControlMetadataForChip(chip);
        if (!meta) {
            [errors addObject:RuntimeError(@"unknown_chip", @"Step references an unknown chip.", stepId, chip, @"validate", YES)];
            index++;
            continue;
        }
        NSDictionary* params = [self paramsForComboStep:step];
        for (NSString* required in meta[@"requiredParams"] ?: @[]) {
            id value = params[required];
            if (!value || value == [NSNull null] || ([value respondsToSelector:@selector(length)] && [value length] == 0)) {
                [errors addObject:RuntimeError(@"invalid_params", [NSString stringWithFormat:@"Missing required parameter: %@", required], stepId, chip, @"validate", YES)];
            }
        }
        if (![self comboPolicy:policy allowsPermission:meta[@"permission"]]) {
            [errors addObject:RuntimeError(@"permission_denied", @"Combo policy does not allow this chip permission.", stepId, chip, @"validate", YES)];
        }
        if ([params[@"confirm"] boolValue]) {
            [errors addObject:RuntimeError(@"confirmation_required", @"Confirmation cannot be embedded inside combo steps.", stepId, chip, @"validate", YES)];
        }
        
        // Path scope check
        NSString* ws = [_windowBridge workspacePath];
        for (NSString* declaredPath in [self pathsDeclaredByParams:params chip:chip]) {
            NSString* absPath = AbsolutePathForRPCPath(declaredPath, ws);
            if (!PathIsInsideWorkspace(absPath, ws)) {
                 [errors addObject:RuntimeError(@"outside_workspace", @"Step declares a path outside workspace.", stepId, chip, @"validate", YES)];
                 continue;
            }
            std::error_code ec;
            std::filesystem::path rel = std::filesystem::relative(std::filesystem::path(StdStringFromNSString(absPath)), std::filesystem::path(StdStringFromNSString(ws)), ec);
            if (ec) {
                [errors addObject:RuntimeError(@"outside_scope", @"Step declares a path that cannot be relativized.", stepId, chip, @"validate", YES)];
                continue;
            }
            std::string relPath = rel.string();
            std::string filename = std::filesystem::path(relPath).filename().string();
            NSArray* includes = scope[@"include"] ?: @[];
            NSArray* excludes = scope[@"exclude"] ?: @[];
            if (AnyPatternMatches(excludes, relPath, filename)) {
                [errors addObject:RuntimeError(@"outside_scope", @"Step declares a path excluded by combo scope.", stepId, chip, @"validate", YES)];
            } else if (includes.count > 0 && !AnyPatternMatches(includes, relPath, filename)) {
                [errors addObject:RuntimeError(@"outside_scope", @"Step declares a path not included by combo scope.", stepId, chip, @"validate", YES)];
            }
        }
        
        for (NSString* dep in step[@"needs"] ?: @[]) {
            if (![completedIds containsObject:dep]) {
                [errors addObject:RuntimeError(@"dependency_failed", @"Dependencies must reference earlier completed step ids in sequential combos.", stepId, chip, @"validate", YES)];
            }
        }
        if ([chip isEqualToString:@"patch.apply"] || [chip isEqualToString:@"patch.applyBatch"]) {
            NSArray* patchItems = [chip isEqualToString:@"patch.apply"] ? @[@{ @"path": params[@"path"] ?: @"", @"patch": params[@"patch"] ?: @"" }] : (params[@"patches"] ?: @[]);
            for (NSDictionary* item in patchItems) {
                // Check dirty buffer
                NSString* pAbs = AbsolutePathForRPCPath(item[@"path"], ws);
                BOOL dirty = NO;
                for (id tab in [_windowBridge openTabs] ?: @[]) {
                    if ([[tab valueForKey:@"path"] isEqualToString:pAbs] && [[tab valueForKey:@"dirty"] boolValue]) {
                        dirty = YES;
                        break;
                    }
                }
                if (dirty && ![params[@"allowDirtyBuffer"] boolValue]) {
                    [errors addObject:RuntimeError(@"dirty_buffer_conflict", @"Mutation targets a dirty editor buffer; set allowDirtyBuffer explicitly for buffer-domain patching.", stepId, chip, @"validate", YES)];
                }
                NSDictionary* validation = [_patchService validatePatchAtPath:item[@"path"] patch:item[@"patch"] currentText:nil options:params];
                if (![validation[@"ok"] boolValue]) {
                    [errors addObject:RuntimeError(@"patch_failed", validation[@"rejectedReason"] ?: @"Patch validation failed.", stepId, chip, @"validate", YES)];
                }
                if ([validation[@"requiresConfirmation"] boolValue]) {
                    [errors addObject:RuntimeError(@"confirmation_required", @"Patch exceeds combo confirmation threshold.", stepId, chip, @"validate", YES)];
                }
            }
        }
        [normalizedSteps addObject:@{ @"id": stepId, @"chip": chip, @"params": params, @"metadata": meta, @"needs": step[@"needs"] ?: @[] }];
        [completedIds addObject:stepId];
        index++;
    }

    if (errors.count > 0) {
        if (errorsOut) *errorsOut = errors;
        return NO;
    }
    if (planOut) {
        *planOut = @{
            @"schemaVersion": combo[@"schemaVersion"] ?: @"1.6.2",
            @"goal": combo[@"goal"] ?: @"",
            @"scope": scope,
            @"policy": policy,
            @"budget": budget,
            @"steps": normalizedSteps
        };
    }
    if (errorsOut) *errorsOut = @[];
    return YES;
}

- (NSDictionary*)serializableCombo:(NSMutableDictionary*)combo {
    NSMutableDictionary* copy = [combo mutableCopy];
    [copy removeObjectForKey:@"startedAtDate"];
    [copy removeObjectForKey:@"lockedPathsSet"];
    return copy;
}

- (NSUInteger)activeComboCount {
    NSUInteger count = 0;
    for (NSDictionary* combo in [_combos allValues]) {
        NSString* status = combo[@"status"] ?: @"";
        if ([status isEqualToString:@"running"] ||
            [status isEqualToString:@"validated"] ||
            [status isEqualToString:@"waiting_confirmation"]) {
            count++;
        }
    }
    return count;
}

- (BOOL)acquireMutationLocks:(NSArray<NSString*>*)paths comboId:(NSString*)comboId error:(NSString**)errorOut {
    for (NSString* path in paths ?: @[]) {
        NSString* holder = _pathLocks[path];
        if (holder.length > 0 && ![holder isEqualToString:comboId]) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Path is locked by another combo: %@", path];
            return NO;
        }
    }
    for (NSString* path in paths ?: @[]) {
        _pathLocks[path] = comboId;
    }
    return YES;
}

- (void)releaseMutationLocks:(NSArray<NSString*>*)paths comboId:(NSString*)comboId {
    for (NSString* path in paths ?: @[]) {
        if ([_pathLocks[path] isEqualToString:comboId]) {
            [_pathLocks removeObjectForKey:path];
        }
    }
}

// Terminal combo states that should not be overwritten by a cancel request.
static NSSet* _terminalComboStatuses(void) {
    static NSSet* s = nil;
    static dispatch_once_t tok;
    dispatch_once(&tok, ^{
        s = [NSSet setWithObjects:@"complete", @"cancelled", @"failed",
             @"rollback_complete", @"rollback_failed", nil];
    });
    return s;
}

- (BOOL)cancelComboWithId:(NSString*)comboId error:(NSString**)errorOut {
    NSMutableDictionary* combo = _combos[comboId];
    if (!combo) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Unknown comboId: %@", comboId];
        return NO;
    }
    NSString* status = combo[@"status"] ?: @"";
    if ([_terminalComboStatuses() containsObject:status]) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Combo '%@' is already in terminal state '%@'.", comboId, status];
        return NO;
    }
    combo[@"status"] = @"cancelled";
    combo[@"cancelledAt"] = ISODateString([NSDate date]);
    // Running combos release locks in their normal cleanup path after rollback/exit.
    // Releasing here would allow another mutation to start while this combo may
    // still be executing or restoring its checkpoint.
    if (![status isEqualToString:@"running"]) {
        [self releaseMutationLocks:[combo[@"lockedPaths"] isKindOfClass:[NSArray class]]
                                   ? combo[@"lockedPaths"] : @[]
                           comboId:comboId];
        if ([combo[@"containsMutation"] boolValue]) {
            _globalMutationLock = NO;
        }
    }
    return YES;
}

- (NSDictionary*)executeComboStep:(NSDictionary*)step combo:(NSMutableDictionary*)combo sequence:(NSInteger)sequence {
    NSString* comboId = combo[@"comboId"] ?: @"";
    NSString* stepId = step[@"id"] ?: @"";
    NSString* chip = step[@"chip"] ?: @"";
    NSDictionary* params = step[@"params"] ?: @{};
    NSDictionary* metadata = step[@"metadata"] ?: @{};
    NSDate* started = [NSDate date];
    NSMutableDictionary* trace = [@{
        @"sequence": @(sequence),
        @"stepId": stepId,
        @"chip": [NSString stringWithFormat:@"%@@%@", chip, metadata[@"version"] ?: @1],
        @"state": @"prechecking",
        @"phase": @"prechecking",
        @"startedAt": ISODateString(started),
        @"inputHash": StableHashForString([params description]),
        @"touchedPaths": [self mutationPathsForChip:chip params:params]
    } mutableCopy];

    if ([combo[@"status"] isEqualToString:@"cancelled"]) {
        trace[@"state"] = @"cancelled";
        trace[@"error"] = RuntimeError(@"cancelled", @"Combo was cancelled before step execution.", stepId, chip, @"prechecking", YES);
        return trace;
    }

    NSArray* mutationPaths = [self mutationPathsForChip:chip params:params];
    for (NSString* p in mutationPaths) {
        if (![_pathLocks[p] isEqualToString:comboId]) {
            trace[@"state"] = @"failed";
            trace[@"error"] = RuntimeError(@"lock_conflict", @"Required path lock not held by active combo.", stepId, chip, @"prechecking", YES);
            return trace;
        }
    }

    NSDictionary* primitive = MacControlPrimitiveForChip(chip, params);
    NSString* method = primitive[@"method"];
    __block NSDictionary* result = nil;
    __block NSString* errCode = nil;
    __block NSString* errMsg = nil;
    __block NSString* affectedPaths = @"";

    trace[@"state"] = @"executing";
    trace[@"phase"] = @"executing";
    
    BOOL isBackground = [method isEqualToString:@"verify.run"] || MacControlIsReadQueueMethod(method);
                        
    if (isBackground) {
        _executor(method, primitive[@"params"] ?: @{}, &result, &errCode, &errMsg, &affectedPaths);
    } else {
        dispatch_semaphore_t execSem = dispatch_semaphore_create(0);
        dispatch_async(dispatch_get_main_queue(), ^{
            self->_executor(method, primitive[@"params"] ?: @{}, &result, &errCode, &errMsg, &affectedPaths);
            dispatch_semaphore_signal(execSem);
        });
        dispatch_semaphore_wait(execSem, DISPATCH_TIME_FOREVER);
    }

    NSDate* finished = [NSDate date];
    trace[@"finishedAt"] = ISODateString(finished);
    trace[@"durationMs"] = @((NSInteger)([finished timeIntervalSinceDate:started] * 1000.0));
    if (affectedPaths.length > 0) trace[@"affectedPaths"] = affectedPaths;

    if (errCode) {
        trace[@"state"] = @"failed";
        trace[@"phase"] = @"failed";
        trace[@"error"] = RuntimeError(errCode, errMsg ?: @"Step failed.", stepId, chip, @"executing", YES);
        return trace;
    }

    trace[@"state"] = @"complete";
    trace[@"phase"] = @"postchecking";
    trace[@"outputHash"] = StableHashForString([result description]);
    trace[@"result"] = result ?: @{};
    return trace;
}

- (NSDictionary*)runComboWithPlan:(NSDictionary*)plan 
                          comboId:(NSString*)comboId 
                     sessionToken:(NSString*)sessionToken {
    NSMutableDictionary* combo = [@{
        @"comboId": comboId,
        @"schemaVersion": plan[@"schemaVersion"] ?: @"1.6",
        @"goal": plan[@"goal"] ?: @"",
        @"status": @"running",
        @"createdAt": ISODateString([NSDate date]),
        @"startedAt": ISODateString([NSDate date]),
        @"plan": plan,
        @"trace": [NSMutableArray array],
        @"errors": [NSMutableArray array],
        @"budgetUsed": [@{ @"steps": @0, @"patchBatches": @0, @"verifyRuns": @0, @"filesTouched": @0, @"durationMs": @0 } mutableCopy]
    } mutableCopy];
    combo[@"startedAtDate"] = [NSDate date];
    combo[@"lockedPathsSet"] = [NSMutableSet set];
    _combos[comboId] = combo;
    _lastComboId = [comboId copy];

    // 1. Gather all mutation paths and determine if there are mutation chips
    BOOL containsMutation = NO;
    NSMutableArray* allMutationPaths = [NSMutableArray array];
    for (NSDictionary* step in plan[@"steps"] ?: @[]) {
        NSString* chip = step[@"chip"];
        if ([chip isEqualToString:@"patch.apply"] || [chip isEqualToString:@"patch.applyBatch"]) {
            containsMutation = YES;
        }
        NSArray* stepPaths = [self mutationPathsForChip:chip params:step[@"params"] ?: @{}];
        for (NSString* p in stepPaths) {
            if (![allMutationPaths containsObject:p]) {
                [allMutationPaths addObject:p];
            }
        }
    }

    // 2. Enforce global mutation lock
    if (containsMutation) {
        if (_globalMutationLock) {
            combo[@"status"] = @"failed";
            [combo[@"errors"] addObject:RuntimeError(@"lock_conflict", @"A mutation combo transaction is already in progress.", nil, nil, @"prechecking", YES)];
            combo[@"finishedAt"] = ISODateString([NSDate date]);
            return [self serializableCombo:combo];
        }
        _globalMutationLock = YES;
        combo[@"containsMutation"] = @YES;
    }

    // 3. Acquire locks for ALL paths
    NSString* lockErr = nil;
    if (![self acquireMutationLocks:allMutationPaths comboId:comboId error:&lockErr]) {
        combo[@"status"] = @"failed";
        [combo[@"errors"] addObject:RuntimeError(@"lock_conflict", lockErr ?: @"Path lock conflict.", nil, nil, @"prechecking", YES)];
        if (containsMutation) _globalMutationLock = NO;
        combo[@"finishedAt"] = ISODateString([NSDate date]);
        return [self serializableCombo:combo];
    }
    combo[@"lockedPaths"] = [allMutationPaths copy];

    // 4. Create Preimage Backup Checkpoint directory and records
    __block NSDictionary* manifest = nil;
    __block NSString* backupDirOut = nil;
    __block NSString* checkpointErr = nil;
    
    BOOL checkpointOk = [_recoveryStore createCheckpointForPaths:allMutationPaths comboId:comboId plan:plan manifestOut:&manifest backupDirOut:&backupDirOut error:&checkpointErr];
    if (!checkpointOk) {
        combo[@"status"] = @"failed";
        [combo[@"errors"] addObject:RuntimeError(@"checkpoint_write_failed", [NSString stringWithFormat:@"Failed to create checkpoint: %@", checkpointErr], nil, nil, @"prechecking", YES)];
        if (containsMutation) _globalMutationLock = NO;
        [self releaseMutationLocks:allMutationPaths comboId:comboId];
        combo[@"finishedAt"] = ISODateString([NSDate date]);
        return [self serializableCombo:combo];
    }

    NSInteger seq = 0;
    NSMutableSet* touched = [NSMutableSet set];
    NSDate* started = combo[@"startedAtDate"];
    NSDictionary* budget = plan[@"budget"] ?: @{};
    NSMutableDictionary* budgetUsed = combo[@"budgetUsed"];
    NSInteger maxVerifyRuns = budget[@"maxVerifyRuns"] ? [budget[@"maxVerifyRuns"] integerValue] : 3;
    NSInteger maxPatchBatches = budget[@"maxPatchBatches"] ? [budget[@"maxPatchBatches"] integerValue] : 3;
    NSInteger maxFilesTouched = budget[@"maxFilesTouched"] ? [budget[@"maxFilesTouched"] integerValue] : 4;
    NSInteger maxDurationMs = budget[@"maxDurationMs"] ? [budget[@"maxDurationMs"] integerValue] : 300000;

    BOOL executionFailed = NO;

    for (NSDictionary* step in plan[@"steps"] ?: @[]) {
        if ([combo[@"status"] isEqualToString:@"cancelled"]) {
            executionFailed = YES;
            break;
        }

        NSTimeInterval elapsed = [[NSDate date] timeIntervalSinceDate:started] * 1000.0;
        if (elapsed > maxDurationMs) {
            combo[@"status"] = @"expired";
            [combo[@"errors"] addObject:RuntimeError(@"timeout", @"Combo exceeded maxDurationMs.", step[@"id"], step[@"chip"], @"prechecking", YES)];
            executionFailed = YES;
            break;
        }

        NSString* chip = step[@"chip"] ?: @"";
        NSArray* mutationPaths = [self mutationPathsForChip:chip params:step[@"params"] ?: @{}];
        NSMutableSet* projectedTouched = [touched mutableCopy];
        for (NSString* path in mutationPaths) [projectedTouched addObject:path];
        if (projectedTouched.count > (NSUInteger)maxFilesTouched) {
            combo[@"status"] = @"failed";
            [combo[@"errors"] addObject:RuntimeError(@"budget_exceeded", @"Combo exceeded maxFilesTouched.", step[@"id"], chip, @"prechecking", YES)];
            executionFailed = YES;
            break;
        }
        if (([chip isEqualToString:@"patch.apply"] || [chip isEqualToString:@"patch.applyBatch"]) &&
            [budgetUsed[@"patchBatches"] integerValue] >= maxPatchBatches) {
            combo[@"status"] = @"failed";
            [combo[@"errors"] addObject:RuntimeError(@"budget_exceeded", @"Combo exceeded maxPatchBatches.", step[@"id"], chip, @"prechecking", YES)];
            executionFailed = YES;
            break;
        }
        if ([chip isEqualToString:@"verify.run"] && [budgetUsed[@"verifyRuns"] integerValue] >= maxVerifyRuns) {
            combo[@"status"] = @"failed";
            [combo[@"errors"] addObject:RuntimeError(@"budget_exceeded", @"Combo exceeded maxVerifyRuns.", step[@"id"], chip, @"prechecking", YES)];
            executionFailed = YES;
            break;
        }

        NSDictionary* trace = [self executeComboStep:step combo:combo sequence:++seq];
        [combo[@"trace"] addObject:trace];
        budgetUsed[@"steps"] = @([budgetUsed[@"steps"] integerValue] + 1);
        for (NSString* path in mutationPaths) [touched addObject:path];
        budgetUsed[@"filesTouched"] = @([touched count]);
        if ([chip isEqualToString:@"patch.apply"] || [chip isEqualToString:@"patch.applyBatch"]) {
            budgetUsed[@"patchBatches"] = @([budgetUsed[@"patchBatches"] integerValue] + 1);
        }
        if ([chip isEqualToString:@"verify.run"]) {
            budgetUsed[@"verifyRuns"] = @([budgetUsed[@"verifyRuns"] integerValue] + 1);
        }
        budgetUsed[@"durationMs"] = @((NSInteger)([[NSDate date] timeIntervalSinceDate:started] * 1000.0));
        if (![trace[@"state"] isEqualToString:@"complete"]) {
            if ([trace[@"state"] isEqualToString:@"cancelled"] || [combo[@"status"] isEqualToString:@"cancelled"]) {
                combo[@"status"] = @"cancelled";
            } else {
                combo[@"status"] = @"failed";
            }
            if (trace[@"error"]) [combo[@"errors"] addObject:trace[@"error"]];
            executionFailed = YES;
            break;
        } else {
            NSString* ws = [_windowBridge workspacePath];
            NSMutableDictionary* mutableManifest = [manifest mutableCopy];
            NSMutableArray* updatedFiles = [NSMutableArray array];
            for (NSDictionary* fileEntry in manifest[@"files"] ?: @[]) {
                NSMutableDictionary* mutFile = [fileEntry mutableCopy];
                NSString* relPath = fileEntry[@"workspaceRelativePath"];
                NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
                if ([[NSFileManager defaultManager] fileExistsAtPath:absPath]) {
                    NSString* currentText = [_windowBridge textForFileAtPath:absPath];
                    if (currentText) {
                        mutFile[@"expectedPostimageHash"] = StableHashForString(currentText);
                    }
                }
                [updatedFiles addObject:mutFile];
            }
            mutableManifest[@"files"] = updatedFiles;
            manifest = mutableManifest;
            
            NSString* manifestPath = [backupDirOut stringByAppendingPathComponent:@"manifest.json"];
            [_recoveryStore writeManifest:manifest toPath:manifestPath error:nil];
        }
    }

    // 5. If failed/expired/cancelled, trigger automatic rollback
    if (executionFailed || [combo[@"status"] isEqualToString:@"cancelled"]) {
        NSString* rollbackErr = nil;
        NSString* rollbackErrorCode = nil;
        BOOL rollbackOk = [_recoveryStore restorePatchFromManifest:manifest backupDir:backupDirOut confirm:YES sessionToken:sessionToken error:&rollbackErr errorCode:&rollbackErrorCode];
        if (!rollbackOk) {
            [combo[@"errors"] addObject:RuntimeError(rollbackErrorCode ?: @"rollback_failed", [NSString stringWithFormat:@"Automatic rollback failed: %@", rollbackErr], nil, nil, @"rolling_back", NO)];
        } else {
            [combo[@"errors"] addObject:RuntimeError(@"rollback_success", @"Automatic rollback completed successfully.", nil, nil, @"rolling_back", YES)];
        }
    }

    if ([combo[@"status"] isEqualToString:@"running"]) {
        combo[@"status"] = @"complete";
    }

    // 6. Release all locks and global lock
    [self releaseMutationLocks:allMutationPaths comboId:comboId];
    if (containsMutation) {
        _globalMutationLock = NO;
    }

    combo[@"finishedAt"] = ISODateString([NSDate date]);
    
    // We need final diff and verify status. 
    // Since we don't have direct access to server's verificationStatus, 
    // we use the executor to fetch them.
    
    __block NSDictionary* finalDiff = nil;
    __block NSDictionary* verifyStatus = nil;
    _executor(@"changes.current", @{}, &finalDiff, nil, nil, nil);
    _executor(@"verify.status", @{}, &verifyStatus, nil, nil, nil);
    
    combo[@"finalDiff"] = finalDiff;
    combo[@"verify"] = verifyStatus;
    
    return [self serializableCombo:combo];
}

@end
