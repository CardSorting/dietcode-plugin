#pragma once

#import <Foundation/Foundation.h>

// INVARIANT: BroccoliQ-backed durable memory — records history; never decides mutation validity.
@interface MacControlMemoryService : NSObject

@property (nonatomic, readonly, copy) NSString* workspacePath;
@property (nonatomic, readonly) BOOL available;
@property (nonatomic, readonly, copy) NSString* checkpointStatus;
@property (nonatomic, readonly) NSInteger droppedTelemetryCount;
@property (nonatomic, readonly) NSInteger bufferedOperations;
@property (nonatomic, readonly, copy) NSDictionary* startupDiagnostics;

- (instancetype)initWithWorkspacePath:(NSString*)workspacePath;
- (void)shutdown;

// Pass VIII: native runtime timeline + continuity
- (BOOL)recordTimelineEvent:(NSDictionary*)event error:(NSString**)errorOut;
- (NSDictionary*)timelineWithParams:(NSDictionary*)params;
- (NSDictionary*)runtimeDiagnosticsPayload;
- (NSDictionary*)compactOperationSummaries:(NSInteger)limit;
- (NSArray<NSDictionary*>*)recentWarnings:(NSInteger)limit;

// Operation history
- (BOOL)recordOperation:(NSDictionary*)record error:(NSString**)errorOut;
- (NSDictionary*)operationForId:(NSString*)operationId;
- (NSDictionary*)operationForIdempotencyKey:(NSString*)key;
- (NSArray<NSDictionary*>*)operationsForRevision:(NSInteger)revisionId limit:(NSInteger)limit;
- (NSArray<NSDictionary*>*)recentOperations:(NSInteger)limit;
- (NSArray<NSDictionary*>*)listOperations:(NSInteger)limit offset:(NSInteger)offset;

// Replay cache
- (BOOL)storeReplayCache:(NSDictionary*)record error:(NSString**)errorOut;
- (NSDictionary*)replayCacheForKey:(NSString*)idempotencyKey;
- (BOOL)evictExpiredReplayEntries:(NSInteger*)evictedCount error:(NSString**)errorOut;

// Revision journal
- (BOOL)recordRevision:(NSDictionary*)record error:(NSString**)errorOut;
- (NSDictionary*)revisionForId:(NSInteger)revisionId;
- (NSArray<NSDictionary*>*)listRevisions:(NSInteger)limit;
- (NSDictionary*)lastMutationRevision;

// Workflow memory
- (NSDictionary*)startWorkflow:(NSDictionary*)params error:(NSString**)errorOut;
- (NSDictionary*)recordWorkflowStep:(NSDictionary*)params error:(NSString**)errorOut;
- (NSDictionary*)completeWorkflow:(NSString*)workflowId error:(NSString**)errorOut;
- (NSDictionary*)failWorkflow:(NSDictionary*)params error:(NSString**)errorOut;
- (NSDictionary*)workflowForId:(NSString*)workflowId;
- (NSArray<NSDictionary*>*)recentWorkflows:(NSInteger)limit;

// Verification store
- (BOOL)recordVerificationRun:(NSDictionary*)record error:(NSString**)errorOut;
- (NSDictionary*)latestVerificationForCommand:(NSString*)command;
- (NSArray<NSDictionary*>*)verificationHistory:(NSString*)command limit:(NSInteger)limit;

// Telemetry / errors (may drop under backpressure)
- (void)recordTelemetryEvent:(NSString*)eventType payload:(NSDictionary*)payload;
- (void)recordErrorEvent:(NSString*)stringCode method:(NSString*)method envelope:(NSDictionary*)envelope;

// Status (memory.status — alias of runtime diagnostics)
- (NSDictionary*)memoryStatusPayload;

- (void)performStartupRestoration;
- (void)markCleanShutdown;

@end
