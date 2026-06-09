#import "MacControlSupport.hpp"
#import "SubprocessRunner.hpp"

#import <CommonCrypto/CommonDigest.h>

#include "domain/control/ControlPermission.hpp"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fnmatch.h>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include "domain/control/ControlRuntimeLimits.hpp"

BOOL IsTextBinary(NSString* text);

const NSUInteger kMaxRequestBytes = dietcode::domain::control::kMaxRequestBytes;
const NSUInteger kMaxResponseBytes = dietcode::domain::control::kMaxResponseBytes;
const NSInteger kMaxGrepResults = dietcode::domain::control::kMaxGrepResults;
const NSUInteger kMaxFileTextBytes = dietcode::domain::control::kMaxFileTextBytes;
const NSUInteger kMaxPatchBytesBeforeConfirmation = dietcode::domain::control::kMaxPatchBytesBeforeConfirmation;
const NSUInteger kMaxPatchBytes = dietcode::domain::control::kMaxPatchBytes;
const NSInteger kMaxBatchPatchCount = dietcode::domain::control::kMaxBatchPatchCount;
const NSUInteger kMaxChunkPreviewLength = dietcode::domain::control::kMaxChunkPreviewLength;
const NSInteger kMaxSearchDepth = dietcode::domain::control::kMaxSearchDepth;
const NSInteger kMaxSearchScanFiles = dietcode::domain::control::kMaxSearchScanFiles;
const NSUInteger kMaxSearchFileBytes = dietcode::domain::control::kMaxSearchFileBytes;
const NSInteger kMaxPlanSteps = dietcode::domain::control::kMaxPlanSteps;
const NSInteger kMaxActiveCombos = dietcode::domain::control::kMaxActiveCombos;
const NSInteger kMaxActiveConnections = dietcode::domain::control::kMaxActiveConnections;
const NSInteger kMaxPendingRequestsPerConnection = dietcode::domain::control::kMaxPendingRequestsPerConnection;
const NSInteger kMaxMalformedRequestsPerConnection = dietcode::domain::control::kMaxMalformedRequestsPerConnection;
const NSInteger kMaxNestedCallWaitSeconds = dietcode::domain::control::kMaxNestedCallWaitSeconds;
const NSInteger kSocketListenBacklog = dietcode::domain::control::kSocketListenBacklog;
const NSUInteger kMaxRuntimeDiagnosticLogBytes = dietcode::domain::control::kMaxRuntimeDiagnosticLogBytes;
const NSUInteger kMaxAuditLogBytes = dietcode::domain::control::kMaxAuditLogBytes;
const NSUInteger kMaxFailureBundleBytes = dietcode::domain::control::kMaxFailureBundleBytes;
NSString* const kDietCodeAppVersion = @"1.6.6";
NSString* const kDietCodeTerminalOutputDidUpdateNotification = @"kDietCodeTerminalOutputDidUpdateNotification";

NSString* NSStringFromStdString(const std::string& value) {
    return [NSString stringWithUTF8String:value.c_str()] ?: @"";
}

std::string StdStringFromNSString(NSString* value) {
    if (value == nil) {
        return {};
    }
    return std::string([value UTF8String]);
}

NSArray<NSString*>* LinesFromText(NSString* text) {
    NSMutableArray<NSString*>* lines = [NSMutableArray array];
    [text enumerateLinesUsingBlock:^(NSString* line, BOOL*) {
        [lines addObject:line ?: @""];
    }];
    if (text.length > 0 && [text hasSuffix:@"\n"]) {
        [lines addObject:@""];
    }
    return lines;
}

std::string LowerASCII(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return (char)std::tolower(c);
    });
    return value;
}

NSArray<NSDictionary*>* LiteralMatchSpans(const std::string& line, const std::string& query, BOOL caseSensitive) {
    NSMutableArray* spans = [NSMutableArray array];
    if (query.empty()) return spans;
    std::string haystack = caseSensitive ? line : LowerASCII(line);
    std::string needle = caseSensitive ? query : LowerASCII(query);
    size_t pos = 0;
    while ((pos = haystack.find(needle, pos)) != std::string::npos) {
        [spans addObject:@{
            @"columnStart": @(pos + 1),
            @"columnEnd": @(pos + needle.size()),
            @"text": NSStringFromStdString(line.substr(pos, needle.size()))
        }];
        pos += std::max<size_t>(needle.size(), 1);
    }
    return spans;
}

NSString* TextForLineRange(NSArray<NSString*>* lines, NSInteger startLine, NSInteger endLine) {
    if (startLine < 1 || endLine < startLine || endLine > (NSInteger)lines.count) {
        return nil;
    }
    NSMutableArray<NSString*>* selected = [NSMutableArray array];
    for (NSInteger i = startLine; i <= endLine; i++) {
        [selected addObject:lines[(NSUInteger)i - 1]];
    }
    return [selected componentsJoinedByString:@"\n"];
}

NSDictionary* TextChunkResponse(NSString* text, NSInteger offset, NSInteger maxBytes) {
    NSData* data = [text dataUsingEncoding:NSUTF8StringEncoding] ?: [NSData data];
    NSInteger totalBytes = (NSInteger)data.length;
    NSInteger safeOffset = MAX(0, MIN(offset, totalBytes));
    NSInteger safeMax = maxBytes > 0 ? MIN(maxBytes, (NSInteger)kMaxResponseBytes / 2) : 64 * 1024;
    NSInteger end = MIN(totalBytes, safeOffset + safeMax);
    NSRange range = NSMakeRange((NSUInteger)safeOffset, (NSUInteger)(end - safeOffset));
    NSData* chunkData = [data subdataWithRange:range];
    NSString* chunk = [[NSString alloc] initWithData:chunkData encoding:NSUTF8StringEncoding];
    while (!chunk && range.length > 0) {
        range.length--;
        chunkData = [data subdataWithRange:range];
        chunk = [[NSString alloc] initWithData:chunkData encoding:NSUTF8StringEncoding];
        end = safeOffset + (NSInteger)range.length;
    }
    if (!chunk) chunk = @"";

    NSString* prefix = @"";
    if (safeOffset > 0) {
        NSData* prefixData = [data subdataWithRange:NSMakeRange(0, (NSUInteger)safeOffset)];
        prefix = [[NSString alloc] initWithData:prefixData encoding:NSUTF8StringEncoding] ?: @"";
    }
    NSInteger lineStart = [[prefix componentsSeparatedByString:@"\n"] count];
    NSInteger lineEnd = lineStart + MAX(0, (NSInteger)[[chunk componentsSeparatedByString:@"\n"] count] - 1);

    return @{
        @"chunk": chunk,
        @"offset": @(safeOffset),
        @"nextOffset": @(end),
        @"totalBytes": @(totalBytes),
        @"hasMore": @(end < totalBytes),
        @"lineStart": @(lineStart),
        @"lineEnd": @(lineEnd),
        @"sha256": StableHashForString(text ?: @""),
        @"chunkSha256": StableHashForString(chunk ?: @"")
    };
}

BOOL FileIsWithinSearchReadCap(const std::filesystem::path& path) {
    std::error_code sizeEc;
    auto size = std::filesystem::file_size(path, sizeEc);
    return sizeEc || size <= kMaxSearchFileBytes;
}

NSString* ReadTextFileFromDisk(NSString* path) {
    if (path.length == 0) return nil;
    NSStringEncoding encoding = NSUTF8StringEncoding;
    NSError* error = nil;
    NSString* text = [NSString stringWithContentsOfFile:path usedEncoding:&encoding error:&error];
    if (!text || IsTextBinary(text)) return nil;
    return text;
}

NSString* TextForSearchAtPath(NSString* editorText, NSString* diskPath, NSString** readSourceOut) {
    if (readSourceOut) *readSourceOut = nil;
    if (editorText.length > 0) {
        if (IsTextBinary(editorText)) return nil;
        if (readSourceOut) *readSourceOut = @"editor";
        return editorText;
    }
    NSString* diskText = ReadTextFileFromDisk(diskPath);
    if (diskText) {
        if (readSourceOut) *readSourceOut = @"disk";
        return diskText;
    }
    return nil;
}

NSString* WordAtOffset(NSString* text, NSInteger offset) {
    if (text.length == 0) return @"";
    NSUInteger idx = (NSUInteger)MAX(0, MIN(offset, (NSInteger)text.length - 1));
    NSCharacterSet* wordSet = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"];
    if (![wordSet characterIsMember:[text characterAtIndex:idx]] && idx > 0) {
        idx--;
    }
    if (![wordSet characterIsMember:[text characterAtIndex:idx]]) {
        return @"";
    }
    NSUInteger start = idx;
    while (start > 0 && [wordSet characterIsMember:[text characterAtIndex:start - 1]]) {
        start--;
    }
    NSUInteger end = idx;
    while (end + 1 < text.length && [wordSet characterIsMember:[text characterAtIndex:end + 1]]) {
        end++;
    }
    return [text substringWithRange:NSMakeRange(start, end - start + 1)];
}

NSString* RunGitOutput(NSString* cwd, NSArray<NSString*>* args) {
    if (cwd.length == 0) return @"";
    std::vector<std::string> cppArgs;
    for (NSString* arg in args) {
        cppArgs.push_back([arg UTF8String]);
    }
    using namespace dietcode::platform::macos;
    SubprocessResult res = SubprocessRunner::run("/usr/bin/git", cppArgs, [cwd UTF8String], 10.0);
    return [NSString stringWithUTF8String:res.stdOut.c_str()] ?: @"";
}

BOOL IsTextBinary(NSString* text) {
    if (text == nil) return NO;
    NSUInteger len = [text length];
    for (NSUInteger i = 0; i < len; i++) {
        unichar c = [text characterAtIndex:i];
        if (c == 0) {
            return YES;
        }
    }
    return NO;
}

NSArray<NSString*>* DefaultVerifyCommands(void) {
    return @[@"make test", @"make kernel", @"git diff --check", @"npm test", @"./verify.sh"];
}

NSArray<NSString*>* VerifyCommandsAllowlist(void) {
    NSArray* configured = [[NSUserDefaults standardUserDefaults] stringArrayForKey:@"AgentVerifyCommands"];
    if (configured.count == 0) {
        return DefaultVerifyCommands();
    }
    NSMutableArray* commands = [NSMutableArray array];
    for (NSString* command in configured) {
        if ([command isKindOfClass:[NSString class]] && command.length > 0) {
            [commands addObject:command];
        }
    }
    return commands.count > 0 ? commands : DefaultVerifyCommands();
}

BOOL VerifyCommandIsAllowed(NSString* command, NSArray<NSString*>* allowedCommands) {
    for (NSString* allowed in allowedCommands) {
        if ([command isEqualToString:allowed] || [command hasPrefix:[allowed stringByAppendingString:@" "]]) {
            return YES;
        }
    }
    return NO;
}

NSDictionary* RuntimeError(NSString* code, NSString* message, NSString* stepId, NSString* chip, NSString* phase, BOOL recoverable) {
    NSMutableDictionary* err = [@{
        @"code": code ?: @"internal_error",
        @"message": message ?: @"",
        @"recoverable": @(recoverable)
    } mutableCopy];
    if (stepId.length > 0) err[@"stepId"] = stepId;
    if (chip.length > 0) err[@"chip"] = chip;
    if (phase.length > 0) err[@"phase"] = phase;
    return err;
}

NSInteger PermissionRank(NSString* permission) {
    return dietcode::domain::control::permissionRankFromString(StdStringFromNSString(permission));
}

NSString* CanonicalChipName(NSString* chip) {
    if (chip.length == 0) return @"";
    NSRange at = [chip rangeOfString:@"@"];
    return at.location == NSNotFound ? chip : [chip substringToIndex:at.location];
}

NSArray<NSString*>* DirtyFilePathsFromTabs(NSArray* tabs) {
    NSMutableArray* paths = [NSMutableArray array];
    for (id tab in tabs) {
        BOOL dirty = [[tab valueForKey:@"dirty"] boolValue];
        NSString* path = [tab valueForKey:@"path"];
        if (dirty && path.length > 0) {
            [paths addObject:path];
        }
    }
    return paths;
}

NSDictionary* DiagnosticsSummaryFromProblems(NSArray<NSDictionary*>* problems) {
    NSInteger errors = 0;
    NSInteger warnings = 0;
    NSInteger infos = 0;
    NSMutableSet* files = [NSMutableSet set];

    for (NSDictionary* problem in problems) {
        NSString* severity = [problem[@"severity"] lowercaseString] ?: @"info";
        if ([severity isEqualToString:@"error"]) errors++;
        else if ([severity isEqualToString:@"warning"] || [severity isEqualToString:@"warn"]) warnings++;
        else infos++;

        NSString* path = problem[@"path"];
        if (path.length > 0) {
            [files addObject:path];
        }
    }

    return @{
        @"errors": @(errors),
        @"warnings": @(warnings),
        @"infos": @(infos),
        @"files": @([files count]),
        @"total": @(problems.count)
    };
}

NSArray<NSDictionary*>* ClusterDiagnostics(NSArray<NSDictionary*>* problems) {
    NSMutableDictionary<NSString*, NSMutableDictionary*>* clusters = [NSMutableDictionary dictionary];

    for (NSDictionary* problem in problems) {
        NSString* path = problem[@"path"] ?: @"";
        NSMutableDictionary* cluster = clusters[path];
        if (!cluster) {
            cluster = [@{
                @"path": path,
                @"errors": @0,
                @"warnings": @0,
                @"infos": @0,
                @"problems": [NSMutableArray array]
            } mutableCopy];
            clusters[path] = cluster;
        }

        NSString* severity = [problem[@"severity"] lowercaseString] ?: @"info";
        if ([severity isEqualToString:@"error"]) {
            cluster[@"errors"] = @([cluster[@"errors"] integerValue] + 1);
        } else if ([severity isEqualToString:@"warning"] || [severity isEqualToString:@"warn"]) {
            cluster[@"warnings"] = @([cluster[@"warnings"] integerValue] + 1);
        } else {
            cluster[@"infos"] = @([cluster[@"infos"] integerValue] + 1);
        }
        [cluster[@"problems"] addObject:problem];
    }

    NSMutableArray* result = [[clusters allValues] mutableCopy];
    [result sortUsingComparator:^NSComparisonResult(NSDictionary* a, NSDictionary* b) {
        NSInteger scoreA = [a[@"errors"] integerValue] * 100 + [a[@"warnings"] integerValue] * 10 + [a[@"infos"] integerValue];
        NSInteger scoreB = [b[@"errors"] integerValue] * 100 + [b[@"warnings"] integerValue] * 10 + [b[@"infos"] integerValue];
        if (scoreA == scoreB) {
            return [a[@"path"] compare:b[@"path"]];
        }
        return scoreA > scoreB ? NSOrderedAscending : NSOrderedDescending;
    }];
    return result;
}

NSArray<NSString*>* ContextLines(const std::vector<std::string>& lines, NSInteger start, NSInteger end) {
    NSMutableArray* context = [NSMutableArray array];
    if (lines.empty()) return context;
    start = MAX(start, 0);
    end = MIN(end, (NSInteger)lines.size() - 1);
    for (NSInteger i = start; i <= end; i++) {
        [context addObject:NSStringFromStdString(lines[(size_t)i])];
    }
    return context;
}

NSDictionary* MacControlEnrichReadSearchResult(NSDictionary* result, NSString* methodName) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    BOOL truncated = [result[@"truncated"] boolValue];
    BOOL hasMore = [result[@"hasMore"] boolValue];
    BOOL scanLimit = [result[@"scanLimitReached"] boolValue];
    NSInteger filesSkipped = [result[@"filesSkippedUnreadable"] integerValue]
        + [result[@"filesSkippedBinary"] integerValue]
        + [result[@"filesSkippedOversize"] integerValue]
        + [result[@"filesSkippedExcluded"] integerValue]
        + [result[@"filesSkippedSymlink"] integerValue];
    NSInteger diskReads = [result[@"filesReadFromDisk"] integerValue];
    BOOL complete = !truncated && !hasMore && !scanLimit;
    BOOL partial = !complete || filesSkipped > 0 || diskReads > 0;

    NSMutableDictionary* enriched = [result mutableCopy];
    enriched[@"complete"] = @(complete);
    enriched[@"partial"] = @(partial);

    NSMutableArray* warnings = [NSMutableArray array];
    if (truncated || hasMore) [warnings addObject:@"results_truncated"];
    if (scanLimit) [warnings addObject:@"scan_limit_reached"];
    if (filesSkipped > 0) [warnings addObject:@"files_skipped_during_scan"];
    if (diskReads > 0) [warnings addObject:@"disk_fallback_reads"];
    if (warnings.count > 0) enriched[@"warnings"] = warnings;

    if (diskReads > 0) enriched[@"fallbackUsed"] = @YES;

    if (!complete) {
        enriched[@"nextRecommendedCommand"] = methodName ?: @"workspace.grep";
        if (hasMore && result[@"nextResultOffset"] != [NSNull null]) {
            enriched[@"recoveryHint"] = @"paginate_with_resultOffset";
        } else if (scanLimit) {
            enriched[@"recoveryHint"] = @"narrow_include_globs";
        } else {
            enriched[@"recoveryHint"] = @"raise_maxResults_or_paginate";
        }
    }
    return enriched;
}

NSDictionary* MacControlEnrichPatchValidateResult(NSDictionary* result) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    NSDictionary* validation = result[@"validation"];
    if (![validation isKindOfClass:[NSDictionary class]]) return result;

    BOOL ok = [validation[@"ok"] boolValue];
    BOOL needsConfirm = [validation[@"requiresConfirmation"] boolValue];
    BOOL syntaxDanger = [validation[@"syntaxDanger"] boolValue];
    NSString* readSource = validation[@"readSource"];

    NSMutableDictionary* enriched = [result mutableCopy];
    enriched[@"complete"] = @(ok && !needsConfirm);
    enriched[@"partial"] = @(!ok || needsConfirm || syntaxDanger);

    NSMutableArray* warnings = [NSMutableArray array];
    if (needsConfirm) [warnings addObject:@"requires_confirmation"];
    if (syntaxDanger) [warnings addObject:@"syntax_danger"];
    if ([readSource isEqualToString:@"disk"]) {
        [warnings addObject:@"read_from_disk_fallback"];
        enriched[@"fallbackUsed"] = @YES;
    }
    if (warnings.count > 0) enriched[@"warnings"] = warnings;

    if (ok) {
        enriched[@"nextRecommendedCommand"] = @"patch.apply";
        enriched[@"recoveryHint"] = needsConfirm ? @"set_confirm_true_on_patch_apply" : @"patch_apply_with_expectBeforeHash";
    } else {
        enriched[@"nextRecommendedCommand"] = @"patch.validate";
        enriched[@"recoveryHint"] = @"fix_patch_or_target_path";
    }
    return enriched;
}

NSDictionary* MacControlEnrichPatchApplyResult(NSDictionary* result) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    NSMutableDictionary* enriched = [result mutableCopy];
    BOOL replay = [result[@"idempotentReplay"] boolValue];
    enriched[@"complete"] = @YES;
    enriched[@"partial"] = @(replay);
    if (replay) {
        enriched[@"warnings"] = @[@"idempotent_replay"];
        enriched[@"recoveryHint"] = @"operation_status_if_uncertain";
        enriched[@"nextRecommendedCommand"] = @"operation.status";
    } else {
        enriched[@"nextRecommendedCommand"] = @"workspace.revision";
        enriched[@"recoveryHint"] = @"verify_revision_and_mutation_receipt";
    }
    return enriched;
}

NSDictionary* MacControlEnrichPatchApplyBatchResult(NSDictionary* result) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    BOOL applied = [result[@"applied"] boolValue];
    BOOL dryRun = [result[@"dryRun"] boolValue];
    BOOL replay = [result[@"idempotentReplay"] boolValue];
    NSMutableDictionary* enriched = [result mutableCopy];

    if (dryRun && !applied) {
        enriched[@"complete"] = @NO;
        enriched[@"partial"] = @YES;
        enriched[@"warnings"] = @[@"dry_run_only"];
        enriched[@"nextRecommendedCommand"] = @"patch.applyBatch";
        enriched[@"recoveryHint"] = @"set_dryRun_false_and_confirm";
        return enriched;
    }
    if (!applied) return enriched;

    enriched[@"complete"] = @YES;
    enriched[@"partial"] = @(replay);
    if (replay) {
        enriched[@"warnings"] = @[@"idempotent_replay"];
        enriched[@"recoveryHint"] = @"operation_status_if_uncertain";
        enriched[@"nextRecommendedCommand"] = @"operation.status";
    } else {
        enriched[@"warnings"] = @[];
        enriched[@"nextRecommendedCommand"] = @"workspace.revision";
        enriched[@"recoveryHint"] = @"verify_revision_and_batch_mutation_receipt";
    }
    return enriched;
}

NSDictionary* MacControlEnrichSnapshotResult(NSDictionary* result) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    BOOL truncated = [result[@"truncated"] boolValue];
    NSInteger filesSkipped = [result[@"filesSkipped"] integerValue];
    BOOL complete = result[@"complete"] ? [result[@"complete"] boolValue] : (!truncated && filesSkipped == 0);
    BOOL partial = !complete || filesSkipped > 0;

    NSMutableDictionary* enriched = [result mutableCopy];
    enriched[@"complete"] = @(complete);
    enriched[@"partial"] = @(partial);

    NSMutableArray* warnings = [NSMutableArray array];
    if (truncated) [warnings addObject:@"snapshot_truncated"];
    if (filesSkipped > 0) [warnings addObject:@"files_skipped_in_snapshot"];
    enriched[@"warnings"] = warnings;

    if (!complete) {
        enriched[@"nextRecommendedCommand"] = @"workspace.snapshot";
        enriched[@"recoveryHint"] = truncated ? @"narrow_snapshot_paths_or_raise_maxFiles" : @"retry_snapshot_with_explicit_paths";
    } else {
        enriched[@"nextRecommendedCommand"] = @"workspace.revision";
        enriched[@"recoveryHint"] = @"compare_revision_delta";
    }
    return enriched;
}

NSDictionary* MacControlOperationIdentity(NSDictionary* record) {
    if (![record isKindOfClass:[NSDictionary class]]) return @{};
    NSInteger revisionAfter = [record[@"revisionAfter"] integerValue];
    if (revisionAfter <= 0) revisionAfter = [record[@"revisionId"] integerValue];
    return @{
        @"operationId": record[@"operationId"] ?: @"",
        @"revisionId": @(revisionAfter),
        @"revisionBefore": record[@"revisionBefore"] ?: @0,
        @"revisionAfter": @(revisionAfter),
        @"idempotencyKey": record[@"idempotencyKey"] ?: @"",
        @"workflowId": record[@"workflowId"] ?: @"",
        @"receiptHash": record[@"receiptHash"] ?: @"",
    };
}

NSDictionary* MacControlApplyJournalAuthorityLabels(NSDictionary* result) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    NSMutableDictionary* enriched = [result mutableCopy];
    enriched[@"recordAuthority"] = @"runtime_journal";
    enriched[@"mutationAuthority"] = @"cpp_kernel";
    enriched[@"currentStateAuthority"] = @"workspace_live_read";
    enriched[@"notCurrentFileTruth"] = @YES;
    return enriched;
}

NSDictionary* MacControlEnrichRuntimeSurface(NSDictionary* result, NSString* mode, NSString* nextCommand) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    NSDictionary* labeled = MacControlApplyJournalAuthorityLabels(result);
    NSMutableDictionary* enriched = [labeled mutableCopy];
    if (!enriched) enriched = [NSMutableDictionary dictionary];
    enriched[@"mode"] = mode ?: @"runtime_surface";
    enriched[@"complete"] = result[@"complete"] ?: @YES;
    enriched[@"partial"] = result[@"partial"] ?: @NO;
    if (!enriched[@"warnings"]) enriched[@"warnings"] = @[];
    if (nextCommand.length > 0 && !enriched[@"nextRecommendedCommand"]) {
        enriched[@"nextRecommendedCommand"] = nextCommand;
    }
    if (result[@"correlation"]) enriched[@"correlation"] = result[@"correlation"];
    else if (result[@"operationId"] || result[@"revisionAfter"] || result[@"revisionId"]) {
        enriched[@"correlation"] = MacControlOperationIdentity(result);
    }
    return enriched;
}

NSDictionary* MacControlEnrichRuntimeListResult(NSDictionary* result, NSString* mode, NSString* nextCommand, BOOL truncated) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    NSDictionary* labeled = MacControlApplyJournalAuthorityLabels(result);
    NSMutableDictionary* enriched = [labeled mutableCopy];
    if (!enriched) enriched = [NSMutableDictionary dictionary];
    enriched[@"mode"] = mode ?: @"runtime_list";
    enriched[@"complete"] = @(!truncated);
    enriched[@"partial"] = @(truncated);
    enriched[@"truncated"] = @(truncated);
    NSMutableArray* warnings = [NSMutableArray array];
    if (truncated) [warnings addObject:@"results_truncated"];
    enriched[@"warnings"] = warnings;
    enriched[@"nextRecommendedCommand"] = nextCommand ?: @"runtime.timeline";
    enriched[@"recoveryHint"] = truncated ? @"paginate_with_offset" : @"filter_with_sinceRevision";
    enriched[@"sortOrder"] = @"timestamp_desc";
    return enriched;
}

NSDictionary* MacControlEnrichDiffHunksResult(NSDictionary* result, NSString* methodName) {
    if (![result isKindOfClass:[NSDictionary class]]) return result ?: @{};
    BOOL truncated = [result[@"truncated"] boolValue];
    BOOL hasMore = [result[@"hasMoreHunks"] boolValue];
    BOOL complete = !truncated && !hasMore;
    BOOL partial = !complete;

    NSMutableDictionary* enriched = [result mutableCopy];
    enriched[@"complete"] = @(complete);
    enriched[@"partial"] = @(partial);

    NSMutableArray* warnings = [NSMutableArray array];
    if (truncated) [warnings addObject:@"hunks_truncated"];
    if (hasMore) [warnings addObject:@"more_hunks_available"];
    enriched[@"warnings"] = warnings;

    if (!complete) {
        enriched[@"nextRecommendedCommand"] = methodName ?: @"diff.hunks";
        enriched[@"recoveryHint"] = hasMore ? @"paginate_with_hunkOffset" : @"raise_maxHunks";
    } else {
        enriched[@"nextRecommendedCommand"] = @"patch.validate";
        enriched[@"recoveryHint"] = @"inspect_hunks_before_patch";
    }
    return enriched;
}
