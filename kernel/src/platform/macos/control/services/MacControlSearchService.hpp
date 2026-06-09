#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;

@interface MacControlSearchService : NSObject

- (instancetype)initWithWindowBridge:(DietCodeControlWindowBridge*)windowBridge;

- (NSDictionary*)workspaceGrep:(NSDictionary*)params 
                    outErrCode:(NSString**)outErrCode 
                     outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchFiles:(NSDictionary*)params 
                  outErrCode:(NSString**)outErrCode 
                   outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchText:(NSDictionary*)params 
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchTodo:(NSDictionary*)params 
                 outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchLiteral:(NSDictionary*)params
                     outErrCode:(NSString**)outErrCode
                      outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchTokens:(NSDictionary*)params
                   outErrCode:(NSString**)outErrCode
                    outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchPaths:(NSDictionary*)params
                    outErrCode:(NSString**)outErrCode
                     outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchReferences:(NSDictionary*)params
                         outErrCode:(NSString**)outErrCode
                          outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchSemantic:(NSDictionary*)params 
                     outErrCode:(NSString**)outErrCode 
                      outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)searchDiagnostics:(NSDictionary*)params 
                        outErrCode:(NSString**)outErrCode 
                         outErrMsg:(NSString**)outErrMsg;

// Search Session Management
- (NSDictionary*)startGrepSession:(NSDictionary*)params 
                       outErrCode:(NSString**)outErrCode 
                        outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)nextGrepResults:(NSDictionary*)params 
                      outErrCode:(NSString**)outErrCode 
                       outErrMsg:(NSString**)outErrMsg;

- (NSDictionary*)cancelGrepSession:(NSDictionary*)params 
                        outErrCode:(NSString**)outErrCode 
                         outErrMsg:(NSString**)outErrMsg;

@end
