#import "MacControlCoherenceTokens.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"
#import "MacControlSupport.hpp"

static NSString* ReadContentHashForRelPath(NSString* relPath, NSString* workspacePath, DietCodeControlWindowBridge* windowBridge) {
    NSString* absPath = AbsolutePathForRPCPath(relPath, workspacePath);
    if (!absPath) return @"";
    NSString* readSource = nil;
    NSString* text = TextForSearchAtPath([windowBridge textForFileAtPath:absPath], absPath, &readSource);
    if (!text) {
        NSError* err = nil;
        text = [NSString stringWithContentsOfFile:absPath encoding:NSUTF8StringEncoding error:&err];
    }
    return StableHashForString(text ?: @"");
}

NSString* MacControlCoherenceAnchorHash(NSString* rawHash) {
    if (rawHash.length == 0) return @"";
    if ([rawHash containsString:@":"]) return rawHash;
    return [NSString stringWithFormat:@"fnv1a:%@", rawHash];
}

NSString* MacControlCoherenceRawHash(NSString* anchoredHash) {
    if (anchoredHash.length == 0) return @"";
    NSRange sep = [anchoredHash rangeOfString:@":"];
    if (sep.location != NSNotFound) {
        return [anchoredHash substringFromIndex:sep.location + 1];
    }
    return anchoredHash;
}

@implementation MacControlCoherenceRegistry {
    NSInteger _tokenSeq;
    NSMutableDictionary<NSString*, NSMutableDictionary*>* _tokens;
    NSMutableDictionary<NSString*, NSString*>* _taskToTokenId;
    NSMutableArray<NSString*>* _taskOrder;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _tokenSeq = 0;
        _tokens = [NSMutableDictionary dictionary];
        _taskToTokenId = [NSMutableDictionary dictionary];
        _taskOrder = [NSMutableArray array];
    }
    return self;
}

- (void)pruneExpiredTokens {
    NSDate* now = [NSDate date];
    NSMutableArray<NSString*>* expired = [NSMutableArray array];
    for (NSString* tokenId in _tokens) {
        NSDictionary* token = _tokens[tokenId];
        NSDate* expiresAt = token[@"expiresAt"];
        if (expiresAt && [expiresAt compare:now] != NSOrderedDescending) {
            [expired addObject:tokenId];
        }
    }
    for (NSString* tokenId in expired) {
        NSDictionary* token = _tokens[tokenId];
        NSString* taskId = token[@"taskId"];
        if (taskId.length > 0 && [_taskToTokenId[taskId] isEqualToString:tokenId]) {
            [_taskToTokenId removeObjectForKey:taskId];
            [_taskOrder removeObject:taskId];
        }
        [_tokens removeObjectForKey:tokenId];
    }
}

- (void)evictTasksIfNeeded {
    while (_taskOrder.count >= (NSUInteger)kCoherenceMaxTasks) {
        NSString* evictTaskId = _taskOrder.firstObject;
        [_taskOrder removeObjectAtIndex:0];
        NSString* evictTokenId = _taskToTokenId[evictTaskId];
        [_taskToTokenId removeObjectForKey:evictTaskId];
        if (evictTokenId.length > 0) {
            [_tokens removeObjectForKey:evictTokenId];
        }
    }
}

- (NSMutableDictionary*)tokenRecordForTask:(NSString*)taskId
                         workspaceRevision:(NSInteger)workspaceRevision
                            verifyRevision:(NSInteger)verifyRevision {
    NSString* existingId = _taskToTokenId[taskId];
    NSMutableDictionary* record = existingId.length > 0 ? [_tokens[existingId] mutableCopy] : nil;
    if (!record) {
        [self evictTasksIfNeeded];
        _tokenSeq += 1;
        NSString* tokenId = [NSString stringWithFormat:@"coh_%ld", (long)_tokenSeq];
        NSDate* now = [NSDate date];
        record = [@{
            @"tokenId": tokenId,
            @"taskId": taskId,
            @"workspaceRevision": @(workspaceRevision),
            @"verifyRevision": @(verifyRevision),
            @"anchors": [NSMutableDictionary dictionary],
            @"createdAt": now,
            @"expiresAt": [now dateByAddingTimeInterval:kCoherenceTokenTTLSeconds],
        } mutableCopy];
        _tokens[tokenId] = record;
        _taskToTokenId[taskId] = tokenId;
        if (![_taskOrder containsObject:taskId]) {
            [_taskOrder addObject:taskId];
        }
    } else {
        record[@"workspaceRevision"] = @(workspaceRevision);
        record[@"verifyRevision"] = @(verifyRevision);
        NSDate* now = [NSDate date];
        record[@"expiresAt"] = [now dateByAddingTimeInterval:kCoherenceTokenTTLSeconds];
    }
    return record;
}

- (NSDictionary*)wirePayloadFromRecord:(NSMutableDictionary*)record paths:(NSArray<NSString*>*)paths {
    NSMutableDictionary* wireAnchors = [NSMutableDictionary dictionary];
    NSMutableDictionary* storedAnchors = record[@"anchors"];
    if (paths.count > 0) {
        for (NSString* relPath in paths) {
            if (relPath.length == 0) continue;
            NSString* raw = storedAnchors[relPath];
            if (raw.length > 0) wireAnchors[relPath] = MacControlCoherenceAnchorHash(raw);
        }
    } else {
        for (NSString* relPath in storedAnchors) {
            wireAnchors[relPath] = MacControlCoherenceAnchorHash(storedAnchors[relPath]);
        }
    }
    return @{
        @"tokenId": record[@"tokenId"] ?: @"",
        @"workspaceRevision": record[@"workspaceRevision"] ?: @0,
        @"verifyRevision": record[@"verifyRevision"] ?: @0,
        @"anchors": wireAnchors,
    };
}

- (NSDictionary*)issueForTask:(NSString*)taskId
                          paths:(NSArray<NSString*>*)paths
              workspaceRevision:(NSInteger)workspaceRevision
                 verifyRevision:(NSInteger)verifyRevision
                      workspace:(NSString*)workspacePath
                   windowBridge:(DietCodeControlWindowBridge*)windowBridge {
    if (taskId.length == 0) return nil;
    [self pruneExpiredTokens];

    NSMutableDictionary* record = [self tokenRecordForTask:taskId
                                         workspaceRevision:workspaceRevision
                                            verifyRevision:verifyRevision];
    NSMutableDictionary* anchors = record[@"anchors"];
    for (NSString* relPath in paths ?: @[]) {
        if (relPath.length == 0) continue;
        anchors[relPath] = ReadContentHashForRelPath(relPath, workspacePath, windowBridge);
        while ((NSInteger)anchors.count > kCoherenceMaxAnchorsPerTask) {
            NSString* oldest = anchors.allKeys.firstObject;
            [anchors removeObjectForKey:oldest];
        }
    }
    _tokens[record[@"tokenId"]] = record;

    return [self wirePayloadFromRecord:record paths:paths ?: @[]];
}

- (NSDictionary*)payloadForTask:(NSString*)taskId
              workspaceRevision:(NSInteger)workspaceRevision
                 verifyRevision:(NSInteger)verifyRevision {
    if (taskId.length == 0) return nil;
    [self pruneExpiredTokens];
    NSString* tokenId = _taskToTokenId[taskId];
    NSMutableDictionary* record = tokenId.length > 0 ? [_tokens[tokenId] mutableCopy] : nil;
    if (!record) {
        record = [self tokenRecordForTask:taskId workspaceRevision:workspaceRevision verifyRevision:verifyRevision];
        _tokens[record[@"tokenId"]] = record;
    } else {
        record[@"workspaceRevision"] = @(workspaceRevision);
        record[@"verifyRevision"] = @(verifyRevision);
        _tokens[record[@"tokenId"]] = record;
    }
    return [self wirePayloadFromRecord:record paths:@[]];
}

- (BOOL)validateMutationParams:(NSDictionary*)params
             workspaceRevision:(NSInteger)workspaceRevision
                verifyRevision:(NSInteger)verifyRevision
                     workspace:(NSString*)workspacePath
                  windowBridge:(DietCodeControlWindowBridge*)windowBridge
                      outDetail:(NSDictionary**)outDetail
                      outMessage:(NSString**)outMessage {
    if (outDetail) *outDetail = nil;
    NSString* taskId = params[@"taskId"];
    if (![taskId isKindOfClass:[NSString class]] || taskId.length == 0) {
        return YES;
    }

    [self pruneExpiredTokens];

    NSString* tokenId = params[@"coherenceTokenId"];
    id expectedRevValue = params[@"expectedWorkspaceRevision"];
    if (tokenId.length == 0 || expectedRevValue == nil) {
        if (outMessage) {
            *outMessage = @"Mutating RPC requires coherenceTokenId and expectedWorkspaceRevision when taskId is set.";
        }
        if (outDetail) {
            *outDetail = @{
                @"reason": @"token_required",
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    NSDictionary* token = _tokens[tokenId];
    NSDate* expiresAt = token[@"expiresAt"];
    if (!token || (expiresAt && [expiresAt timeIntervalSinceNow] <= 0)) {
        if (outMessage) *outMessage = @"Coherence token is missing or expired.";
        if (outDetail) {
            *outDetail = @{
                @"reason": token ? @"token_expired" : @"token_unknown",
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    if (![token[@"taskId"] isEqualToString:taskId]) {
        if (outMessage) *outMessage = @"Coherence token does not match taskId.";
        if (outDetail) {
            *outDetail = @{
                @"reason": @"token_task_mismatch",
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    NSInteger expectedRev = [expectedRevValue integerValue];
    if (expectedRev != workspaceRevision) {
        if (outMessage) {
            *outMessage = @"Workspace revision changed since this task observed state.";
        }
        if (outDetail) {
            *outDetail = @{
                @"reason": @"workspace_changed",
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    NSInteger tokenVerifyRev = [token[@"verifyRevision"] integerValue];
    if (tokenVerifyRev != verifyRevision) {
        if (outMessage) {
            *outMessage = @"Verification revision changed since this task observed state.";
        }
        if (outDetail) {
            *outDetail = @{
                @"reason": @"verify_revision_stale",
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    NSDictionary* anchors = token[@"anchors"] ?: @{};
    NSMutableArray<NSString*>* changedPaths = [NSMutableArray array];
    for (NSString* relPath in anchors) {
        NSString* anchorRaw = anchors[relPath];
        NSString* currentRaw = ReadContentHashForRelPath(relPath, workspacePath, windowBridge);
        if (anchorRaw.length > 0 && currentRaw.length > 0 && ![anchorRaw isEqualToString:currentRaw]) {
            [changedPaths addObject:relPath];
        }
    }
    if (changedPaths.count > 0) {
        if (outMessage) {
            *outMessage = @"Anchored file content changed since this task read it.";
        }
        if (outDetail) {
            *outDetail = @{
                @"reason": @"anchored_file_changed",
                @"changedPaths": changedPaths,
                @"requiredAction": @"refresh_context",
                @"currentWorkspaceRevision": @(workspaceRevision),
            };
        }
        return NO;
    }

    return YES;
}

@end
