#import "WorkspaceAnalysisService.hpp"
#include "filesystem/PathUtils.hpp"
#include <filesystem>
#include <fstream>
#include <vector>
#include <string>
#include <algorithm>
#include <fnmatch.h>

#ifndef FNM_CASEFOLD
#define FNM_CASEFOLD 0
#endif

using namespace dietcode::filesystem;

namespace {
static const NSInteger kMaxAnalysisDepth = 10;
static const NSInteger kMaxAnalysisFiles = 10000;
static const unsigned long long kMaxAnalysisReadBytes = 2 * 1024 * 1024;

NSString* NSStringFromStd(const std::string& str) {
    return [NSString stringWithUTF8String:str.c_str()] ?: @"";
}
std::string StdFromNSString(NSString* str) {
    return std::string([str UTF8String] ?: "");
}

bool isSkippedDirName(const std::string& filename) {
    return filename == ".git" || filename == "node_modules" || filename == "build" ||
           filename == "dist" || filename == "DerivedData" || filename == ".next" ||
           filename == "__pycache__";
}

bool fileWithinReadCap(const std::filesystem::path& p) {
    std::error_code ec;
    auto size = std::filesystem::file_size(p, ec);
    return ec || size <= kMaxAnalysisReadBytes;
}
}

@implementation DietCodeWorkspaceAnalysisService

+ (NSDictionary*)summaryOfWorkspace:(NSString*)ws
                          openFiles:(NSArray<NSString*>*)openFiles
                      modifiedFiles:(NSArray<NSString*>*)modifiedFiles
                        diagnostics:(NSDictionary*)diags
                          gitBranch:(NSString*)branch {

    NSMutableDictionary* result = [NSMutableDictionary dictionary];
    if (ws.length == 0) return result;

    std::filesystem::path folder([ws UTF8String]);
    NSMutableDictionary* languages = [NSMutableDictionary dictionary];
    NSInteger totalFiles = 0;
    unsigned long long totalSize = 0;

    traverseDirectory(folder, [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion, bool& stop) {
        std::error_code ec;
        std::filesystem::path p = entry.path();
        std::string filename = p.filename().string();

        if (entry.is_directory(ec)) {
            if (depth >= kMaxAnalysisDepth || isSkippedDirName(filename)) {
                skipRecursion = true;
            }
            return;
        }

        if (!entry.is_regular_file()) return;
        if (++totalFiles > kMaxAnalysisFiles) {
            stop = true;
            return;
        }


        std::error_code sizeEc;
        auto size = std::filesystem::file_size(p, sizeEc);
        if (!sizeEc) totalSize += size;

        std::string ext = p.extension().string();
        if (ext.length() > 1 && ext[0] == '.') {
            ext = ext.substr(1);
            std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);

            NSString* extKey = NSStringFromStd(ext);
            languages[extKey] = @([languages[extKey] integerValue] + 1);
        }
    });

    result[@"root"] = ws;
    result[@"languages"] = languages;
    result[@"totalFiles"] = @(totalFiles);
    result[@"openFiles"] = openFiles ?: @[];
    result[@"modifiedFiles"] = modifiedFiles ?: @[];
    result[@"diagnostics"] = diags ?: @{ @"errors": @0, @"warnings": @0 };
    result[@"branch"] = branch ?: @"";
    result[@"workspaceSize"] = @(totalSize);

    return result;
}

+ (NSDictionary*)fileSummaryForPath:(NSString*)path symbolsCount:(NSInteger)symCount {
    NSMutableDictionary* result = [NSMutableDictionary dictionary];
    if (path.length == 0 || ![[NSFileManager defaultManager] fileExistsAtPath:path]) {
        return result;
    }

    std::ifstream file([path UTF8String]);
    if (!file.is_open()) return result;

    NSInteger lineCount = 0;
    NSInteger todoCount = 0;
    NSMutableArray* includes = [NSMutableArray array];

    std::string line;
    while (std::getline(file, line)) {
        lineCount++;

        // Count TODOs
        std::string lowerLine = line;
        std::transform(lowerLine.begin(), lowerLine.end(), lowerLine.begin(), ::tolower);
        if (lowerLine.find("todo") != std::string::npos || lowerLine.find("fixme") != std::string::npos || lowerLine.find("xxx") != std::string::npos) {
            todoCount++;
        }

        // Simple C++/Python/JS imports extraction
        if (line.find("#include") == 0) {
            size_t start = line.find("<");
            size_t end = line.find(">");
            if (start == std::string::npos || end == std::string::npos) {
                start = line.find("\"");
                end = line.rfind("\"");
            }
            if (start != std::string::npos && end != std::string::npos && end > start) {
                [includes addObject:NSStringFromStd(line.substr(start + 1, end - start - 1))];
            }
        } else if (line.find("import ") == 0 || line.find("from ") == 0) {
            [includes addObject:NSStringFromStd(line)];
        } else if (line.find("require(") != std::string::npos) {
            [includes addObject:NSStringFromStd(line)];
        }
    }

    NSDictionary* attrs = [[NSFileManager defaultManager] attributesOfItemAtPath:path error:nil];
    NSDate* modDate = attrs.fileModificationDate;

    result[@"path"] = path;
    result[@"symbolCount"] = @(symCount);
    result[@"todos"] = @(todoCount);
    result[@"includes"] = includes;
    result[@"lines"] = @(lineCount);
    result[@"lastModified"] = @((long long)[modDate timeIntervalSince1970]);

    return result;
}

+ (NSArray<NSString*>*)relatedFilesForPath:(NSString*)path workspace:(NSString*)ws {
    NSMutableArray* result = [NSMutableArray array];
    if (path.length == 0 || ws.length == 0) return result;

    NSString* filename = [[path lastPathComponent] stringByDeletingPathExtension];
    std::filesystem::path folder([ws UTF8String]);

    NSInteger scannedFiles = 0;
    traverseDirectory(folder, [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion, bool& stop) {
        std::error_code ec;
        std::filesystem::path p = entry.path();
        std::string filenameStr = p.filename().string();
        
        if (entry.is_directory(ec)) {
            if (depth >= kMaxAnalysisDepth || isSkippedDirName(filenameStr)) {
                skipRecursion = true;
            }
            return;
        }
        
        if (!entry.is_regular_file()) return;
        if (++scannedFiles > kMaxAnalysisFiles) {
            stop = true;
            return;
        }
        if (!fileWithinReadCap(p)) return;

        NSString* currentPath = NSStringFromStd(p.string());
        if ([currentPath isEqualToString:path]) return;

        // Heuristic: check if current file includes this filename or contains it
        std::ifstream file(p.string());
        if (!file.is_open()) return;

        std::string line;
        bool related = false;
        std::string targetSub = [filename UTF8String];

        while (std::getline(file, line)) {
            if (line.find(targetSub) != std::string::npos) {
                related = true;
                break;
            }
        }

        if (related) {
            [result addObject:currentPath];
        }
    });

    return result;
}

+ (NSArray<NSDictionary*>*)searchRankedForQuery:(NSString*)query
                                      workspace:(NSString*)ws
                                      openFiles:(NSArray<NSString*>*)openFiles
                                    recentFiles:(NSArray<NSString*>*)recentFiles
                                        include:(NSArray<NSString*>*)includes
                                        exclude:(NSArray<NSString*>*)excludes
                                  caseSensitive:(BOOL)caseSensitive {

    NSMutableArray* rankedFiles = [NSMutableArray array];
    if (ws.length == 0 || query.length == 0) return rankedFiles;

    std::filesystem::path folder([ws UTF8String]);
    std::string stdQuery = StdFromNSString(query);
    if (!caseSensitive) {
        std::transform(stdQuery.begin(), stdQuery.end(), stdQuery.begin(), ::tolower);
    }

    NSInteger scannedFiles = 0;
    traverseDirectory(folder, [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion, bool& stop) {
        std::error_code ec;
        std::filesystem::path p = entry.path();
        std::string filename = p.filename().string();
        std::string relPath = std::filesystem::relative(p, folder, ec).string();
        
        if (entry.is_directory(ec)) {
            if (depth >= kMaxAnalysisDepth || isSkippedDirName(filename)) {
                skipRecursion = true;
            }
            return;
        }
        
        if (!entry.is_regular_file()) return;
        if (++scannedFiles > kMaxAnalysisFiles) {
            stop = true;
            return;
        }
        if (!fileWithinReadCap(p)) return;

        // Glob matching exclusions
        BOOL skip = false;
        for (NSString* ex in excludes) {
            if (fnmatch([ex UTF8String], relPath.c_str(), FNM_CASEFOLD) == 0 ||
                fnmatch([ex UTF8String], filename.c_str(), FNM_CASEFOLD) == 0) {
                skip = true;
                break;
            }
        }
        if (skip) return;

        // Glob matching inclusions
        if (includes.count > 0) {
            BOOL matchesInclude = NO;
            for (NSString* inc in includes) {
                if (fnmatch([inc UTF8String], relPath.c_str(), FNM_CASEFOLD) == 0 ||
                    fnmatch([inc UTF8String], filename.c_str(), FNM_CASEFOLD) == 0) {
                    matchesInclude = YES;
                    break;
                }
            }
            if (!matchesInclude) return;
        }

        std::ifstream file(p.string());
        if (!file.is_open()) return;

        std::vector<std::string> fileLines;
        std::string lineText;
        while (std::getline(file, lineText)) {
            fileLines.push_back(lineText);
        }

        NSMutableArray* matches = [NSMutableArray array];
        for (size_t i = 0; i < fileLines.size(); i++) {
            std::string currentLine = fileLines[i];
            size_t matchPos = std::string::npos;

            if (caseSensitive) {
                matchPos = currentLine.find(stdQuery);
            } else {
                std::string lowerLine = currentLine;
                std::transform(lowerLine.begin(), lowerLine.end(), lowerLine.begin(), ::tolower);
                matchPos = lowerLine.find(stdQuery);
            }

            if (matchPos != std::string::npos) {
                // Extract context before (up to 2 lines)
                NSMutableArray* contextBefore = [NSMutableArray array];
                size_t startB = (i >= 2) ? i - 2 : 0;
                for (size_t b = startB; b < i; b++) {
                    [contextBefore addObject:NSStringFromStd(fileLines[b])];
                }

                // Extract context after (up to 2 lines)
                NSMutableArray* contextAfter = [NSMutableArray array];
                size_t endA = std::min(fileLines.size() - 1, i + 2);
                for (size_t a = i + 1; a <= endA; a++) {
                    [contextAfter addObject:NSStringFromStd(fileLines[a])];
                }

                [matches addObject:@{
                    @"line": @(i + 1),
                    @"column": @(matchPos + 1),
                    @"preview": NSStringFromStd(currentLine),
                    @"contextBefore": contextBefore,
                    @"contextAfter": contextAfter
                }];
            }
        }

        if (matches.count > 0) {
            double score = matches.count;
            NSString* absPath = NSStringFromStd(p.string());

            // Boost scores
            if ([openFiles containsObject:absPath]) {
                score += 5.0;
            }
            if ([recentFiles containsObject:absPath]) {
                score += 2.0;
            }

            [rankedFiles addObject:@{
                @"path": NSStringFromStd(relPath),
                @"score": @(score),
                @"matches": matches
            }];
        }
    });

    // Sort files by score descending
    [rankedFiles sortUsingComparator:^NSComparisonResult(NSDictionary* obj1, NSDictionary* obj2) {
        return [obj2[@"score"] compare:obj1[@"score"]];
    }];

    return rankedFiles;
}

@end
