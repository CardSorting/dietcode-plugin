#import "MacControlMemoryService.hpp"
#import "MacControlSupport.hpp"

#include <sqlite3.h>
#include <CommonCrypto/CommonDigest.h>

static const NSInteger kDefaultReplayRetentionSeconds = 86400;
static const NSInteger kDefaultMaxBufferedOperations = 5000;
static const NSInteger kDefaultMaxMemoryBytes = 64 * 1024 * 1024;
static const NSInteger kDefaultShardCount = 4;

static NSString* StableJsonHash(NSDictionary* obj) {
    if (!obj) return @"";
    NSData* data = [NSJSONSerialization dataWithJSONObject:obj options:NSJSONWritingSortedKeys error:nil];
    if (!data) return @"";
    return StableHashForString([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);
}

static NSString* MemoryDbPathForWorkspace(NSString* workspacePath) {
    NSString* base = [NSHomeDirectory() stringByAppendingPathComponent:@".dietcode/runtime-memory"];
    NSString* wsHash = StableHashForString(workspacePath ?: @"");
    return [[base stringByAppendingPathComponent:wsHash] stringByAppendingPathComponent:@"runtime_memory.db"];
}

static BOOL ExecSql(sqlite3* db, NSString* sql) {
    char* err = nullptr;
    int rc = sqlite3_exec(db, sql.UTF8String, nullptr, nullptr, &err);
    if (rc != SQLITE_OK) {
        if (err) sqlite3_free(err);
        return NO;
    }
    return YES;
}

static NSString* SqliteError(sqlite3* db) {
    const char* msg = sqlite3_errmsg(db);
    return msg ? [NSString stringWithUTF8String:msg] : @"sqlite error";
}

@implementation MacControlMemoryService {
    NSString* _workspacePath;
    sqlite3* _db;
    BOOL _available;
    NSString* _checkpointStatus;
    NSInteger _droppedTelemetryCount;
    NSInteger _bufferedOperations;
    NSInteger _maxBufferedOperations;
    NSInteger _maxMemoryBytes;
    NSInteger _shardCount;
    NSString* _backpressureMode;
    dispatch_queue_t _writeQueue;
    NSDictionary* _startupDiagnostics;
    BOOL _recoveredFromShutdown;
}

- (instancetype)initWithWorkspacePath:(NSString*)workspacePath {
    self = [super init];
    if (self) {
        _workspacePath = [workspacePath copy] ?: @"";
        _checkpointStatus = @"initializing";
        _backpressureMode = @"normal";
        _maxBufferedOperations = kDefaultMaxBufferedOperations;
        _maxMemoryBytes = kDefaultMaxMemoryBytes;
        _shardCount = kDefaultShardCount;
        _writeQueue = dispatch_queue_create("com.dietcode.runtime.memory", DISPATCH_QUEUE_SERIAL);
        [self openDatabase];
    }
    return self;
}

- (BOOL)available { return _available; }
- (NSString*)workspacePath { return _workspacePath; }
- (NSString*)checkpointStatus { return _checkpointStatus; }
- (NSInteger)droppedTelemetryCount { return _droppedTelemetryCount; }
- (NSInteger)bufferedOperations { return _bufferedOperations; }
- (NSDictionary*)startupDiagnostics { return _startupDiagnostics ?: @{}; }

- (void)openDatabase {
    NSString* dbPath = MemoryDbPathForWorkspace(_workspacePath);
    NSString* dir = [dbPath stringByDeletingLastPathComponent];
    [[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil];

    if (sqlite3_open_v2(dbPath.UTF8String, &_db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nullptr) != SQLITE_OK) {
        _available = NO;
        _checkpointStatus = @"unavailable";
        return;
    }

    NSString* schemaSql = nil;
    NSString* repoSchema = [[[NSProcessInfo processInfo] environment] objectForKey:@"DIETCODE_REPO_ROOT"];
    if (repoSchema.length > 0) {
        NSString* schemaPath = [[repoSchema stringByAppendingPathComponent:@"runtime/memory"] stringByAppendingPathComponent:@"runtime_memory_schema.sql"];
        schemaSql = [NSString stringWithContentsOfFile:schemaPath encoding:NSUTF8StringEncoding error:nil];
    }
    if (schemaSql.length == 0) {
        schemaSql = [NSString stringWithContentsOfFile:
            [[[[NSFileManager defaultManager] currentDirectoryPath] stringByAppendingPathComponent:@"runtime/memory"]
                stringByAppendingPathComponent:@"runtime_memory_schema.sql"]
            encoding:NSUTF8StringEncoding error:nil];
    }
    if (schemaSql.length == 0 || !ExecSql(_db, schemaSql)) {
        _available = NO;
        _checkpointStatus = @"schema_failed";
        return;
    }

    [self seedCheckpointDefaults];
    _available = YES;
    _checkpointStatus = @"ready";
    [self performStartupRestoration];
}

- (void)seedCheckpointDefaults {
    NSDictionary* defaults = @{
        @"maxMemoryBytes": @(_maxMemoryBytes),
        @"maxBufferedOperations": @(_maxBufferedOperations),
        @"flushIntervalMs": @1000,
        @"shardCount": @(_shardCount),
        @"backpressureMode": _backpressureMode,
        @"droppedTelemetryCount": @0,
        @"checkpointStatus": @"ready",
        @"replayRetentionSeconds": @(kDefaultReplayRetentionSeconds),
    };
    NSData* json = [NSJSONSerialization dataWithJSONObject:defaults options:0 error:nil];
    NSString* jsonStr = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    sqlite3_stmt* stmt = nullptr;
    const char* sql = "INSERT OR IGNORE INTO runtime_checkpoint (key, value_json, updated_at) VALUES ('config', ?, ?)";
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, jsonStr.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 2, [[NSDate date] timeIntervalSince1970]);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
}

- (void)shutdown {
    [self markCleanShutdown];
    if (_db) {
        sqlite3_wal_checkpoint_v2(_db, nullptr, SQLITE_CHECKPOINT_TRUNCATE, nullptr, nullptr);
        sqlite3_close(_db);
        _db = nullptr;
    }
    _available = NO;
    _checkpointStatus = @"shutdown";
}

- (BOOL)backpressureActive {
    return _bufferedOperations >= _maxBufferedOperations;
}

- (NSDictionary*)runtimeDiagnosticsPayload {
    NSMutableDictionary* payload = [@{
        @"mode": @"runtime_diagnostics",
        @"available": @(_available),
        @"checkpointStatus": _checkpointStatus ?: @"unknown",
        @"maxMemoryBytes": @(_maxMemoryBytes),
        @"maxBufferedOperations": @(_maxBufferedOperations),
        @"flushIntervalMs": @1000,
        @"shardCount": @(_shardCount),
        @"backpressureMode": _backpressureMode ?: @"normal",
        @"bufferedOperations": @(_bufferedOperations),
        @"droppedTelemetryCount": @(_droppedTelemetryCount),
        @"mutationAuthority": @"cpp_kernel",
        @"recordAuthority": @"runtime_journal",
        @"currentStateAuthority": @"workspace_live_read",
        @"notCurrentFileTruth": @YES,
        @"workspacePath": _workspacePath ?: @"",
        @"startup": _startupDiagnostics ?: @{},
        @"runtimeRecoveredFromShutdown": @(_recoveredFromShutdown),
        @"complete": @(_available),
        @"partial": @(!_available || [_backpressureMode isEqualToString:@"degraded"]),
        @"warnings": (_available ? @[] : @[@"runtime_journal_degraded"]),
        @"nextRecommendedCommand": @"runtime.timeline",
        @"recoveryHint": _available ? @"inspect_runtime_timeline" : @"retry_runtime_diagnostics",
    } mutableCopy];
    if (![payload[@"warnings"] count]) payload[@"warnings"] = @[];
    return payload;
}

- (NSDictionary*)memoryStatusPayload {
    return [self runtimeDiagnosticsPayload];
}

#pragma mark - Operations

- (BOOL)recordOperation:(NSDictionary*)record error:(NSString**)errorOut {
    if (!_available || !_db) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return NO;
    }
    if ([self backpressureActive]) {
        _backpressureMode = @"degraded";
        _checkpointStatus = @"backpressure";
        if (errorOut) *errorOut = @"memory_backpressure";
        return NO;
    }

    NSString* opId = record[@"operationId"] ?: [[NSUUID UUID] UUIDString];
    NSString* method = record[@"method"] ?: @"unknown";
    NSString* paramsHash = record[@"paramsHash"] ?: @"";
    NSString* idempotencyKey = record[@"idempotencyKey"];
    double startedAt = [record[@"startedAt"] doubleValue] ?: [[NSDate date] timeIntervalSince1970];
    double completedAt = [record[@"completedAt"] doubleValue] ?: [[NSDate date] timeIntervalSince1970];
    NSString* status = record[@"status"] ?: @"completed";
    NSDictionary* receipt = record[@"receipt"];
    NSString* receiptJson = @"";
    if (receipt) {
        NSData* data = [NSJSONSerialization dataWithJSONObject:receipt options:0 error:nil];
        receiptJson = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
    }

    const char* sql =
        "INSERT OR REPLACE INTO runtime_operations "
        "(operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
        "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
        "receipt_hash, receipt_json, workspace_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }

    NSString* receiptHash = record[@"receiptHash"] ?: StableJsonHash(receipt);
    sqlite3_bind_text(stmt, 1, opId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, method.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, paramsHash.UTF8String, -1, SQLITE_TRANSIENT);
    if (idempotencyKey.length > 0) sqlite3_bind_text(stmt, 4, idempotencyKey.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 4);
    sqlite3_bind_double(stmt, 5, startedAt);
    sqlite3_bind_double(stmt, 6, completedAt);
    sqlite3_bind_text(stmt, 7, status.UTF8String, -1, SQLITE_TRANSIENT);
    NSString* errCode = record[@"errorCode"];
    if (errCode.length > 0) sqlite3_bind_text(stmt, 8, errCode.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 8);
    NSString* recoveryHint = record[@"recoveryHint"];
    if (recoveryHint.length > 0) sqlite3_bind_text(stmt, 9, recoveryHint.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 9);
    NSString* nextCmd = record[@"nextRecommendedCommand"];
    if (nextCmd.length > 0) sqlite3_bind_text(stmt, 10, nextCmd.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 10);
    if (record[@"revisionBefore"]) sqlite3_bind_int64(stmt, 11, [record[@"revisionBefore"] longLongValue]);
    else sqlite3_bind_null(stmt, 11);
    if (record[@"revisionAfter"]) sqlite3_bind_int64(stmt, 12, [record[@"revisionAfter"] longLongValue]);
    else sqlite3_bind_null(stmt, 12);
    sqlite3_bind_text(stmt, 13, receiptHash.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 14, receiptJson.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 15, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);

    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    _bufferedOperations++;
    [self recordTimelineEvent:@{
        @"eventType": @"mutation_applied",
        @"operationId": opId,
        @"revisionId": record[@"revisionAfter"] ?: @0,
        @"revisionBefore": record[@"revisionBefore"] ?: @0,
        @"idempotencyKey": idempotencyKey ?: @"",
        @"receiptHash": receiptHash,
        @"method": method,
        @"summary": [NSString stringWithFormat:@"%@ completed", method],
        @"payload": @{@"status": status},
    } error:nil];
    return YES;
}

- (NSDictionary*)operationRowFromStatement:(sqlite3_stmt*)stmt {
    NSMutableDictionary* row = [NSMutableDictionary dictionary];
    const unsigned char* opId = sqlite3_column_text(stmt, 0);
    if (opId) row[@"operationId"] = [NSString stringWithUTF8String:(const char*)opId];
    const unsigned char* method = sqlite3_column_text(stmt, 1);
    if (method) row[@"method"] = [NSString stringWithUTF8String:(const char*)method];
    const unsigned char* paramsHash = sqlite3_column_text(stmt, 2);
    if (paramsHash) row[@"paramsHash"] = [NSString stringWithUTF8String:(const char*)paramsHash];
    const unsigned char* idem = sqlite3_column_text(stmt, 3);
    if (idem) row[@"idempotencyKey"] = [NSString stringWithUTF8String:(const char*)idem];
    row[@"startedAt"] = @(sqlite3_column_double(stmt, 4));
    if (sqlite3_column_type(stmt, 5) != SQLITE_NULL) row[@"completedAt"] = @(sqlite3_column_double(stmt, 5));
    const unsigned char* status = sqlite3_column_text(stmt, 6);
    if (status) row[@"status"] = [NSString stringWithUTF8String:(const char*)status];
    if (sqlite3_column_type(stmt, 10) != SQLITE_NULL) row[@"revisionBefore"] = @(sqlite3_column_int64(stmt, 10));
    if (sqlite3_column_type(stmt, 11) != SQLITE_NULL) row[@"revisionAfter"] = @(sqlite3_column_int64(stmt, 11));
    const unsigned char* receiptHash = sqlite3_column_text(stmt, 12);
    if (receiptHash) row[@"receiptHash"] = [NSString stringWithUTF8String:(const char*)receiptHash];
    const unsigned char* receiptJson = sqlite3_column_text(stmt, 13);
    if (receiptJson) {
        NSString* json = [NSString stringWithUTF8String:(const char*)receiptJson];
        NSDictionary* receipt = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        if (receipt) row[@"receipt"] = receipt;
    }
    NSMutableDictionary* rowMut = [row mutableCopy];
    rowMut[@"mode"] = @"runtime_operation";
    rowMut[@"correlation"] = MacControlOperationIdentity(rowMut);
    return rowMut;
}

- (NSDictionary*)operationForIdempotencyKey:(NSString*)key {
    if (!_available || key.length == 0) return nil;
    const char* sql = "SELECT operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
                      "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
                      "receipt_hash, receipt_json FROM runtime_operations WHERE idempotency_key = ? AND workspace_path = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, key.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) result = [self operationRowFromStatement:stmt];
    sqlite3_finalize(stmt);
    return result;
}

- (NSDictionary*)operationForId:(NSString*)operationId {
    if (!_available || operationId.length == 0) return nil;
    const char* sql = "SELECT operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
                      "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
                      "receipt_hash, receipt_json FROM runtime_operations WHERE operation_id = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, operationId.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) result = [self operationRowFromStatement:stmt];
    sqlite3_finalize(stmt);
    return result;
}

- (NSArray<NSDictionary*>*)queryOperations:(const char*)sql bind:(void (^)(sqlite3_stmt*))binder {
    if (!_available) return @[];
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return @[];
    if (binder) binder(stmt);
    NSMutableArray* rows = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        [rows addObject:[self operationRowFromStatement:stmt]];
    }
    sqlite3_finalize(stmt);
    return rows;
}

- (NSArray<NSDictionary*>*)operationsForRevision:(NSInteger)revisionId limit:(NSInteger)limit {
    NSInteger lim = MAX(1, MIN(limit, 100));
    return [self queryOperations:
        "SELECT operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
        "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
        "receipt_hash, receipt_json FROM runtime_operations WHERE workspace_path = ? AND revision_after = ? "
        "ORDER BY completed_at DESC LIMIT ?"
        bind:^(sqlite3_stmt* stmt) {
            sqlite3_bind_text(stmt, 1, self->_workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, revisionId);
            sqlite3_bind_int64(stmt, 3, lim);
        }];
}

- (NSArray<NSDictionary*>*)recentOperations:(NSInteger)limit {
    NSInteger lim = MAX(1, MIN(limit, 100));
    return [self queryOperations:
        "SELECT operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
        "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
        "receipt_hash, receipt_json FROM runtime_operations WHERE workspace_path = ? "
        "ORDER BY completed_at DESC LIMIT ?"
        bind:^(sqlite3_stmt* stmt) {
            sqlite3_bind_text(stmt, 1, self->_workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, lim);
        }];
}

- (NSArray<NSDictionary*>*)listOperations:(NSInteger)limit offset:(NSInteger)offset {
    NSInteger lim = MAX(1, MIN(limit, 100));
    return [self queryOperations:
        "SELECT operation_id, method, params_hash, idempotency_key, started_at, completed_at, status, "
        "error_code, recovery_hint, next_recommended_command, revision_before, revision_after, "
        "receipt_hash, receipt_json FROM runtime_operations WHERE workspace_path = ? "
        "ORDER BY completed_at DESC LIMIT ? OFFSET ?"
        bind:^(sqlite3_stmt* stmt) {
            sqlite3_bind_text(stmt, 1, self->_workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 2, lim);
            sqlite3_bind_int64(stmt, 3, MAX(0, offset));
        }];
}

#pragma mark - Replay cache

- (BOOL)storeReplayCache:(NSDictionary*)record error:(NSString**)errorOut {
    if (!_available) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return NO;
    }
    NSString* key = record[@"idempotencyKey"];
    if (key.length == 0) {
        if (errorOut) *errorOut = @"idempotencyKey required";
        return NO;
    }
    NSDictionary* result = record[@"result"];
    NSData* resultData = [NSJSONSerialization dataWithJSONObject:result ?: @{} options:0 error:nil];
    NSString* resultJson = [[NSString alloc] initWithData:resultData encoding:NSUTF8StringEncoding] ?: @"{}";
    double now = [[NSDate date] timeIntervalSince1970];
    double expiresAt = [record[@"expiresAt"] doubleValue];
    if (expiresAt <= 0) expiresAt = now + kDefaultReplayRetentionSeconds;

    const char* sql =
        "INSERT OR REPLACE INTO runtime_replay_cache "
        "(idempotency_key, method, params_hash, result_json, receipt_hash, created_at, expires_at, workspace_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    NSString* receiptHash = record[@"receiptHash"] ?: StableJsonHash(result);
    sqlite3_bind_text(stmt, 1, key.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, ((NSString*)(record[@"method"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, ((NSString*)(record[@"paramsHash"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, resultJson.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, receiptHash.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 6, now);
    sqlite3_bind_double(stmt, 7, expiresAt);
    sqlite3_bind_text(stmt, 8, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    [self recordTimelineEvent:@{
        @"eventType": @"replay_cached",
        @"idempotencyKey": key,
        @"receiptHash": receiptHash,
        @"method": record[@"method"] ?: @"",
        @"summary": [NSString stringWithFormat:@"replay cached for %@", key],
    } error:nil];
    return YES;
}

- (NSDictionary*)replayCacheForKey:(NSString*)idempotencyKey {
    if (!_available || idempotencyKey.length == 0) return nil;
    [self evictExpiredReplayEntries:nil error:nil];
    const char* sql = "SELECT idempotency_key, method, params_hash, result_json, receipt_hash, created_at, expires_at "
                      "FROM runtime_replay_cache WHERE idempotency_key = ? AND workspace_path = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, idempotencyKey.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        double expiresAt = sqlite3_column_double(stmt, 6);
        double now = [[NSDate date] timeIntervalSince1970];
        if (expiresAt > now) {
            NSString* json = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 3)];
            NSDictionary* payload = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
            result = @{
                @"idempotencyKey": idempotencyKey,
                @"method": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)],
                @"paramsHash": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
                @"result": payload ?: @{},
                @"receiptHash": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 4)],
                @"createdAt": @(sqlite3_column_double(stmt, 5)),
                @"expiresAt": @(expiresAt),
                @"mode": @"memory_replay_cache",
                @"retained": @YES,
            };
        } else {
            result = @{
                @"idempotencyKey": idempotencyKey,
                @"mode": @"memory_replay_cache",
                @"retained": @NO,
                @"expired": @YES,
                @"recoveryHint": @"retry_with_new_idempotencyKey_or_revalidate",
                @"nextRecommendedCommand": @"patch.validate",
            };
        }
    }
    sqlite3_finalize(stmt);
    return result;
}

- (BOOL)evictExpiredReplayEntries:(NSInteger*)evictedCount error:(NSString**)errorOut {
    if (!_available) return NO;
    double now = [[NSDate date] timeIntervalSince1970];
    const char* sql = "DELETE FROM runtime_replay_cache WHERE workspace_path = ? AND expires_at <= ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 2, now);
    int rc = sqlite3_step(stmt);
    if (evictedCount) *evictedCount = sqlite3_changes(_db);
    sqlite3_finalize(stmt);
    return rc == SQLITE_DONE;
}

#pragma mark - Revisions

- (BOOL)recordRevision:(NSDictionary*)record error:(NSString**)errorOut {
    if (!_available) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return NO;
    }
    NSArray* changedFiles = record[@"changedFiles"] ?: @[];
    NSData* filesJson = [NSJSONSerialization dataWithJSONObject:changedFiles options:0 error:nil];
    NSString* filesStr = [[NSString alloc] initWithData:filesJson encoding:NSUTF8StringEncoding] ?: @"[]";
    const char* sql =
        "INSERT OR REPLACE INTO runtime_revisions "
        "(revision_id, workspace_path, changed_files_json, mutation_source, operation_id, receipt_hash, timestamp, previous_revision_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    sqlite3_bind_int64(stmt, 1, [record[@"revisionId"] longLongValue]);
    sqlite3_bind_text(stmt, 2, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, filesStr.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, ((NSString*)(record[@"mutationSource"] ?: @"agent")).UTF8String, -1, SQLITE_TRANSIENT);
    NSString* opId = record[@"operationId"];
    if (opId.length > 0) sqlite3_bind_text(stmt, 5, opId.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 5);
    sqlite3_bind_text(stmt, 6, ((NSString*)(record[@"receiptHash"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 7, [record[@"timestamp"] doubleValue] ?: [[NSDate date] timeIntervalSince1970]);
    if (record[@"previousRevisionId"]) sqlite3_bind_int64(stmt, 8, [record[@"previousRevisionId"] longLongValue]);
    else sqlite3_bind_null(stmt, 8);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc == SQLITE_DONE) {
        [self recordTimelineEvent:@{
            @"eventType": @"revision_recorded",
            @"operationId": record[@"operationId"] ?: @"",
            @"revisionId": record[@"revisionId"] ?: @0,
            @"revisionBefore": record[@"previousRevisionId"] ?: @0,
            @"receiptHash": record[@"receiptHash"] ?: @"",
            @"summary": [NSString stringWithFormat:@"revision %@ recorded", record[@"revisionId"] ?: @0],
            @"payload": @{@"mutationSource": record[@"mutationSource"] ?: @"agent"},
        } error:nil];
    }
    return rc == SQLITE_DONE;
}

- (NSDictionary*)revisionForId:(NSInteger)revisionId {
    if (!_available) return nil;
    const char* sql = "SELECT revision_id, changed_files_json, mutation_source, operation_id, receipt_hash, timestamp, previous_revision_id "
                      "FROM runtime_revisions WHERE workspace_path = ? AND revision_id = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, revisionId);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        NSString* filesJson = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)];
        NSArray* changedFiles = [NSJSONSerialization JSONObjectWithData:[filesJson dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        result = @{
            @"revisionId": @(sqlite3_column_int64(stmt, 0)),
            @"changedFiles": changedFiles ?: @[],
            @"mutationSource": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"operationId": sqlite3_column_type(stmt, 3) != SQLITE_NULL ? [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 3)] : @"",
            @"receiptHash": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 4)],
            @"timestamp": @(sqlite3_column_double(stmt, 5)),
            @"previousRevisionId": sqlite3_column_type(stmt, 6) != SQLITE_NULL ? @(sqlite3_column_int64(stmt, 6)) : @0,
            @"mode": @"memory_revision",
        };
    }
    sqlite3_finalize(stmt);
    return result;
}

- (NSArray<NSDictionary*>*)listRevisions:(NSInteger)limit {
    if (!_available) return @[];
    NSInteger lim = MAX(1, MIN(limit, 100));
    const char* sql = "SELECT revision_id, changed_files_json, mutation_source, operation_id, receipt_hash, timestamp, previous_revision_id "
                      "FROM runtime_revisions WHERE workspace_path = ? ORDER BY revision_id DESC LIMIT ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return @[];
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, lim);
    NSMutableArray* rows = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        NSString* filesJson = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)];
        NSArray* changedFiles = [NSJSONSerialization JSONObjectWithData:[filesJson dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        [rows addObject:@{
            @"revisionId": @(sqlite3_column_int64(stmt, 0)),
            @"changedFiles": changedFiles ?: @[],
            @"mutationSource": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"receiptHash": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 4)],
            @"timestamp": @(sqlite3_column_double(stmt, 5)),
            @"mode": @"memory_revision",
        }];
    }
    sqlite3_finalize(stmt);
    return rows;
}

- (NSDictionary*)lastMutationRevision {
    if (!_available) return nil;
    const char* sql = "SELECT revision_id, changed_files_json, mutation_source, operation_id, receipt_hash, timestamp, previous_revision_id "
                      "FROM runtime_revisions WHERE workspace_path = ? AND mutation_source = 'agent' ORDER BY revision_id DESC LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        NSString* filesJson = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)];
        NSArray* changedFiles = [NSJSONSerialization JSONObjectWithData:[filesJson dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        result = @{
            @"revisionId": @(sqlite3_column_int64(stmt, 0)),
            @"changedFiles": changedFiles ?: @[],
            @"mutationSource": @"agent",
            @"receiptHash": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 4)],
            @"timestamp": @(sqlite3_column_double(stmt, 5)),
            @"mode": @"memory_revision_last_mutation",
        };
    }
    sqlite3_finalize(stmt);
    return result;
}

#pragma mark - Workflows

- (NSDictionary*)startWorkflow:(NSDictionary*)params error:(NSString**)errorOut {
    if (!_available) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return nil;
    }
    NSString* workflowId = params[@"workflowId"] ?: [[NSUUID UUID] UUIDString];
    NSString* agentId = params[@"agentId"] ?: @"default";
    double now = [[NSDate date] timeIntervalSince1970];
    const char* sql = "INSERT INTO runtime_workflows (workflow_id, agent_id, status, started_at, workspace_path) VALUES (?, ?, 'running', ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return nil;
    }
    sqlite3_bind_text(stmt, 1, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, agentId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 3, now);
    sqlite3_bind_text(stmt, 4, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE) {
        if (errorOut) *errorOut = SqliteError(_db);
        return nil;
    }
    return @{
        @"workflowId": workflowId,
        @"agentId": agentId,
        @"status": @"running",
        @"startedAt": @(now),
        @"mode": @"memory_workflow",
    };
}

- (NSDictionary*)recordWorkflowStep:(NSDictionary*)params error:(NSString**)errorOut {
    if (!_available) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return nil;
    }
    NSString* stepId = params[@"stepId"] ?: [[NSUUID UUID] UUIDString];
    NSString* workflowId = params[@"workflowId"];
    if (workflowId.length == 0) {
        if (errorOut) *errorOut = @"workflowId required";
        return nil;
    }
    const char* sql =
        "INSERT INTO runtime_workflow_steps "
        "(step_id, workflow_id, command, status, input_hash, output_hash, recovery_hint, next_recommended_command, "
        "linked_operation_id, linked_revision_id, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return nil;
    }
    double now = [[NSDate date] timeIntervalSince1970];
    sqlite3_bind_text(stmt, 1, stepId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, ((NSString*)(params[@"command"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, ((NSString*)(params[@"status"] ?: @"running")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, ((NSString*)(params[@"inputHash"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 6, ((NSString*)(params[@"outputHash"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    NSString* hint = params[@"recoveryHint"];
    if (hint.length > 0) sqlite3_bind_text(stmt, 7, hint.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 7);
    NSString* next = params[@"nextRecommendedCommand"];
    if (next.length > 0) sqlite3_bind_text(stmt, 8, next.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 8);
    NSString* linkedOp = params[@"linkedOperationId"];
    if (linkedOp.length > 0) sqlite3_bind_text(stmt, 9, linkedOp.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 9);
    if (params[@"linkedRevisionId"]) sqlite3_bind_int64(stmt, 10, [params[@"linkedRevisionId"] longLongValue]);
    else sqlite3_bind_null(stmt, 10);
    sqlite3_bind_double(stmt, 11, now);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE) {
        if (errorOut) *errorOut = SqliteError(_db);
        return nil;
    }
    return @{
        @"stepId": stepId,
        @"workflowId": workflowId,
        @"command": params[@"command"] ?: @"",
        @"status": params[@"status"] ?: @"running",
        @"timestamp": @(now),
        @"mode": @"memory_workflow_step",
    };
}

- (NSDictionary*)completeWorkflow:(NSString*)workflowId error:(NSString**)errorOut {
    if (!_available || workflowId.length == 0) return nil;
    double now = [[NSDate date] timeIntervalSince1970];
    const char* sql = "UPDATE runtime_workflows SET status = 'completed', completed_at = ? WHERE workflow_id = ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_double(stmt, 1, now);
    sqlite3_bind_text(stmt, 2, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return [self workflowForId:workflowId];
}

- (NSDictionary*)failWorkflow:(NSDictionary*)params error:(NSString**)errorOut {
    NSString* workflowId = params[@"workflowId"];
    if (!_available || workflowId.length == 0) return nil;
    double now = [[NSDate date] timeIntervalSince1970];
    const char* sql = "UPDATE runtime_workflows SET status = 'failed', completed_at = ?, recovery_hint = ?, next_recommended_command = ? WHERE workflow_id = ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_double(stmt, 1, now);
    NSString* hint = params[@"recoveryHint"];
    if (hint.length > 0) sqlite3_bind_text(stmt, 2, hint.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 2);
    NSString* next = params[@"nextRecommendedCommand"];
    if (next.length > 0) sqlite3_bind_text(stmt, 3, next.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 3);
    sqlite3_bind_text(stmt, 4, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return [self workflowForId:workflowId];
}

- (NSDictionary*)workflowForId:(NSString*)workflowId {
    if (!_available || workflowId.length == 0) return nil;
    const char* sql = "SELECT workflow_id, agent_id, status, started_at, completed_at, recovery_hint, next_recommended_command "
                      "FROM runtime_workflows WHERE workflow_id = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        result = @{
            @"workflowId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)],
            @"agentId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)],
            @"status": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"startedAt": @(sqlite3_column_double(stmt, 3)),
            @"mode": @"memory_workflow",
        };
        if (sqlite3_column_type(stmt, 4) != SQLITE_NULL) {
            NSMutableDictionary* resultMutable = [result mutableCopy];
            resultMutable[@"completedAt"] = @(sqlite3_column_double(stmt, 4));
            result = resultMutable;
        }
    }
    sqlite3_finalize(stmt);
    return result;
}

- (NSArray<NSDictionary*>*)recentWorkflows:(NSInteger)limit {
    if (!_available) return @[];
    NSInteger lim = MAX(1, MIN(limit, 50));
    const char* sql = "SELECT workflow_id, agent_id, status, started_at, completed_at FROM runtime_workflows "
                      "WHERE workspace_path = ? ORDER BY started_at DESC LIMIT ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return @[];
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, lim);
    NSMutableArray* rows = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        [rows addObject:@{
            @"workflowId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)],
            @"agentId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)],
            @"status": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"startedAt": @(sqlite3_column_double(stmt, 3)),
            @"mode": @"memory_workflow",
        }];
    }
    sqlite3_finalize(stmt);
    return rows;
}

#pragma mark - Verification

- (BOOL)recordVerificationRun:(NSDictionary*)record error:(NSString**)errorOut {
    if (!_available) {
        if (errorOut) *errorOut = @"memory_unavailable";
        return NO;
    }
    NSString* runId = record[@"runId"] ?: [[NSUUID UUID] UUIDString];
    const char* sql =
        "INSERT OR REPLACE INTO runtime_verification_runs "
        "(run_id, command, suite_name, passed_count, failed_count, duration_ms, failure_summary, timestamp, revision_id, operation_id, workspace_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    sqlite3_bind_text(stmt, 1, runId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, ((NSString*)(record[@"command"] ?: @"")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, ((NSString*)(record[@"suiteName"] ?: @"default")).UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 4, [record[@"passedCount"] longLongValue]);
    sqlite3_bind_int64(stmt, 5, [record[@"failedCount"] longLongValue]);
    sqlite3_bind_double(stmt, 6, [record[@"durationMs"] doubleValue]);
    NSString* summary = record[@"failureSummary"];
    if (summary.length > 0) sqlite3_bind_text(stmt, 7, summary.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 7);
    sqlite3_bind_double(stmt, 8, [[NSDate date] timeIntervalSince1970]);
    if (record[@"revisionId"]) sqlite3_bind_int64(stmt, 9, [record[@"revisionId"] longLongValue]);
    else sqlite3_bind_null(stmt, 9);
    NSString* opId = record[@"operationId"];
    if (opId.length > 0) sqlite3_bind_text(stmt, 10, opId.UTF8String, -1, SQLITE_TRANSIENT);
    else sqlite3_bind_null(stmt, 10);
    sqlite3_bind_text(stmt, 11, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return rc == SQLITE_DONE;
}

- (NSDictionary*)latestVerificationForCommand:(NSString*)command {
    if (!_available || command.length == 0) return nil;
    const char* sql = "SELECT run_id, command, suite_name, passed_count, failed_count, duration_ms, failure_summary, timestamp, revision_id "
                      "FROM runtime_verification_runs WHERE workspace_path = ? AND command = ? ORDER BY timestamp DESC LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, command.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        result = @{
            @"runId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)],
            @"command": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)],
            @"suiteName": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"passedCount": @(sqlite3_column_int64(stmt, 3)),
            @"failedCount": @(sqlite3_column_int64(stmt, 4)),
            @"durationMs": @(sqlite3_column_double(stmt, 5)),
            @"timestamp": @(sqlite3_column_double(stmt, 7)),
            @"mode": @"memory_verification",
        };
    }
    sqlite3_finalize(stmt);
    return result;
}

- (NSArray<NSDictionary*>*)verificationHistory:(NSString*)command limit:(NSInteger)limit {
    if (!_available) return @[];
    NSInteger lim = MAX(1, MIN(limit, 50));
    const char* sql = "SELECT run_id, command, suite_name, passed_count, failed_count, duration_ms, timestamp "
                      "FROM runtime_verification_runs WHERE workspace_path = ? AND command = ? ORDER BY timestamp DESC LIMIT ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return @[];
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, command.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 3, lim);
    NSMutableArray* rows = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        [rows addObject:@{
            @"runId": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)],
            @"command": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)],
            @"suiteName": [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 2)],
            @"passedCount": @(sqlite3_column_int64(stmt, 3)),
            @"failedCount": @(sqlite3_column_int64(stmt, 4)),
            @"durationMs": @(sqlite3_column_double(stmt, 5)),
            @"timestamp": @(sqlite3_column_double(stmt, 6)),
            @"mode": @"memory_verification",
        }];
    }
    sqlite3_finalize(stmt);
    return rows;
}

#pragma mark - Telemetry / errors

- (void)recordTelemetryEvent:(NSString*)eventType payload:(NSDictionary*)payload {
    if (!_available) return;
    if ([self backpressureActive]) {
        _droppedTelemetryCount++;
        return;
    }
    NSString* eventId = [[NSUUID UUID] UUIDString];
    NSData* json = [NSJSONSerialization dataWithJSONObject:payload ?: @{} options:0 error:nil];
    NSString* jsonStr = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] ?: @"{}";
    const char* sql = "INSERT INTO runtime_telemetry_events (event_id, event_type, payload_json, timestamp, dropped, workspace_path) VALUES (?, ?, ?, ?, 0, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, eventId.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, eventType.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, jsonStr.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 4, [[NSDate date] timeIntervalSince1970]);
        sqlite3_bind_text(stmt, 5, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
}

- (void)recordErrorEvent:(NSString*)stringCode method:(NSString*)method envelope:(NSDictionary*)envelope {
    if (!_available) return;
    NSString* eventId = [[NSUUID UUID] UUIDString];
    NSData* json = [NSJSONSerialization dataWithJSONObject:envelope ?: @{} options:0 error:nil];
    NSString* jsonStr = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] ?: @"{}";
    const char* sql = "INSERT INTO runtime_error_events (event_id, string_code, recovery_hint, method, timestamp, envelope_json, workspace_path) VALUES (?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, eventId.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, stringCode.UTF8String, -1, SQLITE_TRANSIENT);
        NSString* hint = envelope[@"recovery_hint"] ?: envelope[@"recoveryHint"];
        if (hint.length > 0) sqlite3_bind_text(stmt, 3, hint.UTF8String, -1, SQLITE_TRANSIENT);
        else sqlite3_bind_null(stmt, 3);
        if (method.length > 0) sqlite3_bind_text(stmt, 4, method.UTF8String, -1, SQLITE_TRANSIENT);
        else sqlite3_bind_null(stmt, 4);
        sqlite3_bind_double(stmt, 5, [[NSDate date] timeIntervalSince1970]);
        sqlite3_bind_text(stmt, 6, jsonStr.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 7, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
    [self recordTimelineEvent:@{
        @"eventType": @"error_recorded",
        @"stringCode": stringCode,
        @"method": method ?: @"",
        @"summary": [NSString stringWithFormat:@"error %@ on %@", stringCode, method ?: @"unknown"],
        @"payload": envelope ?: @{},
    } error:nil];
}

#pragma mark - Timeline + startup continuity (Pass VIII)

- (void)writeCheckpoint:(NSString*)key value:(NSDictionary*)value {
    if (!_db || key.length == 0) return;
    NSData* json = [NSJSONSerialization dataWithJSONObject:value ?: @{} options:0 error:nil];
    NSString* jsonStr = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] ?: @"{}";
    const char* sql = "INSERT OR REPLACE INTO runtime_checkpoint (key, value_json, updated_at) VALUES (?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, key.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, jsonStr.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(stmt, 3, [[NSDate date] timeIntervalSince1970]);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
}

- (NSDictionary*)readCheckpoint:(NSString*)key {
    if (!_db || key.length == 0) return nil;
    const char* sql = "SELECT value_json FROM runtime_checkpoint WHERE key = ? LIMIT 1";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return nil;
    sqlite3_bind_text(stmt, 1, key.UTF8String, -1, SQLITE_TRANSIENT);
    NSDictionary* result = nil;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        NSString* json = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)];
        result = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    }
    sqlite3_finalize(stmt);
    return result;
}

- (void)performStartupRestoration {
    if (!_available) return;
    NSInteger evicted = 0;
    [self evictExpiredReplayEntries:&evicted error:nil];

    NSInteger replayRetained = 0;
    const char* replayCountSql = "SELECT COUNT(*) FROM runtime_replay_cache WHERE workspace_path = ? AND expires_at > ?";
    sqlite3_stmt* replayStmt = nullptr;
    double now = [[NSDate date] timeIntervalSince1970];
    if (sqlite3_prepare_v2(_db, replayCountSql, -1, &replayStmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(replayStmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
        sqlite3_bind_double(replayStmt, 2, now);
        if (sqlite3_step(replayStmt) == SQLITE_ROW) replayRetained = sqlite3_column_int64(replayStmt, 0);
        sqlite3_finalize(replayStmt);
    }

    NSInteger lastKnownRevision = 0;
    const char* revSql = "SELECT MAX(revision_id) FROM runtime_revisions WHERE workspace_path = ?";
    sqlite3_stmt* revStmt = nullptr;
    if (sqlite3_prepare_v2(_db, revSql, -1, &revStmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(revStmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
        if (sqlite3_step(revStmt) == SQLITE_ROW) lastKnownRevision = sqlite3_column_int64(revStmt, 0);
        sqlite3_finalize(revStmt);
    }

    NSDictionary* lastShutdown = [self readCheckpoint:@"last_shutdown"];
    BOOL cleanShutdown = [lastShutdown[@"clean"] boolValue];
    _recoveredFromShutdown = lastShutdown != nil && !cleanShutdown;

    _startupDiagnostics = @{
        @"mode": @"runtime_startup",
        @"replayCacheRestoredCount": @(replayRetained),
        @"replayCacheEvictedCount": @(evicted),
        @"lastKnownRevision": @(lastKnownRevision),
        @"runtimeRecoveredFromShutdown": @(_recoveredFromShutdown),
        @"cleanShutdown": @(cleanShutdown),
        @"recoveredShutdown": @(_recoveredFromShutdown),
        @"checkpointStatus": _checkpointStatus ?: @"ready",
    };

    [self writeCheckpoint:@"session_start" value:@{
        @"timestamp": @(now),
        @"lastKnownRevision": @(lastKnownRevision),
        @"replayCacheRestoredCount": @(replayRetained),
    }];

    if (_recoveredFromShutdown) {
        [self recordTimelineEvent:@{
            @"eventType": @"startup_recovered",
            @"summary": @"runtime recovered from unclean shutdown",
            @"payload": _startupDiagnostics,
        } error:nil];
    }
}

- (void)markCleanShutdown {
    if (!_db) return;
    [self writeCheckpoint:@"last_shutdown" value:@{@"clean": @YES, @"timestamp": @([[NSDate date] timeIntervalSince1970])}];
}

- (BOOL)recordTimelineEvent:(NSDictionary*)event error:(NSString**)errorOut {
    if (!_available || !_db) {
        if (errorOut) *errorOut = @"runtime_journal_unavailable";
        return NO;
    }
    NSString* eventId = event[@"eventId"] ?: [[NSUUID UUID] UUIDString];
    NSString* eventType = event[@"eventType"] ?: @"runtime_event";
    NSString* summary = event[@"summary"] ?: eventType;
    NSDictionary* payload = event[@"payload"];
    NSData* payloadData = payload ? [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil] : nil;
    NSString* payloadJson = payloadData ? [[NSString alloc] initWithData:payloadData encoding:NSUTF8StringEncoding] : nil;
    double ts = [event[@"timestamp"] doubleValue] ?: [[NSDate date] timeIntervalSince1970];

    const char* sql =
        "INSERT OR REPLACE INTO runtime_timeline_events "
        "(event_id, event_type, timestamp, operation_id, revision_id, revision_before, idempotency_key, "
        "workflow_id, receipt_hash, method, string_code, summary, payload_json, workspace_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    sqlite3_bind_text(stmt, 1, eventId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, eventType.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 3, ts);
    NSString* opId = event[@"operationId"];
    if (opId.length > 0) sqlite3_bind_text(stmt, 4, opId.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 4);
    if (event[@"revisionId"]) sqlite3_bind_int64(stmt, 5, [event[@"revisionId"] longLongValue]); else sqlite3_bind_null(stmt, 5);
    if (event[@"revisionBefore"]) sqlite3_bind_int64(stmt, 6, [event[@"revisionBefore"] longLongValue]); else sqlite3_bind_null(stmt, 6);
    NSString* idem = event[@"idempotencyKey"];
    if (idem.length > 0) sqlite3_bind_text(stmt, 7, idem.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 7);
    NSString* wf = event[@"workflowId"];
    if (wf.length > 0) sqlite3_bind_text(stmt, 8, wf.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 8);
    NSString* rh = event[@"receiptHash"];
    if (rh.length > 0) sqlite3_bind_text(stmt, 9, rh.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 9);
    NSString* method = event[@"method"];
    if (method.length > 0) sqlite3_bind_text(stmt, 10, method.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 10);
    NSString* code = event[@"stringCode"];
    if (code.length > 0) sqlite3_bind_text(stmt, 11, code.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 11);
    sqlite3_bind_text(stmt, 12, summary.UTF8String, -1, SQLITE_TRANSIENT);
    if (payloadJson.length > 0) sqlite3_bind_text(stmt, 13, payloadJson.UTF8String, -1, SQLITE_TRANSIENT); else sqlite3_bind_null(stmt, 13);
    sqlite3_bind_text(stmt, 14, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    if (rc != SQLITE_DONE) {
        if (errorOut) *errorOut = SqliteError(_db);
        return NO;
    }
    return YES;
}

- (NSDictionary*)timelineEventFromStatement:(sqlite3_stmt*)stmt compact:(BOOL)compact {
    NSMutableDictionary* row = [NSMutableDictionary dictionary];
    row[@"eventId"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 0)];
    row[@"eventType"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 1)];
    row[@"timestamp"] = @(sqlite3_column_double(stmt, 2));
    if (sqlite3_column_type(stmt, 3) != SQLITE_NULL) row[@"operationId"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 3)];
    if (sqlite3_column_type(stmt, 4) != SQLITE_NULL) row[@"revisionId"] = @(sqlite3_column_int64(stmt, 4));
    if (sqlite3_column_type(stmt, 5) != SQLITE_NULL) row[@"revisionBefore"] = @(sqlite3_column_int64(stmt, 5));
    if (sqlite3_column_type(stmt, 6) != SQLITE_NULL) row[@"idempotencyKey"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 6)];
    if (sqlite3_column_type(stmt, 7) != SQLITE_NULL) row[@"workflowId"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 7)];
    if (sqlite3_column_type(stmt, 8) != SQLITE_NULL) row[@"receiptHash"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 8)];
    if (sqlite3_column_type(stmt, 9) != SQLITE_NULL) row[@"method"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 9)];
    if (sqlite3_column_type(stmt, 10) != SQLITE_NULL) row[@"stringCode"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 10)];
    row[@"summary"] = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 11)];
    if (!compact && sqlite3_column_type(stmt, 12) != SQLITE_NULL) {
        NSString* json = [NSString stringWithUTF8String:(const char*)sqlite3_column_text(stmt, 12)];
        NSDictionary* payload = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        if (payload) row[@"payload"] = payload;
    }
    row[@"correlation"] = MacControlOperationIdentity(row);
    row[@"mode"] = @"runtime_timeline_event";
    return row;
}

- (NSDictionary*)timelineWithParams:(NSDictionary*)params {
    if (!_available) return @{@"status": @"degraded", @"events": @[], @"mode": @"runtime_timeline"};
    NSInteger limit = params[@"limit"] ? MIN(MAX([params[@"limit"] integerValue], 1), 100) : 50;
    NSInteger offset = MAX([params[@"offset"] integerValue], 0);
    NSInteger sinceRevision = [params[@"sinceRevision"] integerValue];
    NSInteger untilRevision = [params[@"untilRevision"] integerValue];
    BOOL errorsOnly = [params[@"errorsOnly"] boolValue];
    BOOL compact = [params[@"compact"] boolValue];
    NSString* operationId = params[@"operationId"];
    NSString* workflowId = params[@"workflowId"];
    NSArray* eventTypes = params[@"eventTypes"];

    NSMutableString* sql = [NSMutableString stringWithString:
        @"SELECT event_id, event_type, timestamp, operation_id, revision_id, revision_before, "
        @"idempotency_key, workflow_id, receipt_hash, method, string_code, summary, payload_json "
        @"FROM runtime_timeline_events WHERE workspace_path = ?"];
    if (sinceRevision > 0) [sql appendString:@" AND revision_id >= ?"];
    if (untilRevision > 0) [sql appendString:@" AND revision_id <= ?"];
    if (errorsOnly) [sql appendString:@" AND string_code IS NOT NULL"];
    if (operationId.length > 0) [sql appendString:@" AND operation_id = ?"];
    if (workflowId.length > 0) [sql appendString:@" AND workflow_id = ?"];
    [sql appendString:@" ORDER BY timestamp DESC LIMIT ? OFFSET ?"];

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql.UTF8String, -1, &stmt, nullptr) != SQLITE_OK) {
        return @{@"events": @[], @"mode": @"runtime_timeline", @"status": @"error"};
    }

    int bindIdx = 1;
    sqlite3_bind_text(stmt, bindIdx++, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    if (sinceRevision > 0) sqlite3_bind_int64(stmt, bindIdx++, sinceRevision);
    if (untilRevision > 0) sqlite3_bind_int64(stmt, bindIdx++, untilRevision);
    if (operationId.length > 0) sqlite3_bind_text(stmt, bindIdx++, operationId.UTF8String, -1, SQLITE_TRANSIENT);
    if (workflowId.length > 0) sqlite3_bind_text(stmt, bindIdx++, workflowId.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, bindIdx++, limit + 1);
    sqlite3_bind_int64(stmt, bindIdx++, offset);

    NSMutableArray* events = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        NSDictionary* row = [self timelineEventFromStatement:stmt compact:compact];
        if (eventTypes.count > 0 && ![eventTypes containsObject:row[@"eventType"]]) continue;
        [events addObject:row];
    }
    sqlite3_finalize(stmt);

    BOOL truncated = events.count > (NSUInteger)limit;
    if (truncated) [events removeLastObject];

    return @{
        @"mode": @"runtime_timeline",
        @"events": events,
        @"limit": @(limit),
        @"offset": @(offset),
        @"sinceRevision": @(sinceRevision),
        @"untilRevision": @(untilRevision),
        @"errorsOnly": @(errorsOnly),
        @"compact": @(compact),
        @"eventCount": @(events.count),
        @"truncated": @(truncated),
        @"nextOffset": truncated ? @(offset + limit) : [NSNull null],
        @"sortOrder": @"timestamp_desc",
        @"startup": _startupDiagnostics ?: @{},
    };
}

- (NSDictionary*)compactOperationSummaries:(NSInteger)limit {
    NSArray* ops = [self recentOperations:MAX(1, MIN(limit, 20))];
    NSMutableArray* summaries = [NSMutableArray array];
    for (NSDictionary* op in ops) {
        [summaries addObject:@{
            @"operationId": op[@"operationId"] ?: @"",
            @"method": op[@"method"] ?: @"",
            @"status": op[@"status"] ?: @"",
            @"revisionAfter": op[@"revisionAfter"] ?: @0,
            @"receiptHash": op[@"receiptHash"] ?: @"",
            @"correlation": op[@"correlation"] ?: MacControlOperationIdentity(op),
        }];
    }
    return @{
        @"mode": @"runtime_operation_summary",
        @"summaries": summaries,
        @"complete": @YES,
        @"partial": @NO,
    };
}

- (NSArray<NSDictionary*>*)recentWarnings:(NSInteger)limit {
    if (!_available) return @[];
    NSInteger lim = MAX(1, MIN(limit, 50));
    const char* sql =
        "SELECT event_id, event_type, timestamp, operation_id, revision_id, revision_before, "
        "idempotency_key, workflow_id, receipt_hash, method, string_code, summary, payload_json "
        "FROM runtime_timeline_events WHERE workspace_path = ? AND string_code IS NOT NULL "
        "ORDER BY timestamp DESC LIMIT ?";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(_db, sql, -1, &stmt, nullptr) != SQLITE_OK) return @[];
    sqlite3_bind_text(stmt, 1, _workspacePath.UTF8String, -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, lim);
    NSMutableArray* rows = [NSMutableArray array];
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        [rows addObject:[self timelineEventFromStatement:stmt compact:YES]];
    }
    sqlite3_finalize(stmt);
    return rows;
}

@end
