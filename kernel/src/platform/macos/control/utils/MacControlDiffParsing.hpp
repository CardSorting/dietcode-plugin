#pragma once

#import <Cocoa/Cocoa.h>

namespace dietcode::platform::macos {

NSArray<NSDictionary*>* HunkSummariesFromPatch(NSString* patch);
NSString* CleanUnifiedDiffPath(NSString* rawPath);
NSDictionary* UnifiedDiffHunksResponse(NSString* diffText, NSInteger maxHunks, NSInteger hunkOffset, BOOL includeLines, NSInteger maxLinesPerHunk);
NSArray<NSNumber*>* ModifiedNewLinesFromPatch(NSString* patch);
NSArray<NSString*>* AffectedSymbolsForPatch(NSString* patch, NSArray<NSDictionary*>* symbols);
NSInteger ChangedLineCountFromHunks(NSArray<NSDictionary*>* hunks);
NSDictionary* PatchPreviewSummary(NSString* patch);

} // namespace dietcode::platform::macos
