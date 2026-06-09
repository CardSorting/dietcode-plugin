#import "MacControlApprovalService.hpp"
#import "MacControlSupport.hpp"

static const NSTimeInterval kApprovalTTLSeconds = 30.0 * 60.0;

@implementation MacControlApprovalService {
    NSMutableDictionary<NSString*, NSMutableDictionary*>* _approvals;
    NSInteger _approvalCounter;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _approvals = [NSMutableDictionary dictionary];
        _approvalCounter = 0;
    }
    return self;
}

- (NSString*)nextApprovalId {
    @synchronized(self) {
        _approvalCounter += 1;
        return [NSString stringWithFormat:@"appr_%lld", (long long)_approvalCounter];
    }
}

- (NSString*)paramsHashForMethod:(NSString*)method params:(NSDictionary*)params {
    NSError* err = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:params ?: @{} options:NSJSONWritingSortedKeys error:&err];
    NSString* json = data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : @"{}";
    return StableHashForString([NSString stringWithFormat:@"%@:%@", method ?: @"", json ?: @""]);
}

- (NSString*)actionTypeForMethod:(NSString*)method {
    if ([method hasPrefix:@"patch."]) return @"patch";
    if ([method hasPrefix:@"git."]) return @"git";
    if ([method hasPrefix:@"file."]) return @"file";
    if ([method hasPrefix:@"workspace."]) return @"workspace";
    if ([method hasPrefix:@"combo."]) return @"combo";
    return method ?: @"mutation";
}

- (NSDictionary*)previewForMethod:(NSString*)method params:(NSDictionary*)params {
    NSMutableDictionary* preview = [NSMutableDictionary dictionary];
    NSString* path = params[@"path"];
    if (path.length > 0) preview[@"path"] = path;
    NSString* patch = params[@"patch"];
    if (patch.length > 0) {
        NSString* truncated = patch;
        if (truncated.length > 4000) {
            truncated = [[truncated substringToIndex:4000] stringByAppendingString:@"\n…"];
        }
        preview[@"patch"] = truncated;
    }
    NSString* command = params[@"command"];
    if (command.length > 0) preview[@"command"] = command;
    if (params[@"message"]) preview[@"message"] = params[@"message"];
    if (params[@"patches"]) preview[@"patchCount"] = @([(NSArray*)params[@"patches"] count]);
    preview[@"method"] = method ?: @"";
    return preview;
}

- (void)expireStaleApprovals {
    NSDate* now = [NSDate date];
    @synchronized(self) {
        NSMutableArray* expiredIds = [NSMutableArray array];
        for (NSString* key in _approvals) {
            NSMutableDictionary* record = _approvals[key];
            if (![record[@"status"] isEqualToString:@"pending"]) continue;
            NSDate* createdAt = record[@"createdAtDate"];
            if (createdAt && [now timeIntervalSinceDate:createdAt] > kApprovalTTLSeconds) {
                record[@"status"] = @"expired";
                record[@"resolvedAt"] = ISODateString(now);
                record[@"decision"] = @"expired";
                [expiredIds addObject:key];
            }
        }
        (void)expiredIds;
    }
}

- (NSDictionary*)publicRecordFromInternal:(NSDictionary*)record {
    if (!record) return @{};
    NSMutableDictionary* copy = [record mutableCopy];
    [copy removeObjectForKey:@"createdAtDate"];
    [copy removeObjectForKey:@"params"];
    return copy;
}

- (NSDictionary*)createPendingApprovalWithMethod:(NSString*)method
                                          params:(NSDictionary*)params
                                          caller:(NSString*)caller
                                       rationale:(NSString*)rationale
                                          taskId:(NSString*)taskId {
    [self expireStaleApprovals];
    NSString* approvalId = [self nextApprovalId];
    NSDate* now = [NSDate date];
    NSString* reason = rationale.length > 0 ? rationale : @"Destructive mutation requires explicit approval.";
    NSMutableDictionary* record = [@{
        @"approvalId": approvalId,
        @"taskId": taskId ?: @"",
        @"actionType": [self actionTypeForMethod:method],
        @"method": method ?: @"",
        @"reason": reason,
        @"caller": caller ?: @"unix_socket",
        @"status": @"pending",
        @"preview": [self previewForMethod:method params:params],
        @"paramsHash": [self paramsHashForMethod:method params:params],
        @"createdAt": ISODateString(now),
        @"createdAtDate": now,
        @"params": params ?: @{},
    } mutableCopy];

    @synchronized(self) {
        _approvals[approvalId] = record;
    }
    return [self publicRecordFromInternal:record];
}

- (NSArray<NSDictionary*>*)listApprovalsWithStatus:(NSString*)status limit:(NSInteger)limit {
    [self expireStaleApprovals];
    if (limit < 1) limit = 50;
    if (limit > 200) limit = 200;
    NSMutableArray* items = [NSMutableArray array];
    @synchronized(self) {
        NSArray* keys = [_approvals.allKeys sortedArrayUsingComparator:^NSComparisonResult(NSString* a, NSString* b) {
            return [a compare:b];
        }];
        for (NSString* key in [keys reverseObjectEnumerator]) {
            NSDictionary* record = _approvals[key];
            if (status.length > 0 && ![record[@"status"] isEqualToString:status]) continue;
            [items addObject:[self publicRecordFromInternal:record]];
            if ((NSInteger)items.count >= limit) break;
        }
    }
    return items;
}

- (NSDictionary*)approvalForId:(NSString*)approvalId {
    [self expireStaleApprovals];
    if (approvalId.length == 0) return nil;
    @synchronized(self) {
        return [self publicRecordFromInternal:_approvals[approvalId]];
    }
}

- (BOOL)validateApprovedApproval:(NSString*)approvalId
                          method:(NSString*)method
                          params:(NSDictionary*)params
                           error:(NSString**)errorOut {
    [self expireStaleApprovals];
    if (approvalId.length == 0) {
        if (errorOut) *errorOut = @"approvalId required.";
        return NO;
    }
    @synchronized(self) {
        NSMutableDictionary* record = _approvals[approvalId];
        if (!record) {
            if (errorOut) *errorOut = @"Approval not found.";
            return NO;
        }
        if (record[@"executionResult"]) {
            if (errorOut) *errorOut = @"Approval already executed.";
            return NO;
        }
        if (![record[@"status"] isEqualToString:@"approved"]) {
            if (errorOut) *errorOut = [NSString stringWithFormat:@"Approval status is %@, not approved.", record[@"status"]];
            return NO;
        }
        if (![record[@"method"] isEqualToString:method]) {
            if (errorOut) *errorOut = @"Approval method mismatch.";
            return NO;
        }
        NSString* expectedHash = record[@"paramsHash"];
        NSString* actualHash = [self paramsHashForMethod:method params:params];
        if (expectedHash.length > 0 && ![expectedHash isEqualToString:actualHash]) {
            if (errorOut) *errorOut = @"Approval params hash mismatch.";
            return NO;
        }
        record[@"consumedAt"] = ISODateString([NSDate date]);
        return YES;
    }
}

- (NSDictionary*)resolveApproval:(NSString*)approvalId
                        decision:(NSString*)decision
                          reason:(NSString*)reason
                      resolvedBy:(NSString*)resolvedBy
                        executor:(MacControlApprovalExecutor)executor
                           error:(NSString**)errorOut {
    [self expireStaleApprovals];
    if (approvalId.length == 0) {
        if (errorOut) *errorOut = @"approvalId required.";
        return nil;
    }
    NSString* normalized = [decision lowercaseString];
    if (![normalized isEqualToString:@"approved"] && ![normalized isEqualToString:@"rejected"]) {
        if (errorOut) *errorOut = @"decision must be approved or rejected.";
        return nil;
    }

    NSMutableDictionary* record = nil;
    @synchronized(self) {
        record = _approvals[approvalId];
    }
    if (!record) {
        if (errorOut) *errorOut = @"Approval not found.";
        return nil;
    }
    if (![record[@"status"] isEqualToString:@"pending"]) {
        if (errorOut) *errorOut = [NSString stringWithFormat:@"Approval already %@", record[@"status"]];
        return nil;
    }

    NSDate* now = [NSDate date];
    record[@"status"] = normalized;
    record[@"decision"] = normalized;
    record[@"resolvedAt"] = ISODateString(now);
    record[@"resolvedBy"] = resolvedBy ?: @"cockpit";
    if (reason.length > 0) record[@"resolveReason"] = reason;

    NSMutableDictionary* resolution = [@{
        @"approvalId": approvalId,
        @"taskId": record[@"taskId"] ?: @"",
        @"decision": normalized,
        @"reason": reason ?: (normalized.length > 0 ? [NSString stringWithFormat:@"User %@ from cockpit", normalized] : @""),
        @"resolvedBy": resolvedBy ?: @"cockpit",
        @"timestamp": ISODateString(now),
        @"status": normalized,
    } mutableCopy];

    if ([normalized isEqualToString:@"approved"] && executor) {
        NSString* method = record[@"method"];
        NSDictionary* params = record[@"params"] ?: @{};
        NSDictionary* execResult = nil;
        NSString* errCode = nil;
        NSString* errMsg = nil;
        NSString* paths = nil;
        executor(method, params, &execResult, &errCode, &errMsg, &paths);
        if (errCode) {
            record[@"status"] = @"failed";
            record[@"executionError"] = errMsg ?: errCode;
            resolution[@"executionError"] = errMsg ?: errCode;
            resolution[@"executionErrorCode"] = errCode;
        } else {
            record[@"executionResult"] = execResult ?: @{};
            resolution[@"executionResult"] = execResult ?: @{};
            resolution[@"executed"] = @YES;
        }
    }

    return resolution;
}

@end
