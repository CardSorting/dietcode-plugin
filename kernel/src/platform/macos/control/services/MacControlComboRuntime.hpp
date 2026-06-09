#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;
@class MacControlRecoveryStore;
@class MacControlPatchService;
@class MacControlTaskRuntime;

typedef void (^MacControlMethodExecutor)(NSString* method, NSDictionary* params, NSDictionary** outResult, NSString** outErrCode, NSString** outErrMsg, NSString** outPaths);

@interface MacControlComboRuntime : NSObject

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge
                        recoveryStore:(MacControlRecoveryStore*)recoveryStore
                         patchService:(MacControlPatchService*)patchService
                          taskRuntime:(MacControlTaskRuntime*)taskRuntime
                             executor:(MacControlMethodExecutor)executor;

- (NSDictionary*)runComboWithPlan:(NSDictionary*)plan 
                          comboId:(NSString*)comboId 
                     sessionToken:(NSString*)sessionToken;

- (BOOL)validateCombo:(NSDictionary*)combo 
       normalizedPlan:(NSDictionary**)planOut 
               errors:(NSArray<NSDictionary*>**)errorsOut;

- (NSUInteger)activeComboCount;

- (NSDictionary*)serializableCombo:(NSMutableDictionary*)combo;

- (BOOL)acquireMutationLocks:(NSArray<NSString*>*)paths comboId:(NSString*)comboId error:(NSString**)errorOut;
- (void)releaseMutationLocks:(NSArray<NSString*>*)paths comboId:(NSString*)comboId;

// Cancels an active combo by ID. Returns NO if the comboId is unknown or the combo
// is already in a terminal state (complete, cancelled, failed, rollback_*). For
// running combos, cancellation is cooperative and locks are released by the runner's
// cleanup path after rollback/exit.
- (BOOL)cancelComboWithId:(NSString*)comboId error:(NSString**)errorOut;

@property (nonatomic, readonly) NSDictionary<NSString*, NSDictionary*>* combos;
@property (nonatomic, readonly) NSString* lastComboId;
@property (nonatomic, assign) BOOL globalMutationLock;

@end
