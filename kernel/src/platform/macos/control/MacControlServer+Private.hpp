#pragma once

#import "MacControlServer.hpp"
#import "MacControlWindowBridge.hpp"
#import "WorkspaceSessionBridge.hpp"
#import "MacControlRecoveryStore.hpp"
#import "MacControlSearchService.hpp"
#import "MacControlPatchService.hpp"
#import "MacControlWorkspaceState.hpp"
#import "MacControlTaskRuntime.hpp"
#import "MacControlComboRuntime.hpp"
#import "MacControlMemoryService.hpp"
#import "MacControlApprovalService.hpp"

@class DietCodeClientConnection;

@interface DietCodeControlServer () {
@public
    BOOL _isKernelMode;
    DietCodeWorkspaceSession* _workspaceSession;
    DietCodeControlWindowBridge* _windowBridge;
    MacControlRecoveryStore* _recoveryStore;
    MacControlSearchService* _searchService;
    MacControlPatchService* _patchService;
    MacControlWorkspaceState* _workspaceState;
    MacControlTaskRuntime* _taskRuntime;
    MacControlComboRuntime* _comboRuntime;
    MacControlMemoryService* _memoryService;
    MacControlApprovalService* _approvalService;
    int _serverFd;
    NSThread* _acceptThread;
    NSString* _lastVerifyCommand;
    NSDate* _lastVerifyStartedAt;
    NSDate* _lastVerifyFinishedAt;
    NSNumber* _lastVerifyExitCode;
    NSMutableDictionary<NSString*, NSDictionary*>* _contextSnapshots;
    NSInteger _contextSnapshotCounter;
    NSMutableDictionary<NSString*, NSDictionary*>* _editPlans;
    NSInteger _editPlanCounter;
    NSInteger _comboCounter;
    NSMutableDictionary<NSNumber*, DietCodeClientConnection*>* _activeConnections;
    NSMutableArray<NSDictionary*>* _eventRingBuffer;
    NSInteger _eventSequence;
    NSString* _sessionToken;
    dispatch_queue_t _executionQueue;
    dispatch_queue_t _readQueue;
    BOOL _globalMutationLock;
    NSDictionary* _lastVerifyStatus;
    NSString* _lastComboId;
}

- (NSString*)safeWorkspacePath;
- (NSString*)safeTextForFileAtPath:(NSString*)path;
- (BOOL)safeReplaceTextInRange:(NSRange)range withText:(NSString*)text forFileAtPath:(NSString*)path;
- (NSArray<NSString*>*)safeOpenFilePaths;
- (NSArray<NSDictionary*>*)safeProblemsList;
- (NSString*)safeActiveFilePath;
- (NSArray*)safeOpenTabs;
- (NSDictionary*)safeGitStatusInfo;
- (NSString*)safeGitDiffForFile:(NSString*)path;
- (NSDictionary*)safeActiveSelectionInfo;
- (NSString*)safeTerminalOutput;
- (NSArray*)safeSessionRecentCommands;
- (NSArray*)safeSessionLastSearches;
- (pid_t)safeTerminalPid;
- (NSArray*)safeLanguageDiagnosticsForPath:(NSString*)path;

- (BOOL)path:(NSString*)path isAllowedByScope:(NSDictionary*)scope;
- (BOOL)dirtyBufferExistsAtPath:(NSString*)path;
- (NSArray<NSString*>*)verificationFailureLines;
- (NSDictionary*)currentChangesInfo;
- (NSDictionary*)runVerificationCommand:(NSString*)command cwd:(NSString*)cwd;
- (NSDictionary*)verificationStatus;
- (NSDictionary*)contextSnapshotPayload;
- (NSDictionary*)repairContextForFailure:(NSString*)failure params:(NSDictionary*)params outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg;
- (void)logAuditMethod:(NSString*)method caller:(NSString*)caller permission:(NSString*)permission duration:(long long)duration result:(NSString*)result paths:(NSString*)paths;
- (void)executeNestedMethod:(NSString*)method
                     params:(NSDictionary*)params
                  outResult:(NSDictionary**)outResult
                 outErrCode:(NSString**)outErrCode
                    outErrMsg:(NSString**)outErrMsg
                   outPaths:(NSString**)outPaths;
- (void)executeMethod:(NSString*)method
               params:(NSDictionary*)params
            outResult:(NSDictionary**)outResult
           outErrCode:(NSString**)outErrCode
              outErrMsg:(NSString**)outErrMsg
             outPaths:(NSString**)outPaths;
- (void)configureServices;
- (NSInteger)safeAgentAutonomyLevel;
- (BOOL)isDestructiveRequestSafe:(NSString*)method params:(NSDictionary*)params;
- (void)sendSuccess:(NSString*)reqId result:(NSDictionary*)result clientFd:(int)clientFd;
- (void)sendError:(NSString*)reqId code:(id)code message:(NSString*)message clientFd:(int)clientFd;

@end

@interface DietCodeControlServer (File)
- (void)executeFileMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Editor)
- (void)executeEditorMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Git)
- (void)executeGitMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Terminal)
- (void)executeTerminalMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Context)
- (void)executeContextMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Memory)
- (void)ensureMemoryServiceForWorkspace;
- (void)executeMemoryMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
- (void)persistMutationToMemory:(NSString*)method idempotencyKey:(NSString*)idempotencyKey paramsHash:(NSString*)paramsHash receipt:(NSDictionary*)receipt changedPaths:(NSArray<NSString*>*)paths revisionBefore:(NSInteger)revisionBefore revisionAfter:(NSInteger)revisionAfter resultPayload:(NSDictionary*)resultPayload;
@end

@interface DietCodeControlServer (Runtime)
- (NSDictionary*)runtimeTimelineResult:(NSDictionary*)params activityOnly:(BOOL)activityOnly;
- (void)executeRuntimeMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Shell)
- (void)executeShellMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
@end

@interface DietCodeControlServer (Approval)
- (void)executeApprovalMethod:(NSString*)method params:(NSDictionary*)params outResult:(NSDictionary**)outResult outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg outPaths:(NSString**)outPaths;
- (BOOL)queueDestructiveApprovalIfNeeded:(NSString*)method params:(NSDictionary*)params caller:(NSString*)caller rationale:(NSString*)rationale reqId:(NSString*)reqId clientFd:(int)clientFd;
- (BOOL)validateDestructiveApprovalIfPresent:(NSString*)method params:(NSDictionary*)params outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg;
@end

@interface DietCodeControlServer (WorkspaceDrift)
- (NSDictionary*)currentWorkspaceStatusPayload;
- (BOOL)queueWorkspaceDriftBlockIfNeeded:(NSString*)method params:(NSDictionary*)params reqId:(NSString*)reqId clientFd:(int)clientFd;
@end

@interface DietCodeControlServer (Coherence)
- (BOOL)queueCoherenceMismatchIfNeeded:(NSString*)method params:(NSDictionary*)params reqId:(NSString*)reqId clientFd:(int)clientFd;
@end

@interface DietCodeControlServer (VerifyGate)
- (void)notifyWorkspaceMutatedIfNeededForMethod:(NSString*)method params:(NSDictionary*)params result:(NSDictionary*)result;
- (void)notifyVerifyResult:(NSDictionary*)status taskId:(NSString*)taskId;
@end
