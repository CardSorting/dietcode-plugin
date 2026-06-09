#import "MacControlServer+Private.hpp"
#import "MacControlApprovalService.hpp"

@implementation DietCodeControlServer (Approval)

- (void)executeApprovalMethod:(NSString*)method
                     params:(NSDictionary*)params
                  outResult:(NSDictionary**)outResult
                 outErrCode:(NSString**)outErrCode
                    outErrMsg:(NSString**)outErrMsg
                   outPaths:(NSString**)outPaths {
    (void)outPaths;

    if ([method isEqualToString:@"approval.list"]) {
        NSString* status = params[@"status"];
        NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 50;
        NSArray* approvals = [_approvalService listApprovalsWithStatus:status limit:limit];
        *outResult = @{
            @"approvals": approvals,
            @"mode": @"approval_list",
            @"count": @(approvals.count),
        };
        return;
    }

    if ([method isEqualToString:@"approval.get"]) {
        NSString* approvalId = params[@"approvalId"];
        if (approvalId.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"approvalId required.";
            return;
        }
        NSDictionary* approval = [_approvalService approvalForId:approvalId];
        if (!approval) {
            *outErrCode = @"not_found";
            *outErrMsg = @"Approval not found.";
            return;
        }
        *outResult = @{ @"approval": approval, @"mode": @"approval_get" };
        return;
    }

    if ([method isEqualToString:@"approval.resolve"]) {
        NSString* approvalId = params[@"approvalId"];
        NSString* decision = params[@"decision"];
        NSString* reason = params[@"reason"];
        NSString* resolvedBy = params[@"resolvedBy"] ?: @"cockpit";
        if (approvalId.length == 0 || decision.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"approvalId and decision required.";
            return;
        }

        __weak DietCodeControlServer* weakSelf = self;
        MacControlApprovalExecutor executor = ^(NSString* execMethod, NSDictionary* execParams, NSDictionary** execResult, NSString** execErrCode, NSString** execErrMsg, NSString** execPaths) {
            DietCodeControlServer* strong = weakSelf;
            if (!strong) {
                *execErrCode = @"internal_error";
                *execErrMsg = @"Control server unavailable.";
                return;
            }
            [strong executeMethod:execMethod params:execParams outResult:execResult outErrCode:execErrCode outErrMsg:execErrMsg outPaths:execPaths];
        };

        NSString* resolveError = nil;
        NSDictionary* resolution = [_approvalService resolveApproval:approvalId
                                                            decision:decision
                                                              reason:reason
                                                          resolvedBy:resolvedBy
                                                            executor:executor
                                                               error:&resolveError];
        if (!resolution) {
            *outErrCode = @"approval_resolve_failed";
            *outErrMsg = resolveError ?: @"Failed to resolve approval.";
            return;
        }

        NSDictionary* approval = [_approvalService approvalForId:approvalId];
        [self notifyStructuredEvent:@"approval.resolved"
                             detail:[NSString stringWithFormat:@"%@ %@", approvalId, decision]
                            payload:@{
                                @"resolution": resolution,
                                @"approval": approval ?: @{},
                            }];

        *outResult = @{
            @"resolution": resolution,
            @"approval": approval ?: @{},
            @"mode": @"approval_resolve",
        };
        return;
    }

    *outErrCode = @"method_not_found";
    *outErrMsg = [NSString stringWithFormat:@"Unknown approval method '%@'.", method];
}

- (BOOL)queueDestructiveApprovalIfNeeded:(NSString*)method
                                 params:(NSDictionary*)params
                                 caller:(NSString*)caller
                              rationale:(NSString*)rationale
                                  reqId:(NSString*)reqId
                               clientFd:(int)clientFd {
    NSInteger autonomy = [self safeAgentAutonomyLevel];
    NSString* approvalId = params[@"approvalId"];
    if (approvalId.length > 0) {
        return NO;
    }
    if (autonomy == 1) {
        return NO;
    }
    DietCodeWindowController* windowController = [self windowController];
    if (autonomy == 2 && !_isKernelMode && windowController && !windowController.isHeadless) {
        return NO;
    }
    if (autonomy == 2 && [self isDestructiveRequestSafe:method params:params]) {
        return NO;
    }

    NSDictionary* approval = [_approvalService createPendingApprovalWithMethod:method
                                                                        params:params
                                                                        caller:caller
                                                                     rationale:rationale
                                                                        taskId:params[@"taskId"]];
    [self notifyStructuredEvent:@"approval.required"
                         detail:[NSString stringWithFormat:@"%@ %@", approval[@"approvalId"], method]
                        payload:approval];
    [self sendSuccess:reqId result:@{
        @"approvalRequired": @YES,
        @"approval": approval,
        @"mode": @"approval_pending",
    } clientFd:clientFd];
    [self appendLogLine:[NSString stringWithFormat:@"[Approval] Queued %@ for %@ (%@)", approval[@"approvalId"], method, caller]];
    return YES;
}

- (BOOL)validateDestructiveApprovalIfPresent:(NSString*)method
                                      params:(NSDictionary*)params
                                   outErrCode:(NSString**)outErrCode
                                      outErrMsg:(NSString**)outErrMsg {
    NSString* approvalId = params[@"approvalId"];
    if (approvalId.length == 0) return YES;
    NSString* error = nil;
    if (![_approvalService validateApprovedApproval:approvalId method:method params:params error:&error]) {
        if (outErrCode) *outErrCode = @"approval_invalid";
        if (outErrMsg) *outErrMsg = error ?: @"Invalid or unconsumed approval.";
        return NO;
    }
    return YES;
}

@end
