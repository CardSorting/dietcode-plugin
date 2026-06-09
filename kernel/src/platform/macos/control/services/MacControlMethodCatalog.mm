#import "MacControlMethodCatalog.hpp"
#import "MacControlSupport.hpp"

NSArray<NSDictionary*>* MacControlRPCMethodDescriptions(void) {
    static NSArray<NSDictionary*>* methods = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        methods = @[
            @{ @"name": @"rpc.ping", @"permission": @"Read", @"params": @{}, @"returns": @{ @"pong": @"boolean", @"server": @"string" } },
            @{ @"name": @"rpc.version", @"permission": @"Read", @"params": @{}, @"returns": @{ @"appVersion": @"string", @"controlProtocolVersion": @"string", @"transactionSchemaVersion": @"string", @"supportedRollbackSchemas": @"array", @"supportedInspectOnlySchemas": @"array" } },
            @{ @"name": @"rpc.methods", @"permission": @"Read", @"params": @{}, @"returns": @{ @"methods": @"array" } },
            @{ @"name": @"rpc.describe", @"permission": @"Read", @"params": @{ @"method": @"string optional" }, @"returns": @{ @"methods": @"array" } },
            @{ @"name": @"chip.list", @"permission": @"Read", @"params": @{}, @"returns": @{ @"chips": @"array" } },
            @{ @"name": @"chip.describe", @"permission": @"Read", @"params": @{ @"chip": @"string" }, @"returns": @{ @"chip": @"object" } },
            @{ @"name": @"combo.validate", @"permission": @"Read", @"params": @{ @"combo": @"object" }, @"returns": @{ @"valid": @"boolean", @"errors": @"array", @"plan": @"object optional" } },
            @{ @"name": @"combo.run", @"permission": @"Edit/Execute", @"params": @{ @"combo": @"object" }, @"returns": @{ @"combo": @"object" } },
            @{ @"name": @"combo.status", @"permission": @"Read", @"params": @{ @"comboId": @"string" }, @"returns": @{ @"combo": @"object" } },
            @{ @"name": @"combo.result", @"permission": @"Read", @"params": @{ @"comboId": @"string" }, @"returns": @{ @"combo": @"object" } },
            @{ @"name": @"combo.list", @"permission": @"Read", @"params": @{}, @"returns": @{ @"combos": @"array" } },
            @{ @"name": @"combo.cancel", @"permission": @"Read", @"params": @{ @"comboId": @"string" }, @"returns": @{ @"cancelled": @"boolean" } },
            @{ @"name": @"combo.rollback", @"permission": @"Edit", @"params": @{ @"comboId": @"string optional" }, @"returns": @{ @"reverted": @"boolean" } },
            @{ @"name": @"recovery.scan", @"permission": @"Read", @"params": @{}, @"returns": @{ @"backups": @"array" } },
            @{ @"name": @"recovery.schemaInfo", @"permission": @"Read", @"params": @{}, @"returns": @{ @"transactionSchemaVersion": @"string", @"supportedRollbackSchemas": @"array", @"supportedInspectOnlySchemas": @"array" } },
            @{ @"name": @"recovery.list", @"permission": @"Read", @"params": @{}, @"returns": @{ @"backups": @"array" } },
            @{ @"name": @"recovery.deleteBackup", @"permission": @"Edit", @"params": @{ @"comboId": @"string", @"confirm": @"boolean optional" }, @"returns": @{ @"deleted": @"boolean", @"comboId": @"string" } },
            @{ @"name": @"recovery.prune", @"permission": @"Edit", @"params": @{ @"keepLastN": @"number optional", @"olderThanDays": @"number optional", @"dryRun": @"boolean", @"confirmInvalid": @"boolean optional" }, @"returns": @{ @"dryRun": @"boolean", @"pruned": @"array", @"skipped": @"array" } },
            @{ @"name": @"workspace.getRoot", @"permission": @"Read", @"params": @{}, @"returns": @{ @"path": @"string" } },
            @{ @"name": @"workspace.revision", @"permission": @"Read", @"params": @{}, @"returns": @{ @"revisionId": @"number", @"changedFiles": @"array", @"lastMutationReceipt": @"object", @"externalChangeDetected": @"boolean" } },
            @{ @"name": @"workspace.snapshot", @"permission": @"Read", @"params": @{ @"sinceRevision": @"number optional", @"paths": @"array optional", @"snapshotMode": @"mutated_only|tracked_files|explicit_paths", @"maxFiles": @"number <= 500 optional" }, @"returns": @{ @"snapshotId": @"string", @"snapshotMode": @"string", @"fileHashes": @"object", @"complete": @"boolean", @"truncated": @"boolean", @"hashAlgorithm": @"fnv1a_16hex" } },
            @{ @"name": @"workspace.status", @"permission": @"Read", @"params": @{}, @"returns": @{ @"root": @"string", @"gitHead": @"string", @"dirtyFiles": @"array", @"fileAnchors": @"object", @"affectedFiles": @"array", @"driftDetected": @"boolean", @"contextRefreshId": @"number", @"lastVerifiedCommand": @"string", @"lastVerifiedAt": @"string" } },
            @{ @"name": @"workspace.refreshAnchor", @"permission": @"Read", @"params": @{}, @"returns": @"same as workspace.status with refreshed=true" },
            @{ @"name": @"workspace.continueAnyway", @"permission": @"Read", @"params": @{}, @"returns": @{ @"continueAnyway": @"boolean", @"expiresAt": @"string", @"contextRefreshId": @"number" } },
            @{ @"name": @"operation.status", @"permission": @"Read", @"params": @{ @"idempotencyKey": @"string" }, @"returns": @{ @"status": @"completed|unknown", @"mutationReceipt": @"object optional" } },
            @{ @"name": @"workspace.openFolder", @"permission": @"Destructive", @"params": @{ @"path": @"directory path" }, @"returns": @{ @"opened": @"boolean" } },
            @{ @"name": @"workspace.findFiles", @"permission": @"Read", @"params": @{ @"pattern": @"glob pattern", @"maxResults": @"number <= 1000 optional" }, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"workspace.listFiles", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"workspace.grep", @"permission": @"Read", @"params": @{ @"query": @"literal string", @"maxResults": @"number <= 500 optional", @"resultOffset": @"number optional" }, @"returns": @{ @"matches": @"array with resultIndex/matchSpans/contextBefore/contextAfter", @"mode": @"literal_substring", @"nextResultOffset": @"number|null", @"truncated": @"boolean", @"filesRead": @"number", @"filesReadFromDisk": @"number", @"filesSkippedUnreadable": @"number" } },
            @{ @"name": @"workspace.searchStart", @"permission": @"Read", @"params": @{ @"query": @"string", @"include": @"array optional", @"exclude": @"array optional", @"caseSensitive": @"boolean optional" }, @"returns": @{ @"searchId": @"string", @"totalFiles": @"number" } },
            @{ @"name": @"workspace.searchNext", @"permission": @"Read", @"params": @{ @"searchId": @"string", @"maxFiles": @"number optional" }, @"returns": @{ @"matches": @"array", @"finished": @"boolean" } },
            @{ @"name": @"workspace.searchCancel", @"permission": @"Read", @"params": @{ @"searchId": @"string" }, @"returns": @{ @"cancelled": @"boolean" } },
            @{ @"name": @"workspace.openFile", @"permission": @"Read", @"params": @{ @"path": @"string" }, @"returns": @{ @"opened": @"boolean" } },
            @{ @"name": @"workspace.getRecentFiles", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"search.files", @"permission": @"Read", @"params": @{ @"query": @"string", @"include": @"array optional", @"exclude": @"array optional", @"directory": @"string optional", @"extension": @"string optional", @"maxResults": @"positive number <= 500 optional" }, @"returns": @{ @"results": @"array with path/matchReason", @"searchMode": @"deterministic_path_match", @"sortOrder": @"match_reason_path", @"filesConsidered": @"number", @"filesSkippedSymlink": @"number" } },
            @{ @"name": @"search.text", @"permission": @"Read", @"params": @{ @"query": @"literal string", @"before": @"non-negative number <= 20 optional", @"after": @"non-negative number <= 20 optional", @"maxResults": @"positive number <= 500 optional", @"resultOffset": @"number optional" }, @"returns": @{ @"results": @"array with resultIndex/matchSpans", @"mode": @"literal_substring", @"nextResultOffset": @"number|null", @"truncated": @"boolean" } },
            @{ @"name": @"search.literal", @"permission": @"Read", @"params": @{ @"query": @"literal string", @"maxResults": @"number optional" }, @"returns": @{ @"results": @"array", @"searchMode": @"literal_substring", @"scoringDisabled": @"true", @"agentSafe": @"true" } },
            @{ @"name": @"search.tokens", @"permission": @"Read", @"params": @{ @"query": @"whitespace-separated tokens", @"maxResults": @"number optional" }, @"returns": @{ @"results": @"array", @"searchMode": @"literal_token_conjunctive", @"matchReason": @"all_tokens_literal" } },
            @{ @"name": @"search.paths", @"permission": @"Read", @"params": @{ @"query": @"path substring", @"maxResults": @"number optional" }, @"returns": @"alias of search.files" },
            @{ @"name": @"search.references", @"permission": @"Read", @"params": @{ @"symbol": @"string", @"maxResults": @"number optional" }, @"returns": @{ @"results": @"array sorted path_line_column", @"scoringDisabled": @"true" } },
            @{ @"name": @"search.todo", @"permission": @"Read", @"params": @{ @"include": @"array optional", @"maxResults": @"positive number <= 500 optional" }, @"returns": @{ @"results": @"array" } },
            @{ @"name": @"search.semantic", @"permission": @"Read", @"params": @{ @"query": @"string (deprecated)", @"allowExperimental": @"boolean required for any result" }, @"returns": @"deprecated — returns semantic_disabled unless allowExperimental" },
            @{ @"name": @"tool.registry", @"permission": @"Read", @"params": @{}, @"returns": @{ @"tools": @"array with agentSafe/deterministic/deprecated" } },
            @{ @"name": @"tool.capabilities", @"permission": @"Read", @"params": @{}, @"returns": @{ @"agentSafeMethods": @"array", @"deprecatedMethods": @"array" } },
            @{ @"name": @"search.diagnostics", @"permission": @"Read", @"params": @{ @"severity": @"string optional", @"source": @"string optional" }, @"returns": @{ @"results": @"array" } },
            @{ @"name": @"file.read", @"permission": @"Read", @"params": @{ @"path": @"string" }, @"returns": @{ @"text": @"string" } },
            @{ @"name": @"file.readBatch", @"permission": @"Read", @"params": @{ @"paths": @"array of strings" }, @"returns": @{ @"results": @"object mapping path to {text, ok, error}" } },
            @{ @"name": @"file.readRange", @"permission": @"Read", @"params": @{ @"path": @"string", @"startLine": @"number", @"endLine": @"number" }, @"returns": @{ @"text": @"string" } },
            @{ @"name": @"file.readAround", @"permission": @"Read", @"params": @{ @"path": @"string", @"line": @"positive number", @"before": @"non-negative number <= 500 optional", @"after": @"non-negative number <= 500 optional" }, @"returns": @{ @"text": @"string" } },
            @{ @"name": @"file.getChunks", @"permission": @"Read", @"params": @{ @"path": @"string", @"chunkSize": @"number optional" }, @"returns": @{ @"chunks": @"array" } },
            @{ @"name": @"file.stat", @"permission": @"Read", @"params": @{ @"path": @"string" }, @"returns": @{ @"path": @"string", @"sizeBytes": @"number", @"lineCount": @"number" } },
            @{ @"name": @"file.statBatch", @"permission": @"Read", @"params": @{ @"paths": @"array of strings" }, @"returns": @{ @"results": @"object mapping path to {sizeBytes, lineCount, ok, error}" } },
            @{ @"name": @"file.write", @"permission": @"Edit", @"params": @{ @"path": @"string", @"content": @"string" }, @"returns": @{ @"written": @"boolean" } },
            @{ @"name": @"file.create", @"permission": @"Edit", @"params": @{ @"path": @"string", @"content": @"string" }, @"returns": @{ @"created": @"boolean" } },
            @{ @"name": @"editor.getActiveFile", @"permission": @"Read", @"params": @{}, @"returns": @{ @"path": @"string" } },
            @{ @"name": @"editor.getOpenFiles", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"editor.getText", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"text": @"string" } },
            @{ @"name": @"editor.getSelection", @"permission": @"Read", @"params": @{}, @"returns": @{ @"text": @"string", @"start": @"number", @"end": @"number" } },
            @{ @"name": @"editor.setSelection", @"permission": @"Edit", @"params": @{ @"start": @"number", @"end": @"number" }, @"returns": @{ @"success": @"boolean" } },
            @{ @"name": @"editor.insertText", @"permission": @"Edit", @"params": @{ @"text": @"string" }, @"returns": @{ @"inserted": @"boolean" } },
            @{ @"name": @"editor.replaceSelection", @"permission": @"Edit", @"params": @{ @"text": @"string" }, @"returns": @{ @"replaced": @"boolean" } },
            @{ @"name": @"editor.replaceRange", @"permission": @"Edit", @"params": @{ @"path": @"string optional", @"start": @"number", @"end": @"number", @"text": @"string" }, @"returns": @{ @"replaced": @"boolean" } },
            @{ @"name": @"editor.applyPatch", @"permission": @"Edit/Destructive", @"params": @{ @"path": @"string", @"patch": @"unified diff", @"confirm": @"boolean optional" }, @"returns": @{ @"patched": @"boolean", @"validation": @"object" } },
            @{ @"name": @"editor.saveFile", @"permission": @"Edit", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"saved": @"boolean" } },
            @{ @"name": @"editor.closeFile", @"permission": @"Edit", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"closed": @"boolean" } },
            @{ @"name": @"editor.goto", @"permission": @"Read", @"params": @{ @"path": @"string optional", @"line": @"number", @"column": @"number optional" }, @"returns": @{ @"navigated": @"boolean" } },
            @{ @"name": @"analysis.workspaceSummary", @"permission": @"Read", @"params": @{}, @"returns": @{ @"root": @"string", @"languages": @"object" } },
            @{ @"name": @"analysis.searchRanked", @"permission": @"Read", @"params": @{ @"query": @"string", @"maxResults": @"positive number <= 500 optional" }, @"returns": @{ @"results": @"array" } },
            @{ @"name": @"analysis.fileSummary", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"path": @"string", @"symbolCount": @"number" } },
            @{ @"name": @"analysis.relatedFiles", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"symbols.document", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"symbols": @"array" } },
            @{ @"name": @"symbols.hierarchy", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"symbols": @"array (nested tree)" } },
            @{ @"name": @"symbols.outline", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"symbols": @"array" } },
            @{ @"name": @"symbols.activeDocument", @"permission": @"Read", @"params": @{}, @"returns": @{ @"symbols": @"array" } },
            @{ @"name": @"symbols.references", @"permission": @"Read", @"params": @{ @"symbol": @"string" }, @"returns": @{ @"references": @"array" } },
            @{ @"name": @"symbols.atCursor", @"permission": @"Read", @"params": @{}, @"returns": @{ @"symbol": @"object" } },
            @{ @"name": @"diff.validatePatch", @"permission": @"Read", @"params": @{ @"path": @"string", @"patch": @"unified diff", @"currentText": @"string optional", @"ignoreSyntax": @"boolean optional (default: true, set false for strict syntax enforcement)" }, @"returns": @{ @"validation": @"object with ok/patchAppliesCleanly/requiresConfirmation/syntaxDanger/syntaxWarning/rejectedReason" } },
            @{ @"name": @"diff.applyPatchPreview", @"permission": @"Read", @"params": @{ @"path": @"string", @"patch": @"unified diff" }, @"returns": @{ @"validation": @"object with ok/patchAppliesCleanly/syntaxDanger/syntaxWarning" } },
            @{ @"name": @"diff.workspaceInfo", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array", @"totalAdded": @"number", @"totalDeleted": @"number" } },
            @{ @"name": @"diff.stats", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array", @"totalAdded": @"number", @"totalDeleted": @"number" } },
            @{ @"name": @"diff.file", @"permission": @"Read", @"params": @{ @"path": @"string" }, @"returns": @{ @"diff": @"string" } },
            @{ @"name": @"diff.chunk", @"permission": @"Read", @"params": @{ @"source": @"unstaged|staged|file", @"path": @"string optional", @"offset": @"number optional", @"maxBytes": @"number optional" }, @"returns": @{ @"chunk": @"string", @"offset": @"number", @"nextOffset": @"number", @"hasMore": @"boolean", @"sha256": @"string" } },
            @{ @"name": @"diff.hunks", @"permission": @"Read", @"params": @{ @"source": @"unstaged|staged|file", @"path": @"string optional", @"maxHunks": @"number optional <= 5000", @"hunkOffset": @"number optional", @"includeLines": @"boolean optional", @"maxLinesPerHunk": @"number optional <= 1000" }, @"returns": @{ @"files": @"array with literal unified diff hunk headers/lines", @"totalHunks": @"number", @"nextHunkOffset": @"number|null", @"truncated": @"boolean", @"sha256": @"string" } },
            @{ @"name": @"diff.previewPatch", @"permission": @"Read", @"params": @{ @"path": @"string", @"patch": @"unified diff" }, @"returns": @{ @"ok": @"boolean", @"risk": @"string" } },
            @{ @"name": @"patch.validate", @"permission": @"Read", @"params": @{ @"path": @"string", @"patch": @"unified diff", @"ignoreSyntax": @"boolean optional (default: true; set false for strict syntax rejection)", @"currentText": @"string optional" }, @"returns": @{ @"applies": @"boolean", @"changedLines": @"number", @"hunks": @"number", @"requiresConfirmation": @"boolean", @"validation": @"object with ok/syntaxDanger/syntaxWarning/rejectedReason/patchAppliesCleanly" } },
            @{ @"name": @"patch.preview", @"permission": @"Read", @"params": @{ @"path": @"string", @"patch": @"unified diff" }, @"returns": @{ @"addedLines": @"number", @"removedLines": @"number", @"hunks": @"array", @"syntaxDanger": @"boolean", @"syntaxWarning": @"string optional" } },
            @{ @"name": @"patch.chunk", @"permission": @"Read", @"params": @{ @"patch": @"unified diff", @"offset": @"number optional", @"maxBytes": @"number optional" }, @"returns": @{ @"chunk": @"string", @"offset": @"number", @"nextOffset": @"number", @"hasMore": @"boolean", @"sha256": @"string" } },
            @{ @"name": @"patch.hunks", @"permission": @"Read", @"params": @{ @"patch": @"unified diff", @"maxHunks": @"number optional <= 5000", @"hunkOffset": @"number optional", @"includeLines": @"boolean optional", @"maxLinesPerHunk": @"number optional <= 1000" }, @"returns": @{ @"files": @"array with literal unified diff hunk headers/lines", @"totalHunks": @"number", @"nextHunkOffset": @"number|null", @"truncated": @"boolean", @"sha256": @"string" } },
            @{ @"name": @"patch.apply", @"permission": @"Edit/Destructive", @"params": @{ @"path": @"string", @"patch": @"unified diff", @"confirm": @"boolean optional", @"expectBeforeHash": @"string optional (optimistic concurrency)", @"taskId": @"string optional", @"coherenceTokenId": @"string optional (required with taskId)", @"expectedWorkspaceRevision": @"number optional (required with taskId)" }, @"returns": @{ @"patched": @"boolean", @"mutationReceipt": @"object with beforeContentHash/postContentHash/patchFingerprint/applyChannel" } },
            @{ @"name": @"patch.applyBatch", @"permission": @"Edit/Destructive", @"params": @{ @"patches": @"array with path/patch/expectBeforeHash", @"dryRun": @"boolean optional", @"confirm": @"boolean optional", @"idempotencyKey": @"string optional", @"taskId": @"string optional", @"coherenceTokenId": @"string optional", @"expectedWorkspaceRevision": @"number optional" }, @"returns": @{ @"applied": @"boolean", @"atomic": @"boolean", @"batchMutationReceipt": @"object", @"revisionBefore": @"number", @"revisionAfter": @"number" } },
            @{ @"name": @"patch.revertLast", @"permission": @"Edit", @"params": @{}, @"returns": @{ @"reverted": @"boolean" } },
            @{ @"name": @"diff.current", @"permission": @"Read", @"params": @{}, @"returns": @{ @"changes": @"object" } },
            @{ @"name": @"diff.staged", @"permission": @"Read", @"params": @{}, @"returns": @{ @"diff": @"string" } },
            @{ @"name": @"diff.unstaged", @"permission": @"Read", @"params": @{}, @"returns": @{ @"diff": @"string" } },
            @{ @"name": @"diff.summary", @"permission": @"Read", @"params": @{}, @"returns": @{ @"filesChanged": @"number", @"addedLines": @"number", @"removedLines": @"number" } },
            @{ @"name": @"buffers.snapshot", @"permission": @"Read", @"params": @{}, @"returns": @{ @"buffers": @"array" } },
            @{ @"name": @"buffers.dirty", @"permission": @"Read", @"params": @{}, @"returns": @{ @"files": @"array" } },
            @{ @"name": @"buffers.active", @"permission": @"Read", @"params": @{}, @"returns": @{ @"path": @"string", @"selection": @"object" } },
            @{ @"name": @"buffers.unsavedDiff", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"diff": @"string" } },
            @{ @"name": @"changes.current", @"permission": @"Read", @"params": @{}, @"returns": @{ @"modifiedFiles": @"array", @"unsavedBuffers": @"array", @"stagedFiles": @"array", @"unstagedFiles": @"array" } },
            @{ @"name": @"changes.summary", @"permission": @"Read", @"params": @{}, @"returns": @{ @"summary": @"object" } },
            @{ @"name": @"changes.revertFile", @"permission": @"Destructive", @"params": @{ @"path": @"string" }, @"returns": @{ @"reverted": @"boolean" } },
            @{ @"name": @"verify.run", @"permission": @"Execute", @"params": @{ @"command": @"non-empty string configured by AgentVerifyCommands", @"cwd": @"workspace-relative or absolute workspace path optional" }, @"returns": @{ @"started": @"boolean" } },
            @{ @"name": @"verify.last", @"permission": @"Read", @"params": @{}, @"returns": @{ @"command": @"string", @"status": @"object" } },
            @{ @"name": @"verify.status", @"permission": @"Read", @"params": @{}, @"returns": @{ @"status": @"object" } },
            @{ @"name": @"verify.failures", @"permission": @"Read", @"params": @{}, @"returns": @{ @"failures": @"array", @"problems": @"array" } },
            @{ @"name": @"context.snapshot", @"permission": @"Read", @"params": @{}, @"returns": @{ @"snapshotId": @"string", @"snapshot": @"object" } },
            @{ @"name": @"context.delta", @"permission": @"Read", @"params": @{ @"snapshotId": @"string" }, @"returns": @{ @"changed": @"object" } },
            @{ @"name": @"task.start", @"permission": @"Read", @"params": @{ @"goal": @"string", @"scope": @"object", @"budget": @"object", @"verify": @"array optional" }, @"returns": @{ @"taskId": @"string", @"task": @"object" } },
            @{ @"name": @"task.status", @"permission": @"Read", @"params": @{ @"taskId": @"string" }, @"returns": @{ @"task": @"object" } },
            @{ @"name": @"task.step", @"permission": @"Edit/Execute", @"params": @{ @"taskId": @"string", @"step": @"object" }, @"returns": @{ @"stepResult": @"object" } },
            @{ @"name": @"task.runLoop", @"permission": @"Edit/Execute", @"params": @{ @"taskId": @"string", @"steps": @"array" }, @"returns": @{ @"results": @"array", @"finalDiff": @"object" } },
            @{ @"name": @"task.cancel", @"permission": @"Read", @"params": @{ @"taskId": @"string" }, @"returns": @{ @"cancelled": @"boolean" } },
            @{ @"name": @"task.result", @"permission": @"Read", @"params": @{ @"taskId": @"string" }, @"returns": @{ @"result": @"object" } },
            @{ @"name": @"edit.plan", @"permission": @"Read", @"params": @{ @"steps": @"array" }, @"returns": @{ @"planId": @"string", @"plan": @"object" } },
            @{ @"name": @"edit.executePlan", @"permission": @"Edit/Execute", @"params": @{ @"planId": @"string optional", @"steps": @"array optional", @"taskId": @"string optional" }, @"returns": @{ @"results": @"array" } },
            @{ @"name": @"repair.fromCompilerErrors", @"permission": @"Read", @"params": @{ @"files": @"array optional of {path, ranges:[{startLine,endLine}]}; paths must stay inside workspace", @"diagnostics": @"array optional" }, @"returns": @{ @"failure": @"string", @"files": @"array" } },
            @{ @"name": @"repair.fromTestFailures", @"permission": @"Read", @"params": @{ @"files": @"array optional of {path, ranges:[{startLine,endLine}]}; paths must stay inside workspace", @"diagnostics": @"array optional" }, @"returns": @{ @"failure": @"string", @"files": @"array" } },
            @{ @"name": @"repair.fromPatchFailure", @"permission": @"Read", @"params": @{ @"files": @"array optional of {path, ranges:[{startLine,endLine}]}; paths must stay inside workspace", @"diagnostics": @"array optional" }, @"returns": @{ @"failure": @"string", @"files": @"array" } },
            @{ @"name": @"diagnostics.list", @"permission": @"Read", @"params": @{}, @"returns": @{ @"diagnostics": @"array with stable id" } },
            @{ @"name": @"diagnostics.summary", @"permission": @"Read", @"params": @{}, @"returns": @{ @"errors": @"number", @"warnings": @"number" } },
            @{ @"name": @"diagnostics.cluster", @"permission": @"Read", @"params": @{}, @"returns": @{ @"clusters": @"array" } },
            @{ @"name": @"diagnostics.forFile", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"diagnostics": @"array" } },
            @{ @"name": @"problems.list", @"permission": @"Read", @"params": @{}, @"returns": @{ @"problems": @"array with stable id" } },
            @{ @"name": @"problems.open", @"permission": @"Edit", @"params": @{ @"id": @"stable diagnostic id" }, @"returns": @{ @"opened": @"boolean" } },
            @{ @"name": @"problems.clearSource", @"permission": @"Edit", @"params": @{ @"source": @"string" }, @"returns": @{ @"cleared": @"boolean" } },
            @{ @"name": @"terminal.run", @"permission": @"Execute", @"params": @{ @"command": @"non-empty string", @"cwd": @"workspace-relative or absolute path optional", @"show": @"boolean optional" }, @"returns": @{ @"run": @"boolean" } },
            @{ @"name": @"terminal.stop", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"stopped": @"boolean" } },
            @{ @"name": @"terminal.getOutput", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"output": @"string" } },
            @{ @"name": @"terminal.clear", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"cleared": @"boolean" } },
            @{ @"name": @"terminal.status", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"pid": @"number", @"running": @"boolean" } },
            @{ @"name": @"terminal.jobs", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"jobs": @"array" } },
            @{ @"name": @"terminal.history", @"permission": @"Execute", @"params": @{}, @"returns": @{ @"commands": @"array" } },
            @{ @"name": @"git.status", @"permission": @"Read", @"params": @{}, @"returns": @{ @"branch": @"string", @"staged": @"array", @"modified": @"array", @"untracked": @"array" } },
            @{ @"name": @"git.diff", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"diff": @"string" } },
            @{ @"name": @"git.stage", @"permission": @"Edit", @"params": @{ @"path": @"string" }, @"returns": @{ @"staged": @"boolean" } },
            @{ @"name": @"git.unstage", @"permission": @"Edit", @"params": @{ @"path": @"string" }, @"returns": @{ @"unstaged": @"boolean" } },
            @{ @"name": @"git.discard", @"permission": @"Destructive", @"params": @{ @"path": @"string" }, @"returns": @{ @"discarded": @"boolean" } },
            @{ @"name": @"git.commit", @"permission": @"Destructive", @"params": @{ @"message": @"string" }, @"returns": @{ @"committed": @"boolean" } },
            @{ @"name": @"language.diagnostics", @"permission": @"Read", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"diagnostics": @"array" } },
            @{ @"name": @"language.format", @"permission": @"Execute", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"formatted": @"boolean" } },
            @{ @"name": @"language.lint", @"permission": @"Execute", @"params": @{ @"path": @"string optional" }, @"returns": @{ @"linted": @"boolean" } },
            @{ @"name": @"language.gotoDefinition", @"permission": @"Read", @"params": @{}, @"returns": @{ @"symbol": @"string", @"definition": @"object", @"candidates": @"array" } },
            @{ @"name": @"language.hover", @"permission": @"Read", @"params": @{ @"path": @"string optional", @"line": @"number", @"column": @"number" }, @"returns": @{ @"hover": @"string" } },
            @{ @"name": @"language.completions", @"permission": @"Read", @"params": @{ @"path": @"string optional", @"line": @"number", @"column": @"number" }, @"returns": @{ @"completions": @"array" } },
            @{ @"name": @"language.definition", @"permission": @"Read", @"params": @{ @"path": @"string optional", @"line": @"number", @"column": @"number" }, @"returns": @{ @"location": @"object" } },
            @{ @"name": @"session.info", @"permission": @"Read", @"params": @{}, @"returns": @{ @"workspace": @"string", @"activeFile": @"string" } },
            @{ @"name": @"session.workflowState", @"permission": @"Read", @"params": @{}, @"returns": @{ @"workspace": @"string", @"activeFile": @"string" } },
            @{ @"name": @"session.recentCommands", @"permission": @"Read", @"params": @{}, @"returns": @{ @"commands": @"array" } },
            @{ @"name": @"session.lastSearches", @"permission": @"Read", @"params": @{}, @"returns": @{ @"searches": @"array" } },
            @{ @"name": @"session.clearHistory", @"permission": @"Read", @"params": @{}, @"returns": @{ @"cleared": @"boolean" } },
            @{ @"name": @"system.info", @"permission": @"Read", @"params": @{}, @"returns": @{ @"os": @"string", @"arch": @"string", @"memoryGB": @"number", @"cpuCount": @"number", @"appVersion": @"string" } },
            @{ @"name": @"event.subscribe", @"permission": @"Read", @"params": @{ @"types": @"non-empty string array" }, @"returns": @{ @"subscribed": @"boolean", @"types": @"array" } },
            @{ @"name": @"event.unsubscribe", @"permission": @"Read", @"params": @{ @"types": @"non-empty string array" }, @"returns": @{ @"unsubscribed": @"boolean", @"types": @"array" } },
            @{ @"name": @"events.recent", @"permission": @"Read", @"params": @{ @"limit": @"number optional", @"afterSequence": @"number optional", @"types": @"string array optional" }, @"returns": @{ @"events": @"array", @"truncated": @"boolean", @"mode": @"string" } },
            @{ @"name": @"approval.list", @"permission": @"Read", @"params": @{ @"status": @"pending|approved|rejected|expired optional", @"limit": @"number optional" }, @"returns": @{ @"approvals": @"array", @"count": @"number", @"mode": @"approval_list" } },
            @{ @"name": @"approval.get", @"permission": @"Read", @"params": @{ @"approvalId": @"string" }, @"returns": @{ @"approval": @"object", @"mode": @"approval_get" } },
            @{ @"name": @"approval.resolve", @"permission": @"Execute", @"params": @{ @"approvalId": @"string", @"decision": @"approved|rejected", @"reason": @"string optional", @"resolvedBy": @"string optional" }, @"returns": @{ @"resolution": @"object", @"approval": @"object", @"mode": @"approval_resolve" } }
        ];
    });
    return methods;
}

NSDictionary* MacControlDescriptionForRPCMethod(NSString* method) {
    for (NSDictionary* desc in MacControlRPCMethodDescriptions()) {
        if ([desc[@"name"] isEqualToString:method]) {
            return desc;
        }
    }
    return @{};
}

NSArray<NSDictionary*>* MacControlChipRegistry(void) {
    static NSArray<NSDictionary*>* chips = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        chips = @[
            @{ @"name": @"file.readRange", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"path", @"startLine", @"endLine"] },
            @{ @"name": @"file.readAround", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"path", @"line"] },
            @{ @"name": @"file.getChunks", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"path"] },
            @{ @"name": @"search.files", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"search.text", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"search.todo", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"search.literal", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"search.tokens", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"search.paths", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"search.references", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"symbol"] },
            @{ @"name": @"search.semantic", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @NO, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"query"] },
            @{ @"name": @"tool.registry", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"tool.capabilities", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"search.diagnostics", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"patch.validate", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"path", @"patch"] },
            @{ @"name": @"patch.preview", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"path", @"patch"] },
            @{ @"name": @"patch.chunk", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"patch"] },
            @{ @"name": @"patch.hunks", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"patch"] },
            @{ @"name": @"patch.apply", @"version": @1, @"category": @"mutation", @"permission": @"edit", @"deterministic": @YES, @"idempotency": @"non_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @YES, @"runsProcess": @NO, @"usesTerminal": @NO, @"mayModifyBuffers": @YES }, @"rollback": @{ @"supported": @YES, @"kind": @"content_preimage", @"conflictPolicy": @"fail_closed" }, @"requiredParams": @[@"path", @"patch"] },
            @{ @"name": @"patch.applyBatch", @"version": @1, @"category": @"mutation", @"permission": @"edit", @"deterministic": @YES, @"idempotency": @"non_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @YES, @"runsProcess": @NO, @"usesTerminal": @NO, @"mayModifyBuffers": @YES }, @"rollback": @{ @"supported": @YES, @"kind": @"content_preimage", @"conflictPolicy": @"fail_closed" }, @"requiredParams": @[@"patches"] },
            @{ @"name": @"file.write", @"version": @1, @"category": @"mutation", @"permission": @"edit", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @YES, @"runsProcess": @NO, @"usesTerminal": @NO, @"mayModifyBuffers": @YES }, @"rollback": @{ @"supported": @YES, @"kind": @"content_preimage", @"conflictPolicy": @"fail_closed" }, @"requiredParams": @[@"path", @"content"] },
            @{ @"name": @"file.create", @"version": @1, @"category": @"mutation", @"permission": @"edit", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @YES, @"runsProcess": @NO, @"usesTerminal": @NO, @"mayModifyBuffers": @YES }, @"rollback": @{ @"supported": @YES, @"kind": @"content_preimage", @"conflictPolicy": @"fail_closed" }, @"requiredParams": @[@"path", @"content"] },
            @{ @"name": @"diff.summary", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"diff.current", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"diff.chunk", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @YES, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"source"] },
            @{ @"name": @"diff.hunks", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @YES, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"source"] },
            @{ @"name": @"verify.run", @"version": @1, @"category": @"execute", @"permission": @"execute", @"deterministic": @NO, @"idempotency": @"non_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @YES, @"runsProcess": @YES, @"usesTerminal": @YES }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[@"command"] },
            @{ @"name": @"verify.failures", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @NO, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"context.snapshot", @"version": @1, @"category": @"read", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"repair.fromCompilerErrors", @"version": @1, @"category": @"repair_context", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"repair.fromTestFailures", @"version": @1, @"category": @"repair_context", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] },
            @{ @"name": @"repair.fromPatchFailure", @"version": @1, @"category": @"repair_context", @"permission": @"read", @"deterministic": @YES, @"idempotency": @"conditionally_idempotent", @"sideEffects": @{ @"readsWorkspace": @YES, @"writesWorkspace": @NO, @"runsProcess": @NO, @"usesTerminal": @NO }, @"rollback": @{ @"supported": @NO }, @"requiredParams": @[] }
        ];
    });
    return chips;
}

NSDictionary* MacControlMetadataForChip(NSString* chip) {
    NSString* canonical = CanonicalChipName(chip);
    for (NSDictionary* meta in MacControlChipRegistry()) {
        if ([meta[@"name"] isEqualToString:canonical]) return meta;
    }
    return nil;
}

NSDictionary* MacControlPrimitiveForChip(NSString* chip, NSDictionary* params) {
    NSString* canonical = CanonicalChipName(chip);
    if (canonical.length == 0) return @{};
    return @{ @"method": canonical, @"params": params ?: @{} };
}
