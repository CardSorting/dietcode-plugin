#import "MacControlPatchService.hpp"
#import "MacControlWorkspaceState.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"
#import "MacControlDiffParsing.hpp"
#import "SymbolIndexService.hpp"
#import "DiffAnalysisService.hpp"
#import "SubprocessRunner.hpp"

#include <filesystem>
#include <string>
#include <vector>
#include <unistd.h>

static NSString* DietCodeReadTextFileForPatchService(NSString* path) {
    if (path.length == 0) return nil;
    NSStringEncoding encoding = NSUTF8StringEncoding;
    NSError* error = nil;
    NSString* text = [NSString stringWithContentsOfFile:path usedEncoding:&encoding error:&error];
    return text;
}

static BOOL ApplyUnifiedPatchToDisk(NSString* absPath, NSString* beforeText, NSString* patchStr, NSString** errorOut) {
    if (absPath.length == 0 || beforeText == nil || patchStr.length == 0) {
        if (errorOut) *errorOut = @"Invalid patch apply inputs.";
        return NO;
    }
    NSString* tempDir = NSTemporaryDirectory() ?: @"/tmp";
    NSString* uuidStr = [[NSUUID UUID] UUIDString];
    NSString* tempSrcPath = [tempDir stringByAppendingPathComponent:[NSString stringWithFormat:@"dietcode_apply_src_%@.txt", uuidStr]];
    NSString* tempDiffPath = [tempDir stringByAppendingPathComponent:[NSString stringWithFormat:@"dietcode_apply_diff_%@.diff", uuidStr]];
    NSError* err = nil;
    unlink([tempSrcPath UTF8String]);
    [beforeText writeToFile:tempSrcPath atomically:YES encoding:NSUTF8StringEncoding error:&err];
    if (err) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write temp source: %@", err.localizedDescription];
        return NO;
    }
    unlink([tempDiffPath UTF8String]);
    [patchStr writeToFile:tempDiffPath atomically:YES encoding:NSUTF8StringEncoding error:&err];
    if (err) {
        [[NSFileManager defaultManager] removeItemAtPath:tempSrcPath error:nil];
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write temp patch: %@", err.localizedDescription];
        return NO;
    }
    std::vector<std::string> patchArgs = {"--silent", [tempSrcPath UTF8String], [tempDiffPath UTF8String]};
    dietcode::platform::macos::SubprocessResult patchRes = dietcode::platform::macos::SubprocessRunner::run("/usr/bin/patch", patchArgs, "", 10.0);
    NSString* patchedText = [NSString stringWithContentsOfFile:tempSrcPath encoding:NSUTF8StringEncoding error:nil];
    [[NSFileManager defaultManager] removeItemAtPath:tempSrcPath error:nil];
    [[NSFileManager defaultManager] removeItemAtPath:tempDiffPath error:nil];
    if (patchRes.exitCode != 0 || !patchedText) {
        if (errorOut) {
            *errorOut = [NSString stringWithFormat:@"Disk patch failed: %s", patchRes.stdErr.c_str()];
        }
        return NO;
    }
    [patchedText writeToFile:absPath atomically:YES encoding:NSUTF8StringEncoding error:&err];
    if (err) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to write patched file: %@", err.localizedDescription];
        return NO;
    }
    return YES;
}

@implementation MacControlPatchService {
    DietCodeControlWindowBridge* _windowBridge;
    NSMutableArray<NSDictionary*>* _lastPatchRecords;
}

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge {
    self = [super init];
    if (self) {
        _windowBridge = bridge;
        _lastPatchRecords = [NSMutableArray array];
    }
    return self;
}

- (NSArray<NSDictionary*>*)lastPatchRecords {
    return [_lastPatchRecords copy];
}

- (NSDictionary*)validatePatchAtPath:(NSString*)path patch:(NSString*)patch currentText:(NSString*)currentTextOverride {
    return [self validatePatchAtPath:path patch:patch currentText:currentTextOverride options:@{}];
}

- (NSDictionary*)validatePatchAtPath:(NSString*)path 
                               patch:(NSString*)patch 
                          currentText:(NSString*)currentTextOverride 
                              options:(NSDictionary*)options {
    NSString* ws = [_windowBridge workspacePath];
    NSString* targetPath = AbsolutePathForRPCPath(path, ws);
    BOOL insideWorkspace = ws.length > 0 && PathIsInsideWorkspace(targetPath, ws);
    BOOL targetExists = targetPath.length > 0 && [[NSFileManager defaultManager] fileExistsAtPath:targetPath];
    NSArray* hunks = HunkSummariesFromPatch(patch ?: @"");
    NSInteger changedLineCount = ChangedLineCountFromHunks(hunks);
    BOOL requiresConfirmation = (patch.length > kMaxPatchBytesBeforeConfirmation) || changedLineCount > 200;

    NSMutableDictionary* result = [@{
        @"ok": @NO,
        @"targetFileExists": @(targetExists),
        @"insideWorkspace": @(insideWorkspace),
        @"patchAppliesCleanly": @NO,
        @"changedLineCount": @(changedLineCount),
        @"affectedHunks": hunks,
        @"affectedSymbols": @[],
        @"requiresConfirmation": @(requiresConfirmation),
        @"syntaxDanger": @NO,
        @"rejectedReason": @""
    } mutableCopy];

    if (!insideWorkspace) {
        result[@"rejectedReason"] = @"Target file is outside workspace.";
        return result;
    }
    if (PathIsSymlink(targetPath)) {
        result[@"rejectedReason"] = @"Cannot validate patch for symlink target path.";
        return result;
    }
    if (!targetExists) {
        result[@"rejectedReason"] = @"Target file does not exist.";
        return result;
    }
    if (patch.length == 0) {
        result[@"rejectedReason"] = @"Patch is empty.";
        return result;
    }

    NSString* readSource = nil;
    NSString* currentText = currentTextOverride;
    if (!currentText) {
        currentText = TextForSearchAtPath([_windowBridge textForFileAtPath:targetPath], targetPath, &readSource);
    }
    if (!currentText) {
        currentText = DietCodeReadTextFileForPatchService(targetPath);
        if (currentText) readSource = @"disk";
    }
    if (!currentText) {
        result[@"rejectedReason"] = @"Target file is not readable.";
        return result;
    }
    result[@"beforeContentHash"] = StableHashForString(currentText);
    result[@"patchFingerprint"] = StableHashForString(patch ?: @"");
    result[@"readSource"] = readSource ?: @"disk";

    NSArray* symbols = [DietCodeSymbolIndexService symbolsForFileContent:currentText extension:[[targetPath pathExtension] lowercaseString]];
    NSDictionary* preview = [DietCodeDiffAnalysisService previewPatchAtPath:targetPath patch:patch currentText:currentText symbols:symbols];
    BOOL clean = [preview[@"ok"] boolValue];
    result[@"patchAppliesCleanly"] = @(clean);
    result[@"affectedSymbols"] = AffectedSymbolsForPatch(patch, symbols);
    result[@"preview"] = preview;

    if (!clean) {
        result[@"rejectedReason"] = preview[@"error"] ?: @"Patch does not apply cleanly.";
        return result;
    }

    BOOL ignoreSyntax = YES; // Default is YES (relaxed)
    if (options[@"ignoreSyntax"] != nil) {
        ignoreSyntax = [options[@"ignoreSyntax"] boolValue];
    } else if (options[@"force"] != nil) {
        ignoreSyntax = [options[@"force"] boolValue];
    }

    if ([preview[@"syntaxDanger"] boolValue]) {
        // Hoist syntaxDanger flag and a human-readable syntaxWarning to the root of
        // the validation dict so agents can check validation.syntaxDanger without
        // having to inspect the nested preview object.
        result[@"syntaxDanger"] = @YES;
        result[@"syntaxWarning"] = preview[@"syntaxErrors"] ?: @"Patch introduces syntax risk.";
        if (!ignoreSyntax) {
            result[@"rejectedReason"] = preview[@"syntaxErrors"] ?: @"Patch introduces syntax risk.";
            return result;
        }
    }

    result[@"ok"] = @YES;
    result[@"rejectedReason"] = @"";
    return result;
}

- (NSDictionary*)applyPatch:(NSDictionary*)params 
                      error:(NSString**)errorOut 
                  errorCode:(NSString**)errorCodeOut {
    NSString* targetPath = params[@"path"];
    NSString* patchStr = params[@"patch"];
    if (!targetPath || patchStr.length == 0) {
        if (errorCodeOut) *errorCodeOut = @"invalid_params";
        if (errorOut) *errorOut = @"path and patch parameters required.";
        return nil;
    }

    NSString* ws = [_windowBridge workspacePath];
    NSString* absPath = AbsolutePathForRPCPath(targetPath, ws);
    if (_workspaceState) {
        NSString* coherenceMsg = nil;
        if (![_workspaceState validateCoherenceForMutation:params
                                                 workspace:ws
                                              windowBridge:_windowBridge
                                                outMessage:&coherenceMsg]) {
            if (errorCodeOut) *errorCodeOut = @"coherence_mismatch";
            if (errorOut) *errorOut = coherenceMsg ?: @"Coherence token is stale.";
            return nil;
        }
    }
    NSString* idempotencyKey = params[@"idempotencyKey"];
    if (_workspaceState && idempotencyKey.length > 0) {
        NSDictionary* prior = [_workspaceState operationStatusForKey:idempotencyKey];
        if ([prior[@"status"] isEqualToString:@"expired"]) {
            if (errorCodeOut) *errorCodeOut = @"replay_expired";
            if (errorOut) *errorOut = @"Idempotency replay entry expired; re-validate before retry.";
            return nil;
        }
        if ([prior[@"status"] isEqualToString:@"completed"]) {
            return MacControlEnrichPatchApplyResult(@{
                @"patched": @YES,
                @"path": absPath,
                @"mutationReceipt": prior[@"mutationReceipt"] ?: @{},
                @"revisionBefore": prior[@"revisionBefore"] ?: @(_workspaceState.revisionId),
                @"revisionAfter": prior[@"revisionAfter"] ?: @(_workspaceState.revisionId),
                @"idempotentReplay": @YES
            });
        }
    }
    if (PathIsSymlink(absPath)) {
        if (errorCodeOut) *errorCodeOut = @"symlink_target";
        if (errorOut) *errorOut = @"Cannot apply patch through symlink path.";
        return nil;
    }
    NSString* expectBeforeHash = params[@"expectBeforeHash"];
    NSString* readSourceBefore = nil;
    NSString* beforeText = TextForSearchAtPath([_windowBridge textForFileAtPath:absPath], absPath, &readSourceBefore);
    if (!beforeText) beforeText = DietCodeReadTextFileForPatchService(absPath);
    NSString* beforeHash = StableHashForString(beforeText ?: @"");
    if (expectBeforeHash.length > 0 && ![expectBeforeHash isEqualToString:beforeHash]) {
        if (_workspaceState) {
            [_workspaceState recordRuntimeError:@"stale_content" method:@"patch.apply" envelope:@{
                @"recovery_hint": @"revalidate_patch_with_patch.validate",
                @"nextRecommendedCommand": @"patch.validate",
                @"path": targetPath ?: @"",
            }];
        }
        if (errorCodeOut) *errorCodeOut = @"stale_content";
        if (errorOut) *errorOut = @"Target file content changed since validation (expectBeforeHash mismatch).";
        return nil;
    }

    NSDictionary* validation = [self validatePatchAtPath:targetPath patch:patchStr currentText:beforeText options:params];
    if (![validation[@"ok"] boolValue]) {
        if (errorCodeOut) *errorCodeOut = @"patch_failed";
        if (errorOut) *errorOut = validation[@"rejectedReason"] ?: @"Patch validation failed.";
        return nil;
    }

    if ([validation[@"requiresConfirmation"] boolValue] && ![params[@"confirm"] boolValue]) {
        if (errorCodeOut) *errorCodeOut = @"confirmation_required";
        if (errorOut) *errorOut = @"Patch requires confirmation.";
        return nil;
    }

    NSString* validationBeforeHash = validation[@"beforeContentHash"];
    if (validationBeforeHash.length > 0 && ![validationBeforeHash isEqualToString:beforeHash]) {
        if (errorCodeOut) *errorCodeOut = @"stale_content";
        if (errorOut) *errorOut = @"Target file content drifted between validation and apply.";
        return nil;
    }
    
    NSString* errStr = nil;
    BOOL appliedViaEditor = [_windowBridge applyPatchAtPath:absPath patchString:patchStr errorOut:&errStr];
    NSString* applyChannel = @"editor";
    if (!appliedViaEditor) {
        if (!ApplyUnifiedPatchToDisk(absPath, beforeText, patchStr, &errStr)) {
            if (errorCodeOut) *errorCodeOut = @"patch_failed";
            if (errorOut) *errorOut = errStr ?: @"Unknown patch application error.";
            return nil;
        }
        applyChannel = @"disk";
    }
    
    NSString* afterText = TextForSearchAtPath([_windowBridge textForFileAtPath:absPath], absPath, nil);
    if (!afterText) afterText = DietCodeReadTextFileForPatchService(absPath);
    if (!afterText) afterText = @"";
    [_lastPatchRecords removeAllObjects];
    [_lastPatchRecords addObject:@{
        @"path": absPath,
        @"beforeText": beforeText ?: @"",
        @"beforeHash": StableHashForString(beforeText ?: @""),
        @"postHash": StableHashForString(afterText)
    }];
    
    NSString* postHash = StableHashForString(afterText);
    NSDictionary* mutationReceipt = @{
        @"path": absPath,
        @"beforeContentHash": beforeHash,
        @"postContentHash": postHash,
        @"patchFingerprint": StableHashForString(patchStr ?: @""),
        @"readSourceBefore": readSourceBefore ?: @"disk",
        @"applyChannel": applyChannel,
        @"atomic": @YES
    };
    if (_workspaceState) {
        NSInteger revisionBefore = _workspaceState.revisionId;
        [_workspaceState recordAgentMutationWithReceipt:mutationReceipt
                                           changedPaths:@[targetPath]
                                         idempotencyKey:idempotencyKey
                                         revisionBefore:revisionBefore];
        [_workspaceState trackHashesForPaths:@[targetPath] workspace:ws windowBridge:_windowBridge];
        NSString* opId = [[NSUUID UUID] UUIDString];
        NSDictionary* resultPayload = @{
            @"operationId": opId,
            @"patched": @YES,
            @"path": absPath,
            @"mutationReceipt": mutationReceipt,
            @"revisionBefore": @(revisionBefore),
            @"revisionAfter": @(_workspaceState.revisionId),
        };
        NSString* paramsHash = StableHashForString([NSString stringWithFormat:@"%@:%@", targetPath, StableHashForString(patchStr ?: @"")]);
        [_workspaceState persistMutationToMemory:@"patch.apply"
                                  idempotencyKey:idempotencyKey
                                      paramsHash:paramsHash
                                         receipt:mutationReceipt
                                    changedPaths:@[targetPath]
                                  revisionBefore:revisionBefore
                                   revisionAfter:_workspaceState.revisionId
                                   resultPayload:resultPayload];
        return MacControlEnrichPatchApplyResult(@{
            @"patched": @YES,
            @"path": absPath,
            @"validation": validation,
            @"mutationReceipt": mutationReceipt,
            @"revisionBefore": @(revisionBefore),
            @"revisionAfter": @(_workspaceState.revisionId)
        });
    }
    return MacControlEnrichPatchApplyResult(@{
        @"patched": @YES,
        @"path": absPath,
        @"validation": validation,
        @"mutationReceipt": mutationReceipt
    });
}

- (NSDictionary*)applyPatchBatch:(NSDictionary*)params 
                           error:(NSString**)errorOut 
                       errorCode:(NSString**)errorCodeOut {
    NSArray* patches = params[@"patches"];
    BOOL dryRun = params[@"dryRun"] ? [params[@"dryRun"] boolValue] : YES;
    NSString* idempotencyKey = params[@"idempotencyKey"];
    if (![patches isKindOfClass:[NSArray class]] || patches.count == 0) {
        if (errorCodeOut) *errorCodeOut = @"invalid_params";
        if (errorOut) *errorOut = @"patches array required.";
        return nil;
    }

    NSString* ws = [_windowBridge workspacePath];
    if (_workspaceState) {
        NSString* coherenceMsg = nil;
        if (![_workspaceState validateCoherenceForMutation:params
                                                 workspace:ws
                                              windowBridge:_windowBridge
                                                outMessage:&coherenceMsg]) {
            if (errorCodeOut) *errorCodeOut = @"coherence_mismatch";
            if (errorOut) *errorOut = coherenceMsg ?: @"Coherence token is stale.";
            return nil;
        }
    }

    if (_workspaceState && idempotencyKey.length > 0) {
        NSDictionary* prior = [_workspaceState operationStatusForKey:idempotencyKey];
        if ([prior[@"status"] isEqualToString:@"expired"]) {
            if (errorCodeOut) *errorCodeOut = @"replay_expired";
            if (errorOut) *errorOut = @"Idempotency replay entry expired; re-validate batch before retry.";
            return nil;
        }
        if ([prior[@"status"] isEqualToString:@"completed"]) {
            return @{
                @"dryRun": @NO,
                @"applied": @YES,
                @"results": @[],
                @"batchMutationReceipt": prior[@"batchMutationReceipt"] ?: @{},
                @"revisionBefore": prior[@"revisionBefore"] ?: @(_workspaceState.revisionId),
                @"revisionAfter": prior[@"revisionAfter"] ?: @(_workspaceState.revisionId),
                @"idempotentReplay": @YES
            };
        }
    }
    
    if (patches.count > (NSUInteger)kMaxBatchPatchCount) {
        if (errorCodeOut) *errorCodeOut = @"too_many_results";
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Batch patch count exceeds limit of %ld.", (long)kMaxBatchPatchCount];
        return nil;
    }
    
    NSUInteger combinedBytes = 0;
    NSMutableArray* results = [NSMutableArray array];
    NSMutableArray* records = [NSMutableArray array];
    BOOL needsConfirm = NO;
    
    for (NSDictionary* item in patches) {
        if (![item isKindOfClass:[NSDictionary class]]) {
            if (errorCodeOut) *errorCodeOut = @"invalid_params";
            if (errorOut) *errorOut = @"Each batch patch must be an object.";
            return nil;
        }
        NSString* relPath = item[@"path"];
        NSString* patchStr = item[@"patch"];
        NSString* expectBeforeHash = item[@"expectBeforeHash"];
        if (relPath.length == 0 || patchStr.length == 0) {
            if (errorCodeOut) *errorCodeOut = @"invalid_params";
            if (errorOut) *errorOut = @"Each batch patch requires path and patch.";
            return nil;
        }
        NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
        combinedBytes += [patchStr lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        NSString* readSourceBefore = nil;
        NSString* beforeText = TextForSearchAtPath([_windowBridge textForFileAtPath:absPath], absPath, &readSourceBefore);
        if (!beforeText) beforeText = DietCodeReadTextFileForPatchService(absPath);
        NSString* beforeHash = StableHashForString(beforeText ?: @"");
        if (expectBeforeHash.length > 0 && ![expectBeforeHash isEqualToString:beforeHash]) {
            if (errorCodeOut) *errorCodeOut = @"stale_content";
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Stale content for %@ (expectBeforeHash mismatch).", relPath];
            return nil;
        }
        NSDictionary* validation = [self validatePatchAtPath:relPath patch:patchStr currentText:beforeText options:params];
        if ([validation[@"requiresConfirmation"] boolValue]) needsConfirm = YES;
        [results addObject:@{ @"path": relPath, @"validation": validation }];
        if (![validation[@"ok"] boolValue]) {
            return @{
                @"dryRun": @(dryRun),
                @"applied": @NO,
                @"atomic": @YES,
                @"mutationAttempted": @NO,
                @"results": results
            };
        }
        [records addObject:@{
            @"relPath": relPath,
            @"path": absPath ?: @"",
            @"beforeText": beforeText ?: @"",
            @"beforeHash": beforeHash,
            @"patch": patchStr ?: @"",
            @"readSourceBefore": readSourceBefore ?: @"disk",
            @"patchFingerprint": StableHashForString(patchStr ?: @"")
        }];
    }
    
    if ((combinedBytes > kMaxPatchBytesBeforeConfirmation || needsConfirm) && ![params[@"confirm"] boolValue]) {
        if (errorCodeOut) *errorCodeOut = @"confirmation_required";
        if (errorOut) *errorOut = @"Batch patch requires confirmation.";
        return nil;
    }
    
    if (dryRun) {
        return @{
            @"dryRun": @YES,
            @"applied": @NO,
            @"atomic": @YES,
            @"mutationAttempted": @NO,
            @"results": results
        };
    }
    
    NSMutableArray* applied = [NSMutableArray array];
    NSMutableArray* fileReceipts = [NSMutableArray array];
    NSMutableArray* changedRelPaths = [NSMutableArray array];
    NSInteger revisionBefore = _workspaceState ? _workspaceState.revisionId : 0;
    for (NSDictionary* record in records) {
        NSString* errStr = nil;
        NSString* applyChannel = @"editor";
        BOOL ok = [_windowBridge applyPatchAtPath:record[@"path"] patchString:record[@"patch"] errorOut:&errStr];
        if (!ok) {
            if (!ApplyUnifiedPatchToDisk(record[@"path"], record[@"beforeText"], record[@"patch"], &errStr)) {
                NSString* restoreErr = nil;
                BOOL rolledBack = [self restorePatchRecords:applied error:&restoreErr];
                if (errorCodeOut) *errorCodeOut = @"patch_failed";
                if (errorOut) {
                    NSString* detail = rolledBack ? @"Batch patch failed; prior files rolled back." : @"Batch patch failed; rollback incomplete.";
                    *errorOut = errStr ?: restoreErr ?: detail;
                }
                return nil;
            }
            applyChannel = @"disk";
        }
        NSMutableDictionary* appliedRecord = [record mutableCopy];
        NSString* afterText = TextForSearchAtPath([_windowBridge textForFileAtPath:record[@"path"]], record[@"path"], nil);
        if (!afterText) afterText = DietCodeReadTextFileForPatchService(record[@"path"]);
        if (!afterText) afterText = @"";
        NSString* postHash = StableHashForString(afterText);
        appliedRecord[@"postHash"] = postHash;
        [applied addObject:appliedRecord];
        [changedRelPaths addObject:record[@"relPath"]];
        [fileReceipts addObject:@{
            @"path": record[@"path"],
            @"beforeContentHash": record[@"beforeHash"],
            @"postContentHash": postHash,
            @"patchFingerprint": record[@"patchFingerprint"],
            @"readSourceBefore": record[@"readSourceBefore"],
            @"applyChannel": applyChannel,
            @"atomic": @YES
        }];
    }
    
    [_lastPatchRecords removeAllObjects];
    [_lastPatchRecords addObjectsFromArray:applied];

    NSDictionary* batchReceipt = @{
        @"atomic": @YES,
        @"appliedCount": @(applied.count),
        @"rolledBack": @NO,
        @"fileReceipts": fileReceipts,
        @"rollbackProof": @{ @"verified": @YES, @"restoredFileCount": @0 }
    };
    if (_workspaceState) {
        [_workspaceState recordBatchMutationWithReceipt:batchReceipt
                                          changedPaths:changedRelPaths
                                        idempotencyKey:idempotencyKey
                                        revisionBefore:revisionBefore];
        [_workspaceState trackHashesForPaths:changedRelPaths workspace:ws windowBridge:_windowBridge];
        NSDictionary* batchResultPayload = @{
            @"applied": @YES,
            @"batchMutationReceipt": batchReceipt,
            @"revisionBefore": @(revisionBefore),
            @"revisionAfter": @(_workspaceState.revisionId),
        };
        NSString* batchParamsHash = StableHashForString([NSString stringWithFormat:@"batch:%lu", (unsigned long)patches.count]);
        [_workspaceState persistMutationToMemory:@"patch.applyBatch"
                                  idempotencyKey:idempotencyKey
                                      paramsHash:batchParamsHash
                                         receipt:batchReceipt
                                    changedPaths:changedRelPaths
                                  revisionBefore:revisionBefore
                                   revisionAfter:_workspaceState.revisionId
                                   resultPayload:batchResultPayload];
    }

    NSMutableDictionary* response = [@{
        @"dryRun": @NO,
        @"applied": @YES,
        @"atomic": @YES,
        @"mutationAttempted": @YES,
        @"partialApply": @NO,
        @"rolledBack": @NO,
        @"results": results,
        @"batchMutationReceipt": batchReceipt
    } mutableCopy];
    if (_workspaceState) {
        response[@"revisionBefore"] = @(revisionBefore);
        response[@"revisionAfter"] = @(_workspaceState.revisionId);
    }
    return response;
}

- (NSDictionary*)revertLastPatchWithError:(NSString**)errorOut 
                                errorCode:(NSString**)errorCodeOut {
    if (_lastPatchRecords.count == 0) {
        if (errorCodeOut) *errorCodeOut = @"invalid_request";
        if (errorOut) *errorOut = @"No RPC patch available to revert.";
        return nil;
    }
    
    NSString* errStr = nil;
    BOOL ok = [self restorePatchRecords:_lastPatchRecords error:&errStr];
    if (!ok) {
        if (errorCodeOut) *errorCodeOut = [errStr hasPrefix:@"Rollback conflict"] ? @"rollback_conflict" : @"rollback_failed";
        if (errorOut) *errorOut = errStr ?: @"Failed to revert last RPC patch.";
        return nil;
    }
    
    NSMutableArray* paths = [NSMutableArray array];
    for (NSDictionary* record in _lastPatchRecords) {
        [paths addObject:record[@"path"] ?: @""];
    }
    [_lastPatchRecords removeAllObjects];
    
    return @{ @"reverted": @YES, @"files": paths };
}

- (void)recordMutationRecords:(NSArray<NSDictionary*>*)records {
    [_lastPatchRecords removeAllObjects];
    [_lastPatchRecords addObjectsFromArray:records ?: @[]];
}

- (BOOL)restorePatchRecords:(NSArray<NSDictionary*>*)records error:(NSString**)errorOut {
    NSString* ws = [_windowBridge workspacePath];
    if (ws.length == 0) {
        if (errorOut) *errorOut = @"No active workspace.";
        return NO;
    }
    
    // First pass: validation
    for (NSDictionary* record in records.reverseObjectEnumerator) {
        NSString* path = record[@"path"];
        NSString* beforeText = record[@"beforeText"];
        NSString* expectedPostHash = record[@"postHash"];
        NSString* beforeHash = record[@"beforeHash"];
        BOOL existedBefore = record[@"existed"] ? [record[@"existed"] boolValue] : YES;
        
        if (!path || beforeText == nil) {
            if (errorOut) *errorOut = @"Cannot restore patch because a target buffer record is invalid.";
            return NO;
        }
        
        NSString* absPath = AbsolutePathForRPCPath(path, ws);
        if (!PathIsInsideWorkspace(absPath, ws)) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Target path escapes workspace: %@", path];
            return NO;
        }
        
        NSString* currentText = [_windowBridge textForFileAtPath:absPath];
        if (currentText == nil && existedBefore) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Cannot restore patch because target buffer is unavailable: %@", path];
            return NO;
        }
        
        if (currentText != nil && IsTextBinary(currentText)) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"File is binary: %@", path];
            return NO;
        }
        
        if (currentText != nil && expectedPostHash.length > 0 && ![StableHashForString(currentText) isEqualToString:expectedPostHash]) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Rollback conflict for %@: current buffer no longer matches the expected postimage.", path];
            return NO;
        }
        
        if (beforeHash.length > 0 && ![StableHashForString(beforeText) isEqualToString:beforeHash]) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Preimage hash mismatch for %@", path];
            return NO;
        }
    }
    
    // Second pass: apply
    for (NSDictionary* record in records.reverseObjectEnumerator) {
        NSString* path = record[@"path"];
        NSString* beforeText = record[@"beforeText"];
        NSString* absPath = AbsolutePathForRPCPath(path, ws);
        BOOL existedBefore = record[@"existed"] ? [record[@"existed"] boolValue] : YES;
        if (!existedBefore) {
            NSError* deleteErr = nil;
            if ([[NSFileManager defaultManager] fileExistsAtPath:absPath] &&
                ![[NSFileManager defaultManager] removeItemAtPath:absPath error:&deleteErr]) {
                if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to remove created file %@: %@", path, deleteErr.localizedDescription];
                return NO;
            }
            continue;
        }
        NSString* currentText = [_windowBridge textForFileAtPath:absPath];
        BOOL ok = currentText != nil && [_windowBridge replaceTextInRange:NSMakeRange(0, currentText.length) withText:beforeText forFileAtPath:absPath];
        NSError* writeErr = nil;
        BOOL writeOk = [beforeText writeToFile:absPath atomically:YES encoding:NSUTF8StringEncoding error:&writeErr];
        if (!ok && !writeOk) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Failed to restore %@", path];
            return NO;
        }
    }
    return YES;
}

@end
