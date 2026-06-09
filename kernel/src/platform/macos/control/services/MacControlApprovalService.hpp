#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlServer;

typedef void (^MacControlApprovalExecutor)(
    NSString* method,
    NSDictionary* params,
    NSDictionary** outResult,
    NSString** outErrCode,
    NSString** outErrMsg,
    NSString** outPaths);

@interface MacControlApprovalService : NSObject

- (NSDictionary*)createPendingApprovalWithMethod:(NSString*)method
                                          params:(NSDictionary*)params
                                          caller:(NSString*)caller
                                       rationale:(NSString*)rationale
                                          taskId:(NSString*)taskId;

- (NSArray<NSDictionary*>*)listApprovalsWithStatus:(NSString*)status limit:(NSInteger)limit;

- (NSDictionary*)approvalForId:(NSString*)approvalId;

- (BOOL)validateApprovedApproval:(NSString*)approvalId
                          method:(NSString*)method
                          params:(NSDictionary*)params
                           error:(NSString**)errorOut;

- (NSDictionary*)resolveApproval:(NSString*)approvalId
                        decision:(NSString*)decision
                          reason:(NSString*)reason
                      resolvedBy:(NSString*)resolvedBy
                        executor:(MacControlApprovalExecutor)executor
                           error:(NSString**)errorOut;

@end
