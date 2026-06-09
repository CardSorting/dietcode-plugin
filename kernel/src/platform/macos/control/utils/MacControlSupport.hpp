#pragma once

#import <Cocoa/Cocoa.h>

#include <filesystem>
#include <string>
#include <vector>

#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"
#import "MacControlDiffParsing.hpp"

extern const NSUInteger kMaxRequestBytes;
extern const NSUInteger kMaxResponseBytes;
extern const NSInteger kMaxGrepResults;
extern const NSUInteger kMaxFileTextBytes;
extern const NSUInteger kMaxPatchBytesBeforeConfirmation;
extern const NSUInteger kMaxPatchBytes;
extern const NSInteger kMaxBatchPatchCount;
extern const NSUInteger kMaxChunkPreviewLength;
extern const NSInteger kMaxSearchDepth;
extern const NSInteger kMaxSearchScanFiles;
extern const NSUInteger kMaxSearchFileBytes;
extern const NSInteger kMaxPlanSteps;
extern const NSInteger kMaxActiveCombos;
extern const NSInteger kMaxActiveConnections;
extern const NSInteger kMaxPendingRequestsPerConnection;
extern const NSInteger kMaxMalformedRequestsPerConnection;
extern const NSInteger kMaxNestedCallWaitSeconds;
extern const NSInteger kSocketListenBacklog;
extern const NSUInteger kMaxRuntimeDiagnosticLogBytes;
extern const NSUInteger kMaxAuditLogBytes;
extern const NSUInteger kMaxFailureBundleBytes;
extern NSString* const kDietCodeAppVersion;
extern NSString* const kDietCodeTerminalOutputDidUpdateNotification;

NSString* NSStringFromStdString(const std::string& value);
std::string StdStringFromNSString(NSString* value);

// Moved to MacControlPathSecurity.hpp
// NSString* AbsolutePathForRPCPath(NSString* path, NSString* workspace);
// BOOL PathIsInsideWorkspace(NSString* path, NSString* workspace);
// BOOL AnyPatternMatches(NSArray<NSString*>* patterns, const std::string& relPath, const std::string& filename);
// BOOL ShouldSkipSearchPath(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* includes, NSArray<NSString*>* excludes);
// BOOL ShouldPruneSearchDirectory(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* excludes);

// Moved to MacControlDiffParsing.hpp
// NSArray<NSDictionary*>* HunkSummariesFromPatch(NSString* patch);
// NSString* CleanUnifiedDiffPath(NSString* rawPath);
// NSDictionary* UnifiedDiffHunksResponse(NSString* diffText, NSInteger maxHunks, NSInteger hunkOffset, BOOL includeLines, NSInteger maxLinesPerHunk);
// NSArray<NSNumber*>* ModifiedNewLinesFromPatch(NSString* patch);
// NSArray<NSString*>* AffectedSymbolsForPatch(NSString* patch, NSArray<NSDictionary*>* symbols);
// NSInteger ChangedLineCountFromHunks(NSArray<NSDictionary*>* hunks);
// NSDictionary* PatchPreviewSummary(NSString* patch);

NSArray<NSString*>* LinesFromText(NSString* text);
std::string LowerASCII(std::string value);
NSArray<NSDictionary*>* LiteralMatchSpans(const std::string& line, const std::string& query, BOOL caseSensitive);
NSString* TextForLineRange(NSArray<NSString*>* lines, NSInteger startLine, NSInteger endLine);
NSDictionary* TextChunkResponse(NSString* text, NSInteger offset, NSInteger maxBytes);
BOOL FileIsWithinSearchReadCap(const std::filesystem::path& path);
NSString* ReadTextFileFromDisk(NSString* path);
NSString* TextForSearchAtPath(NSString* editorText, NSString* diskPath, NSString** readSourceOut);
NSString* WordAtOffset(NSString* text, NSInteger offset);
NSString* RunGitOutput(NSString* cwd, NSArray<NSString*>* args);
BOOL IsTextBinary(NSString* text);

// Moved to MacControlSerialization.hpp
// NSString* ISODateString(NSDate* date);
// NSString* StableHashForData(NSData* data);
// NSString* StableHashForString(NSString* text);
// NSString* RequestIdString(id value);
// NSString* SHA256ForData(NSData* data);

NSArray<NSString*>* DefaultVerifyCommands(void);
NSArray<NSString*>* VerifyCommandsAllowlist(void);
BOOL VerifyCommandIsAllowed(NSString* command, NSArray<NSString*>* allowedCommands);
NSDictionary* RuntimeError(NSString* code, NSString* message, NSString* stepId, NSString* chip, NSString* phase, BOOL recoverable);
NSInteger PermissionRank(NSString* permission);
NSString* CanonicalChipName(NSString* chip);
NSArray<NSString*>* DirtyFilePathsFromTabs(NSArray* tabs);
NSDictionary* DiagnosticsSummaryFromProblems(NSArray<NSDictionary*>* problems);
NSArray<NSDictionary*>* ClusterDiagnostics(NSArray<NSDictionary*>* problems);
NSArray<NSString*>* ContextLines(const std::vector<std::string>& lines, NSInteger start, NSInteger end);

NSDictionary* MacControlEnrichReadSearchResult(NSDictionary* result, NSString* methodName);
NSDictionary* MacControlEnrichPatchValidateResult(NSDictionary* result);
NSDictionary* MacControlEnrichPatchApplyResult(NSDictionary* result);
NSDictionary* MacControlEnrichPatchApplyBatchResult(NSDictionary* result);
NSDictionary* MacControlEnrichSnapshotResult(NSDictionary* result);
NSDictionary* MacControlEnrichDiffHunksResult(NSDictionary* result, NSString* methodName);

NSDictionary* MacControlOperationIdentity(NSDictionary* record);
NSDictionary* MacControlApplyJournalAuthorityLabels(NSDictionary* result);
NSDictionary* MacControlEnrichRuntimeSurface(NSDictionary* result, NSString* mode, NSString* nextCommand);
NSDictionary* MacControlEnrichRuntimeListResult(NSDictionary* result, NSString* mode, NSString* nextCommand, BOOL truncated);

using namespace dietcode::platform::macos;
