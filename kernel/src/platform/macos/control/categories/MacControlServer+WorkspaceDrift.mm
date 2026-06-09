#import "MacControlServer+Private.hpp"

@implementation DietCodeControlServer (WorkspaceDrift)

- (NSDictionary*)currentWorkspaceStatusPayload {
    return [_workspaceState statusPayloadWithWorkspace:[self safeWorkspacePath] ?: @""
                                          windowBridge:_windowBridge
                                               gitInfo:[self safeGitStatusInfo] ?: @{}
                                         verifyStatus:[self verificationStatus] ?: @{}
                                   lastVerifyFinishedAt:_lastVerifyFinishedAt];
}

- (BOOL)queueWorkspaceDriftBlockIfNeeded:(NSString*)method
                                  params:(NSDictionary*)params
                                   reqId:(NSString*)reqId
                                clientFd:(int)clientFd {
    if ([method isEqualToString:@"workspace.refreshAnchor"] ||
        [method isEqualToString:@"workspace.continueAnyway"] ||
        [method isEqualToString:@"workspace.status"] ||
        [method isEqualToString:@"workspace.snapshot"] ||
        [method isEqualToString:@"workspace.revision"]) {
        return NO;
    }

    NSDictionary* status = [self currentWorkspaceStatusPayload];
    BOOL driftDetected = [status[@"driftDetected"] boolValue];
    if (!driftDetected) {
        return NO;
    }
    if ([_workspaceState validateContextRefreshForParams:params driftDetected:driftDetected]) {
        return NO;
    }

    [self notifyStructuredEvent:@"workspace.drift.detected"
                         detail:[NSString stringWithFormat:@"drift blocked %@", method]
                        payload:status];
    [self sendSuccess:reqId result:@{
        @"workspaceDriftRequired": @YES,
        @"workspace": status,
        @"blockedMethod": method ?: @"",
        @"mode": @"workspace_drift_pending",
    } clientFd:clientFd];
    [self appendLogLine:[NSString stringWithFormat:@"[WorkspaceDrift] Blocked %@ — context refresh required (%lu affected)",
                         method, (unsigned long)[status[@"affectedFiles"] count]]];
    return YES;
}

@end
