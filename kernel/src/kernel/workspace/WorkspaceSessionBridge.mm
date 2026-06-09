#import "WorkspaceSessionBridge.hpp"
#import "kernel/workspace/WorkspaceSession.hpp"

@implementation DietCodeWorkspaceSession {
    dietcode::kernel::workspace::WorkspaceSession* _session;
    BOOL _ownsSession;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _session = new dietcode::kernel::workspace::WorkspaceSession();
        _ownsSession = YES;
    }
    return self;
}

- (instancetype)initWithSession:(dietcode::kernel::workspace::WorkspaceSession*)session {
    self = [super init];
    if (self) {
        _session = session;
        _ownsSession = NO;
    }
    return self;
}

- (void)dealloc {
    if (_ownsSession) {
        delete _session;
    }
}

- (dietcode::kernel::workspace::WorkspaceSession*)cppSession {
    return _session;
}

- (BOOL)hasWorkspace {
    return self.workspacePath.length > 0;
}

- (NSString*)workspacePath {
    if (!_session) return @"";
    const std::string& root = _session->workspaceRoot();
    return root.empty() ? @"" : [NSString stringWithUTF8String:root.c_str()];
}

- (void)setWorkspaceRoot:(NSString*)path {
    if (!_session) return;
    _session->setWorkspaceRoot(path.length > 0 ? std::string([path UTF8String]) : "");
}

- (NSString*)readTextAtPath:(NSString*)path readSource:(NSString**)readSourceOut error:(NSString**)errorOut {
    if (!_session) {
        if (errorOut) *errorOut = @"Workspace session unavailable.";
        return nil;
    }
    auto result = _session->readText([path UTF8String]);
    if (!result.ok) {
        if (errorOut) *errorOut = [NSString stringWithUTF8String:result.error.c_str()];
        return nil;
    }
    if (readSourceOut) {
        *readSourceOut = [NSString stringWithUTF8String:result.readSource.c_str()];
    }
    return [NSString stringWithUTF8String:result.text.c_str()];
}

- (BOOL)writeTextAtPath:(NSString*)path content:(NSString*)content error:(NSString**)errorOut {
    if (!_session) {
        if (errorOut) *errorOut = @"Workspace session unavailable.";
        return NO;
    }
    auto result = _session->writeText([path UTF8String], [content UTF8String]);
    if (!result.ok && errorOut) {
        *errorOut = [NSString stringWithUTF8String:result.error.c_str()];
    }
    return result.ok;
}

- (BOOL)applyPatchAtPath:(NSString*)path patchString:(NSString*)patchString error:(NSString**)errorOut {
    if (!_session) {
        if (errorOut) *errorOut = @"Workspace session unavailable.";
        return NO;
    }
    auto result = _session->applyPatch([path UTF8String], [patchString UTF8String]);
    if (!result.ok && errorOut) {
        *errorOut = [NSString stringWithUTF8String:result.error.c_str()];
    }
    return result.ok;
}

- (NSDictionary*)runVerificationCommand:(NSString*)command cwd:(NSString*)cwd {
    if (!_session) {
        return @{
            @"command": command ?: @"",
            @"state": @"idle",
            @"exitCode": [NSNull null],
            @"passed": @NO,
        };
    }
    auto status = _session->runVerification(
        [command UTF8String],
        cwd.length > 0 ? std::string([cwd UTF8String]) : "");
    return @{
        @"command": [NSString stringWithUTF8String:status.command.c_str()],
        @"state": [NSString stringWithUTF8String:status.state.c_str()],
        @"exitCode": @(status.exitCode),
        @"passed": @(status.passed),
        @"timedOut": @(status.timedOut),
        @"stdout": [NSString stringWithUTF8String:status.stdoutText.c_str()],
        @"stderr": [NSString stringWithUTF8String:status.stderrText.c_str()],
        @"durationMs": @(status.durationMs),
    };
}

- (NSDictionary*)verificationStatus {
    if (!_session) {
        return @{
            @"command": @"",
            @"state": @"idle",
            @"exitCode": [NSNull null],
            @"passed": @NO,
        };
    }
    auto status = _session->verificationStatus();
    return @{
        @"command": [NSString stringWithUTF8String:status.command.c_str()],
        @"state": [NSString stringWithUTF8String:status.state.c_str()],
        @"exitCode": @(status.exitCode),
        @"passed": @(status.passed),
        @"timedOut": @(status.timedOut),
        @"stdout": [NSString stringWithUTF8String:status.stdoutText.c_str()],
        @"stderr": [NSString stringWithUTF8String:status.stderrText.c_str()],
        @"durationMs": @(status.durationMs),
    };
}

- (NSDictionary*)gitStatusDictionary {
    if (!_session || _session->workspaceRoot().empty()) {
        return @{};
    }
    auto status = _session->gitStatus();
    NSMutableArray* staged = [NSMutableArray array];
    NSMutableArray* modified = [NSMutableArray array];
    NSMutableArray* untracked = [NSMutableArray array];
    for (const auto& change : status.changes) {
        NSString* relPath = [NSString stringWithUTF8String:change.path.c_str()];
        if (change.status == "??") {
            [untracked addObject:relPath];
        } else if (change.staged) {
            [staged addObject:relPath];
        } else {
            [modified addObject:relPath];
        }
    }
    return @{
        @"branch": [NSString stringWithUTF8String:status.branch.c_str()],
        @"staged": staged,
        @"modified": modified,
        @"untracked": untracked,
    };
}

- (NSString*)gitDiffForFile:(NSString*)path staged:(BOOL)staged {
    if (!_session) return @"";
    const std::string diff = _session->gitDiff([path UTF8String], staged);
    return [NSString stringWithUTF8String:diff.c_str()];
}

- (void)setAgentAutonomyLevel:(NSInteger)level {
    if (_session) _session->setAgentAutonomyLevel(static_cast<int>(level));
}

- (NSInteger)agentAutonomyLevel {
    return _session ? _session->agentAutonomyLevel() : 1;
}

- (NSArray<NSString*>*)recentCommands {
    if (!_session) return @[];
    NSMutableArray* items = [NSMutableArray array];
    for (const auto& cmd : _session->recentCommands()) {
        [items addObject:[NSString stringWithUTF8String:cmd.c_str()]];
    }
    return items;
}

- (NSArray<NSString*>*)recentSearches {
    if (!_session) return @[];
    NSMutableArray* items = [NSMutableArray array];
    for (const auto& query : _session->recentSearches()) {
        [items addObject:[NSString stringWithUTF8String:query.c_str()]];
    }
    return items;
}

- (void)appendRecentCommand:(NSString*)command {
    if (_session && command.length > 0) {
        _session->appendRecentCommand([command UTF8String]);
    }
}

- (void)appendRecentSearch:(NSString*)query {
    if (_session && query.length > 0) {
        _session->appendRecentSearch([query UTF8String]);
    }
}

- (void)clearSessionHistory {
    if (_session) _session->clearSessionHistory();
}

@end
