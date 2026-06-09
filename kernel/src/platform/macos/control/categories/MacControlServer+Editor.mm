#import "MacControlServer+Private.hpp"
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#else
#import "DietCodeWindowController+ControlHost.h"
#endif
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "BufferStateService.hpp"
#include "filesystem/GitService.hpp"
#import "DiffAnalysisService.hpp"
#import "SymbolIndexService.hpp"

@implementation DietCodeControlServer (Editor)

- (void)executeEditorMethod:(NSString*)method 
                     params:(NSDictionary*)params 
                  outResult:(NSDictionary**)outResult 
                 outErrCode:(NSString**)outErrCode 
                outErrMsg:(NSString**)outErrMsg
                   outPaths:(NSString**)outPaths {
    
    // Editor commands
    if ([method isEqualToString:@"editor.getActiveFile"]) {
        NSString* active = [self safeActiveFilePath] ?: @"";
        *outResult = @{ @"path": active };
        return;
    }
    
    if ([method isEqualToString:@"editor.getOpenFiles"]) {
        NSArray* list = [self safeOpenFilePaths];
        *outResult = @{ @"files": list };
        return;
    }
    
    if ([method isEqualToString:@"editor.getText"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Open document path required.";
            return;
        }
        NSString* text = [self safeTextForFileAtPath:targetPath];
        if (!text) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"File is not open and is not in workspace.";
            return;
        }
        NSUInteger textBytes = [text lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
        if (textBytes > kMaxFileTextBytes && ![params[@"allowLarge"] boolValue]) {
            *outErrCode = @"response_too_large";
            *outErrMsg = @"File text exceeds maximum RPC response size; pass allowLarge=true only when needed.";
            return;
        }
        *outResult = @{ @"text": text };
        return;
    }
    
    if ([method isEqualToString:@"editor.getSelection"]) {
        NSDictionary* sel = [self safeActiveSelectionInfo];
        if (sel.count == 0) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No active editor tab.";
            return;
        }
        *outResult = sel;
        return;
    }
    
    if ([method isEqualToString:@"editor.setSelection"]) {
        if (self.isKernelMode || !self.windowController) {
            *outErrCode = @"ui_unavailable";
            *outErrMsg = @"Editor selection is unavailable in kernel mode.";
            return;
        }
        NSInteger start = [params[@"start"] integerValue];
        NSInteger end = [params[@"end"] integerValue];
        BOOL ok = [(id)self.windowController setActiveSelectionStart:start end:end];
        if (!ok) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Selection range indices out of bounds or no active editor.";
            return;
        }
        *outResult = @{ @"success": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.insertText"]) {
        NSString* text = params[@"text"];
        if (!text) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"text parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outErrCode = @"ui_unavailable";
            *outErrMsg = @"Editor insert is unavailable in kernel mode.";
            return;
        }
        BOOL ok = [(id)self.windowController insertTextAtActiveCursor:text];
        if (!ok) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"Failed to insert text in active editor buffer.";
            return;
        }
        *outResult = @{ @"inserted": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.replaceSelection"]) {
        NSString* text = params[@"text"];
        if (!text) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"text parameter required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outErrCode = @"ui_unavailable";
            *outErrMsg = @"Editor replace is unavailable in kernel mode.";
            return;
        }
        BOOL ok = [(id)self.windowController replaceActiveSelectionWithText:text];
        if (!ok) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"Failed to replace selection.";
            return;
        }
        *outResult = @{ @"replaced": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.replaceRange"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        NSString* text = params[@"text"];
        NSInteger start = [params[@"start"] integerValue];
        NSInteger end = [params[@"end"] integerValue];
        if (!targetPath || !text || start < 0 || end < start) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path, text, start, and end parameters required.";
            return;
        }
        NSRange range = NSMakeRange(start, end - start);
        BOOL ok = [self safeReplaceTextInRange:range withText:text forFileAtPath:targetPath];
        if (!ok) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"Range is out of bounds or file is read-only.";
            return;
        }
        *outResult = @{ @"replaced": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.applyPatch"]) {
        NSString* errStr = nil;
        NSString* errCode = nil;
        NSDictionary* result = [_patchService applyPatch:params error:&errStr errorCode:&errCode];
        if (!result) {
            *outErrCode = errCode ?: @"patch_failed";
            *outErrMsg = errStr ?: @"Patch application failed.";
            return;
        }
        *outResult = result;
        return;
    }
    
    if ([method isEqualToString:@"editor.saveFile"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Open document path required.";
            return;
        }
        if (self.windowController) {
            [(id)self.windowController saveFileAtPath:targetPath];
        } else {
            NSString* text = [self safeTextForFileAtPath:targetPath];
            NSString* err = nil;
            if (!text || ![self.workspaceSession writeTextAtPath:targetPath content:text error:&err]) {
                *outErrCode = @"write_failed";
                *outErrMsg = err ?: @"Failed to save file in kernel mode.";
                return;
            }
        }
        *outResult = @{ @"saved": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.closeFile"]) {
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"closed": @YES, @"headless": @YES };
            return;
        }
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"Open document path required.";
            return;
        }
        [(id)self.windowController closeFileAtPath:targetPath];
        *outResult = @{ @"closed": @YES };
        return;
    }
    
    if ([method isEqualToString:@"editor.goto"]) {
        NSString* targetPath = params[@"path"] ?: [self safeActiveFilePath];
        NSInteger line = [params[@"line"] integerValue];
        NSInteger col = params[@"column"] ? [params[@"column"] integerValue] : 1;
        if (!targetPath || line <= 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path and line parameters required.";
            return;
        }
        if (self.isKernelMode || !self.windowController) {
            *outResult = @{ @"navigated": @YES, @"path": targetPath, @"line": @(line), @"headless": @YES };
            return;
        }
        [self.windowController openFileAtPath:targetPath line:line column:col];
        *outResult = @{ @"navigated": @YES };
        return;
    }

    // Buffer commands
    if ([method isEqualToString:@"buffers.snapshot"]) {
        *outResult = @{ @"buffers": [DietCodeBufferStateService snapshotForTabs:[self safeOpenTabs] ?: @[]] };
        return;
    }

    if ([method isEqualToString:@"buffers.dirty"]) {
        *outResult = @{ @"files": DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[]) };
        return;
    }

    if ([method isEqualToString:@"buffers.active"]) {
        NSString* pathValue = [self safeActiveFilePath] ?: @"";
        NSDictionary* selection = [self safeActiveSelectionInfo] ?: @{};
        *outResult = @{ @"path": pathValue, @"selection": selection };
        return;
    }

    if ([method isEqualToString:@"buffers.unsavedDiff"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [self safeActiveFilePath], ws);
        NSString* diff = @"";
        for (id tab in [self safeOpenTabs] ?: @[]) {
            if ([[tab valueForKey:@"path"] isEqualToString:targetPath]) {
                diff = [DietCodeBufferStateService unsavedDiffForTab:tab];
                break;
            }
        }
        *outResult = @{ @"path": targetPath ?: @"", @"diff": diff ?: @"" };
        return;
    }

    // Change set commands
    if ([method isEqualToString:@"changes.current"]) {
        *outResult = [self currentChangesInfo];
        return;
    }

    if ([method isEqualToString:@"changes.summary"]) {
        NSDictionary* changes = [self currentChangesInfo];
        *outResult = @{
            @"summary": @{
                @"modifiedFileCount": @([changes[@"modifiedFiles"] count]),
                @"unsavedBufferCount": @([changes[@"unsavedBuffers"] count]),
                @"stagedFileCount": @([changes[@"stagedFiles"] count]),
                @"unstagedFileCount": @([changes[@"unstagedFiles"] count]),
                @"untrackedFileCount": @([changes[@"untrackedFiles"] count]),
                @"totalAdded": changes[@"totalAdded"] ?: @0,
                @"totalDeleted": changes[@"totalDeleted"] ?: @0
            },
            @"changes": changes
        };
        return;
    }

    if ([method isEqualToString:@"changes.revertFile"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"], ws);
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [(id)self.windowController gitDiscardFile:targetPath errorOut:&errStr];
        } else {
            std::string err;
            ok = dietcode::filesystem::GitService::discardChanges(
                std::string([[self safeWorkspacePath] UTF8String]),
                std::string([targetPath UTF8String]),
                err);
            if (!ok) errStr = [NSString stringWithUTF8String:err.c_str()];
        }
        if (!ok) {
            *outErrCode = @"git_failed";
            *outErrMsg = errStr ?: @"Failed to revert file.";
            return;
        }
        *outResult = @{ @"reverted": @YES, @"path": targetPath };
        return;
    }

    // Diff commands
    if ([method isEqualToString:@"diff.workspaceInfo"] || [method isEqualToString:@"diff.stats"]) {
        NSString* ws = [self safeWorkspacePath];
        if (!ws) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }
        *outResult = [DietCodeDiffAnalysisService workspaceDiffInfo:ws];
        return;
    }

    if ([method isEqualToString:@"diff.file"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: @"", ws);
        NSString* diff = [self safeGitDiffForFile:targetPath];
        *outResult = @{
            @"path": targetPath ?: @"",
            @"diff": diff ?: @"",
            @"mode": @"literal_git_diff",
            @"sha256": StableHashForString(diff ?: @"")
        };
        return;
    }

    if ([method isEqualToString:@"diff.chunk"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* source = [params[@"source"] lowercaseString] ?: @"unstaged";
        NSInteger offset = params[@"offset"] ? [params[@"offset"] integerValue] : 0;
        NSInteger maxBytes = params[@"maxBytes"] ? [params[@"maxBytes"] integerValue] : 64 * 1024;
        if (!ws) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }
        NSString* diff = @"";
        NSString* absPath = @"";
        if ([source isEqualToString:@"staged"]) {
            diff = RunGitOutput(ws, @[@"diff", @"--cached"]);
        } else if ([source isEqualToString:@"unstaged"]) {
            diff = RunGitOutput(ws, @[@"diff"]);
        } else if ([source isEqualToString:@"file"]) {
            absPath = AbsolutePathForRPCPath(params[@"path"] ?: @"", ws);
            if (!absPath) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"path required when source=file.";
                return;
            }
            diff = [self safeGitDiffForFile:absPath] ?: @"";
        } else {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"source must be one of unstaged, staged, or file.";
            return;
        }
        NSMutableDictionary* chunk = [TextChunkResponse(diff ?: @"", offset, maxBytes) mutableCopy];
        chunk[@"source"] = source;
        chunk[@"path"] = absPath ?: @"";
        chunk[@"mode"] = @"literal_git_diff_chunk";
        chunk[@"encoding"] = @"utf-8";
        *outResult = chunk;
        return;
    }

    if ([method isEqualToString:@"diff.hunks"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* source = [params[@"source"] lowercaseString] ?: @"unstaged";
        NSInteger maxHunks = params[@"maxHunks"] ? [params[@"maxHunks"] integerValue] : 500;
        NSInteger hunkOffset = params[@"hunkOffset"] ? [params[@"hunkOffset"] integerValue] : 0;
        BOOL includeLines = [params[@"includeLines"] boolValue];
        NSInteger maxLinesPerHunk = params[@"maxLinesPerHunk"] ? [params[@"maxLinesPerHunk"] integerValue] : 200;
        if (!ws) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }
        NSString* diff = @"";
        NSString* absPath = @"";
        if ([source isEqualToString:@"staged"]) {
            diff = RunGitOutput(ws, @[@"diff", @"--cached"]);
        } else if ([source isEqualToString:@"unstaged"]) {
            diff = RunGitOutput(ws, @[@"diff"]);
        } else if ([source isEqualToString:@"file"]) {
            absPath = AbsolutePathForRPCPath(params[@"path"] ?: @"", ws);
            if (!absPath) {
                *outErrCode = @"invalid_params";
                *outErrMsg = @"path required when source=file.";
                return;
            }
            diff = [self safeGitDiffForFile:absPath] ?: @"";
        } else {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"source must be one of unstaged, staged, or file.";
            return;
        }
        NSMutableDictionary* response = [UnifiedDiffHunksResponse(diff ?: @"", maxHunks, hunkOffset, includeLines, maxLinesPerHunk) mutableCopy];
        response[@"source"] = source;
        response[@"path"] = absPath ?: @"";
        response[@"mode"] = @"literal_unified_diff_hunks";
        response[@"sha256"] = StableHashForString(diff ?: @"");
        *outResult = MacControlEnrichDiffHunksResult(response, @"diff.hunks");
        return;
    }

    if ([method isEqualToString:@"diff.current"]) {
        NSString* ws = [self safeWorkspacePath] ?: @"";
        *outResult = @{
            @"changes": [self currentChangesInfo],
            @"unstagedDiff": RunGitOutput(ws, @[@"diff"]),
            @"stagedDiff": RunGitOutput(ws, @[@"diff", @"--cached"]),
            @"unsavedBuffers": [DietCodeBufferStateService snapshotForTabs:[self safeOpenTabs] ?: @[]]
        };
        return;
    }

    if ([method isEqualToString:@"diff.staged"]) {
        NSString* diff = RunGitOutput([self safeWorkspacePath] ?: @"", @[@"diff", @"--cached"]);
        *outResult = @{ @"diff": diff, @"mode": @"literal_git_diff", @"sha256": StableHashForString(diff ?: @"") };
        return;
    }

    if ([method isEqualToString:@"diff.unstaged"]) {
        NSString* diff = RunGitOutput([self safeWorkspacePath] ?: @"", @[@"diff"]);
        *outResult = @{ @"diff": diff, @"mode": @"literal_git_diff", @"sha256": StableHashForString(diff ?: @"") };
        return;
    }

    if ([method isEqualToString:@"diff.summary"]) {
        NSDictionary* changes = [self currentChangesInfo];
        *outResult = @{
            @"filesChanged": @([changes[@"modifiedFiles"] count]),
            @"addedLines": changes[@"totalAdded"] ?: @0,
            @"removedLines": changes[@"totalDeleted"] ?: @0,
            @"stagedFiles": @([changes[@"stagedFiles"] count]),
            @"unstagedFiles": @([changes[@"unstagedFiles"] count]),
            @"untrackedFiles": @([changes[@"untrackedFiles"] count])
        };
        return;
    }

    if ([method isEqualToString:@"diff.validatePatch"] || [method isEqualToString:@"diff.applyPatchPreview"]) {
        NSString* ws = [_windowBridge workspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [_windowBridge activeFilePath], ws);
        NSString* patchStr = params[@"patch"];
        if (!targetPath || patchStr.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path and patch parameters required.";
            return;
        }
        NSDictionary* validation = [_patchService validatePatchAtPath:targetPath patch:patchStr currentText:params[@"currentText"] options:params];
        *outResult = @{ @"validation": validation };
        return;
    }

    if ([method isEqualToString:@"diff.previewPatch"]) {
        NSString* ws = [_windowBridge workspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [_windowBridge activeFilePath], ws);
        NSString* patchStr = params[@"patch"];
        if (!targetPath || patchStr.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path and patch parameters required.";
            return;
        }
        NSString* currentText = params[@"currentText"] ?: [_windowBridge textForFileAtPath:targetPath];
        if (!currentText) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"File is not readable.";
            return;
        }
        NSArray* symbols = [DietCodeSymbolIndexService symbolsForFileContent:currentText extension:[[targetPath pathExtension] lowercaseString]];
        *outResult = [DietCodeDiffAnalysisService previewPatchAtPath:targetPath patch:patchStr currentText:currentText symbols:symbols];
        return;
    }

    // Patch primitives
    if ([method isEqualToString:@"patch.chunk"]) {
        NSString* patchStr = params[@"patch"] ?: @"";
        NSInteger offset = params[@"offset"] ? [params[@"offset"] integerValue] : 0;
        NSInteger maxBytes = params[@"maxBytes"] ? [params[@"maxBytes"] integerValue] : 64 * 1024;
        if (patchStr.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"patch parameter required.";
            return;
        }
        NSMutableDictionary* chunk = [TextChunkResponse(patchStr, offset, maxBytes) mutableCopy];
        chunk[@"mode"] = @"literal_patch_chunk";
        chunk[@"encoding"] = @"utf-8";
        *outResult = chunk;
        return;
    }

    if ([method isEqualToString:@"patch.hunks"]) {
        NSString* patchStr = params[@"patch"] ?: @"";
        NSInteger maxHunks = params[@"maxHunks"] ? [params[@"maxHunks"] integerValue] : 500;
        NSInteger hunkOffset = params[@"hunkOffset"] ? [params[@"hunkOffset"] integerValue] : 0;
        BOOL includeLines = [params[@"includeLines"] boolValue];
        NSInteger maxLinesPerHunk = params[@"maxLinesPerHunk"] ? [params[@"maxLinesPerHunk"] integerValue] : 200;
        if (patchStr.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"patch parameter required.";
            return;
        }
        NSMutableDictionary* response = [UnifiedDiffHunksResponse(patchStr, maxHunks, hunkOffset, includeLines, maxLinesPerHunk) mutableCopy];
        response[@"source"] = @"patch";
        response[@"path"] = @"";
        response[@"mode"] = @"literal_unified_diff_hunks";
        response[@"sha256"] = StableHashForString(patchStr ?: @"");
        *outResult = MacControlEnrichDiffHunksResult(response, @"patch.hunks");
        return;
    }

    if ([method isEqualToString:@"patch.validate"] || [method isEqualToString:@"patch.preview"]) {
        NSString* ws = [_windowBridge workspacePath];
        NSString* targetPath = AbsolutePathForRPCPath(params[@"path"] ?: [_windowBridge activeFilePath], ws);
        NSString* patchStr = params[@"patch"];
        if (!targetPath || patchStr.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path and patch parameters required.";
            return;
        }
        if ([patchStr lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > kMaxPatchBytes) {
            *outErrCode = @"patch_failed";
            *outErrMsg = @"Patch exceeds maximum RPC patch size.";
            return;
        }
        NSDictionary* validation = [_patchService validatePatchAtPath:targetPath patch:patchStr currentText:params[@"currentText"] options:params];
        NSDictionary* preview = PatchPreviewSummary(patchStr);
        if ([method isEqualToString:@"patch.validate"]) {
            *outResult = MacControlEnrichPatchValidateResult(@{
                @"path": targetPath,
                @"applies": validation[@"patchAppliesCleanly"] ?: @NO,
                @"changedLines": validation[@"changedLineCount"] ?: @0,
                @"hunks": @([validation[@"affectedHunks"] count]),
                @"requiresConfirmation": validation[@"requiresConfirmation"] ?: @NO,
                @"validation": validation
            });
        } else {
            NSMutableDictionary* result = [preview mutableCopy];
            result[@"path"] = targetPath;
            result[@"validation"] = validation;
            result[@"syntaxDanger"] = validation[@"syntaxDanger"] ?: @NO;
            if (validation[@"syntaxWarning"]) {
                result[@"syntaxWarning"] = validation[@"syntaxWarning"];
            }
            *outResult = result;
        }
        return;
    }

    if ([method isEqualToString:@"patch.apply"]) {
        NSString* errStr = nil;
        NSString* errCode = nil;
        NSDictionary* result = [_patchService applyPatch:params error:&errStr errorCode:&errCode];
        if (!result) {
            *outErrCode = errCode ?: @"patch_failed";
            *outErrMsg = errStr ?: @"Patch application failed.";
            return;
        }
        *outResult = MacControlEnrichPatchApplyResult(result);
        return;
    }

    if ([method isEqualToString:@"patch.applyBatch"]) {
        NSString* errStr = nil;
        NSString* errCode = nil;
        NSDictionary* result = [_patchService applyPatchBatch:params error:&errStr errorCode:&errCode];
        if (!result) {
            *outErrCode = errCode ?: @"patch_failed";
            *outErrMsg = errStr ?: @"Batch patch application failed.";
            return;
        }
        *outResult = MacControlEnrichPatchApplyBatchResult(result);
        return;
    }

    if ([method isEqualToString:@"patch.revertLast"]) {
        NSString* errStr = nil;
        NSString* errCode = nil;
        NSDictionary* result = [_patchService revertLastPatchWithError:&errStr errorCode:&errCode];
        if (!result) {
            *outErrCode = errCode ?: @"rollback_failed";
            *outErrMsg = errStr ?: @"Failed to revert last RPC patch.";
            return;
        }
        *outResult = result;
        return;
    }
}

@end
