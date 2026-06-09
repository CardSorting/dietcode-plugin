#import "MacControlShellService.hpp"
#import "MacControlWorkspaceState.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSupport.hpp"
#import "SubprocessRunner.hpp"
#include "domain/control/ControlRuntimeLimits.hpp"

#include <filesystem>
#include <algorithm>
#include <vector>

using namespace dietcode::domain::control;
using namespace dietcode::platform::macos;

static NSString* ShellRelPath(NSString* absPath, NSString* workspace) {
    if (absPath.length == 0) return @"";
    if (workspace.length == 0) return absPath;
    std::error_code ec;
    auto rel = std::filesystem::relative(
        std::filesystem::path(StdStringFromNSString(absPath)),
        std::filesystem::path(StdStringFromNSString(workspace)),
        ec);
    if (ec) return absPath;
    return NSStringFromStdString(rel.string());
}

static NSString* ResolveShellTargetPath(NSString* path, NSString* cwd, NSString* workspace, NSString** outResolved) {
    if (path.length == 0) {
        if (outResolved) *outResolved = @"";
        return nil;
    }
    NSString* resolved = nil;
    if ([path isAbsolutePath]) {
        resolved = path;
    } else if (cwd.length > 0) {
        resolved = [cwd stringByAppendingPathComponent:path];
    } else {
        resolved = AbsolutePathForRPCPath(path, workspace);
    }
    if (outResolved) *outResolved = resolved ?: @"";
    if (workspace.length > 0 && resolved.length > 0 && !PathIsInsideWorkspace(resolved, workspace)) {
        return nil;
    }
    return resolved;
}

static NSMutableDictionary* ShellEnvelopeBase(
    NSString* command,
    NSString* cwdBefore,
    NSString* cwdAfter,
    NSString* workspaceRoot,
    NSString* pathResolved,
    NSInteger exitCode,
    BOOL complete,
    BOOL partial) {
    return [@{
        @"ok": @(exitCode == 0),
        @"complete": @(complete),
        @"partial": @(partial),
        @"command": command ?: @"",
        @"cwdBefore": cwdBefore ?: @"",
        @"cwdAfter": cwdAfter ?: @"",
        @"workspaceRoot": workspaceRoot ?: @"",
        @"pathResolved": pathResolved ?: @"",
        @"exitCode": @(exitCode),
        @"stdout": @"",
        @"stderr": @"",
        @"truncated": @NO,
        @"bytesRead": @0,
        @"lineCount": @0,
        @"warnings": @[],
        @"recoveryHint": @"",
        @"nextRecommendedCommand": @"",
    } mutableCopy];
}

static void ShellApplyPartial(
    NSMutableDictionary* result,
    BOOL truncated,
    NSArray<NSString*>* warnings,
    NSString* recoveryHint,
    NSString* nextCommand) {
    BOOL partial = truncated || warnings.count > 0;
    result[@"truncated"] = @(truncated);
    result[@"partial"] = @(partial);
    result[@"complete"] = @(truncated ? NO : !partial);
    if (warnings.count > 0) {
        result[@"warnings"] = warnings;
    }
    if (recoveryHint.length > 0) {
        result[@"recoveryHint"] = recoveryHint;
    }
    if (nextCommand.length > 0) {
        result[@"nextRecommendedCommand"] = nextCommand;
    }
}

static BOOL FileLooksBinaryAtPath(NSString* path) {
    NSFileHandle* handle = [NSFileHandle fileHandleForReadingAtPath:path];
    if (!handle) return NO;
    NSData* chunk = [handle readDataOfLength:8192];
    [handle closeFile];
    if (!chunk) return NO;
    const unsigned char* bytes = (const unsigned char*)chunk.bytes;
    for (NSUInteger i = 0; i < chunk.length; i++) {
        if (bytes[i] == 0) return YES;
    }
    return NO;
}

static NSString* ReadTextPrefix(NSString* path, NSUInteger maxBytes, NSUInteger* outBytesRead, BOOL* outTruncated) {
    NSFileHandle* handle = [NSFileHandle fileHandleForReadingAtPath:path];
    if (!handle) return nil;
    NSData* chunk = [handle readDataOfLength:maxBytes + 1];
    [handle closeFile];
    if (!chunk) return nil;
    BOOL truncated = chunk.length > maxBytes;
    if (truncated) {
        chunk = [chunk subdataWithRange:NSMakeRange(0, maxBytes)];
    }
    if (outBytesRead) *outBytesRead = chunk.length;
    if (outTruncated) *outTruncated = truncated;
    NSString* text = [[NSString alloc] initWithData:chunk encoding:NSUTF8StringEncoding];
    if (!text) return nil;
    if (IsTextBinary(text)) return nil;
    return text;
}

static BOOL ShellValidateReadableFile(
    NSString* pathParam,
    NSString* cwdBefore,
    NSString* workspacePath,
    BOOL rejectSymlink,
    NSString** outResolved,
    NSString** outTarget,
    NSString** outErrCode,
    NSString** outErrMsg) {
    if (pathParam.length == 0) {
        if (outErrCode) *outErrCode = @"invalid_params";
        if (outErrMsg) *outErrMsg = @"path parameter required.";
        return NO;
    }
    NSString* resolved = nil;
    NSString* target = ResolveShellTargetPath(pathParam, cwdBefore, workspacePath, &resolved);
    if (outResolved) *outResolved = resolved ?: @"";
    if (!target) {
        NSDictionary* probeMeta = PathSymlinkMetadata(
            [pathParam isAbsolutePath] ? pathParam : AbsolutePathForRPCPath(pathParam, workspacePath),
            workspacePath);
        if ([probeMeta[@"isSymlink"] boolValue] || [probeMeta[@"pathEscapesWorkspace"] boolValue]) {
            if (outErrCode) *outErrCode = @"shell_symlink_escape";
            if (outErrMsg) *outErrMsg = @"Symlink target escapes workspace.";
        } else {
            if (outErrCode) *outErrCode = @"shell_outside_workspace";
            if (outErrMsg) *outErrMsg = @"Target path is outside workspace.";
        }
        return NO;
    }
    if (outTarget) *outTarget = target;
    if (rejectSymlink && PathIsSymlink(target)) {
        if (outErrCode) *outErrCode = @"shell_symlink_escape";
        if (outErrMsg) *outErrMsg = @"Symlink paths are not readable via shell wrappers.";
        return NO;
    }
    BOOL isDir = NO;
    if (![[NSFileManager defaultManager] fileExistsAtPath:target isDirectory:&isDir]) {
        if (outErrCode) *outErrCode = @"not_found";
        if (outErrMsg) *outErrMsg = @"File does not exist.";
        return NO;
    }
    if (isDir) {
        if (outErrCode) *outErrCode = @"shell_directory_target";
        if (outErrMsg) *outErrMsg = @"Target path is a directory; use shell.cd or shell.rg.";
        return NO;
    }
    if (FileLooksBinaryAtPath(target)) {
        if (outErrCode) *outErrCode = @"shell_binary_file";
        if (outErrMsg) *outErrMsg = @"File appears binary; use file.stat or a specialized reader.";
        return NO;
    }
    NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:target error:nil];
    NSUInteger fileSize = [attrs fileSize];
    if (fileSize > kShellMaxReadFileBytes) {
        if (outErrCode) *outErrCode = @"shell_file_too_large";
        if (outErrMsg) *outErrMsg = @"File exceeds shell read cap; use shell.head, shell.tail, or shell.sedRange.";
        return NO;
    }
    return YES;
}

static NSDictionary* ShellCountSearchSkipStats(
    NSString* searchRoot,
    NSString* workspacePath,
    NSArray* includes,
    NSArray* excludes,
    BOOL includeHidden) {
    NSInteger filesSkippedBinary = 0;
    NSInteger filesSkippedSymlink = 0;
    NSInteger filesSkippedExcluded = 0;
    NSInteger filesSearched = 0;
    NSInteger scanned = 0;
    std::error_code ec;
    std::filesystem::path root(StdStringFromNSString(searchRoot));
    std::filesystem::path ws(StdStringFromNSString(workspacePath));
    if (!std::filesystem::exists(root, ec)) {
        return @{
            @"filesSearched": @0,
            @"filesSkipped": @0,
            @"filesSkippedBinary": @0,
            @"filesSkippedSymlink": @0,
            @"filesSkippedExcluded": @0,
        };
    }
    auto visit = [&](const std::filesystem::path& entry, const std::string& relPath, BOOL isDir) {
        if (scanned >= kShellRgMaxScanFiles) return;
        scanned++;
        std::string filename = entry.filename().string();
        if (!includeHidden && !filename.empty() && filename[0] == '.') {
            filesSkippedExcluded++;
            return;
        }
        if (ShouldSkipSearchPath(entry, relPath, includes, excludes)) {
            filesSkippedExcluded++;
            return;
        }
        if (isDir) return;
        if (PathIsSymlink(NSStringFromStdString(entry.string()))) {
            filesSkippedSymlink++;
            return;
        }
        if (FileLooksBinaryAtPath(NSStringFromStdString(entry.string()))) {
            filesSkippedBinary++;
            return;
        }
        filesSearched++;
    };
    if (std::filesystem::is_directory(root, ec)) {
        for (auto it = std::filesystem::recursive_directory_iterator(
                 root,
                 std::filesystem::directory_options::skip_permission_denied,
                 ec);
             it != std::filesystem::recursive_directory_iterator() && scanned < kShellRgMaxScanFiles;
             it.increment(ec)) {
            if (ec) continue;
            const auto& entry = *it;
            std::error_code relEc;
            auto rel = std::filesystem::relative(entry.path(), ws, relEc);
            std::string relPath = relEc ? entry.path().filename().string() : rel.string();
            if (entry.is_symlink(relEc)) {
                it.disable_recursion_pending();
                filesSkippedSymlink++;
                continue;
            }
            if (entry.is_directory(relEc)) {
                if (ShouldPruneSearchDirectory(entry.path(), relPath, excludes)) {
                    it.disable_recursion_pending();
                }
                continue;
            }
            visit(entry.path(), relPath, NO);
        }
    } else {
        std::string relPath = StdStringFromNSString(ShellRelPath(searchRoot, workspacePath));
        visit(root, relPath, NO);
    }
    NSInteger filesSkipped = filesSkippedBinary + filesSkippedSymlink + filesSkippedExcluded;
    return @{
        @"filesSearched": @(filesSearched),
        @"filesSkipped": @(filesSkipped),
        @"filesSkippedBinary": @(filesSkippedBinary),
        @"filesSkippedSymlink": @(filesSkippedSymlink),
        @"filesSkippedExcluded": @(filesSkippedExcluded),
    };
}

@implementation MacControlShellService {
    MacControlWorkspaceState* _workspaceState;
}

- (instancetype)initWithWorkspaceState:(MacControlWorkspaceState*)workspaceState {
    self = [super init];
    if (self) {
        _workspaceState = workspaceState;
    }
    return self;
}

- (NSString*)currentCwd:(NSString*)workspace {
    return [_workspaceState agentShellCwdForWorkspace:workspace];
}

- (void)executeMethod:(NSString*)method
               params:(NSDictionary*)params
            workspace:(NSString*)workspacePath
            outResult:(NSDictionary**)outResult
           outErrCode:(NSString**)outErrCode
            outErrMsg:(NSString**)outErrMsg {
    NSString* cwdBefore = [self currentCwd:workspacePath];

    if ([method isEqualToString:@"shell.pwd"]) {
        NSMutableDictionary* result = ShellEnvelopeBase(@"pwd", cwdBefore, cwdBefore, workspacePath, @"", 0, YES, NO);
        result[@"stdout"] = cwdBefore ?: @"";
        result[@"nextRecommendedCommand"] = @"shell.cd";
        *outResult = result;
        return;
    }

    if ([method isEqualToString:@"shell.cd"]) {
        NSString* pathParam = params[@"path"];
        if (pathParam.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        if ([pathParam rangeOfString:@"\0"].location != NSNotFound) {
            *outErrCode = @"invalid_path";
            *outErrMsg = @"Path contains invalid characters.";
            return;
        }
        NSString* resolved = nil;
        NSString* target = nil;
        if ([pathParam isAbsolutePath]) {
            target = pathParam;
        } else if (cwdBefore.length > 0) {
            target = [cwdBefore stringByAppendingPathComponent:pathParam];
        } else {
            target = AbsolutePathForRPCPath(pathParam, workspacePath);
        }
        resolved = target ?: @"";
        if (target.length == 0) {
            *outErrCode = @"invalid_path";
            *outErrMsg = @"Path could not be resolved.";
            return;
        }
        NSDictionary* symlinkMeta = PathSymlinkMetadata(target, workspacePath);
        if ([symlinkMeta[@"pathEscapesWorkspace"] boolValue] || [symlinkMeta[@"isSymlink"] boolValue]) {
            if (!PathIsInsideWorkspace(target, workspacePath)) {
                *outErrCode = @"symlink_escape";
                *outErrMsg = @"Symlink target escapes workspace.";
                return;
            }
        }
        if (workspacePath.length > 0 && !PathIsInsideWorkspace(target, workspacePath)) {
            *outErrCode = @"outside_workspace";
            *outErrMsg = @"Target directory is outside workspace.";
            return;
        }
        BOOL isDir = NO;
        if (![[NSFileManager defaultManager] fileExistsAtPath:target isDirectory:&isDir]) {
            *outErrCode = @"directory_not_found";
            *outErrMsg = @"Directory does not exist.";
            return;
        }
        if (!isDir) {
            *outErrCode = @"not_directory";
            *outErrMsg = @"Target path is not a directory.";
            return;
        }
        NSString* errCode = nil;
        NSString* errMsg = nil;
        if (![_workspaceState setAgentShellCwd:target workspace:workspacePath errorCode:&errCode errorMessage:&errMsg]) {
            *outErrCode = errCode ?: @"invalid_request";
            *outErrMsg = errMsg ?: @"shell.cd failed.";
            return;
        }
        NSString* cwdAfter = [self currentCwd:workspacePath];
        NSMutableDictionary* result = ShellEnvelopeBase(@"cd", cwdBefore, cwdAfter, workspacePath, resolved, 0, YES, NO);
        result[@"stdout"] = cwdAfter ?: @"";
        result[@"nextRecommendedCommand"] = @"shell.pwd";
        *outResult = result;
        return;
    }

    if ([method isEqualToString:@"shell.rg"]) {
        [self executeRg:params workspace:workspacePath cwdBefore:cwdBefore outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"shell.head"] || [method isEqualToString:@"shell.tail"]) {
        [self executeHeadTail:method params:params workspace:workspacePath cwdBefore:cwdBefore outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"shell.sedRange"]) {
        [self executeSedRange:params workspace:workspacePath cwdBefore:cwdBefore outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    if ([method isEqualToString:@"shell.catSmall"]) {
        [self executeCatSmall:params workspace:workspacePath cwdBefore:cwdBefore outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg];
        return;
    }

    *outErrCode = @"shell_command_not_allowed";
    *outErrMsg = [NSString stringWithFormat:@"Unknown shell method '%@'.", method];
}

- (void)executeRg:(NSDictionary*)params
        workspace:(NSString*)workspacePath
        cwdBefore:(NSString*)cwdBefore
        outResult:(NSDictionary**)outResult
       outErrCode:(NSString**)outErrCode
        outErrMsg:(NSString**)outErrMsg {
    NSString* pattern = params[@"pattern"] ?: params[@"query"];
    if (pattern.length == 0) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"pattern parameter required.";
        return;
    }
    BOOL regexMode = [params[@"regex"] boolValue];
    NSInteger maxResults = params[@"maxResults"] ? [params[@"maxResults"] integerValue] : kShellRgMaxResults;
    maxResults = MIN(MAX(maxResults, 1), kShellRgMaxResults);
    BOOL includeHidden = params[@"hidden"] == nil ? YES : [params[@"hidden"] boolValue];

    NSMutableArray<NSString*>* rgArgs;
    rgArgs = [NSMutableArray arrayWithObjects:
        @"rg",
        @"--json",
        @"--line-number",
        @"--column",
        @"--no-heading",
        @"--sort", @"path",
        @"--max-count", [NSString stringWithFormat:@"%ld", (long)maxResults],
        nil];
    if (includeHidden) [rgArgs addObject:@"--hidden"];
    [rgArgs addObject:@"--no-follow"];
    if (!regexMode) [rgArgs addObject:@"--fixed-strings"];

    NSArray* includes = params[@"include"];
    if ([includes isKindOfClass:[NSArray class]]) {
        for (NSString* glob in includes) {
            if ([glob isKindOfClass:[NSString class]] && glob.length > 0) {
                [rgArgs addObject:@"--glob"];
                [rgArgs addObject:glob];
            }
        }
    }
    NSArray* excludes = params[@"exclude"];
    if ([excludes isKindOfClass:[NSArray class]]) {
        for (NSString* glob in excludes) {
            if ([glob isKindOfClass:[NSString class]] && glob.length > 0) {
                [rgArgs addObject:@"--glob"];
                [rgArgs addObject:[NSString stringWithFormat:@"!%@", glob]];
            }
        }
    }
    [rgArgs addObject:pattern];

    NSString* searchPath = params[@"path"];
    NSString* resolved = nil;
    NSString* searchRoot = nil;
    if (searchPath.length > 0) {
        NSString* target = ResolveShellTargetPath(searchPath, cwdBefore, workspacePath, &resolved);
        if (!target) {
            *outErrCode = @"shell_outside_workspace";
            *outErrMsg = @"Search path is outside workspace.";
            return;
        }
        searchRoot = target;
        [rgArgs addObject:target];
    } else {
        searchRoot = workspacePath.length > 0 ? workspacePath : cwdBefore;
        [rgArgs addObject:searchRoot.length > 0 ? searchRoot : @"."];
        resolved = workspacePath;
    }

    NSString* cwd = cwdBefore.length > 0 ? cwdBefore : workspacePath;
    std::vector<std::string> cppArgs;
    for (NSUInteger i = 0; i < rgArgs.count; i++) {
        cppArgs.push_back([rgArgs[i] UTF8String]);
    }
    using namespace dietcode::platform::macos;
    SubprocessResult proc = SubprocessRunner::run("/usr/bin/env", cppArgs, [cwd UTF8String] ?: ".", kShellRgTimeoutSeconds);

    if (proc.timedOut) {
        *outErrCode = @"shell_timeout";
        *outErrMsg = @"shell.rg exceeded timeout.";
        return;
    }
    if (proc.exitCode > 1) {
        *outErrCode = @"shell_rg_failed";
        *outErrMsg = [NSString stringWithFormat:@"shell.rg failed with exit code %d.", proc.exitCode];
        return;
    }

    NSMutableArray<NSDictionary*>* matches = [NSMutableArray array];
    NSMutableSet<NSString*>* seenFiles = [NSMutableSet set];
    for (NSString* line in [[NSString stringWithUTF8String:proc.stdOut.c_str()] componentsSeparatedByString:@"\n"]) {
        if (line.length == 0) continue;
        NSData* jsonData = [line dataUsingEncoding:NSUTF8StringEncoding];
        if (!jsonData) continue;
        id parsed = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:nil];
        if (![parsed isKindOfClass:[NSDictionary class]]) continue;
        NSDictionary* row = (NSDictionary*)parsed;
        if (![row[@"type"] isEqualToString:@"match"]) continue;
        NSDictionary* data = row[@"data"];
        if (![data isKindOfClass:[NSDictionary class]]) continue;
        NSDictionary* pathObj = data[@"path"];
        NSDictionary* lineNumber = data[@"line_number"];
        NSDictionary* submatches = [data[@"submatches"] isKindOfClass:[NSArray class]] ? [data[@"submatches"] firstObject] : nil;
        NSString* filePath = [pathObj isKindOfClass:[NSDictionary class]] ? pathObj[@"text"] : nil;
        if (filePath.length == 0) continue;
        NSInteger lineNo = [lineNumber isKindOfClass:[NSDictionary class]] ? [lineNumber[@"text"] integerValue] : [data[@"line_number"] integerValue];
        NSInteger column = [submatches isKindOfClass:[NSDictionary class]] ? [submatches[@"start"] integerValue] + 1 : 1;
        NSString* preview = [data[@"lines"] isKindOfClass:[NSDictionary class]] ? data[@"lines"][@"text"] : @"";
        NSString* rel = ShellRelPath(filePath, workspacePath);
        if (![seenFiles containsObject:rel]) {
            [seenFiles addObject:rel];
        }
        [matches addObject:@{
            @"path": rel,
            @"line": @(lineNo),
            @"column": @(column),
            @"preview": preview ?: @"",
        }];
    }

    NSDictionary* skipStats = ShellCountSearchSkipStats(searchRoot, workspacePath, includes, excludes, includeHidden);
    NSInteger filesSearched = [skipStats[@"filesSearched"] integerValue];
    if (filesSearched == 0) {
        filesSearched = (NSInteger)seenFiles.count;
    }
    BOOL truncated = (NSInteger)matches.count >= maxResults;
    NSInteger exitCode = proc.exitCode;
    BOOL cmdOk = (exitCode == 0 || exitCode == 1);
    NSString* cwdAfter = [self currentCwd:workspacePath];
    NSMutableDictionary* result = ShellEnvelopeBase(@"rg", cwdBefore, cwdAfter, workspacePath, resolved ?: @"", cmdOk ? 0 : exitCode, !truncated, truncated);
    result[@"exitCode"] = @(exitCode);
    result[@"ok"] = @(cmdOk);
    result[@"stdout"] = [NSString stringWithUTF8String:proc.stdOut.c_str()] ?: @"";
    result[@"stderr"] = [NSString stringWithUTF8String:proc.stdErr.c_str()] ?: @"";
    result[@"matches"] = matches;
    result[@"matchCount"] = @(matches.count);
    result[@"filesSearched"] = @(filesSearched);
    result[@"filesSkipped"] = skipStats[@"filesSkipped"];
    result[@"filesSkippedBinary"] = skipStats[@"filesSkippedBinary"];
    result[@"filesSkippedSymlink"] = skipStats[@"filesSkippedSymlink"];
    result[@"filesSkippedExcluded"] = skipStats[@"filesSkippedExcluded"];
    result[@"searchMode"] = regexMode ? @"regex" : @"literal";
    result[@"sortOrder"] = @"path_line_column";
    result[@"hiddenPolicy"] = includeHidden ? @"include_hidden" : @"exclude_hidden";
    result[@"symlinkPolicy"] = @"no_follow";
    if (truncated) {
        ShellApplyPartial(result, YES, @[@"shell_truncated", @"result_limit_reached"], @"narrow_pattern_or_paginate", @"shell.rg");
    } else if (matches.count == 0) {
        result[@"recoveryHint"] = @"verify_pattern_or_path";
        result[@"nextRecommendedCommand"] = @"shell.rg";
    } else {
        result[@"nextRecommendedCommand"] = @"shell.sedRange";
    }
    *outResult = result;
}

- (void)executeHeadTail:(NSString*)method
                 params:(NSDictionary*)params
              workspace:(NSString*)workspacePath
              cwdBefore:(NSString*)cwdBefore
              outResult:(NSDictionary**)outResult
             outErrCode:(NSString**)outErrCode
              outErrMsg:(NSString**)outErrMsg {
    NSString* resolved = nil;
    NSString* target = nil;
    NSString* errCode = nil;
    NSString* errMsg = nil;
    if (!ShellValidateReadableFile(params[@"path"], cwdBefore, workspacePath, YES, &resolved, &target, &errCode, &errMsg)) {
        *outErrCode = errCode;
        *outErrMsg = errMsg;
        return;
    }
    NSError* err = nil;
    NSString* text = [NSString stringWithContentsOfFile:target encoding:NSUTF8StringEncoding error:&err];
    if (!text) {
        *outErrCode = @"invalid_request";
        *outErrMsg = @"File is not readable.";
        return;
    }
    NSArray<NSString*>* lines = LinesFromText(text);
    NSInteger totalLines = (NSInteger)lines.count;
    NSInteger lineCount = params[@"lines"] ? [params[@"lines"] integerValue] : kShellHeadTailDefaultLines;
    lineCount = MIN(MAX(lineCount, 1), kShellHeadTailMaxLines);

    NSInteger startLine = 1;
    NSInteger endLine = totalLines;
    BOOL isHead = [method isEqualToString:@"shell.head"];
    if (isHead) {
        endLine = MIN(lineCount, totalLines);
    } else {
        startLine = MAX(1, totalLines - lineCount + 1);
        endLine = totalLines;
    }
    NSString* rangeText = TextForLineRange(lines, startLine, endLine) ?: @"";
    NSUInteger bytesRead = [rangeText lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
    BOOL truncated = totalLines > lineCount;
    NSString* cwdAfter = [self currentCwd:workspacePath];
    NSString* shellCmd = isHead ? @"head" : @"tail";
    NSMutableDictionary* result = ShellEnvelopeBase(shellCmd, cwdBefore, cwdAfter, workspacePath, resolved, 0, !truncated, truncated);
    result[@"stdout"] = rangeText;
    result[@"bytesRead"] = @(bytesRead);
    result[@"lineCount"] = @(endLine - startLine + 1);
    result[@"startLine"] = @(startLine);
    result[@"endLine"] = @(endLine);
    result[@"fileLineCount"] = @(totalLines);
    result[@"hasMoreBefore"] = @(startLine > 1);
    result[@"hasMoreAfter"] = @(endLine < totalLines);
    if (truncated) {
        ShellApplyPartial(result, YES, @[@"file_has_more_lines"], @"use_shell_sedRange_for_context", @"shell.sedRange");
    } else {
        result[@"nextRecommendedCommand"] = @"shell.sedRange";
    }
    *outResult = result;
}

- (void)executeSedRange:(NSDictionary*)params
              workspace:(NSString*)workspacePath
              cwdBefore:(NSString*)cwdBefore
              outResult:(NSDictionary**)outResult
             outErrCode:(NSString**)outErrCode
              outErrMsg:(NSString**)outErrMsg {
    if (params[@"path"] == nil || params[@"startLine"] == nil || params[@"endLine"] == nil) {
        *outErrCode = @"invalid_params";
        *outErrMsg = @"path, startLine, and endLine parameters required.";
        return;
    }
    NSInteger requestedStart = [params[@"startLine"] integerValue];
    NSInteger requestedEnd = [params[@"endLine"] integerValue];
    if (requestedStart <= 0 || requestedEnd <= 0 || requestedEnd < requestedStart) {
        *outErrCode = @"shell_invalid_range";
        *outErrMsg = @"startLine and endLine must be positive with endLine >= startLine.";
        return;
    }
    if (requestedEnd - requestedStart + 1 > kShellHeadTailMaxLines) {
        *outErrCode = @"shell_truncated";
        *outErrMsg = [NSString stringWithFormat:@"Range exceeds %d lines; narrow the window.", kShellHeadTailMaxLines];
        return;
    }
    NSString* resolved = nil;
    NSString* target = nil;
    NSString* errCode = nil;
    NSString* errMsg = nil;
    if (!ShellValidateReadableFile(params[@"path"], cwdBefore, workspacePath, YES, &resolved, &target, &errCode, &errMsg)) {
        *outErrCode = errCode;
        *outErrMsg = errMsg;
        return;
    }
    NSError* err = nil;
    NSString* text = [NSString stringWithContentsOfFile:target encoding:NSUTF8StringEncoding error:&err];
    if (!text) {
        *outErrCode = @"invalid_request";
        *outErrMsg = @"File is not readable.";
        return;
    }
    NSArray<NSString*>* lines = LinesFromText(text);
    NSInteger totalLines = (NSInteger)lines.count;
    NSInteger actualStart = MIN(MAX(requestedStart, 1), totalLines > 0 ? totalLines : 1);
    NSInteger actualEnd = MIN(requestedEnd, totalLines);
    if (totalLines == 0) {
        actualStart = 1;
        actualEnd = 0;
    }
    NSString* rangeText = TextForLineRange(lines, actualStart, actualEnd);
    if (!rangeText && totalLines > 0) {
        *outErrCode = @"shell_invalid_range";
        *outErrMsg = @"Line range is outside file bounds.";
        return;
    }
    NSUInteger bytesRead = [rangeText lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
    BOOL hasMoreAfter = actualEnd < totalLines;
    BOOL hasMoreBefore = actualStart > 1;
    NSString* command = [NSString stringWithFormat:@"sed -n '%ld,%ldp' %@", (long)requestedStart, (long)requestedEnd, resolved];
    NSString* cwdAfter = [self currentCwd:workspacePath];
    BOOL partial = actualStart != requestedStart || actualEnd != requestedEnd;
    NSMutableDictionary* result = ShellEnvelopeBase(@"sed -n", cwdBefore, cwdAfter, workspacePath, resolved, 0, !partial, partial);
    result[@"stdout"] = rangeText ?: @"";
    result[@"bytesRead"] = @(bytesRead);
    result[@"lineCount"] = @(MAX(0, actualEnd - actualStart + 1));
    result[@"requestedStartLine"] = @(requestedStart);
    result[@"requestedEndLine"] = @(requestedEnd);
    result[@"actualStartLine"] = @(actualStart);
    result[@"actualEndLine"] = @(actualEnd);
    result[@"startLine"] = @(actualStart);
    result[@"endLine"] = @(actualEnd);
    result[@"fileLineCount"] = @(totalLines);
    result[@"hasMoreBefore"] = @(hasMoreBefore);
    result[@"hasMoreAfter"] = @(hasMoreAfter);
    result[@"command"] = command;
    if (hasMoreAfter) {
        NSInteger nextStart = actualEnd + 1;
        NSInteger nextEnd = MIN(actualEnd + (actualEnd - actualStart + 1), totalLines);
        result[@"nextRecommendedCommand"] = @"shell.sedRange";
        result[@"recoveryHint"] = [NSString stringWithFormat:@"more_lines_after; try startLine=%ld endLine=%ld", (long)nextStart, (long)nextEnd];
    } else if (hasMoreBefore) {
        result[@"nextRecommendedCommand"] = @"shell.sedRange";
    }
    if (partial) {
        NSMutableArray* warnings = [NSMutableArray arrayWithObject:@"range_clamped_to_file_bounds"];
        result[@"warnings"] = warnings;
    }
    *outResult = result;
}

- (void)executeCatSmall:(NSDictionary*)params
              workspace:(NSString*)workspacePath
              cwdBefore:(NSString*)cwdBefore
              outResult:(NSDictionary**)outResult
             outErrCode:(NSString**)outErrCode
              outErrMsg:(NSString**)outErrMsg {
    NSString* resolved = nil;
    NSString* target = nil;
    NSString* errCode = nil;
    NSString* errMsg = nil;
    if (!ShellValidateReadableFile(params[@"path"], cwdBefore, workspacePath, YES, &resolved, &target, &errCode, &errMsg)) {
        *outErrCode = errCode;
        *outErrMsg = errMsg;
        return;
    }
    NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:target error:nil];
    NSUInteger fileSize = [attrs fileSize];
    NSUInteger maxBytes = kShellCatSmallMaxBytes;
    NSUInteger bytesRead = 0;
    BOOL truncated = fileSize > maxBytes;
    NSString* text = nil;
    if (truncated) {
        BOOL prefixTruncated = NO;
        text = ReadTextPrefix(target, maxBytes, &bytesRead, &prefixTruncated);
        truncated = YES;
    } else {
        NSError* err = nil;
        text = [NSString stringWithContentsOfFile:target encoding:NSUTF8StringEncoding error:&err];
        bytesRead = [text lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
    }
    if (!text) {
        *outErrCode = @"invalid_request";
        *outErrMsg = @"File is not readable as UTF-8 text.";
        return;
    }
    NSArray<NSString*>* lines = LinesFromText(text);
    NSInteger lineCount = (NSInteger)lines.count;
    BOOL partial = truncated || lineCount > kShellCatSmallMaxLines;
    if (lineCount > kShellCatSmallMaxLines) {
        lines = [lines subarrayWithRange:NSMakeRange(0, kShellCatSmallMaxLines)];
        text = [lines componentsJoinedByString:@"\n"];
        if (lines.count > 0) text = [text stringByAppendingString:@"\n"];
        truncated = YES;
        lineCount = kShellCatSmallMaxLines;
    }
    NSString* cwdAfter = [self currentCwd:workspacePath];
    NSMutableDictionary* result = ShellEnvelopeBase(@"cat", cwdBefore, cwdAfter, workspacePath, resolved, 0, !partial, partial);
    result[@"stdout"] = text ?: @"";
    result[@"bytesRead"] = @(bytesRead);
    result[@"lineCount"] = @(lineCount);
    result[@"fileSizeBytes"] = @(fileSize);
    if (partial) {
        ShellApplyPartial(result, truncated, @[@"file_too_large_for_cat"], @"use_shell_head_tail_or_sedRange", @"shell.sedRange");
    } else {
        result[@"nextRecommendedCommand"] = @"shell.head";
    }
    *outResult = result;
}

@end
