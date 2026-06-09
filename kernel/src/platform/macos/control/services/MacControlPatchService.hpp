#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;
@class MacControlWorkspaceState;

@interface MacControlPatchService : NSObject

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge;

@property (nonatomic, weak) MacControlWorkspaceState* workspaceState;

- (NSDictionary*)applyPatch:(NSDictionary*)params 
                      error:(NSString**)errorOut 
                  errorCode:(NSString**)errorCodeOut;

- (NSDictionary*)applyPatchBatch:(NSDictionary*)params 
                           error:(NSString**)errorOut 
                       errorCode:(NSString**)errorCodeOut;

- (NSDictionary*)revertLastPatchWithError:(NSString**)errorOut 
                                errorCode:(NSString**)errorCodeOut;

- (void)recordMutationRecords:(NSArray<NSDictionary*>*)records;

- (NSDictionary*)validatePatchAtPath:(NSString*)path 
                               patch:(NSString*)patch 
                         currentText:(NSString*)currentTextOverride;

- (NSDictionary*)validatePatchAtPath:(NSString*)path 
                               patch:(NSString*)patch 
                         currentText:(NSString*)currentTextOverride
                             options:(NSDictionary*)options;

- (BOOL)restorePatchRecords:(NSArray<NSDictionary*>*)records error:(NSString**)errorOut;

@property (nonatomic, readonly) NSArray<NSDictionary*>* lastPatchRecords;

@end
