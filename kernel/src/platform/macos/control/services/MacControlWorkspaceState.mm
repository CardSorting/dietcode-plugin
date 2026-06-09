#import "MacControlWorkspaceState.hpp"
#import "MacControlMemoryService.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlCoherenceTokens.hpp"
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"

@implementation MacControlWorkspaceState {
    NSInteger _revisionCounter;
    NSDictionary* _lastMutationReceipt;
    NSArray<NSString*>* _lastChangedFiles;
    NSString* _lastMutationSource;
    BOOL _externalChangeDetected;
    NSMutableDictionary<NSString*, NSDictionary*>* _completedOperations;
    NSMutableDictionary<NSString*, NSString*>* _trackedFileHashes;
    NSMutableSet<NSString*>* _externallyChangedPaths;
    NSString* _agentShellCwd;
    NSInteger _contextRefreshId;
    NSString* _anchorGitHead;
    NSDate* _anchorRefreshedAt;
    BOOL _continueAnywayActive;
    NSDate* _continueAnywayExpiresAt;
    NSInteger _verifyRevisionCounter;
    MacControlCoherenceRegistry* _coherenceRegistry;
    NSDictionary* _lastCoherenceMismatchDetail;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _revisionCounter = 1;
        _lastChangedFiles = @[];
        _lastMutationSource = @"none";
        _completedOperations = [NSMutableDictionary dictionary];
        _trackedFileHashes = [NSMutableDictionary dictionary];
        _externallyChangedPaths = [NSMutableSet set];
        _contextRefreshId = 1;
        _verifyRevisionCounter = 0;
        _coherenceRegistry = [[MacControlCoherenceRegistry alloc] init];
    }
    return self;
}

static NSString* GitHeadHashForWorkspace(NSString* workspacePath) {
    if (workspacePath.length == 0) return @"";
    NSTask* task = [[NSTask alloc] init];
    task.launchPath = @"/usr/bin/git";
    task.arguments = @[@"-C", workspacePath, @"rev-parse", @"HEAD"];
    NSPipe* pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = [NSPipe pipe];
    @try {
        [task launch];
        [task waitUntilExit];
        if (task.terminationStatus != 0) return @"";
        NSData* data = [[pipe fileHandleForReading] readDataToEndOfFile];
        return [[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] ?: @"";
    } @catch (...) {
        return @"";
    }
}

static NSString* ISODateFromNSDate(NSDate* date) {
    if (!date) return @"";
    return ISODateString(date);
}

- (NSInteger)revisionId {
    return _revisionCounter;
}

- (NSInteger)verifyRevision {
    return _verifyRevisionCounter;
}

- (NSDictionary*)lastCoherenceMismatchDetail {
    return _lastCoherenceMismatchDetail ?: @{};
}

- (void)bumpVerifyRevision {
    _verifyRevisionCounter += 1;
}

- (NSDictionary*)lastMutationReceipt {
    return _lastMutationReceipt ?: @{};
}

- (NSArray<NSString*>*)lastChangedFiles {
    return _lastChangedFiles ?: @[];
}

- (NSString*)lastMutationSource {
    return _lastMutationSource ?: @"none";
}

- (BOOL)externalChangeDetected {
    return _externalChangeDetected;
}

- (void)bumpRevision {
    _revisionCounter++;
}

- (NSDictionary*)revisionPayloadWithWorkspace:(NSString*)workspacePath {
    return @{
        @"revisionId": @(_revisionCounter),
        @"workspaceRevision": @(_revisionCounter),
        @"verifyRevision": @(_verifyRevisionCounter),
        @"workspacePath": workspacePath ?: @"",
        @"changedFiles": self.lastChangedFiles,
        @"lastMutationReceipt": self.lastMutationReceipt,
        @"lastMutationSource": self.lastMutationSource,
        @"externalChangeDetected": @(_externalChangeDetected),
        @"externallyChangedPaths": _externallyChangedPaths.allObjects ?: @[],
        @"mode": @"workspace_revision"
    };
}

static NSString* ReadHashForPath(NSString* absPath, DietCodeControlWindowBridge* windowBridge) {
    NSString* readSource = nil;
    NSString* text = TextForSearchAtPath([windowBridge textForFileAtPath:absPath], absPath, &readSource);
    if (!text) {
        NSError* err = nil;
        text = [NSString stringWithContentsOfFile:absPath encoding:NSUTF8StringEncoding error:&err];
    }
    return StableHashForString(text ?: @"");
}

- (NSDictionary*)snapshotPayloadWithWorkspace:(NSString*)workspacePath
                                 sinceRevision:(NSNumber*)sinceRevision
                                         paths:(NSArray<NSString*>*)paths
                                  snapshotMode:(NSString*)snapshotMode
                                      maxFiles:(NSNumber*)maxFiles
                                  windowBridge:(DietCodeControlWindowBridge*)windowBridge {
    NSInteger since = sinceRevision ? [sinceRevision integerValue] : 0;
    NSInteger limit = maxFiles ? MAX([maxFiles integerValue], 1) : 100;
    if (limit > 500) limit = 500;
    NSString* mode = snapshotMode.length > 0 ? snapshotMode : @"mutated_only";
    NSMutableArray* changedFiles = [NSMutableArray array];
    NSMutableDictionary* fileHashes = [NSMutableDictionary dictionary];
    BOOL externalDetected = NO;
    NSInteger filesSkipped = 0;
    NSInteger filesHashed = 0;
    BOOL truncated = NO;

    NSMutableArray<NSString*>* inspectPaths = [NSMutableArray array];
    if ([mode isEqualToString:@"explicit_paths"]) {
        for (NSString* p in paths ?: @[]) {
            if (p.length > 0) [inspectPaths addObject:p];
        }
    } else if ([mode isEqualToString:@"tracked_files"]) {
        for (NSString* tracked in _trackedFileHashes.allKeys) {
            [inspectPaths addObject:tracked];
        }
    } else {
        NSMutableSet<NSString*>* mutated = [NSMutableSet set];
        for (NSString* p in paths ?: @[]) {
            if (p.length > 0) [mutated addObject:p];
        }
        for (NSString* p in self.lastChangedFiles) [mutated addObject:p];
        for (NSString* p in _externallyChangedPaths) [mutated addObject:p];
        for (NSString* tracked in _trackedFileHashes.allKeys) [mutated addObject:tracked];
        inspectPaths = [NSMutableArray arrayWithArray:[[mutated allObjects] sortedArrayUsingSelector:@selector(compare:)]];
    }

    for (NSString* relPath in inspectPaths) {
        if (filesHashed >= limit) {
            truncated = YES;
            filesSkipped++;
            continue;
        }
        NSString* absPath = AbsolutePathForRPCPath(relPath, workspacePath);
        if (!absPath || !PathIsInsideWorkspace(absPath, workspacePath)) {
            filesSkipped++;
            continue;
        }
        if (PathIsSymlink(absPath)) {
            filesSkipped++;
            continue;
        }
        NSString* currentHash = ReadHashForPath(absPath, windowBridge);
        fileHashes[relPath] = currentHash;
        filesHashed++;
        NSString* priorHash = _trackedFileHashes[relPath];
        if (since > 0 && since < _revisionCounter && priorHash.length > 0 && ![priorHash isEqualToString:currentHash]) {
            [changedFiles addObject:@{
                @"path": relPath,
                @"priorContentHash": priorHash,
                @"currentContentHash": currentHash,
                @"source": [_externallyChangedPaths containsObject:relPath] ? @"external" : @"unknown"
            }];
            externalDetected = YES;
        }
    }

    BOOL complete = !truncated && filesSkipped == 0;
    return @{
        @"revisionId": @(_revisionCounter),
        @"snapshotId": [NSString stringWithFormat:@"snap-%ld", (long)_revisionCounter],
        @"sinceRevision": @(since),
        @"revisionDelta": @(MAX(0, _revisionCounter - since)),
        @"snapshotMode": mode,
        @"fileHashes": fileHashes,
        @"changedFiles": changedFiles,
        @"filesHashed": @(filesHashed),
        @"filesSkipped": @(filesSkipped),
        @"complete": @(complete),
        @"truncated": @(truncated),
        @"hashAlgorithm": @"fnv1a_16hex",
        @"externalChangeDetected": @(externalDetected || _externalChangeDetected),
        @"mode": @"workspace_snapshot"
    };
}

- (NSDictionary*)operationStatusForKey:(NSString*)idempotencyKey {
    if (idempotencyKey.length == 0) {
        return @{ @"status": @"unknown", @"reason": @"idempotencyKey required" };
    }
    NSDictionary* record = _completedOperations[idempotencyKey];
    if (!record && self.memoryService.available) {
        NSDictionary* durable = [self.memoryService operationForIdempotencyKey:idempotencyKey];
        if (durable && [durable[@"status"] isEqualToString:@"completed"]) {
            NSMutableDictionary* payload = [NSMutableDictionary dictionary];
            payload[@"status"] = @"completed";
            payload[@"idempotencyKey"] = idempotencyKey;
            payload[@"revisionBefore"] = durable[@"revisionBefore"] ?: @0;
            payload[@"revisionAfter"] = durable[@"revisionAfter"] ?: @0;
            payload[@"completedAt"] = durable[@"completedAt"] ?: @0;
            NSDictionary* receipt = durable[@"receipt"];
            if (receipt) {
                if (receipt[@"atomic"] && [receipt[@"fileReceipts"] isKindOfClass:[NSArray class]]) {
                    payload[@"batchMutationReceipt"] = receipt;
                } else {
                    payload[@"mutationReceipt"] = receipt;
                }
            }
            payload[@"durableReplay"] = @YES;
            payload[@"source"] = @"broccoliq_memory";
            return payload;
        }
        NSDictionary* replay = [self.memoryService replayCacheForKey:idempotencyKey];
        if (replay && [replay[@"retained"] boolValue]) {
            NSDictionary* result = replay[@"result"];
            NSMutableDictionary* payload = [NSMutableDictionary dictionary];
            payload[@"status"] = @"completed";
            payload[@"idempotencyKey"] = idempotencyKey;
            payload[@"durableReplay"] = @YES;
            payload[@"source"] = @"broccoliq_replay_cache";
            if ([result[@"mutationReceipt"] isKindOfClass:[NSDictionary class]]) {
                payload[@"mutationReceipt"] = result[@"mutationReceipt"];
            }
            if ([result[@"batchMutationReceipt"] isKindOfClass:[NSDictionary class]]) {
                payload[@"batchMutationReceipt"] = result[@"batchMutationReceipt"];
            }
            payload[@"revisionBefore"] = result[@"revisionBefore"] ?: @0;
            payload[@"revisionAfter"] = result[@"revisionAfter"] ?: @0;
            return payload;
        }
        if (replay && [replay[@"expired"] boolValue]) {
            return @{
                @"status": @"expired",
                @"idempotencyKey": idempotencyKey,
                @"recoveryHint": replay[@"recoveryHint"] ?: @"retry_with_new_idempotencyKey_or_revalidate",
                @"nextRecommendedCommand": replay[@"nextRecommendedCommand"] ?: @"patch.validate",
            };
        }
    }
    if (!record) {
        return @{ @"status": @"unknown", @"idempotencyKey": idempotencyKey };
    }
    NSMutableDictionary* payload = [record mutableCopy];
    payload[@"status"] = @"completed";
    return payload;
}

- (void)trackHashesForPaths:(NSArray<NSString*>*)paths workspace:(NSString*)ws windowBridge:(DietCodeControlWindowBridge*)windowBridge {
    for (NSString* relPath in paths) {
        NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
        if (!absPath) continue;
        _trackedFileHashes[relPath] = ReadHashForPath(absPath, windowBridge);
    }
}

- (void)recordAgentMutationWithReceipt:(NSDictionary*)receipt
                          changedPaths:(NSArray<NSString*>*)paths
                        idempotencyKey:(NSString*)idempotencyKey
                        revisionBefore:(NSInteger)revisionBefore {
    NSInteger revisionAfter = _revisionCounter + 1;
    [self bumpRevision];
    _lastMutationReceipt = receipt ?: @{};
    _lastChangedFiles = paths ?: @[];
    _lastMutationSource = @"agent";
    [_externallyChangedPaths minusSet:[NSSet setWithArray:paths ?: @[]]];
    if (_externallyChangedPaths.count == 0) _externalChangeDetected = NO;

    if (idempotencyKey.length > 0) {
        _completedOperations[idempotencyKey] = @{
            @"idempotencyKey": idempotencyKey,
            @"mutationReceipt": receipt ?: @{},
            @"revisionBefore": @(revisionBefore),
            @"revisionAfter": @(revisionAfter),
            @"changedFiles": paths ?: @[],
            @"completedAt": @([[NSDate date] timeIntervalSince1970])
        };
    }
}

- (void)recordBatchMutationWithReceipt:(NSDictionary*)batchReceipt
                           changedPaths:(NSArray<NSString*>*)paths
                         idempotencyKey:(NSString*)idempotencyKey
                         revisionBefore:(NSInteger)revisionBefore {
    NSInteger revisionAfter = _revisionCounter + 1;
    [self bumpRevision];
    _lastMutationReceipt = batchReceipt ?: @{};
    _lastChangedFiles = paths ?: @[];
    _lastMutationSource = @"agent";
    [_externallyChangedPaths minusSet:[NSSet setWithArray:paths ?: @[]]];
    if (_externallyChangedPaths.count == 0) _externalChangeDetected = NO;

    if (idempotencyKey.length > 0) {
        _completedOperations[idempotencyKey] = @{
            @"idempotencyKey": idempotencyKey,
            @"batchMutationReceipt": batchReceipt ?: @{},
            @"revisionBefore": @(revisionBefore),
            @"revisionAfter": @(revisionAfter),
            @"changedFiles": paths ?: @[],
            @"completedAt": @([[NSDate date] timeIntervalSince1970])
        };
    }
}

- (void)noteExternalChangeForPath:(NSString*)path {
    if (path.length == 0) return;
    [_externallyChangedPaths addObject:path];
    _externalChangeDetected = YES;
    _lastMutationSource = @"external";
}

- (void)clearExternalChangeFlag {
    _externalChangeDetected = NO;
    [_externallyChangedPaths removeAllObjects];
}

- (NSInteger)contextRefreshId {
    return _contextRefreshId;
}

- (BOOL)validateContextRefreshForParams:(NSDictionary*)params driftDetected:(BOOL)driftDetected {
    if (!driftDetected) return YES;
    if ([params[@"continueAnyway"] boolValue]) return YES;
    if (_continueAnywayActive && _continueAnywayExpiresAt && [_continueAnywayExpiresAt timeIntervalSinceNow] > 0) {
        _continueAnywayActive = NO;
        return YES;
    }
    NSNumber* refreshId = params[@"contextRefreshId"];
    if (refreshId && [refreshId integerValue] == _contextRefreshId) return YES;
    return NO;
}

- (NSDictionary*)continueAnywayPayload {
    _continueAnywayActive = YES;
    _continueAnywayExpiresAt = [NSDate dateWithTimeIntervalSinceNow:300];
    return @{
        @"mode": @"workspace_continue_anyway",
        @"continueAnyway": @YES,
        @"expiresAt": ISODateFromNSDate(_continueAnywayExpiresAt),
        @"contextRefreshId": @(_contextRefreshId),
    };
}

- (NSDictionary*)statusPayloadWithWorkspace:(NSString*)workspacePath
                               windowBridge:(DietCodeControlWindowBridge*)windowBridge
                                    gitInfo:(NSDictionary*)gitInfo
                              verifyStatus:(NSDictionary*)verifyStatus
                        lastVerifyFinishedAt:(NSDate*)lastVerifyFinishedAt {
    NSString* gitHead = GitHeadHashForWorkspace(workspacePath);
    NSString* branch = gitInfo[@"branch"] ?: @"";
    NSMutableArray* dirtyFiles = [NSMutableArray array];
    for (NSString* key in @[@"modified", @"staged", @"untracked"]) {
        for (NSString* path in gitInfo[key] ?: @[]) {
            if (path.length > 0) [dirtyFiles addObject:path];
        }
    }

    NSMutableArray* affectedFiles = [NSMutableArray array];
    NSMutableSet* seen = [NSMutableSet set];
    NSDate* verifyFinished = lastVerifyFinishedAt;

    for (NSString* relPath in _trackedFileHashes.allKeys) {
        NSString* absPath = AbsolutePathForRPCPath(relPath, workspacePath);
        if (!absPath) continue;
        NSString* anchorHash = _trackedFileHashes[relPath];
        NSString* currentHash = ReadHashForPath(absPath, windowBridge);
        if (anchorHash.length > 0 && ![anchorHash isEqualToString:currentHash]) {
            [affectedFiles addObject:@{
                @"path": relPath,
                @"reason": @"changed since agent read it",
                @"anchorHash": anchorHash,
                @"currentHash": currentHash,
                @"source": @"tracked_hash",
            }];
            [seen addObject:relPath];
        }
    }

    for (NSString* relPath in _externallyChangedPaths) {
        if ([seen containsObject:relPath]) continue;
        [affectedFiles addObject:@{
            @"path": relPath,
            @"reason": @"changed outside DietCode",
            @"source": @"external_watch",
        }];
        [seen addObject:relPath];
    }

    if (_anchorGitHead.length > 0 && gitHead.length > 0 && ![_anchorGitHead isEqualToString:gitHead]) {
        [affectedFiles addObject:@{
            @"path": @"(git HEAD)",
            @"reason": @"git HEAD moved since context anchor",
            @"anchorGitHead": _anchorGitHead,
            @"currentGitHead": gitHead,
            @"source": @"git_head",
        }];
    }

    if (verifyFinished && _lastChangedFiles.count > 0) {
        for (NSString* relPath in _lastChangedFiles) {
            if ([seen containsObject:relPath]) continue;
            NSString* absPath = AbsolutePathForRPCPath(relPath, workspacePath);
            if (!absPath) continue;
            NSString* anchorHash = _trackedFileHashes[relPath];
            NSString* currentHash = ReadHashForPath(absPath, windowBridge);
            if (anchorHash.length > 0 && ![anchorHash isEqualToString:currentHash]) {
                [affectedFiles addObject:@{
                    @"path": relPath,
                    @"reason": @"changed after verification",
                    @"source": @"post_verify",
                }];
                [seen addObject:relPath];
            }
        }
    }

    BOOL driftDetected = affectedFiles.count > 0 || _externalChangeDetected;

    NSMutableDictionary* anchors = [NSMutableDictionary dictionary];
    for (NSString* relPath in _trackedFileHashes) {
        anchors[relPath] = @{
            @"hash": _trackedFileHashes[relPath] ?: @"",
            @"algorithm": @"fnv1a_16hex",
        };
    }

    return @{
        @"mode": @"workspace_status",
        @"root": workspacePath ?: @"",
        @"revisionId": @(_revisionCounter),
        @"workspaceRevision": @(_revisionCounter),
        @"verifyRevision": @(_verifyRevisionCounter),
        @"gitHead": gitHead,
        @"gitBranch": branch,
        @"anchorGitHead": _anchorGitHead ?: @"",
        @"anchorRefreshedAt": ISODateFromNSDate(_anchorRefreshedAt),
        @"contextRefreshId": @(_contextRefreshId),
        @"dirtyFiles": dirtyFiles,
        @"fileAnchors": anchors,
        @"affectedFiles": affectedFiles,
        @"driftDetected": @(driftDetected),
        @"externalChangeDetected": @(_externalChangeDetected),
        @"lastVerifiedCommand": verifyStatus[@"command"] ?: @"",
        @"lastVerifiedAt": ISODateFromNSDate(lastVerifyFinishedAt),
        @"lastVerifyPassed": verifyStatus[@"passed"] ?: @NO,
        @"lastMutationSource": self.lastMutationSource,
        @"requiresContextRefresh": @(driftDetected),
    };
}

- (NSDictionary*)refreshAnchorWithWorkspace:(NSString*)workspacePath
                               windowBridge:(DietCodeControlWindowBridge*)windowBridge
                                    gitInfo:(NSDictionary*)gitInfo
                              verifyStatus:(NSDictionary*)verifyStatus
                        lastVerifyFinishedAt:(NSDate*)lastVerifyFinishedAt {
    NSArray* paths = [_trackedFileHashes.allKeys copy];
    if (paths.count == 0) {
        for (NSString* relPath in self.lastChangedFiles) {
            [self trackHashesForPaths:@[relPath] workspace:workspacePath windowBridge:windowBridge];
        }
        paths = [_trackedFileHashes.allKeys copy];
    }
    [self trackHashesForPaths:paths workspace:workspacePath windowBridge:windowBridge];
    [self clearExternalChangeFlag];
    _contextRefreshId += 1;
    _anchorGitHead = GitHeadHashForWorkspace(workspacePath);
    _anchorRefreshedAt = [NSDate date];
    _lastMutationSource = @"anchor_refresh";

    NSMutableDictionary* status = [[self statusPayloadWithWorkspace:workspacePath
                                                       windowBridge:windowBridge
                                                            gitInfo:gitInfo
                                                      verifyStatus:verifyStatus
                                                lastVerifyFinishedAt:lastVerifyFinishedAt] mutableCopy];
    status[@"refreshed"] = @YES;
    status[@"mode"] = @"workspace_refresh_anchor";
    return status;
}

- (void)recordRuntimeError:(NSString*)stringCode method:(NSString*)method envelope:(NSDictionary*)envelope {
    MacControlMemoryService* memory = self.memoryService;
    if (!memory.available) return;
    [memory recordErrorEvent:stringCode method:method envelope:envelope ?: @{}];
}

- (void)persistMutationToMemory:(NSString*)method
                   idempotencyKey:(NSString*)idempotencyKey
                       paramsHash:(NSString*)paramsHash
                          receipt:(NSDictionary*)receipt
                     changedPaths:(NSArray<NSString*>*)paths
                   revisionBefore:(NSInteger)revisionBefore
                    revisionAfter:(NSInteger)revisionAfter
                    resultPayload:(NSDictionary*)resultPayload {
    MacControlMemoryService* memory = self.memoryService;
    if (!memory.available) return;

    NSString* opId = resultPayload[@"operationId"] ?: [[NSUUID UUID] UUIDString];
    NSString* receiptJson = [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:receipt ?: @{} options:0 error:nil] encoding:NSUTF8StringEncoding] ?: @"";
    NSString* receiptHash = StableHashForString(receiptJson);

    [memory recordOperation:@{
        @"operationId": opId,
        @"method": method ?: @"",
        @"paramsHash": paramsHash ?: @"",
        @"idempotencyKey": idempotencyKey ?: @"",
        @"status": @"completed",
        @"receipt": receipt ?: @{},
        @"receiptHash": receiptHash,
        @"revisionBefore": @(revisionBefore),
        @"revisionAfter": @(revisionAfter),
        @"completedAt": @([[NSDate date] timeIntervalSince1970]),
    } error:nil];

    [memory recordRevision:@{
        @"revisionId": @(revisionAfter),
        @"changedFiles": paths ?: @[],
        @"mutationSource": @"agent",
        @"operationId": opId,
        @"receiptHash": receiptHash,
        @"previousRevisionId": @(revisionBefore),
    } error:nil];

    if (idempotencyKey.length > 0 && resultPayload) {
        [memory storeReplayCache:@{
            @"idempotencyKey": idempotencyKey,
            @"method": method ?: @"",
            @"paramsHash": paramsHash ?: @"",
            @"result": resultPayload,
            @"receiptHash": receiptHash,
        } error:nil];
    }

    [memory recordTelemetryEvent:@"mutation_recorded" payload:@{
        @"method": method ?: @"",
        @"revisionAfter": @(revisionAfter),
        @"idempotencyKey": idempotencyKey ?: @"",
    }];
}

- (NSString*)agentShellCwdForWorkspace:(NSString*)workspacePath {
    if (_agentShellCwd.length > 0) return _agentShellCwd;
    return workspacePath ?: @"";
}

- (void)resetAgentShellCwdForWorkspace:(NSString*)workspacePath {
    (void)workspacePath;
    _agentShellCwd = nil;
}

- (BOOL)setAgentShellCwd:(NSString*)absolutePath
               workspace:(NSString*)workspacePath
               errorCode:(NSString**)outErrCode
            errorMessage:(NSString**)outErrMsg {
    if (absolutePath.length == 0) {
        if (outErrCode) *outErrCode = @"invalid_params";
        if (outErrMsg) *outErrMsg = @"path parameter required.";
        return NO;
    }
    if (workspacePath.length > 0 && !PathIsInsideWorkspace(absolutePath, workspacePath)) {
        if (outErrCode) *outErrCode = @"outside_workspace";
        if (outErrMsg) *outErrMsg = @"Target directory is outside workspace.";
        return NO;
    }
    NSDictionary* symlinkMeta = PathSymlinkMetadata(absolutePath, workspacePath);
    if ([symlinkMeta[@"pathEscapesWorkspace"] boolValue]) {
        if (outErrCode) *outErrCode = @"symlink_escape";
        if (outErrMsg) *outErrMsg = @"Symlink target escapes workspace.";
        return NO;
    }
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:absolutePath isDirectory:&isDir] || !isDir) {
        if (outErrCode) *outErrCode = @"directory_not_found";
        if (outErrMsg) *outErrMsg = @"Directory does not exist.";
        return NO;
    }
    _agentShellCwd = [absolutePath copy];
    return YES;
}

- (NSDictionary*)issueCoherenceForTask:(NSString*)taskId
                                 paths:(NSArray<NSString*>*)paths
                             workspace:(NSString*)workspacePath
                          windowBridge:(DietCodeControlWindowBridge*)windowBridge {
    return [_coherenceRegistry issueForTask:taskId
                                      paths:paths
                          workspaceRevision:_revisionCounter
                             verifyRevision:_verifyRevisionCounter
                                  workspace:workspacePath
                               windowBridge:windowBridge];
}

- (NSDictionary*)coherencePayloadForTask:(NSString*)taskId {
    return [_coherenceRegistry payloadForTask:taskId
                            workspaceRevision:_revisionCounter
                               verifyRevision:_verifyRevisionCounter];
}

- (BOOL)validateCoherenceForMutation:(NSDictionary*)params
                           workspace:(NSString*)workspacePath
                        windowBridge:(DietCodeControlWindowBridge*)windowBridge
                           outMessage:(NSString**)outMessage {
    _lastCoherenceMismatchDetail = nil;
    NSDictionary* detail = nil;
    BOOL ok = [_coherenceRegistry validateMutationParams:params
                                     workspaceRevision:_revisionCounter
                                        verifyRevision:_verifyRevisionCounter
                                             workspace:workspacePath
                                          windowBridge:windowBridge
                                              outDetail:&detail
                                              outMessage:outMessage];
    if (!ok && detail) {
        _lastCoherenceMismatchDetail = detail;
    }
    return ok;
}

@end
