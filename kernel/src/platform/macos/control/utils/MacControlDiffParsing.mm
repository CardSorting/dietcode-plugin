#import "MacControlDiffParsing.hpp"

namespace dietcode::platform::macos {

NSArray<NSDictionary*>* HunkSummariesFromPatch(NSString* patch) {
    NSMutableArray* hunks = [NSMutableArray array];
    NSError* regErr = nil;
    NSRegularExpression* hunkRegex = [NSRegularExpression regularExpressionWithPattern:@"^@@ -(\\d+),?(\\d*) \\+(\\d+),?(\\d*) @@" options:0 error:&regErr];
    NSArray<NSString*>* lines = [patch componentsSeparatedByString:@"\n"];
    NSMutableDictionary* current = nil;
    NSInteger added = 0;
    NSInteger removed = 0;

    for (NSString* line in lines) {
        NSTextCheckingResult* match = [hunkRegex firstMatchInString:line options:0 range:NSMakeRange(0, line.length)];
        if (match) {
            if (current) {
                current[@"addedLines"] = @(added);
                current[@"removedLines"] = @(removed);
                [hunks addObject:current];
            }
            NSString* oldStart = [line substringWithRange:[match rangeAtIndex:1]];
            NSString* oldCount = [match rangeAtIndex:2].location == NSNotFound ? @"" : [line substringWithRange:[match rangeAtIndex:2]];
            NSString* newStart = [line substringWithRange:[match rangeAtIndex:3]];
            NSString* newCount = [match rangeAtIndex:4].location == NSNotFound ? @"" : [line substringWithRange:[match rangeAtIndex:4]];
            current = [@{
                @"oldStart": @([oldStart integerValue]),
                @"oldLines": @(oldCount.length > 0 ? [oldCount integerValue] : 1),
                @"newStart": @([newStart integerValue]),
                @"newLines": @(newCount.length > 0 ? [newCount integerValue] : 1),
                @"header": line
            } mutableCopy];
            added = 0;
            removed = 0;
        } else if (current) {
            if ([line hasPrefix:@"+"] && ![line hasPrefix:@"+++"]) added++;
            else if ([line hasPrefix:@"-"] && ![line hasPrefix:@"---"]) removed++;
        }
    }

    if (current) {
        current[@"addedLines"] = @(added);
        current[@"removedLines"] = @(removed);
        [hunks addObject:current];
    }
    return hunks;
}

NSString* CleanUnifiedDiffPath(NSString* rawPath) {
    NSString* path = [rawPath stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] ?: @"";
    NSRange tab = [path rangeOfString:@"\t"];
    if (tab.location != NSNotFound) {
        path = [path substringToIndex:tab.location];
    }
    if ([path hasPrefix:@"\""] && [path hasSuffix:@"\""] && path.length >= 2) {
        path = [path substringWithRange:NSMakeRange(1, path.length - 2)];
    }
    if ([path isEqualToString:@"/dev/null"]) return path;
    if ([path hasPrefix:@"a/"] || [path hasPrefix:@"b/"]) {
        return [path substringFromIndex:2];
    }
    return path;
}

NSDictionary* UnifiedDiffHunksResponse(NSString* diffText, NSInteger maxHunks, NSInteger hunkOffset, BOOL includeLines, NSInteger maxLinesPerHunk) {
    NSInteger limit = maxHunks > 0 ? MIN(maxHunks, 5000) : 500;
    NSInteger offset = MAX(hunkOffset, 0);
    NSInteger lineLimit = maxLinesPerHunk > 0 ? MIN(maxLinesPerHunk, 1000) : 200;
    NSMutableArray* files = [NSMutableArray array];
    NSError* regErr = nil;
    NSRegularExpression* hunkRegex = [NSRegularExpression regularExpressionWithPattern:@"^@@ -(\\d+),?(\\d*) \\+(\\d+),?(\\d*) @@" options:0 error:&regErr];
    NSArray<NSString*>* lines = [diffText componentsSeparatedByString:@"\n"];
    NSUInteger lineCount = lines.count;
    if (diffText.length > 0 && [diffText hasSuffix:@"\n"] && lineCount > 0) {
        lineCount--;
    }

    __block NSMutableDictionary* currentFile = nil;
    __block NSMutableArray* currentHunks = nil;
    __block NSMutableDictionary* currentHunk = nil;
    __block NSMutableArray* currentLineRows = nil;
    __block NSInteger added = 0;
    __block NSInteger removed = 0;
    __block NSInteger context = 0;
    __block NSInteger oldLineCursor = 0;
    __block NSInteger newLineCursor = 0;
    __block NSInteger currentHunkTotalLineRows = 0;
    __block NSInteger currentHunkReturnedLineRows = 0;
    __block BOOL currentHunkLinesTruncated = NO;
    __block BOOL collectCurrentLines = NO;
    __block NSInteger totalFiles = 0;
    __block NSInteger totalHunks = 0;
    __block NSInteger returnedHunks = 0;
    __block NSInteger totalAdded = 0;
    __block NSInteger totalRemoved = 0;
    __block BOOL truncated = NO;
    __block NSInteger currentFileTotalHunks = 0;
    __block NSInteger currentFileOmittedBefore = 0;
    __block NSInteger currentFileOmittedAfter = 0;
    __block NSInteger currentFileAdded = 0;
    __block NSInteger currentFileRemoved = 0;

    void (^ensureFile)(NSInteger) = ^(NSInteger lineNumber) {
        if (currentFile) return;
        currentHunks = [NSMutableArray array];
        currentFile = [@{
            @"oldPath": @"",
            @"newPath": @"",
            @"fileHeader": @"",
            @"lineStart": @(lineNumber)
        } mutableCopy];
    };

    void (^finishHunk)(void) = ^{
        if (!currentHunk) return;
        currentHunk[@"addedLines"] = @(added);
        currentHunk[@"removedLines"] = @(removed);
        currentHunk[@"contextLines"] = @(context);
        if (includeLines) {
            currentHunk[@"lines"] = currentLineRows ?: @[];
            currentHunk[@"totalLineRows"] = @(currentHunkTotalLineRows);
            currentHunk[@"returnedLineRows"] = @(currentHunkReturnedLineRows);
            currentHunk[@"linesTruncated"] = @(currentHunkLinesTruncated);
        }
        NSInteger hunkIndex = totalHunks;
        currentHunk[@"hunkIndex"] = @(hunkIndex);
        currentHunk[@"hunkOrdinal"] = @(hunkIndex + 1);
        totalHunks++;
        currentFileTotalHunks++;
        totalAdded += added;
        totalRemoved += removed;
        currentFileAdded += added;
        currentFileRemoved += removed;
        if (hunkIndex < offset) {
            currentFileOmittedBefore++;
        } else if (returnedHunks < limit) {
            [currentHunks addObject:currentHunk];
            returnedHunks++;
        } else {
            truncated = YES;
            currentFileOmittedAfter++;
        }
        currentHunk = nil;
        currentLineRows = nil;
        added = 0;
        removed = 0;
        context = 0;
        oldLineCursor = 0;
        newLineCursor = 0;
        currentHunkTotalLineRows = 0;
        currentHunkReturnedLineRows = 0;
        currentHunkLinesTruncated = NO;
        collectCurrentLines = NO;
    };

    void (^finishFile)(void) = ^{
        if (!currentFile) return;
        finishHunk();
        BOOL hasFileEvidence = currentFileTotalHunks > 0 || [currentFile[@"fileHeader"] length] > 0 || [currentFile[@"oldPath"] length] > 0 || [currentFile[@"newPath"] length] > 0;
        if (hasFileEvidence) {
            totalFiles++;
        }
        BOOL hasMetadataOnlyEvidence = currentFileTotalHunks == 0 && hasFileEvidence;
        if (currentHunks.count > 0 || hasMetadataOnlyEvidence) {
            currentFile[@"hunks"] = currentHunks ?: @[];
            currentFile[@"returnedHunks"] = @(currentHunks.count);
            currentFile[@"totalHunks"] = @(currentFileTotalHunks);
            currentFile[@"omittedBefore"] = @(currentFileOmittedBefore);
            currentFile[@"omittedAfter"] = @(currentFileOmittedAfter);
            currentFile[@"addedLines"] = @(currentFileAdded);
            currentFile[@"removedLines"] = @(currentFileRemoved);
            currentFile[@"truncated"] = @(currentFileOmittedAfter > 0);
            [files addObject:currentFile];
        }
        currentFile = nil;
        currentHunks = nil;
        currentFileTotalHunks = 0;
        currentFileOmittedBefore = 0;
        currentFileOmittedAfter = 0;
        currentFileAdded = 0;
        currentFileRemoved = 0;
    };

    for (NSUInteger index = 0; index < lineCount; index++) {
        NSString* line = lines[index] ?: @"";
        NSInteger lineNumber = (NSInteger)index + 1;
        if ([line hasPrefix:@"diff --git "]) {
            finishFile();
            ensureFile(lineNumber);
            currentFile[@"fileHeader"] = line;
            NSArray<NSString*>* parts = [line componentsSeparatedByString:@" "];
            if (parts.count >= 4) {
                currentFile[@"oldPath"] = CleanUnifiedDiffPath(parts[2]);
                currentFile[@"newPath"] = CleanUnifiedDiffPath(parts[3]);
            }
            continue;
        }
        if ([line hasPrefix:@"--- "]) {
            ensureFile(lineNumber);
            currentFile[@"oldPath"] = CleanUnifiedDiffPath([line substringFromIndex:4]);
            currentFile[@"oldHeaderLine"] = @(lineNumber);
            continue;
        }
        if ([line hasPrefix:@"+++ "]) {
            ensureFile(lineNumber);
            currentFile[@"newPath"] = CleanUnifiedDiffPath([line substringFromIndex:4]);
            currentFile[@"newHeaderLine"] = @(lineNumber);
            continue;
        }

        NSTextCheckingResult* match = [hunkRegex firstMatchInString:line options:0 range:NSMakeRange(0, line.length)];
        if (match) {
            ensureFile(lineNumber);
            finishHunk();
            NSString* oldStart = [line substringWithRange:[match rangeAtIndex:1]];
            NSString* oldCount = [match rangeAtIndex:2].location == NSNotFound ? @"" : [line substringWithRange:[match rangeAtIndex:2]];
            NSString* newStart = [line substringWithRange:[match rangeAtIndex:3]];
            NSString* newCount = [match rangeAtIndex:4].location == NSNotFound ? @"" : [line substringWithRange:[match rangeAtIndex:4]];
            currentHunk = [@{
                @"header": line,
                @"lineStart": @(lineNumber),
                @"lineEnd": @(lineNumber),
                @"oldStart": @([oldStart integerValue]),
                @"oldLines": @(oldCount.length > 0 ? [oldCount integerValue] : 1),
                @"newStart": @([newStart integerValue]),
                @"newLines": @(newCount.length > 0 ? [newCount integerValue] : 1)
            } mutableCopy];
            oldLineCursor = [oldStart integerValue];
            newLineCursor = [newStart integerValue];
            NSInteger candidateHunkIndex = totalHunks;
            collectCurrentLines = includeLines && candidateHunkIndex >= offset && candidateHunkIndex < offset + limit;
            currentLineRows = collectCurrentLines ? [NSMutableArray array] : nil;
            currentHunkTotalLineRows = 0;
            currentHunkReturnedLineRows = 0;
            currentHunkLinesTruncated = NO;
            continue;
        }

        if (currentHunk) {
            currentHunk[@"lineEnd"] = @(lineNumber);
            NSString* kind = @"meta";
            id oldLineValue = [NSNull null];
            id newLineValue = [NSNull null];
            NSString* text = line;
            if ([line hasPrefix:@"+"] && ![line hasPrefix:@"+++"]) {
                kind = @"add";
                newLineValue = @(newLineCursor);
                text = [line substringFromIndex:1];
                added++;
                newLineCursor++;
            } else if ([line hasPrefix:@"-"] && ![line hasPrefix:@"---"]) {
                kind = @"remove";
                oldLineValue = @(oldLineCursor);
                text = [line substringFromIndex:1];
                removed++;
                oldLineCursor++;
            } else if ([line hasPrefix:@" "]) {
                kind = @"context";
                oldLineValue = @(oldLineCursor);
                newLineValue = @(newLineCursor);
                text = [line substringFromIndex:1];
                context++;
                oldLineCursor++;
                newLineCursor++;
            } else if ([line hasPrefix:@"\\"]) {
                kind = @"meta";
            }
            if (includeLines && collectCurrentLines) {
                currentHunkTotalLineRows++;
                if (currentHunkReturnedLineRows < lineLimit) {
                    [currentLineRows addObject:@{
                        @"diffLine": @(lineNumber),
                        @"kind": kind,
                        @"oldLine": oldLineValue,
                        @"newLine": newLineValue,
                        @"raw": line,
                        @"text": text
                    }];
                    currentHunkReturnedLineRows++;
                } else {
                    currentHunkLinesTruncated = YES;
                }
            }
        }
    }

    finishFile();
    BOOL hasMoreHunks = offset + returnedHunks < totalHunks;
    return @{
        @"files": files,
        @"totalFiles": @(totalFiles),
        @"totalHunks": @(totalHunks),
        @"returnedHunks": @(returnedHunks),
        @"totalAddedLines": @(totalAdded),
        @"totalRemovedLines": @(totalRemoved),
        @"maxHunks": @(limit),
        @"hunkOffset": @(offset),
        @"nextHunkOffset": hasMoreHunks ? @(offset + returnedHunks) : [NSNull null],
        @"hasMoreHunks": @(hasMoreHunks),
        @"includeLines": @(includeLines),
        @"maxLinesPerHunk": @(lineLimit),
        @"truncated": @(truncated)
    };
}

NSArray<NSNumber*>* ModifiedNewLinesFromPatch(NSString* patch) {
    NSMutableArray<NSNumber*>* linesOut = [NSMutableArray array];
    NSError* regErr = nil;
    NSRegularExpression* hunkRegex = [NSRegularExpression regularExpressionWithPattern:@"^@@ -(\\d+),?(\\d*) \\+(\\d+),?(\\d*) @@" options:0 error:&regErr];
    NSInteger currentNewLine = 0;
    for (NSString* line in [patch componentsSeparatedByString:@"\n"]) {
        NSTextCheckingResult* match = [hunkRegex firstMatchInString:line options:0 range:NSMakeRange(0, line.length)];
        if (match) {
            currentNewLine = [[line substringWithRange:[match rangeAtIndex:3]] integerValue];
            continue;
        }
        if (currentNewLine <= 0) continue;
        if ([line hasPrefix:@"+"] && ![line hasPrefix:@"+++"]) {
            [linesOut addObject:@(currentNewLine)];
            currentNewLine++;
        } else if ([line hasPrefix:@"-"] && ![line hasPrefix:@"---"]) {
            [linesOut addObject:@(currentNewLine)];
        } else if ([line hasPrefix:@" "]) {
            currentNewLine++;
        }
    }
    return linesOut;
}

NSArray<NSString*>* AffectedSymbolsForPatch(NSString* patch, NSArray<NSDictionary*>* symbols) {
    NSArray<NSNumber*>* modifiedLines = ModifiedNewLinesFromPatch(patch);
    NSMutableSet<NSString*>* names = [NSMutableSet set];
    for (NSDictionary* sym in symbols ?: @[]) {
        NSInteger startLine = [sym[@"line"] integerValue];
        NSInteger endLine = [sym[@"endLine"] integerValue];
        for (NSNumber* line in modifiedLines) {
            NSInteger value = [line integerValue];
            if (value >= startLine && value <= endLine && [sym[@"name"] length] > 0) {
                [names addObject:sym[@"name"]];
                break;
            }
        }
    }
    return [[names allObjects] sortedArrayUsingSelector:@selector(compare:)];
}

NSInteger ChangedLineCountFromHunks(NSArray<NSDictionary*>* hunks) {
    NSInteger count = 0;
    for (NSDictionary* hunk in hunks) {
        count += [hunk[@"addedLines"] integerValue] + [hunk[@"removedLines"] integerValue];
    }
    return count;
}

NSDictionary* PatchPreviewSummary(NSString* patch) {
    NSArray<NSDictionary*>* hunks = HunkSummariesFromPatch(patch ?: @"");
    NSMutableArray* previews = [NSMutableArray array];
    for (NSDictionary* hunk in hunks) {
        NSInteger start = [hunk[@"newStart"] integerValue];
        NSInteger end = start + MAX([hunk[@"newLines"] integerValue] - 1, 0);
        [previews addObject:@{
            @"startLine": @(start),
            @"endLine": @(end),
            @"preview": hunk[@"header"] ?: @"",
            @"addedLines": hunk[@"addedLines"] ?: @0,
            @"removedLines": hunk[@"removedLines"] ?: @0
        }];
    }
    NSInteger added = 0;
    NSInteger removed = 0;
    for (NSDictionary* hunk in hunks) {
        added += [hunk[@"addedLines"] integerValue];
        removed += [hunk[@"removedLines"] integerValue];
    }
    return @{
        @"addedLines": @(added),
        @"removedLines": @(removed),
        @"changedLines": @(added + removed),
        @"hunks": previews
    };
}

} // namespace dietcode::platform::macos
