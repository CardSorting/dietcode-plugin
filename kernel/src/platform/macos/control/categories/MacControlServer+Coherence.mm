#import "MacControlServer+Private.hpp"

@implementation DietCodeControlServer (Coherence)

- (BOOL)queueCoherenceMismatchIfNeeded:(NSString*)method
                                  params:(NSDictionary*)params
                                   reqId:(NSString*)reqId
                                clientFd:(int)clientFd {
    if (![method isEqualToString:@"patch.apply"] && ![method isEqualToString:@"patch.applyBatch"]) {
        return NO;
    }
    NSString* taskId = params[@"taskId"];
    if (![taskId isKindOfClass:[NSString class]] || taskId.length == 0) {
        return NO;
    }

    NSString* message = nil;
    NSString* ws = [self safeWorkspacePath] ?: @"";
    if ([_workspaceState validateCoherenceForMutation:params
                                            workspace:ws
                                         windowBridge:_windowBridge
                                           outMessage:&message]) {
        return NO;
    }

    [self sendError:reqId
               code:@"coherence_mismatch"
            message:message ?: @"Coherence token is stale."
           clientFd:clientFd];
    [self appendLogLine:[NSString stringWithFormat:@"[Coherence] Blocked %@ task=%@",
                         method, taskId]];
    return YES;
}

@end
