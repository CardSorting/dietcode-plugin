#import "MacControlServer+Private.hpp"
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#else
#import "DietCodeWindowController+ControlHost.h"
#endif
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "filesystem/PathUtils.hpp"

#include <filesystem>
#include <vector>
#include <string>

static const NSInteger kMaxReadAroundContextLines = 500;
static const NSInteger kMaxBatchFilePaths = 100;

static void AttachCoherenceToResult(NSMutableDictionary* result,
                                    NSDictionary* params,
                                    NSArray<NSString*>* paths,
                                    MacControlWorkspaceState* workspaceState,
                                    NSString* workspacePath,
                                    DietCodeControlWindowBridge* windowBridge) {
    NSString* taskId = params[@"taskId"];
    if (![taskId isKindOfClass:[NSString class]] || taskId.length == 0) return;
    NSDictionary* coherence = [workspaceState issueCoherenceForTask:taskId
                                                              paths:paths
                                                          workspace:workspacePath
                                                       windowBridge:windowBridge];
    if (coherence) result[@"coherence"] = coherence;
}

@implementation DietCodeControlServer (File)

- (void)executeFileMethod:(NSString*)method 
                   params:(NSDictionary*)params 
                outResult:(NSDictionary**)outResult 
               outErrCode:(NSString**)outErrCode 
              outErrMsg:(NSString**)outErrMsg
                 outPaths:(NSString**)outPaths {
    
    if ([method isEqualToString:@"workspace.openFolder"]) {
        NSString* targetPath = params[@"path"];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        BOOL isDir = NO;
        if (![[NSFileManager defaultManager] fileExistsAtPath:targetPath isDirectory:&isDir] || !isDir) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Target path is not a valid directory.";
            return;
        }
        [self.workspaceSession setWorkspaceRoot:targetPath];
        if (self.windowController) {
            [self.windowController openWorkspaceFolder:targetPath];
        }
        *outResult = @{ @"opened": @YES, @"path": targetPath, @"headless": @(self.isKernelMode) };
        return;
    }
    
    if ([method isEqualToString:@"workspace.getRoot"]) {
        NSString* root = [self safeWorkspacePath] ?: @"";
        *outResult = @{ @"path": root };
        return;
    }

    if ([method isEqualToString:@"workspace.revision"]) {
        *outResult = [_workspaceState revisionPayloadWithWorkspace:[self safeWorkspacePath] ?: @""];
        return;
    }

    if ([method isEqualToString:@"workspace.snapshot"]) {
        *outResult = MacControlEnrichSnapshotResult([_workspaceState snapshotPayloadWithWorkspace:[self safeWorkspacePath] ?: @""
                                                                                      sinceRevision:params[@"sinceRevision"]
                                                                                              paths:params[@"paths"]
                                                                                       snapshotMode:params[@"snapshotMode"]
                                                                                           maxFiles:params[@"maxFiles"]
                                                                                       windowBridge:_windowBridge]);
        return;
    }

    if ([method isEqualToString:@"workspace.status"]) {
        NSMutableDictionary* status = [[_workspaceState statusPayloadWithWorkspace:[self safeWorkspacePath] ?: @""
                                                      windowBridge:_windowBridge
                                                           gitInfo:[self safeGitStatusInfo] ?: @{}
                                                     verifyStatus:[self verificationStatus] ?: @{}
                                               lastVerifyFinishedAt:_lastVerifyFinishedAt] mutableCopy];
        NSString* taskId = params[@"taskId"];
        if ([taskId isKindOfClass:[NSString class]] && taskId.length > 0) {
            NSDictionary* coherence = [_workspaceState coherencePayloadForTask:taskId];
            if (coherence) status[@"coherence"] = coherence;
        }
        *outResult = status;
        return;
    }

    if ([method isEqualToString:@"workspace.refreshAnchor"]) {
        *outResult = [_workspaceState refreshAnchorWithWorkspace:[self safeWorkspacePath] ?: @""
                                                    windowBridge:_windowBridge
                                                         gitInfo:[self safeGitStatusInfo] ?: @{}
                                                   verifyStatus:[self verificationStatus] ?: @{}
                                             lastVerifyFinishedAt:_lastVerifyFinishedAt];
        return;
    }

    if ([method isEqualToString:@"workspace.continueAnyway"]) {
        *outResult = [_workspaceState continueAnywayPayload];
        return;
    }

    if ([method isEqualToString:@"operation.status"]) {
        NSString* key = params[@"idempotencyKey"] ?: params[@"clientOperationId"];
        *outResult = MacControlApplyJournalAuthorityLabels([_workspaceState operationStatusForKey:key]);
        return;
    }
    
    if ([method isEqualToString:@"workspace.findFiles"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* pattern = params[@"pattern"];
        if (!ws || !pattern) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"pattern and workspace required.";
            return;
        }
        NSInteger maxResults = params[@"maxResults"] ? [params[@"maxResults"] integerValue] : 1000;
        if (maxResults <= 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"maxResults must be greater than zero.";
            return;
        }
        if (maxResults > 1000) {
            *outErrCode = @"response_too_large";
            *outErrMsg = @"maxResults exceeds limit of 1000.";
            return;
        }
        
        std::filesystem::path folder([ws UTF8String]);
        NSMutableArray* matches = [NSMutableArray array];
        std::error_code ec;
        
        for (auto const& entry : std::filesystem::recursive_directory_iterator(folder, ec)) {
            if (matches.count >= (NSUInteger)maxResults) break;
            if (entry.is_regular_file()) {
                auto rel = std::filesystem::relative(entry.path(), folder, ec);
                if (!ec) {
                    NSString* relPath = NSStringFromStdString(rel.string());
                    if (fnmatch([pattern UTF8String], [relPath UTF8String], FNM_CASEFOLD) == 0) {
                        [matches addObject:relPath];
                    }
                }
            }
        }
        *outResult = @{ @"files": matches };
        return;
    }
    
    if ([method isEqualToString:@"workspace.listFiles"]) {
        NSString* ws = [self safeWorkspacePath];
        if (!ws) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }
        
        std::filesystem::path folder([ws UTF8String]);
        std::vector<std::string> relativePaths;
        
        dietcode::filesystem::traverseDirectory(folder, [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion, bool& stop) {
            if (relativePaths.size() >= 1000) {
                stop = true;
                return;
            }
            
            std::filesystem::path p = entry.path();
            std::string filename = p.filename().string();
            if (entry.is_directory()) {
                if (depth >= kMaxSearchDepth || 
                    filename == ".git" || filename == "build" || filename == "dist" || 
                    filename == "node_modules" || filename == "DerivedData") {
                    skipRecursion = true;
                }
                return;
            }
            
            if (entry.is_regular_file()) {
                std::error_code ec;
                auto rel = std::filesystem::relative(p, folder, ec);
                if (!ec) {
                    relativePaths.push_back(rel.string());
                }
            }
        });
        
        NSMutableArray* filesArr = [NSMutableArray array];
        for (const auto& r : relativePaths) {
            [filesArr addObject:NSStringFromStdString(r)];
        }
        *outResult = @{ @"files": filesArr };
        return;
    }
    
    if ([method isEqualToString:@"workspace.grep"]) {
        *outResult = [_searchService workspaceGrep:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"workspace.searchStart"]) {
        *outResult = [_searchService startGrepSession:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"workspace.searchNext"]) {
        *outResult = [_searchService nextGrepResults:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"workspace.searchCancel"]) {
        *outResult = [_searchService cancelGrepSession:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }
    
    if ([method isEqualToString:@"workspace.openFile"]) {
        NSString* absPath = AbsolutePathForRPCPath(params[@"path"], [self safeWorkspacePath]);
        if (!absPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        if (![[NSFileManager defaultManager] fileExistsAtPath:absPath]) {
            *outErrCode = @"not_found";
            *outErrMsg = [NSString stringWithFormat:@"File does not exist: %@", absPath];
            return;
        }
        if (self.isKernelMode || !self.windowController || self.windowController.isHeadless || ![[self.windowController window] isVisible]) {
            NSArray* recents = [[NSUserDefaults standardUserDefaults] stringArrayForKey:@"RecentFiles"] ?: @[];
            NSMutableArray* updatedRecents = [recents mutableCopy];
            [updatedRecents removeObject:absPath];
            [updatedRecents insertObject:absPath atIndex:0];
            if (updatedRecents.count > 20) {
                [updatedRecents removeObjectsInRange:NSMakeRange(20, updatedRecents.count - 20)];
            }
            [[NSUserDefaults standardUserDefaults] setObject:updatedRecents forKey:@"RecentFiles"];
            *outResult = @{ @"opened": @YES, @"path": absPath, @"headless": @YES };
            return;
        }
        [self.windowController openFileAtPath:absPath line:1 column:1];
        *outResult = @{ @"opened": @YES, @"path": absPath };
        return;
    }
    
    if ([method isEqualToString:@"workspace.getRecentFiles"]) {
        NSArray* recents = [[NSUserDefaults standardUserDefaults] stringArrayForKey:@"RecentFiles"] ?: @[];
        *outResult = @{ @"files": recents };
        return;
    }

    // Search primitives
    if ([method isEqualToString:@"search.files"]) {
        *outResult = [_searchService searchFiles:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.text"]) {
        *outResult = [_searchService searchText:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.literal"]) {
        *outResult = [_searchService searchLiteral:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.tokens"]) {
        *outResult = [_searchService searchTokens:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.paths"]) {
        *outResult = [_searchService searchPaths:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.references"]) {
        *outResult = [_searchService searchReferences:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.todo"]) {
        *outResult = [_searchService searchTodo:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.semantic"]) {
        *outResult = [_searchService searchSemantic:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"search.diagnostics"]) {
        *outResult = [_searchService searchDiagnostics:params outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    // File reading primitives
    if ([method isEqualToString:@"file.read"] || [method isEqualToString:@"file.readBatch"] || [method isEqualToString:@"file.readRange"] || [method isEqualToString:@"file.readAround"] || [method isEqualToString:@"file.getChunks"] || [method isEqualToString:@"file.stat"] || [method isEqualToString:@"file.statBatch"]) {
        NSString* ws = [self safeWorkspacePath];
        
        if ([method isEqualToString:@"file.readBatch"] || [method isEqualToString:@"file.statBatch"]) {
            NSArray* paths = params[@"paths"];
            if (![paths isKindOfClass:[NSArray class]] || paths.count == 0) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"non-empty paths array required.";
                return;
            }
            if (paths.count > (NSUInteger)kMaxBatchFilePaths) {
                *outErrCode = @"response_too_large";
                *outErrMsg = [NSString stringWithFormat:@"paths exceeds limit of %ld.", (long)kMaxBatchFilePaths];
                return;
            }
            NSMutableDictionary* results = [NSMutableDictionary dictionary];
            NSMutableArray<NSString*>* readPaths = [NSMutableArray array];
            for (id pathValue in paths) {
                if (![pathValue isKindOfClass:[NSString class]] || [pathValue length] == 0) {
                    *outErrCode = @"invalid_params";
                    *outErrMsg = @"every paths entry must be a non-empty string.";
                    return;
                }
                NSString* p = (NSString*)pathValue;
                NSString* absPath = AbsolutePathForRPCPath(p, ws);
                if (!absPath || (ws && !PathIsInsideWorkspace(absPath, ws))) {
                    results[p] = @{ @"ok": @NO, @"error": @"outside_workspace" };
                    continue;
                }
                if (![[NSFileManager defaultManager] fileExistsAtPath:absPath]) {
                    results[p] = @{ @"ok": @NO, @"error": @"not_found" };
                    continue;
                }
                
                if ([method isEqualToString:@"file.readBatch"]) {
                    NSString* text = [self safeTextForFileAtPath:absPath];
                    if (text) {
                        results[p] = @{ @"ok": @YES, @"text": text };
                        [readPaths addObject:p];
                    } else {
                        results[p] = @{ @"ok": @NO, @"error": @"read_failed" };
                    }
                } else {
                    NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:absPath error:nil];
                    NSString* text = [self safeTextForFileAtPath:absPath];
                    results[p] = @{
                        @"ok": @YES,
                        @"sizeBytes": attrs[NSFileSize] ?: @([text lengthOfBytesUsingEncoding:NSUTF8StringEncoding]),
                        @"lineCount": @(LinesFromText(text ?: @"").count)
                    };
                }
            }
            if ([method isEqualToString:@"file.readBatch"] && readPaths.count > 0) {
                [_workspaceState trackHashesForPaths:readPaths workspace:ws windowBridge:_windowBridge];
            }
            NSMutableDictionary* batchResult = [@{ @"results": results } mutableCopy];
            if ([method isEqualToString:@"file.readBatch"]) {
                AttachCoherenceToResult(batchResult, params, readPaths, _workspaceState, ws, _windowBridge);
            }
            *outResult = batchResult;
            return;
        }

        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        if ([method isEqualToString:@"file.readRange"]) {
            if (params[@"startLine"] == nil || params[@"endLine"] == nil) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"startLine and endLine parameters required.";
                return;
            }
            NSInteger startLine = [params[@"startLine"] integerValue];
            NSInteger endLine = [params[@"endLine"] integerValue];
            if (startLine <= 0 || endLine <= 0) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"startLine and endLine must be positive integers (1-indexed).";
                return;
            }
        }
        if ([method isEqualToString:@"file.readAround"]) {
            NSInteger line = [params[@"line"] integerValue];
            if (line <= 0) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"line parameter must be a positive integer (1-indexed).";
                return;
            }
            NSInteger before = params[@"before"] ? [params[@"before"] integerValue] : 40;
            NSInteger after = params[@"after"] ? [params[@"after"] integerValue] : 80;
            if (before < 0 || after < 0) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"before and after must be non-negative integers.";
                return;
            }
            if (before > kMaxReadAroundContextLines || after > kMaxReadAroundContextLines) {
                *outErrCode = @"response_too_large";
                *outErrMsg = [NSString stringWithFormat:@"before and after must be <= %ld.", (long)kMaxReadAroundContextLines];
                return;
            }
        }
        if (ws && !PathIsInsideWorkspace(targetPath, ws)) {
            *outErrCode = @"outside_workspace";
            *outErrMsg = @"Target path is outside workspace.";
            return;
        }
        NSString* readSource = nil;
        NSString* editorText = self.windowController ? [self.windowController textForFileAtPath:targetPath] : nil;
        NSString* text = TextForSearchAtPath(editorText, targetPath, &readSource);
        if (!text) text = [self safeTextForFileAtPath:targetPath];
        if (!text && ![method isEqualToString:@"file.stat"]) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"File is not readable.";
            return;
        }
        if ([method isEqualToString:@"file.stat"] && !text) {
            text = @"";
            readSource = @"disk";
        }
        if (!readSource) readSource = @"disk";
        NSArray<NSString*>* lines = LinesFromText(text);
        NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:targetPath error:nil];
        NSUInteger sizeBytes = [text lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        BOOL open = [[self safeOpenFilePaths] containsObject:targetPath];
        BOOL dirty = [DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[]) containsObject:targetPath];
        if ([method isEqualToString:@"file.stat"]) {
            NSDictionary* symlinkMeta = PathSymlinkMetadata(targetPath, ws);
            NSMutableDictionary* stat = [@{
                @"path": targetPath,
                @"sizeBytes": @(attrs.fileSize ?: sizeBytes),
                @"lineCount": @(lines.count),
                @"modified": @(attrs.fileModificationDate != nil),
                @"open": @(open),
                @"dirty": @(dirty),
                @"contentHash": StableHashForString(text),
                @"readSource": readSource,
                @"isSymlink": symlinkMeta[@"isSymlink"] ?: @NO,
                @"symlinkTarget": symlinkMeta[@"symlinkTarget"] ?: @"",
                @"insideWorkspace": symlinkMeta[@"insideWorkspace"] ?: @YES,
                @"pathEscapesWorkspace": symlinkMeta[@"pathEscapesWorkspace"] ?: @NO
            } mutableCopy];
            if (attrs.fileModificationDate) {
                stat[@"modifiedAt"] = ISODateString(attrs.fileModificationDate);
            }
            AttachCoherenceToResult(stat, params, @[params[@"path"] ?: targetPath], _workspaceState, ws, _windowBridge);
            *outResult = stat;
            return;
        }
        if ([method isEqualToString:@"file.read"]) {
            if (sizeBytes > kMaxFileTextBytes) {
                *outErrCode = @"file_too_large";
                *outErrMsg = @"File exceeds read cap; use file.getChunks or file.readRange.";
                return;
            }
            [_workspaceState trackHashesForPaths:@[params[@"path"] ?: targetPath] workspace:ws windowBridge:_windowBridge];
            NSMutableDictionary* readResult = [@{ @"path": targetPath, @"text": text, @"lineCount": @(lines.count), @"sizeBytes": @(sizeBytes) } mutableCopy];
            AttachCoherenceToResult(readResult, params, @[params[@"path"] ?: targetPath], _workspaceState, ws, _windowBridge);
            *outResult = readResult;
            return;
        }
        if ([method isEqualToString:@"file.readRange"]) {
            NSInteger startLine = [params[@"startLine"] integerValue];
            NSInteger endLine = [params[@"endLine"] integerValue];
            NSString* rangeText = TextForLineRange(lines, startLine, endLine);
            if (!rangeText) {
                *outErrCode = @"invalid_range";
                *outErrMsg = @"Invalid line range.";
                return;
            }
            if ([rangeText lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > kMaxFileTextBytes) {
                *outErrCode = @"response_too_large";
                *outErrMsg = @"Requested range exceeds response size cap.";
                return;
            }
            [_workspaceState trackHashesForPaths:@[params[@"path"] ?: targetPath] workspace:ws windowBridge:_windowBridge];
            NSMutableDictionary* rangeResult = [@{ @"path": targetPath, @"startLine": @(startLine), @"endLine": @(endLine), @"text": rangeText } mutableCopy];
            AttachCoherenceToResult(rangeResult, params, @[params[@"path"] ?: targetPath], _workspaceState, ws, _windowBridge);
            *outResult = rangeResult;
            return;
        }
        if ([method isEqualToString:@"file.readAround"]) {
            NSInteger line = [params[@"line"] integerValue];
            NSInteger before = params[@"before"] ? [params[@"before"] integerValue] : 40;
            NSInteger after = params[@"after"] ? [params[@"after"] integerValue] : 80;
            NSInteger startLine = MAX(1, line - before);
            NSInteger endLine = MIN((NSInteger)lines.count, line + after);
            NSString* rangeText = TextForLineRange(lines, startLine, endLine);
            if (!rangeText || line > (NSInteger)lines.count) {
                *outErrCode = @"invalid_range";
                *outErrMsg = @"Invalid line.";
                return;
            }
            [_workspaceState trackHashesForPaths:@[params[@"path"] ?: targetPath] workspace:ws windowBridge:_windowBridge];
            NSMutableDictionary* aroundResult = [@{ @"path": targetPath, @"startLine": @(startLine), @"endLine": @(endLine), @"text": rangeText } mutableCopy];
            AttachCoherenceToResult(aroundResult, params, @[params[@"path"] ?: targetPath], _workspaceState, ws, _windowBridge);
            *outResult = aroundResult;
            return;
        }
        if ([method isEqualToString:@"file.getChunks"]) {
            NSInteger chunkSize = params[@"chunkSize"] ? [params[@"chunkSize"] integerValue] : 120;
            if (chunkSize < 20) chunkSize = 20;
            if (chunkSize > 500) chunkSize = 500;
            NSMutableArray* chunks = [NSMutableArray array];
            for (NSInteger start = 1, idx = 0; start <= (NSInteger)lines.count; start += chunkSize, idx++) {
                NSInteger end = MIN(start + chunkSize - 1, (NSInteger)lines.count);
                NSString* preview = TextForLineRange(lines, start, MIN(end, start + 4)) ?: @"";
                if (preview.length > kMaxChunkPreviewLength) {
                    preview = [[preview substringToIndex:kMaxChunkPreviewLength] stringByAppendingString:@"..."];
                }
                [chunks addObject:@{ @"index": @(idx), @"startLine": @(start), @"endLine": @(end), @"preview": preview }];
            }
            *outResult = @{ @"path": targetPath, @"chunks": chunks };
            return;
        }
    }

    if ([method isEqualToString:@"file.write"] || [method isEqualToString:@"file.create"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"], ws);
        NSString* content = params[@"content"];
        if (targetPath.length == 0 || ![content isKindOfClass:[NSString class]]) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path and content parameters required.";
            return;
        }
        if (!PathIsInsideWorkspace(targetPath, ws)) {
            *outErrCode = @"outside_workspace";
            *outErrMsg = @"Target path must be inside workspace.";
            return;
        }
        NSUInteger contentBytes = [content lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        if (contentBytes > kMaxFileTextBytes) {
            *outErrCode = @"file_too_large";
            *outErrMsg = @"Content exceeds write cap.";
            return;
        }
        BOOL existed = [[NSFileManager defaultManager] fileExistsAtPath:targetPath];
        if ([method isEqualToString:@"file.create"] && existed) {
            *outErrCode = @"already_exists";
            *outErrMsg = [NSString stringWithFormat:@"File already exists: %@", targetPath];
            return;
        }
        NSString* beforeText = existed ? [self safeTextForFileAtPath:targetPath] : @"";
        if (existed && beforeText == nil) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"Existing file is not readable as UTF-8 text.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [self.windowController writeFileAtPath:targetPath content:content errorOut:&errStr];
        } else {
            ok = [self.workspaceSession writeTextAtPath:targetPath content:content error:&errStr];
        }
        if (!ok) {
            *outErrCode = @"write_failed";
            *outErrMsg = errStr ?: @"Failed to write file.";
            return;
        }
        NSString* afterText = [self safeTextForFileAtPath:targetPath] ?: content;
        [_patchService recordMutationRecords:@[@{
            @"path": targetPath,
            @"beforeText": beforeText ?: @"",
            @"beforeHash": StableHashForString(beforeText ?: @""),
            @"postHash": StableHashForString(afterText ?: @""),
            @"existed": @(existed)
        }]];
        NSString* key = [method isEqualToString:@"file.create"] ? @"created" : @"written";
        *outResult = @{ key: @YES, @"path": targetPath, @"sizeBytes": @(contentBytes) };
        return;
    }

    *outErrCode = @"method_not_found";
    *outErrMsg = [NSString stringWithFormat:@"Unhandled file/workspace/search method: %@", method];
}

@end
