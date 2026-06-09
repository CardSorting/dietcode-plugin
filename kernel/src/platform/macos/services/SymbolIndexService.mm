#import "SymbolIndexService.hpp"
#include "filesystem/PathUtils.hpp"
#include <vector>
#include <string>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <filesystem>
#include <cctype>

using namespace dietcode::filesystem;

namespace {
static const NSInteger kMaxSymbolSearchDepth = 10;
static const NSInteger kMaxSymbolSearchFiles = 10000;
static const unsigned long long kMaxSymbolSearchReadBytes = 2 * 1024 * 1024;

struct LineColumn {
    NSInteger line;
    NSInteger column;
};

// Map character index to line and column
class LineMap {
    std::vector<NSUInteger> lineStarts;
    NSUInteger totalLen;
public:
    LineMap(NSString* text) {
        totalLen = text.length;
        lineStarts.push_back(0);
        for (NSUInteger i = 0; i < totalLen; i++) {
            if ([text characterAtIndex:i] == '\n') {
                lineStarts.push_back(i + 1);
            }
        }
    }

    LineColumn getLineColumn(NSUInteger index) {
        if (index >= totalLen) index = totalLen > 0 ? totalLen - 1 : 0;
        auto it = std::upper_bound(lineStarts.begin(), lineStarts.end(), index);
        NSInteger lineIdx = std::distance(lineStarts.begin(), it) - 1;
        NSInteger col = index - lineStarts[lineIdx] + 1;
        return { lineIdx + 1, col };
    }

    NSInteger lineCount() const {
        return lineStarts.size();
    }
};

NSInteger getIndentationLevel(NSString* line) {
    NSInteger count = 0;
    for (NSUInteger i = 0; i < line.length; i++) {
        unichar c = [line characterAtIndex:i];
        if (c == ' ') {
            count++;
        } else if (c == '\t') {
            count += 4;
        } else {
            break;
        }
    }
    return count;
}

BOOL isPythonEmptyOrComment(NSString* line) {
    NSString* trimmed = [line stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    return trimmed.length == 0 || [trimmed hasPrefix:@"#"];
}

NSRange findBraceBlockEnd(NSString* text, NSUInteger startIndex) {
    NSInteger braceDepth = 0;
    BOOL inString = NO;
    unichar stringChar = 0;
    BOOL inLineComment = NO;
    BOOL inBlockComment = NO;
    BOOL enteredBrace = NO;

    NSUInteger len = text.length;
    for (NSUInteger i = startIndex; i < len; i++) {
        unichar c = [text characterAtIndex:i];
        unichar nextC = (i + 1 < len) ? [text characterAtIndex:i+1] : 0;

        if (inLineComment) {
            if (c == '\n') inLineComment = NO;
            continue;
        }
        if (inBlockComment) {
            if (c == '*' && nextC == '/') {
                inBlockComment = NO;
                i++;
            }
            continue;
        }
        if (inString) {
            if (c == '\\') {
                i++;
            } else if (c == stringChar) {
                inString = NO;
            }
            continue;
        }

        if (c == '/' && nextC == '/') {
            inLineComment = YES;
            i++;
            continue;
        }
        if (c == '/' && nextC == '*') {
            inBlockComment = YES;
            i++;
            continue;
        }

        if (c == '"' || c == '\'') {
            inString = YES;
            stringChar = c;
            continue;
        }

        if (c == '{') {
            braceDepth++;
            enteredBrace = YES;
        } else if (c == '}') {
            braceDepth--;
            if (enteredBrace && braceDepth <= 0) {
                return NSMakeRange(i, 1);
            }
        }
    }
    return NSMakeRange(NSNotFound, 0);
}

bool shouldSkipSymbolDirectory(const std::string& filename) {
    return filename == ".git" || filename == "node_modules" || filename == "build" ||
           filename == "dist" || filename == "DerivedData" || filename == ".next" ||
           filename == "__pycache__";
}

bool symbolFileWithinReadCap(const std::filesystem::path& p) {
    std::error_code ec;
    auto size = std::filesystem::file_size(p, ec);
    return ec || size <= kMaxSymbolSearchReadBytes;
}
}

@implementation DietCodeSymbolIndexService

+ (NSArray<NSDictionary*>*)symbolsForFileContent:(NSString*)content extension:(NSString*)ext {
    NSMutableArray* result = [NSMutableArray array];
    if (content.length == 0) return result;

    LineMap map(content);
    NSArray<NSString*>* lines = [content componentsSeparatedByString:@"\n"];

    NSString* lowerExt = [ext lowercaseString];

    if ([lowerExt isEqualToString:@"py"]) {
        // Python symbol parser (indentation block-matching)
        NSError* error = nil;
        NSRegularExpression* regex = [NSRegularExpression regularExpressionWithPattern:@"^(class|def)\\s+([A-Za-z0-9_]+)" options:0 error:&error];

        for (NSInteger i = 0; i < (NSInteger)lines.count; i++) {
            NSString* line = lines[i];
            NSTextCheckingResult* match = [regex firstMatchInString:line options:0 range:NSMakeRange(0, line.length)];
            if (match) {
                NSString* type = [line substringWithRange:[match rangeAtIndex:1]];
                NSString* name = [line substringWithRange:[match rangeAtIndex:2]];
                NSString* kind = [type isEqualToString:@"class"] ? @"Class" : @"Function";

                NSInteger defIndent = getIndentationLevel(line);
                NSInteger endLine = i + 1;

                // Scan forward to determine Python block end
                for (NSInteger j = i + 1; j < (NSInteger)lines.count; j++) {
                    NSString* nextLine = lines[j];
                    if (isPythonEmptyOrComment(nextLine)) continue;

                    NSInteger nextIndent = getIndentationLevel(nextLine);
                    if (nextIndent <= defIndent) {
                        break;
                    }
                    endLine = j + 1;
                }

                [result addObject:@{
                    @"name": name,
                    @"kind": kind,
                    @"line": @(i + 1),
                    @"column": @(defIndent + 1),
                    @"endLine": @(endLine),
                    @"endColumn": @((lines[endLine - 1]).length + 1)
                }];
            }
        }
    } else {
        // C++, JS/TS symbol parser (brace counting)
        // Match: namespaces, classes, structs, interfaces, functions, methods, enums
        NSString* pattern = @"(class|struct|interface|enum|namespace)\\s+([A-Za-z0-9_]+)|([A-Za-z0-9_:<>&\\*]+)\\s+([A-Za-z0-9_]+)\\s*\\(([^)]*)\\)\\s*(const)?\\s*(?=\\{|\\s*$)";
        NSError* error = nil;
        NSRegularExpression* regex = [NSRegularExpression regularExpressionWithPattern:pattern options:0 error:&error];

        NSUInteger searchOffset = 0;
        while (searchOffset < content.length) {
            NSRange searchRange = NSMakeRange(searchOffset, content.length - searchOffset);
            NSTextCheckingResult* match = [regex firstMatchInString:content options:0 range:searchRange];
            if (!match) break;

            NSRange matchedRange = match.range;
            searchOffset = matchedRange.location + matchedRange.length;

            NSString* kind = @"Symbol";
            NSString* name = @"";

            if ([match rangeAtIndex:1].location != NSNotFound) {
                // Keyword match (class, struct, interface, enum, namespace)
                NSString* keyword = [content substringWithRange:[match rangeAtIndex:1]];
                name = [content substringWithRange:[match rangeAtIndex:2]];
                if ([keyword isEqualToString:@"class"]) kind = @"Class";
                else if ([keyword isEqualToString:@"struct"]) kind = @"Struct";
                else if ([keyword isEqualToString:@"interface"]) kind = @"Interface";
                else if ([keyword isEqualToString:@"enum"]) kind = @"Enum";
                else if ([keyword isEqualToString:@"namespace"]) kind = @"Namespace";
            } else if ([match rangeAtIndex:4].location != NSNotFound) {
                // Function/Method match
                name = [content substringWithRange:[match rangeAtIndex:4]];
                // Skip common language keywords that look like functions
                if ([name isEqualToString:@"if"] || [name isEqualToString:@"for"] || [name isEqualToString:@"while"] || [name isEqualToString:@"switch"] || [name isEqualToString:@"catch"]) {
                    continue;
                }
                kind = @"Function";
            } else {
                continue;
            }

            LineColumn startLoc = map.getLineColumn(matchedRange.location);
            LineColumn endLoc = startLoc;
            NSUInteger endOffset = matchedRange.location + matchedRange.length;

            // Search matching closing brace
            NSRange endBraceRange = findBraceBlockEnd(content, matchedRange.location + matchedRange.length);
            if (endBraceRange.location != NSNotFound) {
                endLoc = map.getLineColumn(endBraceRange.location);
                endOffset = endBraceRange.location + endBraceRange.length;
            } else {
                // Fallback to line end if no brace block is found
                endLoc.column = [lines[startLoc.line - 1] length] + 1;
            }

            [result addObject:@{
                @"name": name,
                @"kind": kind,
                @"line": @(startLoc.line),
                @"column": @(startLoc.column),
                @"offset": @(matchedRange.location),
                @"endLine": @(endLoc.line),
                @"endColumn": @(endLoc.column),
                @"endOffset": @(endOffset)
            }];
        }
    }

    return result;
}

+ (NSArray<NSDictionary*>*)referencesForSymbol:(NSString*)symbol
                                   inWorkspace:(NSString*)ws
                                     openFiles:(NSArray<NSString*>*)openFiles
                              diagnosticsFiles:(NSArray<NSString*>*)diagFiles {
    NSMutableArray* references = [NSMutableArray array];
    if (ws.length == 0 || symbol.length == 0) return references;

    // Perform standard directory walk and look for the word
    std::filesystem::path folder([ws UTF8String]);
    std::string targetSymbol = [symbol UTF8String];

    NSInteger scannedFiles = 0;
    traverseDirectory(folder, [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion, bool& stop) {
        std::error_code ec;
        std::filesystem::path p = entry.path();
        std::string filename = p.filename().string();
        
        if (entry.is_directory(ec)) {
            if (depth >= kMaxSymbolSearchDepth || shouldSkipSymbolDirectory(filename)) {
                skipRecursion = true;
            }
            return;
        }
        
        if (!entry.is_regular_file()) return;
        if (++scannedFiles > kMaxSymbolSearchFiles) {
            stop = true;
            return;
        }
        if (!symbolFileWithinReadCap(p)) return;

        std::string absPathStr = p.string();
        NSString* absPath = [NSString stringWithUTF8String:absPathStr.c_str()];

        // Read file contents
        std::ifstream file(absPathStr);
        if (!file.is_open()) return;

        std::string line;
        int lineNum = 1;

        while (std::getline(file, line)) {
            size_t pos = 0;
            while ((pos = line.find(targetSymbol, pos)) != std::string::npos) {
                // Check word boundaries
                bool leftBoundary = (pos == 0) || (!isalnum(line[pos - 1]) && line[pos - 1] != '_');
                bool rightBoundary = (pos + targetSymbol.length() >= line.length()) ||
                                     (!isalnum(line[pos + targetSymbol.length()]) && line[pos + targetSymbol.length()] != '_');

                if (leftBoundary && rightBoundary) {
                    double score = 1.0;

                    // Boost score based on situational context
                    if ([openFiles containsObject:absPath]) {
                        score += 0.5; // open file boost
                    }
                    if ([diagFiles containsObject:absPath]) {
                        score += 0.3; // diagnostics adjacency boost
                    }

                    [references addObject:@{
                        @"path": absPath,
                        @"line": @(lineNum),
                        @"column": @(pos + 1),
                        @"preview": [NSString stringWithUTF8String:line.c_str()] ?: @"",
                        @"score": @(score)
                    }];
                }
                pos += targetSymbol.length();
            }
            lineNum++;
        }
    });

    // Sort by score descending
    [references sortUsingComparator:^NSComparisonResult(NSDictionary* obj1, NSDictionary* obj2) {
        return [obj2[@"score"] compare:obj1[@"score"]];
    }];

    return references;
}

@end
