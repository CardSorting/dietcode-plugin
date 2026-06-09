#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;
@class MacControlMemoryService;
@class MacControlCoherenceRegistry;

// INVARIANT: Monotonic workspace revision + operation registry for transaction kernel.
@interface MacControlWorkspaceState : NSObject

@property (nonatomic, weak) MacControlMemoryService* memoryService;

@property (nonatomic, readonly) NSInteger revisionId;
@property (nonatomic, readonly) NSInteger verifyRevision;
@property (nonatomic, readonly, copy) NSDictionary* lastCoherenceMismatchDetail;
@property (nonatomic, readonly, copy) NSDictionary* lastMutationReceipt;
@property (nonatomic, readonly, copy) NSArray<NSString*>* lastChangedFiles;
@property (nonatomic, readonly, copy) NSString* lastMutationSource;
@property (nonatomic, readonly) BOOL externalChangeDetected;

- (NSDictionary*)revisionPayloadWithWorkspace:(NSString*)workspacePath;
- (NSDictionary*)snapshotPayloadWithWorkspace:(NSString*)workspacePath
                                 sinceRevision:(NSNumber*)sinceRevision
                                         paths:(NSArray<NSString*>*)paths
                                  snapshotMode:(NSString*)snapshotMode
                                      maxFiles:(NSNumber*)maxFiles
                                  windowBridge:(DietCodeControlWindowBridge*)windowBridge;
- (NSDictionary*)operationStatusForKey:(NSString*)idempotencyKey;

- (void)recordAgentMutationWithReceipt:(NSDictionary*)receipt
                          changedPaths:(NSArray<NSString*>*)paths
                        idempotencyKey:(NSString*)idempotencyKey
                        revisionBefore:(NSInteger)revisionBefore;
- (void)recordBatchMutationWithReceipt:(NSDictionary*)batchReceipt
                           changedPaths:(NSArray<NSString*>*)paths
                         idempotencyKey:(NSString*)idempotencyKey
                         revisionBefore:(NSInteger)revisionBefore;
- (void)noteExternalChangeForPath:(NSString*)path;
- (void)clearExternalChangeFlag;
- (void)trackHashesForPaths:(NSArray<NSString*>*)paths workspace:(NSString*)ws windowBridge:(DietCodeControlWindowBridge*)windowBridge;

- (NSDictionary*)statusPayloadWithWorkspace:(NSString*)workspacePath
                               windowBridge:(DietCodeControlWindowBridge*)windowBridge
                                    gitInfo:(NSDictionary*)gitInfo
                              verifyStatus:(NSDictionary*)verifyStatus
                        lastVerifyFinishedAt:(NSDate*)lastVerifyFinishedAt;

- (NSDictionary*)refreshAnchorWithWorkspace:(NSString*)workspacePath
                               windowBridge:(DietCodeControlWindowBridge*)windowBridge
                                    gitInfo:(NSDictionary*)gitInfo
                              verifyStatus:(NSDictionary*)verifyStatus
                        lastVerifyFinishedAt:(NSDate*)lastVerifyFinishedAt;

- (NSInteger)contextRefreshId;
- (BOOL)validateContextRefreshForParams:(NSDictionary*)params driftDetected:(BOOL)driftDetected;
- (NSDictionary*)continueAnywayPayload;

- (void)recordRuntimeError:(NSString*)stringCode method:(NSString*)method envelope:(NSDictionary*)envelope;

- (void)persistMutationToMemory:(NSString*)method
                   idempotencyKey:(NSString*)idempotencyKey
                       paramsHash:(NSString*)paramsHash
                          receipt:(NSDictionary*)receipt
                     changedPaths:(NSArray<NSString*>*)paths
                   revisionBefore:(NSInteger)revisionBefore
                    revisionAfter:(NSInteger)revisionAfter
                    resultPayload:(NSDictionary*)resultPayload;

/** Agent shell session cwd — defaults to workspace root; persists until shell.cd changes it. */
- (NSString*)agentShellCwdForWorkspace:(NSString*)workspacePath;
- (void)resetAgentShellCwdForWorkspace:(NSString*)workspacePath;
- (BOOL)setAgentShellCwd:(NSString*)absolutePath
               workspace:(NSString*)workspacePath
               errorCode:(NSString**)outErrCode
            errorMessage:(NSString**)outErrMsg;

- (void)bumpRevision;
- (void)bumpVerifyRevision;

- (NSDictionary*)issueCoherenceForTask:(NSString*)taskId
                                 paths:(NSArray<NSString*>*)paths
                             workspace:(NSString*)workspacePath
                          windowBridge:(DietCodeControlWindowBridge*)windowBridge;

- (NSDictionary*)coherencePayloadForTask:(NSString*)taskId;

- (BOOL)validateCoherenceForMutation:(NSDictionary*)params
                           workspace:(NSString*)workspacePath
                        windowBridge:(DietCodeControlWindowBridge*)windowBridge
                           outMessage:(NSString**)outMessage;

@end
