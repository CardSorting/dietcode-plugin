#import "MacControlServer+Private.hpp"

@implementation DietCodeControlServer (VerifyGate)

- (void)notifyWorkspaceMutatedIfNeededForMethod:(NSString*)method
                                         params:(NSDictionary*)params
                                         result:(NSDictionary*)result {
    if (!result) return;
    if ([result[@"dryRun"] boolValue]) return;

    BOOL mutated = NO;
    NSMutableArray<NSString*>* changedPaths = [NSMutableArray array];

    if ([method isEqualToString:@"patch.apply"]) {
        mutated = [result[@"patched"] boolValue];
        NSString* path = result[@"path"] ?: params[@"path"];
        if (path.length > 0) [changedPaths addObject:path];
    } else if ([method isEqualToString:@"patch.applyBatch"]) {
        mutated = [result[@"applied"] boolValue];
        for (NSDictionary* item in result[@"results"] ?: result[@"patches"] ?: @[]) {
            NSString* path = item[@"path"];
            if (path.length > 0) [changedPaths addObject:path];
        }
        if (changedPaths.count == 0) {
            for (NSDictionary* item in params[@"patches"] ?: @[]) {
                NSString* path = item[@"path"];
                if (path.length > 0) [changedPaths addObject:path];
            }
        }
    }

    if (!mutated) return;

    NSString* taskId = params[@"taskId"];
    if (![taskId isKindOfClass:[NSString class]]) taskId = @"";

    [self notifyStructuredEvent:@"workspace.mutated"
                         detail:[NSString stringWithFormat:@"%@ (%lu paths)", method, (unsigned long)changedPaths.count]
                        payload:@{
                            @"taskId": taskId,
                            @"method": method ?: @"",
                            @"changedPaths": changedPaths,
                            @"revisionAfter": result[@"revisionAfter"] ?: @(_workspaceState.revisionId),
                            @"verificationRequired": @YES,
                        }];
    [self appendLogLine:[NSString stringWithFormat:@"[VerifyGate] workspace.mutated %@ task=%@", method, taskId.length > 0 ? taskId : @"(none)"]];
}

- (void)notifyVerifyResult:(NSDictionary*)status taskId:(NSString*)taskId {
    BOOL passed = [status[@"passed"] boolValue];
    NSString* eventType = passed ? @"verify.completed" : @"verify.failed";
    NSMutableDictionary* payload = [status mutableCopy] ?: [NSMutableDictionary dictionary];
    if (taskId.length > 0) payload[@"taskId"] = taskId;
    payload[@"passed"] = @(passed);
    [self notifyStructuredEvent:eventType
                         detail:[NSString stringWithFormat:@"exit=%@ passed=%@", status[@"exitCode"], passed ? @"yes" : @"no"]
                        payload:payload];
}

@end
