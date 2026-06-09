#import "DiffAnalysisService.hpp"
#import "SubprocessRunner.hpp"
#include <unistd.h>
#include <stdlib.h>
#include <iostream>
#include <vector>

using namespace dietcode::platform::macos;

namespace {
NSString* runGitCmd(NSString* dir, NSArray<NSString*>* args) {
    std::vector<std::string> cppArgs;
    for (NSString* arg in args) {
        cppArgs.push_back([arg UTF8String]);
    }
    
    SubprocessResult res = SubprocessRunner::run("/usr/bin/git", cppArgs, [dir UTF8String], 10.0);
    return [NSString stringWithUTF8String:res.stdOut.c_str()] ?: @"";
}

BOOL checkBracketBalance(NSString* text, NSString* path) {
    NSString* ext = [[path pathExtension] lowercaseString];
    static NSSet* skippedExtensions = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        skippedExtensions = [NSSet setWithObjects:@"md", @"markdown", @"txt", @"text", @"log", @"patch", @"diff", @"plist", @"svg", @"csv", @"tsv", @"yml", @"yaml", @"ini", @"conf", @"cfg", @"toml", @"css", @"scss", @"html", @"htm", @"xml", nil];
    });
    if (ext.length > 0 && [skippedExtensions containsObject:ext]) {
        return YES;
    }

    BOOL isPython = [ext isEqualToString:@"py"];
    std::vector<unichar> stack;
    NSUInteger len = text.length;
    NSUInteger i = 0;

    while (i < len) {
        unichar c = [text characterAtIndex:i];

        if (isPython) {
            if (c == '#') {
                while (i < len && [text characterAtIndex:i] != '\n') {
                    i++;
                }
                continue;
            }
            if (i + 2 < len) {
                NSString* sub3 = [text substringWithRange:NSMakeRange(i, 3)];
                if ([sub3 isEqualToString:@"\"\"\""]) {
                    i += 3;
                    while (i < len) {
                        if (i + 2 < len && [[text substringWithRange:NSMakeRange(i, 3)] isEqualToString:@"\"\"\""]) {
                            i += 3;
                            break;
                        }
                        if ([text characterAtIndex:i] == '\\') {
                            i += 2;
                        } else {
                            i++;
                        }
                    }
                    continue;
                }
                if ([sub3 isEqualToString:@"'''"]) {
                    i += 3;
                    while (i < len) {
                        if (i + 2 < len && [[text substringWithRange:NSMakeRange(i, 3)] isEqualToString:@"'''"]) {
                            i += 3;
                            break;
                        }
                        if ([text characterAtIndex:i] == '\\') {
                            i += 2;
                        } else {
                            i++;
                        }
                    }
                    continue;
                }
            }
            if (c == '"') {
                i++;
                while (i < len) {
                    unichar sc = [text characterAtIndex:i];
                    if (sc == '"') {
                        i++;
                        break;
                    }
                    if (sc == '\\') {
                        i += 2;
                    } else {
                        i++;
                    }
                }
                continue;
            }
            if (c == '\'') {
                i++;
                while (i < len) {
                    unichar sc = [text characterAtIndex:i];
                    if (sc == '\'') {
                        i++;
                        break;
                    }
                    if (sc == '\\') {
                        i += 2;
                    } else {
                        i++;
                    }
                }
                continue;
            }
        } else {
            if (c == '/' && i + 1 < len) {
                unichar nextC = [text characterAtIndex:i+1];
                if (nextC == '/') {
                    i += 2;
                    while (i < len && [text characterAtIndex:i] != '\n') {
                        i++;
                    }
                    continue;
                } else if (nextC == '*') {
                    i += 2;
                    while (i < len) {
                        if (i + 1 < len && [text characterAtIndex:i] == '*' && [text characterAtIndex:i+1] == '/') {
                            i += 2;
                            break;
                        }
                        i++;
                    }
                    continue;
                }
            }
            if (c == '"') {
                i++;
                while (i < len) {
                    unichar sc = [text characterAtIndex:i];
                    if (sc == '"') {
                        i++;
                        break;
                    }
                    if (sc == '\\') {
                        i += 2;
                    } else {
                        i++;
                    }
                }
                continue;
            }
            if (c == '\'') {
                i++;
                while (i < len) {
                    unichar sc = [text characterAtIndex:i];
                    if (sc == '\'') {
                        i++;
                        break;
                    }
                    if (sc == '\\') {
                        i += 2;
                    } else {
                        i++;
                    }
                }
                continue;
            }
            if (c == '`') {
                i++;
                while (i < len) {
                    unichar sc = [text characterAtIndex:i];
                    if (sc == '`') {
                        i++;
                        break;
                    }
                    if (sc == '\\') {
                        i += 2;
                    } else {
                        i++;
                    }
                }
                continue;
            }
        }

        if (c == '(' || c == '[' || c == '{') {
            stack.push_back(c);
        } else if (c == ')') {
            if (stack.empty() || stack.back() != '(') return NO;
            stack.pop_back();
        } else if (c == ']') {
            if (stack.empty() || stack.back() != '[') return NO;
            stack.pop_back();
        } else if (c == '}') {
            if (stack.empty() || stack.back() != '{') return NO;
            stack.pop_back();
        }
        i++;
    }
    return stack.empty();
}
}

@implementation DietCodeDiffAnalysisService

+ (NSDictionary*)workspaceDiffInfo:(NSString*)ws {
    NSMutableDictionary* result = [NSMutableDictionary dictionary];
    if (ws.length == 0) return result;

    // Run git diff --numstat for unstaged changes
    NSString* numstatUnstaged = runGitCmd(ws, @[@"diff", @"--numstat"]);
    // Run git diff --numstat --cached for staged changes
    NSString* numstatStaged = runGitCmd(ws, @[@"diff", @"--cached", @"--numstat"]);

    NSMutableDictionary* filesInfo = [NSMutableDictionary dictionary];

    auto parseNumstat = ^(NSString* output, BOOL staged) {
        NSArray<NSString*>* lines = [output componentsSeparatedByString:@"\n"];
        for (NSString* line in lines) {
            NSArray<NSString*>* parts = [line componentsSeparatedByCharactersInSet:[NSCharacterSet whitespaceCharacterSet]];
            NSMutableArray<NSString*>* cleanParts = [NSMutableArray array];
            for (NSString* p in parts) {
                if (p.length > 0) [cleanParts addObject:p];
            }
            if (cleanParts.count >= 3) {
                NSInteger added = [cleanParts[0] integerValue];
                NSInteger deleted = [cleanParts[1] integerValue];
                NSString* filePath = cleanParts[2];

                NSMutableDictionary* fileMeta = filesInfo[filePath] ?: [NSMutableDictionary dictionary];
                fileMeta[@"added"] = @([fileMeta[@"added"] integerValue] + added);
                fileMeta[@"deleted"] = @([fileMeta[@"deleted"] integerValue] + deleted);
                if (staged) {
                    fileMeta[@"staged"] = @YES;
                } else {
                    fileMeta[@"unstaged"] = @YES;
                }
                filesInfo[filePath] = fileMeta;
            }
        }
    };

    parseNumstat(numstatUnstaged, NO);
    parseNumstat(numstatStaged, YES);

    NSMutableArray* filesArr = [NSMutableArray array];
    NSInteger totalAdded = 0;
    NSInteger totalDeleted = 0;

    for (NSString* filePath in filesInfo) {
        NSDictionary* meta = filesInfo[filePath];
        totalAdded += [meta[@"added"] integerValue];
        totalDeleted += [meta[@"deleted"] integerValue];
        [filesArr addObject:@{
            @"path": filePath,
            @"added": meta[@"added"] ?: @0,
            @"deleted": meta[@"deleted"] ?: @0,
            @"staged": meta[@"staged"] ?: @NO,
            @"unstaged": meta[@"unstaged"] ?: @NO
        }];
    }

    result[@"files"] = filesArr;
    result[@"totalAdded"] = @(totalAdded);
    result[@"totalDeleted"] = @(totalDeleted);

    return result;
}

+ (NSDictionary*)previewPatchAtPath:(NSString*)path
                              patch:(NSString*)patch
                        currentText:(NSString*)currentText
                            symbols:(NSArray<NSDictionary*>*)symbols {

    NSMutableDictionary* result = [NSMutableDictionary dictionary];

    // Setup temp files
    NSString* tempDir = NSTemporaryDirectory() ?: @"/tmp";
    NSString* uuidStr = [[NSUUID UUID] UUIDString];
    NSString* tempSrcPath = [tempDir stringByAppendingPathComponent:[NSString stringWithFormat:@"dietcode_preview_src_%@.txt", uuidStr]];
    NSString* tempDiffPath = [tempDir stringByAppendingPathComponent:[NSString stringWithFormat:@"dietcode_preview_diff_%@.diff", uuidStr]];

    // RAII-style cleanup: guarantee temp files are removed on all exit paths.
    @try {
        NSError* err = nil;
        unlink([tempSrcPath UTF8String]);
        [currentText writeToFile:tempSrcPath atomically:YES encoding:NSUTF8StringEncoding error:&err];
        if (err) {
            return @{ @"ok": @NO, @"error": @"Failed to write temp source." };
        }
        unlink([tempDiffPath UTF8String]);
        [patch writeToFile:tempDiffPath atomically:YES encoding:NSUTF8StringEncoding error:&err];
        if (err) {
            return @{ @"ok": @NO, @"error": @"Failed to write temp diff patch." };
        }

        // Run patch --silent
        std::vector<std::string> patchArgs = {"--silent", [tempSrcPath UTF8String], [tempDiffPath UTF8String]};
        SubprocessResult patchRes = SubprocessRunner::run("/usr/bin/patch", patchArgs, "", 10.0);

        if (patchRes.timedOut) {
            return @{ @"ok": @NO, @"risk": @"high", @"error": @"Patch simulation timed out." };
        }

        if (patchRes.exitCode != 0) {
            return @{
                @"ok": @NO,
                @"risk": @"high",
                @"error": [NSString stringWithFormat:@"Patch simulation failed: %s", patchRes.stdErr.c_str()]
            };
        }

        NSString* patchedText = [NSString stringWithContentsOfFile:tempSrcPath encoding:NSUTF8StringEncoding error:nil];

        if (!patchedText) {
            return @{ @"ok": @NO, @"error": @"Failed to read patched output." };
        }

        // Parse patch to count added/removed lines and identify modified line numbers
        NSInteger addedLines = 0;
        NSInteger removedLines = 0;

        NSError* regErr = nil;
        NSRegularExpression* hunkRegex = [NSRegularExpression regularExpressionWithPattern:@"^@@ -(\\d+),?(\\d*) \\+(\\d+),?(\\d*) @@" options:0 error:&regErr];

        NSArray<NSString*>* patchLines = [patch componentsSeparatedByString:@"\n"];
        NSInteger currentNewLine = 0;
        NSMutableSet* modifiedLines = [NSMutableSet set];

        for (NSString* line in patchLines) {
            if ([line hasPrefix:@"@@"]) {
                NSTextCheckingResult* match = [hunkRegex firstMatchInString:line options:0 range:NSMakeRange(0, line.length)];
                if (match) {
                    currentNewLine = [[line substringWithRange:[match rangeAtIndex:3]] integerValue];
                }
            } else if (currentNewLine > 0) {
                if ([line hasPrefix:@"+"]) {
                    addedLines++;
                    [modifiedLines addObject:@(currentNewLine)];
                    currentNewLine++;
                } else if ([line hasPrefix:@"-"]) {
                    removedLines++;
                    [modifiedLines addObject:@(currentNewLine)];
                } else if ([line hasPrefix:@" "]) {
                    currentNewLine++;
                }
            }
        }

        // Determine which functions/symbols were touched
        NSMutableSet* touchedFunctions = [NSMutableSet set];
        for (NSDictionary* sym in symbols) {
            NSInteger sLine = [sym[@"line"] integerValue];
            NSInteger eLine = [sym[@"endLine"] integerValue];
            for (NSNumber* mLine in modifiedLines) {
                if ([mLine integerValue] >= sLine && [mLine integerValue] <= eLine) {
                    [touchedFunctions addObject:sym[@"name"]];
                    break;
                }
            }
        }

        // Assess risk level
        NSString* risk = @"low";
        double changeRatio = (double)(addedLines + removedLines) / (double)(currentText.length > 0 ? [currentText componentsSeparatedByString:@"\n"].count : 1);
        if ((addedLines + removedLines) > 200 || changeRatio > 0.5 || [[path lastPathComponent] isEqualToString:@"Makefile"]) {
            risk = @"high";
        } else if ((addedLines + removedLines) > 50 || changeRatio > 0.15 || touchedFunctions.count > 2) {
            risk = @"medium";
        }

        // Bracket-matching syntax safety check
        BOOL syntaxDanger = !checkBracketBalance(patchedText, path);
        NSString* syntaxErrors = @"";

        // Python-specific compile check
        if ([[path lowercaseString] hasSuffix:@".py"]) {
            NSString* tempPyPath = [tempDir stringByAppendingPathComponent:[NSString stringWithFormat:@"dietcode_syntax_check_%@.py", [[NSUUID UUID] UUIDString]]];
            unlink([tempPyPath UTF8String]);
            [patchedText writeToFile:tempPyPath atomically:YES encoding:NSUTF8StringEncoding error:nil];

            std::vector<std::string> pyArgs = {"-m", "py_compile", [tempPyPath UTF8String]};
            SubprocessResult pyRes = SubprocessRunner::run("/usr/bin/python3", pyArgs, "", 5.0);

            if (pyRes.timedOut) {
                syntaxDanger = YES;
                syntaxErrors = @"Python syntax check timed out.";
            } else if (pyRes.exitCode != 0) {
                syntaxDanger = YES;
                syntaxErrors = [NSString stringWithUTF8String:pyRes.stdErr.c_str()] ?: @"Python compile failed.";
            }
            [[NSFileManager defaultManager] removeItemAtPath:tempPyPath error:nil];
        }

        result[@"ok"] = @YES;
        result[@"addedLines"] = @(addedLines);
        result[@"removedLines"] = @(removedLines);
        result[@"functionsTouched"] = [touchedFunctions allObjects];
        result[@"risk"] = risk;
        result[@"syntaxDanger"] = @(syntaxDanger);
        result[@"syntaxErrors"] = syntaxErrors;

        return result;

    } @finally {
        // Guaranteed cleanup of temp files on all exit paths (normal, error, exception).
        [[NSFileManager defaultManager] removeItemAtPath:tempSrcPath error:nil];
        [[NSFileManager defaultManager] removeItemAtPath:tempDiffPath error:nil];
    }
}

@end
