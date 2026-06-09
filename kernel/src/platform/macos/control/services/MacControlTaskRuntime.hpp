#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;
@class MacControlPatchService;
@class MacControlSearchService;

typedef void (^MacControlMethodExecutor)(NSString* method, NSDictionary* params, NSDictionary** outResult, NSString** outErrCode, NSString** outErrMsg, NSString** outPaths);

@interface MacControlTaskRuntime : NSObject

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)bridge
                        patchService:(MacControlPatchService*)patchService
                       searchService:(MacControlSearchService*)searchService
                            executor:(MacControlMethodExecutor)executor;

- (NSDictionary*)startTask:(NSDictionary*)params 
                outErrCode:(NSString**)outErrCode 
                 outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)taskStatus:(NSDictionary*)params 
                     result:(BOOL)isResult
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)cancelTask:(NSDictionary*)params 
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)taskStep:(NSDictionary*)params 
               outErrCode:(NSString**)outErrCode 
                outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)taskRunLoop:(NSDictionary*)params 
                  outErrCode:(NSString**)outErrCode 
                   outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)editPlan:(NSDictionary*)params 
               outErrCode:(NSString**)outErrCode 
                outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)editExecutePlan:(NSDictionary*)params 
                      outErrCode:(NSString**)outErrCode 
                       outErrMsg:(NSString**)outErrMsg;

// Helpers that might be useful externally if needed, but primarily internal
- (BOOL)task:(NSMutableDictionary*)task canConsumeStep:(NSDictionary*)step error:(NSString**)errorOut errorCode:(NSString**)errorCodeOut;
- (NSDictionary*)serializableTask:(NSMutableDictionary*)task;
- (NSDictionary*)executeWorkbenchStep:(NSDictionary*)step task:(NSMutableDictionary*)task;
- (NSDictionary*)primitiveForWorkbenchStep:(NSDictionary*)step;

@end
