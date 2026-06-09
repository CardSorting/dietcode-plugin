#import "MacControlServer+Private.hpp"
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#else
#import "DietCodeWindowController+ControlHost.h"
#endif
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "WorkspaceAnalysisService.hpp"
#import "SymbolIndexService.hpp"

#include <sys/utsname.h>

static NSString* DietCodeMachineArchitecture(void) {
    struct utsname systemInfo;
    if (uname(&systemInfo) == 0) {
        return [NSString stringWithUTF8String:systemInfo.machine] ?: @"unknown";
    }
    return @"unknown";
}

static NSArray* BuildSymbolHierarchy(NSArray* flatSymbols) {
    if (flatSymbols.count == 0) return @[];
    
    // Sort symbols by range (start offset ascending, then end offset descending)
    NSArray* sorted = [flatSymbols sortedArrayUsingComparator:^NSComparisonResult(NSDictionary* a, NSDictionary* b) {
        NSInteger aStart = [a[@"offset"] integerValue];
        NSInteger bStart = [b[@"offset"] integerValue];
        if (aStart < bStart) return NSOrderedAscending;
        if (aStart > bStart) return NSOrderedDescending;
        
        NSInteger aEnd = [a[@"endOffset"] integerValue];
        NSInteger bEnd = [b[@"endOffset"] integerValue];
        if (aEnd > bEnd) return NSOrderedAscending; // Larger range first
        if (aEnd < bEnd) return NSOrderedDescending;
        return NSOrderedSame;
    }];
    
    NSMutableArray* roots = [NSMutableArray array];
    NSMutableArray* stack = [NSMutableArray array];
    
    for (NSDictionary* symbol in sorted) {
        NSMutableDictionary* node = [symbol mutableCopy];
        node[@"children"] = [NSMutableArray array];
        
        NSInteger start = [node[@"offset"] integerValue];
        
        while (stack.count > 0) {
            NSDictionary* parent = stack.lastObject;
            NSInteger pEnd = [parent[@"endOffset"] integerValue];
            if (start < pEnd) {
                // node is a child of parent
                [parent[@"children"] addObject:node];
                break;
            } else {
                [stack removeLastObject];
            }
        }
        
        if (stack.count == 0) {
            [roots addObject:node];
        }
        [stack addObject:node];
    }
    
    return roots;
}

@implementation DietCodeControlServer (Context)

- (void)handleTerminalOutputUpdate:(NSNotification*)notification {
    NSString* text = notification.userInfo[@"text"];
    if (text.length > 0) {
        [self notifyEvent:@"terminal.output" detail:text];
    }
}

- (void)executeContextMethod:(NSString*)method 
                      params:(NSDictionary*)params 
                   outResult:(NSDictionary**)outResult 
                  outErrCode:(NSString**)outErrCode 
                 outErrMsg:(NSString**)outErrMsg
                    outPaths:(NSString**)outPaths {
    
    // Combo commands
    if ([method isEqualToString:@"combo.validate"]) {
        NSDictionary* plan = params[@"combo"] ?: params;
        NSDictionary* normalizedPlan = nil;
        NSArray* errors = nil;
        BOOL ok = [_comboRuntime validateCombo:plan normalizedPlan:&normalizedPlan errors:&errors];
        *outResult = @{
            @"ok": @(ok),
            @"errors": errors ?: @[],
            @"plan": normalizedPlan ?: @{}
        };
        return;
    }

    if ([method isEqualToString:@"combo.run"]) {
        NSDictionary* comboReq = params[@"combo"] ?: params;
        NSString* comboId = comboReq[@"comboId"] ?: [NSString stringWithFormat:@"combo-%ld", (long)++_comboCounter];
        
        NSDictionary* plan = nil;
        NSArray* errors = nil;
        if (![_comboRuntime validateCombo:comboReq normalizedPlan:&plan errors:&errors]) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"Combo validation failed.";
            *outResult = @{ @"errors": errors ?: @[] };
            return;
        }

        if ([_comboRuntime activeComboCount] >= (NSUInteger)kMaxActiveCombos) {
            *outErrCode = @"resource_exhausted";
            *outErrMsg = @"Maximum number of active combos reached.";
            return;
        }

        *outResult = [_comboRuntime runComboWithPlan:plan comboId:comboId sessionToken:_sessionToken];
        return;
    }

    if ([method isEqualToString:@"combo.status"] || [method isEqualToString:@"combo.result"]) {
        NSString* comboId = params[@"comboId"];
        if (comboId.length == 0) {
            comboId = _comboRuntime.lastComboId;
        }
        NSDictionary* combo = comboId ? _comboRuntime.combos[comboId] : nil;
        if (!combo) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Unknown comboId.";
            return;
        }
        *outResult = combo;
        return;
    }

    if ([method isEqualToString:@"combo.list"]) {
        NSMutableArray* list = [NSMutableArray array];
        for (NSDictionary* c in [_comboRuntime.combos allValues]) {
            [list addObject:[_comboRuntime serializableCombo:[c mutableCopy]]];
        }
        *outResult = @{ @"combos": list };
        return;
    }

    if ([method isEqualToString:@"combo.cancel"]) {
        NSString* comboId = params[@"comboId"];
        if (comboId.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"comboId parameter required.";
            return;
        }
        NSString* cancelErr = nil;
        BOOL ok = [_comboRuntime cancelComboWithId:comboId error:&cancelErr];
        if (!ok) {
            *outErrCode = @"invalid_request";
            *outErrMsg = cancelErr ?: @"Failed to cancel combo.";
            return;
        }
        *outResult = @{ @"cancelled": @YES, @"comboId": comboId };
        return;
    }

    if ([method isEqualToString:@"combo.rollback"]) {
        NSString* comboId = params[@"comboId"];
        BOOL confirm = [params[@"confirm"] boolValue];
        
        if (comboId.length == 0) {
            comboId = _comboRuntime.lastComboId;
        }
        
        if (comboId.length == 0) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No session combo transaction is available to roll back.";
            return;
        }
        
        NSString* backupDir = [[NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"] stringByAppendingPathComponent:comboId];
        NSString* manifestPath = [backupDir stringByAppendingPathComponent:@"manifest.json"];
        
        NSString* mErr = nil;
        NSDictionary* manifest = [_recoveryStore loadManifestFromPath:manifestPath error:&mErr];
        if (!manifest) {
            if ([mErr isEqualToString:@"Manifest file missing."]) {
                *outErrCode = @"backup_manifest_missing";
            } else if ([mErr isEqualToString:@"manifest.sha256 file missing."] || [mErr isEqualToString:@"Manifest checksum verification failed."]) {
                *outErrCode = @"backup_corrupt";
            } else {
                *outErrCode = @"backup_manifest_invalid";
            }
            *outErrMsg = mErr ?: @"Manifest missing or invalid.";
            return;
        }
        
        NSString* schemaVersion = manifest[@"schemaVersion"] ?: @"1.6.1";
        if (![schemaVersion isEqualToString:@"1.6.2"]) {
            *outErrCode = @"backup_manifest_invalid";
            *outErrMsg = [NSString stringWithFormat:@"Unsupported schema version '%@'. Rollback is only supported for schema version 1.6.2.", schemaVersion];
            return;
        }
        
        NSString* rollbackErr = nil;
        NSString* rollbackErrorCode = nil;
        BOOL ok = [_recoveryStore restorePatchFromManifest:manifest backupDir:backupDir confirm:confirm sessionToken:_sessionToken error:&rollbackErr errorCode:&rollbackErrorCode];
        if (!ok) {
            *outErrCode = rollbackErrorCode ?: @"rollback_failed";
            *outErrMsg = rollbackErr ?: @"Rollback failed.";
            return;
        }
        
        NSMutableArray* pathsArr = [NSMutableArray array];
        for (NSDictionary* fileEntry in manifest[@"files"] ?: @[]) {
            [pathsArr addObject:fileEntry[@"workspaceRelativePath"] ?: @""];
        }
        *outResult = @{ @"schemaVersion": @"1.6.2", @"reverted": @YES, @"files": pathsArr };
        return;
    }
    
    // Recovery commands
    if ([method isEqualToString:@"recovery.scan"]) {
        NSString* errStr = nil;
        NSDictionary* report = [_recoveryStore performRecoveryScan:&errStr];
        if (errStr) {
            *outErrCode = @"internal_error";
            *outErrMsg = errStr;
            return;
        }
        *outResult = report;
        return;
    }

    if ([method isEqualToString:@"recovery.schemaInfo"]) {
        *outResult = @{
            @"transactionSchemaVersion": @"1.6.2",
            @"supportedRollbackSchemas": @[@"1.6.2"],
            @"supportedInspectOnlySchemas": @[@"1.6.1"]
        };
        return;
    }

    if ([method isEqualToString:@"recovery.list"]) {
        NSString* errStr = nil;
        NSArray* backups = [_recoveryStore listBackupsQuickWithActiveCombos:_comboRuntime.combos error:&errStr];
        if (errStr) {
            *outErrCode = @"internal_error";
            *outErrMsg = errStr;
            return;
        }
        *outResult = @{ @"backups": backups };
        return;
    }

    if ([method isEqualToString:@"recovery.deleteBackup"]) {
        NSString* comboId = params[@"comboId"];
        if (!comboId) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"comboId parameter required.";
            return;
        }
        BOOL confirm = [params[@"confirm"] boolValue];
        NSString* errStr = nil;
        NSString* errCodeVal = nil;
        if (![_recoveryStore deleteBackupWithId:comboId confirm:confirm activeCombos:_comboRuntime.combos error:&errStr errorCode:&errCodeVal]) {
            *outErrCode = errCodeVal ?: @"delete_failed";
            *outErrMsg = errStr ?: @"Failed to delete backup.";
            return;
        }
        *outResult = @{ @"deleted": @YES, @"comboId": comboId };
        
        // Audit log the deletion
        NSString* backupDir = [[NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/backups"] stringByAppendingPathComponent:comboId];
        [self logAuditMethod:@"recovery.deleteBackup" caller:@"unix_socket" permission:@"Edit" duration:0 result:@"success" paths:[NSString stringWithFormat:@"deleted comboId: %@ | path: %@", comboId, backupDir]];
        return;
    }

    if ([method isEqualToString:@"recovery.prune"]) {
        NSNumber* keepLastN = params[@"keepLastN"];
        NSNumber* olderThanDays = params[@"olderThanDays"];
        if (!params[@"dryRun"]) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"dryRun parameter required.";
            return;
        }
        BOOL dryRun = [params[@"dryRun"] boolValue];
        BOOL confirmInvalid = [params[@"confirmInvalid"] boolValue];
        
        NSString* errStr = nil;
        NSDictionary* pruneReport = [_recoveryStore pruneBackupsWithKeepLastN:keepLastN olderThanDays:olderThanDays dryRun:dryRun confirmInvalid:confirmInvalid activeCombos:_comboRuntime.combos error:&errStr];
        if (errStr) {
            *outErrCode = @"internal_error";
            *outErrMsg = errStr;
            return;
        }
        *outResult = pruneReport;
        return;
    }

    // Diagnostics commands
    if ([method isEqualToString:@"diagnostics.list"]) {
        NSArray* problems = [self safeProblemsList] ?: @[];
        *outResult = @{ @"diagnostics": problems };
        return;
    }

    if ([method isEqualToString:@"diagnostics.summary"]) {
        NSArray* problems = [self safeProblemsList] ?: @[];
        *outResult = DiagnosticsSummaryFromProblems(problems);
        return;
    }

    if ([method isEqualToString:@"diagnostics.cluster"]) {
        NSArray* problems = [self safeProblemsList] ?: @[];
        *outResult = @{ @"clusters": ClusterDiagnostics(problems) };
        return;
    }

    if ([method isEqualToString:@"diagnostics.forFile"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter or active file required.";
            return;
        }
        NSMutableArray* matches = [NSMutableArray array];
        for (NSDictionary* problem in [self safeProblemsList] ?: @[]) {
            NSString* problemPath = AbsolutePathForRPCPath(problem[@"path"], ws);
            if ([problemPath isEqualToString:targetPath]) {
                [matches addObject:problem];
            }
        }
        *outResult = @{ @"path": targetPath, @"diagnostics": matches };
        return;
    }

    // Analysis commands
    if ([method isEqualToString:@"analysis.workspaceSummary"]) {
        NSString* ws = [self safeWorkspacePath];
        if (!ws) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }

        NSDictionary* git = [self safeGitStatusInfo] ?: @{};
        NSMutableArray* modified = [NSMutableArray arrayWithArray:DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[])];
        for (NSString* key in @[@"modified", @"staged", @"untracked"]) {
            for (NSString* rel in git[key] ?: @[]) {
                NSString* abs = AbsolutePathForRPCPath(rel, ws);
                if (![modified containsObject:abs]) {
                    [modified addObject:abs];
                }
            }
        }

        NSArray* problems = [self safeProblemsList] ?: @[];
        *outResult = [DietCodeWorkspaceAnalysisService summaryOfWorkspace:ws
                                                                 openFiles:[self safeOpenFilePaths]
                                                             modifiedFiles:modified
                                                               diagnostics:DiagnosticsSummaryFromProblems(problems)
                                                                 gitBranch:git[@"branch"]];
        return;
    }

    if ([method isEqualToString:@"analysis.searchRanked"]) {
        if (![params[@"allowExperimental"] boolValue]) {
            *outErrCode = @"ranked_search_disabled";
            *outErrMsg = @"analysis.searchRanked is quarantined in deterministic agent mode. Use search.literal, workspace.grep, or search.tokens.";
            return;
        }
        NSString* ws = [self safeWorkspacePath];
        NSString* query = params[@"query"];
        if (!ws || query.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Query string and workspace required.";
            return;
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            [self.workspaceSession appendRecentSearch:query];
        });

        NSInteger requestedMax = params[@"maxResults"] ? [params[@"maxResults"] integerValue] : kMaxGrepResults;
        if (requestedMax <= 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"maxResults must be greater than zero.";
            return;
        }
        if (requestedMax > kMaxGrepResults) {
            *outErrCode = @"response_too_large";
            *outErrMsg = [NSString stringWithFormat:@"maxResults exceeds limit of %ld.", (long)kMaxGrepResults];
            return;
        }
        NSArray* ranked = [DietCodeWorkspaceAnalysisService searchRankedForQuery:query
                                                                       workspace:ws
                                                                       openFiles:[self safeOpenFilePaths]
                                                                     recentFiles:[[NSUserDefaults standardUserDefaults] stringArrayForKey:@"RecentFiles"] ?: @[]
                                                                         include:params[@"include"] ?: @[]
                                                                         exclude:params[@"exclude"] ?: @[]
                                                                   caseSensitive:[params[@"caseSensitive"] boolValue]];
        NSInteger maxResults = MIN(requestedMax, (NSInteger)ranked.count);
        if (maxResults >= 0 && maxResults < (NSInteger)ranked.count) {
            ranked = [ranked subarrayWithRange:NSMakeRange(0, (NSUInteger)maxResults)];
        }
        *outResult = @{ @"results": ranked };
        return;
    }

    if ([method isEqualToString:@"analysis.fileSummary"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter or active file required.";
            return;
        }
        NSString* text = [self safeTextForFileAtPath:targetPath] ?: @"";
        NSArray* symbols = [DietCodeSymbolIndexService symbolsForFileContent:text extension:[[targetPath pathExtension] lowercaseString]];
        *outResult = [DietCodeWorkspaceAnalysisService fileSummaryForPath:targetPath symbolsCount:symbols.count];
        return;
    }

    if ([method isEqualToString:@"analysis.relatedFiles"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        if (!ws || !targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Workspace and path required.";
            return;
        }
        *outResult = @{ @"files": [DietCodeWorkspaceAnalysisService relatedFilesForPath:targetPath workspace:ws] };
        return;
    }

    // Symbol commands
    if ([method isEqualToString:@"symbols.document"] || [method isEqualToString:@"symbols.outline"] || [method isEqualToString:@"symbols.hierarchy"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter or active file required.";
            return;
        }
        NSString* text = [self safeTextForFileAtPath:targetPath];
        if (!text) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"File is not readable.";
            return;
        }
        NSArray* flat = [DietCodeSymbolIndexService symbolsForFileContent:text extension:[[targetPath pathExtension] lowercaseString]];
        if ([method isEqualToString:@"symbols.hierarchy"]) {
            *outResult = @{
                @"path": targetPath,
                @"symbols": BuildSymbolHierarchy(flat)
            };
        } else {
            *outResult = @{
                @"path": targetPath,
                @"symbols": flat
            };
        }
        return;
    }

    if ([method isEqualToString:@"symbols.activeDocument"]) {
        NSString* targetPath = [self safeActiveFilePath];
        NSString* text = targetPath ? [self safeTextForFileAtPath:targetPath] : nil;
        if (!targetPath || !text) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No active readable file.";
            return;
        }
        *outResult = @{
            @"path": targetPath,
            @"symbols": [DietCodeSymbolIndexService symbolsForFileContent:text extension:[[targetPath pathExtension] lowercaseString]]
        };
        return;
    }

    if ([method isEqualToString:@"symbols.references"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* symbol = params[@"symbol"];
        if (!ws || symbol.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"symbol and workspace required.";
            return;
        }
        NSArray* problems = [self safeProblemsList] ?: @[];
        NSMutableArray* diagFiles = [NSMutableArray array];
        for (NSDictionary* problem in problems) {
            NSString* abs = AbsolutePathForRPCPath(problem[@"path"], ws);
            if (abs.length > 0 && ![diagFiles containsObject:abs]) {
                [diagFiles addObject:abs];
            }
        }
        *outResult = @{
            @"symbol": symbol,
            @"references": [DietCodeSymbolIndexService referencesForSymbol:symbol
                                                                inWorkspace:ws
                                                                  openFiles:[self safeOpenFilePaths]
                                                           diagnosticsFiles:diagFiles]
        };
        return;
    }

    if ([method isEqualToString:@"symbols.atCursor"]) {
        NSDictionary* sel = [self safeActiveSelectionInfo];
        NSString* targetPath = [self safeActiveFilePath];
        NSString* text = targetPath ? [self safeTextForFileAtPath:targetPath] : nil;
        if (!targetPath || !text) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No active readable file.";
            return;
        }
        NSInteger cursor = [sel[@"start"] integerValue];
        NSArray* symbols = [DietCodeSymbolIndexService symbolsForFileContent:text extension:[[targetPath pathExtension] lowercaseString]];
        __block NSDictionary* match = @{};
        NSInteger currentLine = 1;
        NSUInteger boundedCursor = MIN((NSUInteger)MAX(cursor, 0), text.length);
        for (NSUInteger i = 0; i < boundedCursor; i++) {
            if ([text characterAtIndex:i] == '\n') currentLine++;
        }
        for (NSDictionary* symbolInfo in symbols) {
            NSInteger startLine = [symbolInfo[@"line"] integerValue];
            NSInteger endLine = [symbolInfo[@"endLine"] integerValue];
            if (currentLine >= startLine && currentLine <= endLine) {
                match = symbolInfo;
                break;
            }
        }
        *outResult = @{ @"path": targetPath, @"symbol": match };
        return;
    }

    // Session workflow commands
    if ([method isEqualToString:@"session.info"] || [method isEqualToString:@"session.workflowState"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* activeFile = [self safeActiveFilePath];
        NSArray* openFiles = [self safeOpenFilePaths];
        NSArray* dirtyFiles = DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[]);
        NSArray* recentCmds = [self safeSessionRecentCommands];
        NSArray* lastSearches = [self safeSessionLastSearches];
        pid_t termPid = [self safeTerminalPid];
        
        NSDictionary* git = [self safeGitStatusInfo] ?: @{};
        *outResult = @{
            @"workspace": ws ?: @"",
            @"activeFile": activeFile ?: @"",
            @"openFiles": openFiles ?: @[],
            @"dirtyFiles": dirtyFiles ?: @[],
            @"gitBranch": git[@"branch"] ?: @"",
            @"recentCommands": recentCmds ?: @[],
            @"lastSearches": lastSearches ?: @[],
            @"terminalPid": @(termPid)
        };
        return;
    }

    if ([method isEqualToString:@"session.recentCommands"]) {
        NSArray* recentCmds = [self safeSessionRecentCommands];
        *outResult = @{ @"commands": recentCmds ?: @[] };
        return;
    }

    if ([method isEqualToString:@"session.lastSearches"]) {
        NSArray* lastSearches = [self safeSessionLastSearches];
        *outResult = @{ @"searches": lastSearches ?: @[] };
        return;
    }

    if ([method isEqualToString:@"session.clearHistory"]) {
        [self.workspaceSession clearSessionHistory];
        *outResult = @{ @"cleared": @YES };
        return;
    }

    if ([method isEqualToString:@"system.info"]) {
        NSProcessInfo* info = [NSProcessInfo processInfo];
        *outResult = @{
            @"os": info.operatingSystemVersionString,
            @"arch": DietCodeMachineArchitecture(),
            @"memoryGB": @(info.physicalMemory / (1024 * 1024 * 1024.0)),
            @"cpuCount": @(info.processorCount),
            @"appVersion": kDietCodeAppVersion,
            @"isAgentMode": @YES
        };
        return;
    }

    // Language features commands
    if ([method isEqualToString:@"language.hover"] || [method isEqualToString:@"language.completions"] || [method isEqualToString:@"language.definition"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter or active file required.";
            return;
        }
        NSInteger line = [params[@"line"] integerValue];
        NSInteger column = [params[@"column"] integerValue];
        if (line <= 0 || column <= 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"line and column must be positive 1-indexed integers.";
            return;
        }
        if (self.isKernelMode || !self.windowController || self.windowController.isHeadless || ![[self.windowController window] isVisible]) {
            if ([method isEqualToString:@"language.hover"]) {
                *outResult = @{ @"hover": @"", @"headless": @YES };
            } else if ([method isEqualToString:@"language.completions"]) {
                *outResult = @{ @"completions": @[], @"headless": @YES };
            } else {
                *outResult = @{ @"location": [NSNull null], @"heuristic": @YES, @"headless": @YES };
            }
            return;
        }

        if ([method isEqualToString:@"language.hover"]) {
            NSString* hover = [_windowBridge hoverAtLocation:targetPath line:line column:column];
            *outResult = @{ @"hover": hover ?: @"" };
        } else if ([method isEqualToString:@"language.completions"]) {
            NSArray* completions = [_windowBridge completionsAtLocation:targetPath line:line column:column];
            *outResult = @{ @"completions": completions ?: @[] };
        } else if ([method isEqualToString:@"language.definition"]) {
            NSDictionary* def = [_windowBridge definitionAtLocation:targetPath line:line column:column];
            if (def) {
                *outResult = @{ @"location": def };
            } else {
                *outResult = @{ @"location": [NSNull null], @"heuristic": @YES };
            }
        }
        return;
    }

    // Context primitives
    if ([method isEqualToString:@"context.snapshot"]) {
        NSDictionary* snapshot = [self contextSnapshotPayload];
        NSString* snapshotId = [NSString stringWithFormat:@"snapshot-%ld", (long)++_contextSnapshotCounter];
        _contextSnapshots[snapshotId] = snapshot;
        *outResult = @{ @"snapshotId": snapshotId, @"snapshot": snapshot };
        return;
    }

    if ([method isEqualToString:@"context.delta"]) {
        NSString* snapshotId = params[@"snapshotId"];
        NSDictionary* previous = snapshotId ? _contextSnapshots[snapshotId] : nil;
        if (!previous) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Unknown snapshotId.";
            return;
        }
        NSDictionary* current = [self contextSnapshotPayload];
        NSMutableDictionary* changed = [NSMutableDictionary dictionary];
        for (NSString* key in current) {
            id oldValue = previous[key];
            id newValue = current[key];
            if (![oldValue isEqual:newValue]) {
                changed[key] = @{ @"before": oldValue ?: [NSNull null], @"after": newValue ?: [NSNull null] };
            }
        }
        *outResult = @{ @"snapshotId": snapshotId, @"changed": changed, @"current": current };
        return;
    }

    // Bounded combo primitives
    if ([method isEqualToString:@"task.start"]) {
        *outResult = [_taskRuntime startTask:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"task.status"] || [method isEqualToString:@"task.result"]) {
        *outResult = [_taskRuntime taskStatus:params result:[method isEqualToString:@"task.result"] outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"task.cancel"]) {
        *outResult = [_taskRuntime cancelTask:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"task.step"]) {
        *outResult = [_taskRuntime taskStep:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"task.runLoop"]) {
        *outResult = [_taskRuntime taskRunLoop:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"edit.plan"]) {
        *outResult = [_taskRuntime editPlan:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"edit.executePlan"]) {
        *outResult = [_taskRuntime editExecutePlan:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"repair.fromCompilerErrors"] ||
        [method isEqualToString:@"repair.fromTestFailures"] ||
        [method isEqualToString:@"repair.fromPatchFailure"]) {
        NSString* failure = @"patch";
        if ([method isEqualToString:@"repair.fromCompilerErrors"]) failure = @"compiler";
        else if ([method isEqualToString:@"repair.fromTestFailures"]) failure = @"test";
        *outResult = [self repairContextForFailure:failure params:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    // Problems commands
    if ([method isEqualToString:@"problems.list"]) {
        NSArray* problems = [self safeProblemsList] ?: @[];
        *outResult = @{ @"problems": problems };
        return;
    }
    
    if ([method isEqualToString:@"problems.open"]) {
        NSString* problemId = params[@"id"];
        if (!problemId) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"id parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"opened": @YES, @"headless": @YES };
            return;
        }
        [(id)self.windowController problemsOpen:problemId];
        *outResult = @{ @"opened": @YES };
        return;
    }
    
    if ([method isEqualToString:@"problems.clearSource"]) {
        NSString* source = params[@"source"];
        if (!source) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"source parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"cleared": @YES, @"headless": @YES };
            return;
        }
        [(id)self.windowController problemsClearSource:source];
        *outResult = @{ @"cleared": @YES };
        return;
    }
    
    // Language features commands
    if ([method isEqualToString:@"language.diagnostics"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        NSArray* diags = [self safeLanguageDiagnosticsForPath:targetPath] ?: @[];
        *outResult = @{ @"diagnostics": diags };
        return;
    }
    
    if ([method isEqualToString:@"language.format"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"formatted": @YES, @"headless": @YES };
            return;
        }
        [(id)self.windowController formatFileAtPath:targetPath];
        *outResult = @{ @"formatted": @YES };
        return;
    }
    
    if ([method isEqualToString:@"language.lint"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"linted": @YES, @"headless": @YES };
            return;
        }
        [(id)self.windowController lintFileAtPath:targetPath];
        *outResult = @{ @"linted": @YES };
        return;
    }
    
    if ([method isEqualToString:@"language.gotoDefinition"]) {
        NSDictionary* sel = [self safeActiveSelectionInfo] ?: @{};
        NSString* targetPath = [self safeActiveFilePath];
        NSString* text = targetPath ? [self safeTextForFileAtPath:targetPath] : nil;
        if (!targetPath || !text) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No active readable editor tab.";
            return;
        }
        NSString* symbol = params[@"symbol"];
        if (symbol.length == 0) {
            symbol = WordAtOffset(text, [sel[@"start"] integerValue]);
        }
        if (symbol.length == 0) {
            *outResult = @{ @"found": @NO, @"symbol": @"", @"definition": @{}, @"candidates": @[] };
            return;
        }
        NSString* ws = [self safeWorkspacePath];
        NSArray* problems = [self safeProblemsList] ?: @[];
        NSMutableArray* diagFiles = [NSMutableArray array];
        for (NSDictionary* problem in problems) {
            NSString* abs = AbsolutePathForRPCPath(problem[@"path"], ws);
            if (abs.length > 0 && ![diagFiles containsObject:abs]) {
                [diagFiles addObject:abs];
            }
        }
        NSArray* references = [DietCodeSymbolIndexService referencesForSymbol:symbol
                                                                   inWorkspace:ws
                                                                     openFiles:[self safeOpenFilePaths]
                                                              diagnosticsFiles:diagFiles];
        NSDictionary* best = @{};
        for (NSDictionary* candidate in references) {
            NSString* preview = [candidate[@"preview"] lowercaseString] ?: @"";
            NSString* lowerSymbol = [symbol lowercaseString];
            if ([preview containsString:[NSString stringWithFormat:@"def %@", lowerSymbol]] ||
                [preview containsString:[NSString stringWithFormat:@"class %@", lowerSymbol]] ||
                [preview containsString:[NSString stringWithFormat:@"function %@", lowerSymbol]] ||
                [preview containsString:[NSString stringWithFormat:@"%@(", lowerSymbol]]) {
                best = candidate;
                break;
            }
        }
        if (best.count == 0 && references.count > 0) {
            best = references[0];
        }
        *outResult = @{ @"found": @(best.count > 0), @"symbol": symbol, @"definition": best, @"candidates": references };
        return;
    }
}

@end
