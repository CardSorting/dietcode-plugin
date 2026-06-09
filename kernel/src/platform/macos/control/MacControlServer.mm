#import "MacControlServer.hpp"
#import "WorkspaceSessionBridge.hpp"
#ifdef DIETCODE_KERNEL_BUILD
#import "DietCodeWindowController+ControlHost.h"
#endif
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#import "DietCodeLegacyWindowBridge.hpp"
#endif
#import <CommonCrypto/CommonDigest.h>
#import "SymbolIndexService.hpp"
#import "DiffAnalysisService.hpp"
#import "WorkspaceAnalysisService.hpp"
#import "BufferStateService.hpp"
#import "SubprocessRunner.hpp"

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <fnmatch.h>
#include <fstream>
#include <sstream>
#include <chrono>
#include <filesystem>
#include <vector>
#include <string>
#include <set>
#include <map>
#include <signal.h>
#include <cstring>
#include <algorithm>
#include <cctype>
#include "filesystem/PathUtils.hpp"

#import "MacControlSupport.hpp"
#import "MacControlRuntimeDiagnostics.hpp"
#import "MacControlSocketSafety.hpp"
#import "MacControlReleaseVersions.hpp"
#import "MacControlPathSecurity.hpp"
#import "MacControlSerialization.hpp"
#import "MacControlDiffParsing.hpp"
#import "MacControlWindowBridge.hpp"
#import "MacControlRoutingPolicy.hpp"
#import "MacControlMethodCatalog.hpp"
#import "MacControlToolRegistry.hpp"
#import "MacControlSearchService.hpp"
#import "MacControlRecoveryStore.hpp"
#import "MacControlPatchService.hpp"
#import "MacControlTaskRuntime.hpp"
#import "MacControlComboRuntime.hpp"
#import "MacControlServer+Private.hpp"

static NSString* DietCodeReadTextFileForControlServer(NSString* path) {
    if (path.length == 0) return nil;
    NSStringEncoding encoding = NSUTF8StringEncoding;
    NSError* error = nil;
    return [NSString stringWithContentsOfFile:path usedEncoding:&encoding error:&error];
}

@interface DietCodeClientConnection : NSObject
@property (nonatomic, assign) int fd;
@property (nonatomic, assign) BOOL readEOF;
@property (nonatomic, assign) NSInteger pendingRequestsCount;
@property (nonatomic, assign) NSInteger malformedRequestCount;
@property (nonatomic, strong) NSMutableSet<NSString*>* subscriptions;
@end

@implementation DietCodeClientConnection
- (instancetype)init {
    self = [super init];
    if (self) {
        _subscriptions = [NSMutableSet set];
    }
    return self;
}
@end

@interface DietCodeControlServer ()

- (void)acceptLoop;
- (void)handleClient:(DietCodeClientConnection*)conn;
- (void)processRequest:(const std::string&)requestStr connection:(DietCodeClientConnection*)conn;
- (void)markConnectionEOF:(DietCodeClientConnection*)conn;
- (void)decrementPendingRequestsForConnection:(DietCodeClientConnection*)conn;
- (NSString*)permissionLevelForMethod:(NSString*)method params:(NSDictionary*)params;
- (void)sendError:(NSString*)reqId code:(id)code message:(NSString*)message clientFd:(int)clientFd;
- (void)sendError:(NSString*)reqId code:(id)code message:(NSString*)message method:(NSString*)method phase:(NSString*)phase queue:(NSString*)queue durationMs:(long long)durationMs clientFd:(int)clientFd;
- (void)sendSuccess:(NSString*)reqId result:(NSDictionary*)result clientFd:(int)clientFd;
- (void)sendSuccess:(NSString*)reqId result:(NSDictionary*)result method:(NSString*)method phase:(NSString*)phase queue:(NSString*)queue durationMs:(long long)durationMs clientFd:(int)clientFd;
- (void)logRuntimeDiagnostic:(NSString*)requestId method:(NSString*)method phase:(NSString*)phase ok:(BOOL)ok stringCode:(NSString*)stringCode queue:(NSString*)queue durationMs:(long long)durationMs;
- (void)recordMalformedRequestOnConnection:(DietCodeClientConnection*)conn clientFd:(int)clientFd reqId:(NSString*)reqId;
- (NSString*)queueLabelForMethod:(NSString*)method background:(BOOL)background;
- (NSString*)chipNameForStep:(NSDictionary*)step;
- (NSDictionary*)paramsForComboStep:(NSDictionary*)step;
- (NSArray<NSDictionary*>*)rpcMethodDescriptions;
- (NSDictionary*)descriptionForRPCMethod:(NSString*)method;
- (NSArray<NSDictionary*>*)chipRegistry;
- (NSDictionary*)metadataForChip:(NSString*)chip;
- (NSDictionary*)primitiveForChip:(NSString*)chip params:(NSDictionary*)params;

@end

static const void* kDietCodeExecutionQueueKey = &kDietCodeExecutionQueueKey;
static const void* kDietCodeReadQueueKey = &kDietCodeReadQueueKey;

@implementation DietCodeControlServer

- (void)configureServices {
        _searchService = [[MacControlSearchService alloc] initWithWindowBridge:_windowBridge];
        _recoveryStore = [[MacControlRecoveryStore alloc] initWithWindowBridge:_windowBridge];
        _workspaceState = [[MacControlWorkspaceState alloc] init];
        _patchService = [[MacControlPatchService alloc] initWithWindowBridge:_windowBridge];
        _patchService.workspaceState = _workspaceState;
        
        __weak DietCodeControlServer* weakSelf = self;
        MacControlMethodExecutor nestedExecutor = ^(NSString* method, NSDictionary* params, NSDictionary** outResult, NSString** outErrCode, NSString** outErrMsg, NSString** outPaths) {
            [weakSelf executeNestedMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
        };
        _taskRuntime = [[MacControlTaskRuntime alloc] initWithWindowBridge:_windowBridge
                                                               patchService:_patchService
                                                              searchService:_searchService
                                                                   executor:nestedExecutor];
        
        _comboRuntime = [[MacControlComboRuntime alloc] initWithWindowBridge:_windowBridge
                                                               recoveryStore:_recoveryStore
                                                                patchService:_patchService
                                                                 taskRuntime:_taskRuntime
                                                                    executor:nestedExecutor];
        _approvalService = [[MacControlApprovalService alloc] init];

        _isRunning = NO;
        _serverFd = -1;
        _contextSnapshots = [NSMutableDictionary dictionary];
        _contextSnapshotCounter = 0;
        _activeConnections = [NSMutableDictionary dictionary];
        _eventRingBuffer = [NSMutableArray array];
        _eventSequence = 0;
        _sessionToken = nil;
        _executionQueue = dispatch_queue_create("com.dietcode.runtime.execution", DISPATCH_QUEUE_SERIAL);
        _readQueue = dispatch_queue_create("com.dietcode.runtime.read", DISPATCH_QUEUE_CONCURRENT);
        dispatch_queue_set_specific(_executionQueue, kDietCodeExecutionQueueKey, (void*)kDietCodeExecutionQueueKey, NULL);
        dispatch_queue_set_specific(_readQueue, kDietCodeReadQueueKey, (void*)kDietCodeReadQueueKey, NULL);
        
        [[NSNotificationCenter defaultCenter] addObserver:self
                                                 selector:@selector(handleTerminalOutputUpdate:)
                                                     name:kDietCodeTerminalOutputDidUpdateNotification
                                                   object:nil];
        _globalMutationLock = NO;
        _lastVerifyStatus = @{
            @"command": @"",
            @"state": @"idle",
            @"exitCode": [NSNull null],
            @"passed": @NO
        };
        _lastComboId = nil;
}

- (instancetype)initWithWorkspaceSession:(DietCodeWorkspaceSession*)session {
    self = [super init];
    if (self) {
        _isKernelMode = YES;
        _workspaceSession = session;
        _windowController = nil;
        _windowBridge = [[DietCodeControlWindowBridge alloc] initWithWorkspaceSession:session windowController:nil];
        [self configureServices];
    }
    return self;
}

#ifndef DIETCODE_KERNEL_BUILD
- (instancetype)initWithWindowController:(DietCodeWindowController*)controller {
    self = [super init];
    if (self) {
        _isKernelMode = NO;
        _windowController = controller;
        _windowBridge = [[DietCodeLegacyWindowBridge alloc] initWithWindowController:controller];
        _workspaceSession = _windowBridge.workspaceSession;
        [self configureServices];
    }
    return self;
}
#endif

- (BOOL)isKernelMode {
    return _isKernelMode;
}

- (DietCodeWorkspaceSession*)workspaceSession {
    return _workspaceSession;
}

- (NSString*)safeWorkspacePath {
    return [_windowBridge workspacePath];
}

- (NSString*)safeTextForFileAtPath:(NSString*)path {
    NSString* text = [_windowBridge textForFileAtPath:path];
    if (text) return text;
    return DietCodeReadTextFileForControlServer(path);
}

- (BOOL)safeReplaceTextInRange:(NSRange)range withText:(NSString*)text forFileAtPath:(NSString*)path {
    return [_windowBridge replaceTextInRange:range withText:text forFileAtPath:path];
}

- (NSArray<NSString*>*)safeOpenFilePaths {
    return [_windowBridge openFilePaths];
}

- (NSArray<NSDictionary*>*)safeProblemsList {
    return [_windowBridge problemsList];
}

- (NSString*)safeActiveFilePath {
    return [_windowBridge activeFilePath];
}

- (NSArray*)safeOpenTabs {
    return [_windowBridge openTabs];
}

- (NSDictionary*)safeGitStatusInfo {
    return [_windowBridge gitStatusInfo];
}

- (NSString*)safeGitDiffForFile:(NSString*)path {
    return [_windowBridge gitDiffForFile:path];
}

- (NSDictionary*)safeActiveSelectionInfo {
    return [_windowBridge activeSelectionInfo];
}

- (NSString*)safeTerminalOutput {
    return [_windowBridge terminalOutput];
}

- (NSArray*)safeSessionRecentCommands {
    return [_windowBridge sessionRecentCommands];
}

- (NSArray*)safeSessionLastSearches {
    return [_windowBridge sessionLastSearches];
}

- (pid_t)safeTerminalPid {
    return [_windowBridge terminalPid];
}

- (NSArray*)safeLanguageDiagnosticsForPath:(NSString*)path {
    return [_windowBridge languageDiagnosticsForPath:path];
}

- (NSInteger)safeAgentAutonomyLevel {
    return [_windowBridge agentAutonomyLevel];
}

- (void)start {
    if (_isRunning) return;
    
    signal(SIGPIPE, SIG_IGN);
    
    NSString* homeDir = NSHomeDirectory();
    NSString* dcDir = [homeDir stringByAppendingPathComponent:@".dietcode"];
    
    NSString* dirIssue = MacControlDietcodeDirIssue(dcDir);
    if (dirIssue) {
        [self appendLogLine:[NSString stringWithFormat:@"[Error] ~/.dietcode unsafe (%@). Aborting for security.", dirIssue]];
        [self logRuntimeDiagnostic:@"startup" method:@"socket" phase:@"socket_unsafe" ok:NO stringCode:dirIssue queue:nil durationMs:-1];
        return;
    }
    if (![[NSFileManager defaultManager] fileExistsAtPath:dcDir]) {
        [[NSFileManager defaultManager] createDirectoryAtPath:dcDir withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions: @(0700)} error:nil];
    }
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @(0700)} ofItemAtPath:dcDir error:nil];
    
    mode_t oldUmask = umask(0077);
    
    NSString* token = [NSString stringWithFormat:@"%08x%08x%08x%08x", 
                       arc4random(), arc4random(), arc4random(), arc4random()];
    NSString* tokenPath = [dcDir stringByAppendingPathComponent:@"session.token"];
    unlink([tokenPath UTF8String]);
    
    int tokenFd = open([tokenPath UTF8String], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (tokenFd >= 0) {
        NSData* tokenData = [token dataUsingEncoding:NSUTF8StringEncoding];
        write(tokenFd, tokenData.bytes, tokenData.length);
        close(tokenFd);
    } else {
        [token writeToFile:tokenPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
    }
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @(0600)} ofItemAtPath:tokenPath error:nil];
    _sessionToken = [token copy];
    
    // Unix socket setup
    NSString* sockPathStr = [dcDir stringByAppendingPathComponent:@"control.sock"];
    const char* sockPath = [sockPathStr UTF8String];
    
    _serverFd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (_serverFd < 0) {
        [self appendLogLine:@"[Error] Failed to create Unix socket."];
        umask(oldUmask);
        return;
    }
    
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(sockPath) >= sizeof(addr.sun_path)) {
        [self appendLogLine:[NSString stringWithFormat:@"[Error] Unix socket path is too long: %lu bytes (max %lu bytes). Can't bind.", strlen(sockPath), sizeof(addr.sun_path) - 1]];
        close(_serverFd);
        _serverFd = -1;
        umask(oldUmask);
        return;
    }
    strncpy(addr.sun_path, sockPath, sizeof(addr.sun_path) - 1);

    NSString* sockIssue = MacControlSocketPathIssue(sockPathStr);
    if (sockIssue) {
        [self appendLogLine:[NSString stringWithFormat:@"[Error] control socket path unsafe (%@). Aborting.", sockIssue]];
        [self logRuntimeDiagnostic:@"startup" method:@"socket" phase:@"socket_unsafe" ok:NO stringCode:sockIssue queue:nil durationMs:-1];
        close(_serverFd);
        _serverFd = -1;
        umask(oldUmask);
        return;
    }
    
    unlink(sockPath);
    
    if (bind(_serverFd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        [self appendLogLine:@"[Error] Failed to bind Unix socket."];
        close(_serverFd);
        _serverFd = -1;
        umask(oldUmask);
        return;
    }
    
    chmod(sockPath, 0600);
    umask(oldUmask);
    
    if (listen(_serverFd, (int)kSocketListenBacklog) < 0) {
        [self appendLogLine:@"[Error] Failed to listen on socket."];
        close(_serverFd);
        _serverFd = -1;
        unlink(sockPath);
        return;
    }
    
    _isRunning = YES;
    [self appendLogLine:@"[System] External Control Server started. Listening on ~/.dietcode/control.sock"];
    
    _acceptThread = [[NSThread alloc] initWithTarget:self selector:@selector(acceptLoop) object:nil];
    [_acceptThread start];
}

- (void)stop {
    if (!_isRunning) return;
    _isRunning = NO;
    
    int fd = _serverFd;
    _serverFd = -1;
    if (fd >= 0) {
        close(fd);
    }
    
    @synchronized(self) {
        for (NSNumber* fdNum in _activeConnections) {
            DietCodeClientConnection* conn = _activeConnections[fdNum];
            shutdown(conn.fd, SHUT_RDWR);
        }
    }
    
    NSString* dcDir = [NSHomeDirectory() stringByAppendingPathComponent:@".dietcode"];
    unlink([[dcDir stringByAppendingPathComponent:@"control.sock"] UTF8String]);
    unlink([[dcDir stringByAppendingPathComponent:@"session.token"] UTF8String]);
    
    [self appendLogLine:@"[System] External Control Server stopped."];
    if (_windowController) {
        [_windowController setControlActiveCommand:nil caller:nil];
    }
}

- (void)acceptLoop {
    while (_isRunning && _serverFd >= 0) {
        @autoreleasepool {
            struct sockaddr_un clientAddr;
            socklen_t clientLen = sizeof(clientAddr);
            int clientFd = accept(_serverFd, (struct sockaddr*)&clientAddr, &clientLen);
            if (clientFd < 0) {
                if (!_isRunning) return;
                if (errno != EINTR) {
                    [self appendLogLine:[NSString stringWithFormat:@"[Error] accept() failed with errno %d: %s", errno, strerror(errno)]];
                }
                usleep(100000); // 100ms backoff on error
            } else {
                int optval = 1;
                setsockopt(clientFd, SOL_SOCKET, SO_NOSIGPIPE, &optval, sizeof(optval));
                
                DietCodeClientConnection* conn = [[DietCodeClientConnection alloc] init];
                conn.fd = clientFd;
                conn.readEOF = NO;
                conn.pendingRequestsCount = 0;
                conn.malformedRequestCount = 0;
                
                @synchronized(self) {
                    if (!_isRunning) {
                        close(clientFd);
                    } else if ((NSInteger)_activeConnections.count >= kMaxActiveConnections) {
                        [self logRuntimeDiagnostic:@"unknown" method:@"connection" phase:@"connection_rejected" ok:NO stringCode:@"connection_limit_exceeded" queue:nil durationMs:-1];
                        close(clientFd);
                    } else {
                        _activeConnections[@(clientFd)] = conn;
                        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
                            [self handleClient:conn];
                        });
                    }
                }
            }
        }
    }
}

- (BOOL)isReadQueueMethod:(NSString*)method {
    return MacControlIsReadQueueMethod(method);
}

- (void)executeNestedMethod:(NSString*)method
                     params:(NSDictionary*)params
                  outResult:(NSDictionary**)outResult
                 outErrCode:(NSString**)outErrCode
                    outErrMsg:(NSString**)outErrMsg
                   outPaths:(NSString**)outPaths {
    dispatch_queue_t targetQueue = MacControlIsReadQueueMethod(method) ? _readQueue : _executionQueue;
    const void* queueKey = MacControlIsReadQueueMethod(method) ? kDietCodeReadQueueKey : kDietCodeExecutionQueueKey;
    if (dispatch_get_specific(queueKey)) {
        [self executeMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
        return;
    }

    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block NSDictionary* result = nil;
    __block NSString* errCode = nil;
    __block NSString* errMsg = nil;
    __block NSString* paths = nil;
    dispatch_async(targetQueue, ^{
        [self executeMethod:method params:params outResult:&result outErrCode:&errCode outErrMsg:&errMsg outPaths:&paths];
        dispatch_semaphore_signal(sem);
    });
    long waitResult = dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(kMaxNestedCallWaitSeconds * NSEC_PER_SEC)));
    if (waitResult != 0) {
        if (outErrCode) *outErrCode = @"nested_call_timeout";
        if (outErrMsg) *outErrMsg = [NSString stringWithFormat:@"Nested method call timed out after %ld seconds.", (long)kMaxNestedCallWaitSeconds];
        return;
    }
    if (outResult) *outResult = result;
    if (outErrCode) *outErrCode = errCode;
    if (outErrMsg) *outErrMsg = errMsg;
    if (outPaths) *outPaths = paths;
}

- (dispatch_queue_t)queueForRequestLine:(const std::string&)line {
    NSData* data = [NSData dataWithBytes:line.data() length:line.size()];
    NSDictionary* req = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    NSString* method = [req isKindOfClass:[NSDictionary class]] ? req[@"method"] : nil;
    return [self isReadQueueMethod:method] ? _readQueue : _executionQueue;
}

- (void)handleClient:(DietCodeClientConnection*)conn {
    int clientFd = conn.fd;
    std::string buffer;
    char readBuf[4096];
    BOOL connectionActive = YES;
    
    while (_isRunning && connectionActive) {
        @autoreleasepool {
            ssize_t bytes = read(clientFd, readBuf, sizeof(readBuf));
            if (bytes < 0) {
                if (errno == EINTR) {
                    continue;
                }
                connectionActive = NO;
            } else if (bytes == 0) {
                connectionActive = NO;
            } else {
                buffer.append(readBuf, bytes);
                if (buffer.size() > kMaxRequestBytes) {
                    [self sendError:@"unknown" code:@"request_too_large" message:@"Request exceeds maximum allowed size." clientFd:clientFd];
                    buffer.clear();
                    connectionActive = NO;
                } else {
                    size_t newlinePos;
                    while ((newlinePos = buffer.find('\n')) != std::string::npos) {
                        std::string line = buffer.substr(0, newlinePos);
                        buffer.erase(0, newlinePos + 1);
                        
                        if (line.empty()) continue;
                        if (line.size() > kMaxRequestBytes) {
                            [self sendError:@"unknown" code:@"request_too_large" message:@"Request exceeds maximum allowed size." clientFd:clientFd];
                            continue;
                        }
                        
                        BOOL rejectPending = NO;
                        @synchronized(self) {
                            if (conn.pendingRequestsCount >= kMaxPendingRequestsPerConnection) {
                                rejectPending = YES;
                            } else {
                                conn.pendingRequestsCount++;
                            }
                        }
                        if (rejectPending) {
                            [self sendError:@"unknown" code:@"too_many_pending" message:@"Too many in-flight requests on this connection." clientFd:clientFd];
                            continue;
                        }
                        
                        dispatch_async([self queueForRequestLine:line], ^{
                            @autoreleasepool {
                                [self processRequest:line connection:conn];
                            }
                        });
                    }
                }
            }
        }
    }
    
    [self markConnectionEOF:conn];
}

- (void)markConnectionEOF:(DietCodeClientConnection*)conn {
    BOOL shouldClose = NO;
    @synchronized(self) {
        conn.readEOF = YES;
        if (conn.pendingRequestsCount == 0) {
            shouldClose = YES;
            [_activeConnections removeObjectForKey:@(conn.fd)];
        }
    }
    if (shouldClose) {
        [self logRuntimeDiagnostic:@"unknown" method:@"connection" phase:@"connection_close" ok:YES stringCode:nil queue:nil durationMs:-1];
        close(conn.fd);
    }
}

- (void)decrementPendingRequestsForConnection:(DietCodeClientConnection*)conn {
    BOOL shouldClose = NO;
    @synchronized(self) {
        conn.pendingRequestsCount--;
        if (conn.readEOF && conn.pendingRequestsCount == 0) {
            shouldClose = YES;
            [_activeConnections removeObjectForKey:@(conn.fd)];
        }
    }
    if (shouldClose) {
        close(conn.fd);
    }
}

- (void)processRequest:(const std::string&)requestStr connection:(DietCodeClientConnection*)conn {
    NSString* reqId = @"unknown";
    NSString* method = @"unknown";
    int clientFd = conn.fd;
    @try {
        auto startTime = std::chrono::high_resolution_clock::now();
        if (requestStr.size() > kMaxRequestBytes) {
            [self sendError:@"unknown" code:@"request_too_large" message:@"Request exceeds maximum allowed size." clientFd:clientFd];
            [self logAuditMethod:@"invalid" caller:@"unknown" permission:@"none" duration:0 result:@"request_too_large" paths:@""];
            return;
        }
        
        NSData* reqData = [NSData dataWithBytes:requestStr.data() length:requestStr.size()];
        NSError* jsonErr = nil;
        id reqObj = [NSJSONSerialization JSONObjectWithData:reqData options:0 error:&jsonErr];
        if (jsonErr || ![reqObj isKindOfClass:[NSDictionary class]]) {
            [self sendError:@"unknown" code:@"invalid_request" message:@"Malformed JSON request object." clientFd:clientFd];
            [self recordMalformedRequestOnConnection:conn clientFd:clientFd reqId:@"unknown"];
            [self logAuditMethod:@"invalid" caller:@"unknown" permission:@"none" duration:0 result:@"failed" paths:@""];
            return;
        }
        
        NSDictionary* req = (NSDictionary*)reqObj;
        reqId = RequestIdString(req[@"id"]);
        id methodObj = req[@"method"];
        [self logRuntimeDiagnostic:reqId method:@"unknown" phase:@"request_accepted" ok:YES stringCode:nil queue:nil durationMs:-1];
        if (![methodObj isKindOfClass:[NSString class]] || [methodObj length] == 0) {
            [self sendError:reqId code:@"invalid_request" message:@"Malformed JSON or missing method." clientFd:clientFd];
            [self logAuditMethod:@"invalid" caller:@"unknown" permission:@"none" duration:0 result:@"failed" paths:@""];
            return;
        }
        method = (NSString*)methodObj;
        NSString* queueLabel = [self queueLabelForMethod:method background:YES];
        [self logRuntimeDiagnostic:reqId method:method phase:@"request_parsed" ok:YES stringCode:nil queue:queueLabel durationMs:-1];
        id paramsObj = req[@"params"];
        if (paramsObj && ![paramsObj isKindOfClass:[NSDictionary class]]) {
            [self sendError:reqId code:@"invalid_params" message:@"params must be a JSON object." clientFd:clientFd];
            [self logAuditMethod:method caller:@"unknown" permission:@"none" duration:0 result:@"invalid_params" paths:@""];
            return;
        }
        NSDictionary* params = paramsObj ?: @{};
        id schemaObj = req[@"schemaVersion"];
        if (schemaObj && (![schemaObj isKindOfClass:[NSString class]] ||
                          (![(NSString*)schemaObj isEqualToString:@"1.6"] && ![(NSString*)schemaObj isEqualToString:@"1.6.2"]))) {
            [self sendError:reqId code:@"invalid_request" message:@"Unsupported RPC schemaVersion." clientFd:clientFd];
            [self logAuditMethod:method caller:@"unknown" permission:@"none" duration:0 result:@"invalid_schema" paths:@""];
            return;
        }
        
        // Validate session token
        id tokenObj = req[@"token"];
        NSString* token = [tokenObj isKindOfClass:[NSString class]] ? (NSString*)tokenObj : nil;
        if (!_sessionToken || !token || ![token isEqualToString:_sessionToken]) {
            [self sendError:reqId code:@"permission_denied" message:@"Invalid or missing session token." clientFd:clientFd];
            [self logAuditMethod:method caller:@"unknown" permission:@"none" duration:0 result:@"auth_failed" paths:@""];
            return;
        }
        
        // Agent Attribution & Rationale
        NSString* agentId = req[@"agentId"] ?: params[@"agentId"];
        if (![agentId isKindOfClass:[NSString class]]) agentId = nil;
        NSString* rationale = req[@"rationale"] ?: params[@"rationale"];
        if (![rationale isKindOfClass:[NSString class]]) rationale = nil;
        
        NSString* caller = agentId ?: @"unix_socket";
        NSString* permission = [self permissionLevelForMethod:method params:params];
        
        if ([method isEqualToString:@"event.subscribe"] || [method isEqualToString:@"event.unsubscribe"] || [method isEqualToString:@"events.recent"]) {
            if ([method isEqualToString:@"events.recent"]) {
                NSInteger limit = params[@"limit"] ? [params[@"limit"] integerValue] : 50;
                if (limit < 1) limit = 1;
                if (limit > 500) limit = 500;
                NSString* afterSeq = params[@"afterSequence"];
                NSInteger afterSequence = afterSeq.length > 0 ? [afterSeq integerValue] : 0;
                NSArray* typesFilter = params[@"types"];
                NSMutableArray* events = [NSMutableArray array];
                @synchronized(self) {
                    for (NSDictionary* event in _eventRingBuffer) {
                        NSInteger seq = [event[@"sequence"] integerValue];
                        if (seq <= afterSequence) continue;
                        if ([typesFilter isKindOfClass:[NSArray class]] && typesFilter.count > 0) {
                            NSString* eventType = event[@"type"];
                            if (![typesFilter containsObject:eventType] && ![typesFilter containsObject:@"*"]) continue;
                        }
                        [events addObject:event];
                    }
                }
                BOOL truncated = events.count > (NSUInteger)limit;
                if (truncated) {
                    events = [[events subarrayWithRange:NSMakeRange(events.count - (NSUInteger)limit, (NSUInteger)limit)] mutableCopy];
                }
                [self sendSuccess:reqId result:@{
                    @"events": events,
                    @"truncated": @(truncated),
                    @"mode": @"events_recent",
                } clientFd:clientFd];
                return;
            }
            NSArray* types = params[@"types"];
            if (![types isKindOfClass:[NSArray class]] || types.count == 0) {
                [self sendError:reqId code:@"invalid_params" message:@"types must be a non-empty array of strings." clientFd:clientFd];
                return;
            }
            NSMutableArray<NSString*>* normalizedTypes = [NSMutableArray array];
            for (id typeValue in types) {
                if (![typeValue isKindOfClass:[NSString class]] || [(NSString*)typeValue length] == 0) {
                    [self sendError:reqId code:@"invalid_params" message:@"types must contain only non-empty strings." clientFd:clientFd];
                    return;
                }
                [normalizedTypes addObject:(NSString*)typeValue];
            }
            BOOL subscribe = [method isEqualToString:@"event.subscribe"];
            @synchronized(self) {
                for (NSString* t in normalizedTypes) {
                    if (subscribe) {
                        [conn.subscriptions addObject:t];
                    } else {
                        [conn.subscriptions removeObject:t];
                    }
                }
            }
            if (subscribe) {
                [self sendSuccess:reqId result:@{ @"subscribed": @YES, @"types": normalizedTypes } clientFd:clientFd];
            } else {
                [self sendSuccess:reqId result:@{ @"unsubscribed": @YES, @"types": normalizedTypes } clientFd:clientFd];
            }
            return;
        }
        
        if (_windowController) {
            dispatch_async(dispatch_get_main_queue(), ^{
                [_windowController setControlActiveCommand:method caller:caller];
            });
        }
        
        if ([permission isEqualToString:@"Edit"] || [permission isEqualToString:@"Destructive"]) {
            if ([self queueCoherenceMismatchIfNeeded:method params:params reqId:reqId clientFd:clientFd]) {
                return;
            }
            if ([self queueWorkspaceDriftBlockIfNeeded:method params:params reqId:reqId clientFd:clientFd]) {
                return;
            }
        }

        if ([permission isEqualToString:@"Destructive"]) {
            NSString* approvalErrCode = nil;
            NSString* approvalErrMsg = nil;
            if (![self validateDestructiveApprovalIfPresent:method params:params outErrCode:&approvalErrCode outErrMsg:&approvalErrMsg]) {
                [self sendError:reqId code:approvalErrCode ?: @"approval_invalid" message:approvalErrMsg ?: @"Invalid approval." clientFd:clientFd];
                return;
            }
            if ([self queueDestructiveApprovalIfNeeded:method params:params caller:caller rationale:rationale reqId:reqId clientFd:clientFd]) {
                return;
            }
        }

        __block BOOL allowed = YES;
        if ([permission isEqualToString:@"Destructive"]) {
            NSInteger autonomy = [self safeAgentAutonomyLevel];
            if (autonomy == 1) {
                allowed = YES;
            } else if (autonomy == 2) {
                if (_windowController && !_windowController.isHeadless) {
                    allowed = [self isDestructiveRequestSafe:method params:params];
                } else {
                    allowed = YES;
                }
            } else {
                NSMutableString* alertMsg = [NSMutableString stringWithFormat:@"An external agent is requesting to execute a destructive command:\n\nMethod: %@\nParams: %@", method, params];
                if (rationale.length > 0) {
                    [alertMsg appendFormat:@"\n\nRationale: %@", rationale];
                }
                dispatch_semaphore_t sem = dispatch_semaphore_create(0);
                dispatch_async(dispatch_get_main_queue(), ^{
                    NSAlert* alert = [[NSAlert alloc] init];
                    [alert setMessageText:@"External Control Confirmation"];
                    [alert setInformativeText:alertMsg];
                    [alert addButtonWithTitle:@"Allow"];
                    [alert addButtonWithTitle:@"Deny"];
                    NSModalResponse res = [alert runModal];
                    allowed = (res == NSAlertFirstButtonReturn);
                    dispatch_semaphore_signal(sem);
                });
                dispatch_semaphore_wait(sem, DISPATCH_TIME_FOREVER);
            }
        } else if ([permission isEqualToString:@"Execute"] && _windowController) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if ([method hasPrefix:@"terminal"]) {
                    [[self windowController] showBottomPanelTab:@"terminal"];
                } else if ([method hasPrefix:@"language.lint"]) {
                    [[self windowController] showBottomPanelTab:@"errors"];
                }
            });
        }
        
        if (!allowed) {
            [self sendError:reqId code:@"permission_denied" message:@"User rejected the command execution." clientFd:clientFd];
            if (_windowController) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    [_windowController setControlActiveCommand:nil caller:caller];
                });
            }
            
            auto endTime = std::chrono::high_resolution_clock::now();
            auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime).count();
            [self logAuditMethod:method caller:caller permission:permission duration:duration result:@"rejected" paths:@""];
            [self appendLogLine:[NSString stringWithFormat:@"[%@] %@ -> Rejected (user denied)", caller, method]];
            return;
        }
        
        __block NSDictionary* result = nil;
        __block NSString* errCode = nil;
        __block NSString* errMsg = nil;
        __block NSString* affectedPaths = @"";
        
        BOOL isBackgroundMethod = [method isEqualToString:@"verify.run"] ||
                                  [self isReadQueueMethod:method] ||
                                  [method isEqualToString:@"combo.run"] ||
                                  [method isEqualToString:@"combo.status"] ||
                                  [method isEqualToString:@"combo.result"] ||
                                  [method isEqualToString:@"combo.cancel"] ||
                                  [method isEqualToString:@"combo.rollback"] ||
                                  [method isEqualToString:@"combo.list"] ||
                                  [method isEqualToString:@"workspace.searchStart"] ||
                                  [method isEqualToString:@"workspace.searchNext"] ||
                                  [method isEqualToString:@"workspace.searchCancel"] ||
                                  [method isEqualToString:@"verify.last"] ||
                                  [method isEqualToString:@"verify.status"] ||
                                  [method isEqualToString:@"verify.failures"] ||
                                  [method isEqualToString:@"context.snapshot"] ||
                                  [method isEqualToString:@"context.delta"] ||
                                  [method isEqualToString:@"task.start"] ||
                                  [method isEqualToString:@"task.status"] ||
                                  [method isEqualToString:@"task.result"] ||
                                  [method isEqualToString:@"task.cancel"] ||
                                  [method isEqualToString:@"task.step"] ||
                                  [method isEqualToString:@"task.runLoop"] ||
                                  [method isEqualToString:@"edit.plan"] ||
                                  [method isEqualToString:@"edit.executePlan"];
        
        NSString* execQueue = isBackgroundMethod ? queueLabel : @"com.dietcode.runtime.main";
        [self logRuntimeDiagnostic:reqId method:method phase:@"queue_dispatch" ok:YES stringCode:nil queue:execQueue durationMs:-1];
        if (isBackgroundMethod) {
            [self executeMethod:method params:params outResult:&result outErrCode:&errCode outErrMsg:&errMsg outPaths:&affectedPaths];
        } else {
            dispatch_semaphore_t execSem = dispatch_semaphore_create(0);
            dispatch_async(dispatch_get_main_queue(), ^{
                [self executeMethod:method params:params outResult:&result outErrCode:&errCode outErrMsg:&errMsg outPaths:&affectedPaths];
                dispatch_semaphore_signal(execSem);
            });
            dispatch_semaphore_wait(execSem, DISPATCH_TIME_FOREVER);
        }
        
        if (_windowController) {
            dispatch_async(dispatch_get_main_queue(), ^{
                [_windowController setControlActiveCommand:nil caller:caller];
            });
        }
        
        auto endTime = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(endTime - startTime).count();
        
        if (errCode) {
            [self sendError:reqId code:errCode message:errMsg method:method phase:@"response_error" queue:execQueue durationMs:duration clientFd:clientFd];
            [self logAuditMethod:method caller:caller permission:permission duration:duration result:[NSString stringWithFormat:@"error: %@", errCode] paths:affectedPaths];
            [self appendLogLine:[NSString stringWithFormat:@"[%@] %@ -> Error (%@) in %lldms", caller, method, errMsg, duration]];
        } else {
            [self notifyWorkspaceMutatedIfNeededForMethod:method params:params result:result];
            [self sendSuccess:reqId result:result method:method phase:@"response_success" queue:execQueue durationMs:duration clientFd:clientFd];
            [self logAuditMethod:method caller:caller permission:permission duration:duration result:@"success" paths:affectedPaths];
            [self appendLogLine:[NSString stringWithFormat:@"[%@] %@ -> Success in %lldms", caller, method, duration]];
        }
    } @catch (NSException* exception) {
        NSString* message = exception.reason ?: @"Unhandled server exception.";
        NSString* failedMethod = method.length > 0 ? method : @"unknown";
        [self sendError:(reqId.length > 0 ? reqId : @"unknown") code:@"internal_error" message:message method:failedMethod phase:@"exception" queue:nil durationMs:-1 clientFd:clientFd];
        [self appendLogLine:[NSString stringWithFormat:@"[Exception] %@ -> %@", failedMethod, message]];
    } @finally {
        [self decrementPendingRequestsForConnection:conn];
    }
}

- (NSArray<NSDictionary*>*)rpcMethodDescriptions {
    return MacControlRPCMethodDescriptions();
}

- (NSDictionary*)descriptionForRPCMethod:(NSString*)method {
    return MacControlDescriptionForRPCMethod(method);
}

- (NSArray<NSDictionary*>*)chipRegistry {
    return MacControlChipRegistry();
}

- (NSDictionary*)metadataForChip:(NSString*)chip {
    return MacControlMetadataForChip(chip);
}

- (NSDictionary*)primitiveForChip:(NSString*)chip params:(NSDictionary*)params {
    return MacControlPrimitiveForChip(chip, params);
}

- (NSString*)chipNameForStep:(NSDictionary*)step {
    NSString* chip = step[@"chip"];
    if (chip.length > 0) return CanonicalChipName(chip);
    NSDictionary* primitive = [_taskRuntime primitiveForWorkbenchStep:step];
    return primitive[@"method"] ?: @"";
}

- (NSDictionary*)paramsForComboStep:(NSDictionary*)step {
    NSDictionary* params = step[@"params"];
    if ([params isKindOfClass:[NSDictionary class]]) return params;
    NSMutableDictionary* copy = [step mutableCopy];
    [copy removeObjectForKey:@"id"];
    [copy removeObjectForKey:@"chip"];
    [copy removeObjectForKey:@"type"];
    [copy removeObjectForKey:@"needs"];
    [copy removeObjectForKey:@"expects"];
    return copy;
}

- (BOOL)isDestructiveRequestSafe:(NSString*)method params:(NSDictionary*)params {
    NSString* ws = [self safeWorkspacePath];
    if (!ws) return NO;
    
    if ([method isEqualToString:@"git.commit"]) {
        return YES;
    }
    if ([method isEqualToString:@"workspace.openFolder"]) {
        return NO;
    }
    
    NSString* path = params[@"path"];
    if (path) {
        NSString* checkedPath = AbsolutePathForRPCPath(path, ws);
        if (!PathIsInsideWorkspace(checkedPath, ws)) {
            return NO;
        }
    }
    
    if ([method isEqualToString:@"patch.applyBatch"]) {
        NSArray* patches = params[@"patches"];
        if ([patches isKindOfClass:[NSArray class]]) {
            for (NSDictionary* patchDict in patches) {
                if ([patchDict isKindOfClass:[NSDictionary class]]) {
                    NSString* pPath = patchDict[@"path"];
                    if (pPath) {
                        NSString* checkedPath = AbsolutePathForRPCPath(pPath, ws);
                        if (!PathIsInsideWorkspace(checkedPath, ws)) {
                            return NO;
                        }
                    }
                }
            }
        }
    }
    
    if ([method isEqualToString:@"combo.run"]) {
        NSDictionary* comboReq = params[@"combo"] ?: params;
        for (NSDictionary* step in comboReq[@"steps"] ?: @[]) {
            NSString* chip = step[@"chip"];
            if (chip.length == 0) continue;
            NSDictionary* stepParams = step[@"params"];
            if ([chip isEqualToString:@"patch.apply"]) {
                NSString* pPath = stepParams[@"path"];
                if (pPath) {
                    NSString* checkedPath = AbsolutePathForRPCPath(pPath, ws);
                    if (!PathIsInsideWorkspace(checkedPath, ws)) return NO;
                }
            }
            if ([chip isEqualToString:@"patch.applyBatch"]) {
                for (NSDictionary* p in stepParams[@"patches"] ?: @[]) {
                    NSString* pPath = p[@"path"];
                    if (pPath) {
                        NSString* checkedPath = AbsolutePathForRPCPath(pPath, ws);
                        if (!PathIsInsideWorkspace(checkedPath, ws)) return NO;
                    }
                }
            }
        }
    }
    
    return YES;
}

- (NSDictionary*)currentChangesInfo {
    NSString* ws = [_windowBridge workspacePath] ?: @"";
    NSDictionary* git = [self safeGitStatusInfo] ?: @{};
    NSDictionary* diffInfo = ws.length > 0 ? [DietCodeDiffAnalysisService workspaceDiffInfo:ws] : @{};
    NSMutableArray* files = [NSMutableArray array];

    for (NSDictionary* file in diffInfo[@"files"] ?: @[]) {
        NSString* relPath = file[@"path"] ?: @"";
        NSString* absPath = AbsolutePathForRPCPath(relPath, ws);
        NSString* text = [self safeTextForFileAtPath:absPath] ?: @"";
        NSArray* symbols = text.length > 0 ? [DietCodeSymbolIndexService symbolsForFileContent:text extension:[[absPath pathExtension] lowercaseString]] : @[];
        NSString* diff = [self safeGitDiffForFile:absPath] ?: @"";
        NSMutableDictionary* enriched = [file mutableCopy];
        enriched[@"absolutePath"] = absPath ?: @"";
        enriched[@"affectedSymbols"] = AffectedSymbolsForPatch(diff, symbols);
        [files addObject:enriched];
    }

    NSArray* dirtyFiles = DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[]);
    NSMutableArray* unsaved = [NSMutableArray array];
    for (NSString* dirtyPath in dirtyFiles) {
        [unsaved addObject:@{ @"path": dirtyPath }];
    }

    return @{
        @"modifiedFiles": files,
        @"unsavedBuffers": unsaved,
        @"stagedFiles": git[@"staged"] ?: @[],
        @"unstagedFiles": git[@"modified"] ?: @[],
        @"untrackedFiles": git[@"untracked"] ?: @[],
        @"totalAdded": diffInfo[@"totalAdded"] ?: @0,
        @"totalDeleted": diffInfo[@"totalDeleted"] ?: @0
    };
}

- (NSDictionary*)runVerificationCommand:(NSString*)command cwd:(NSString*)cwd {
    NSString* ws = [self safeWorkspacePath];
    NSString* runCwd = cwd.length > 0 ? cwd : ws;

    [self appendLogLine:[NSString stringWithFormat:@"[Verify] Starting command: %@", command]];
    _lastVerifyStartedAt = [NSDate date];
    _lastVerifyCommand = [command copy];

    NSDictionary* status = [_workspaceSession runVerificationCommand:command cwd:runCwd];
    _lastVerifyStatus = status;
    _lastVerifyFinishedAt = [NSDate date];
    _lastVerifyExitCode = status[@"exitCode"];

    if ([status[@"timedOut"] boolValue]) {
        [self appendLogLine:@"[Verify] Error: Command timed out after 60s"];
    }
    NSString* stdoutText = status[@"stdout"];
    if (stdoutText.length > 0) {
        [self appendLogLine:stdoutText];
    }
    NSString* stderrText = status[@"stderr"];
    if (stderrText.length > 0) {
        [self appendLogLine:[NSString stringWithFormat:@"[Stderr] %@", stderrText]];
    }

    return _lastVerifyStatus;
}

- (NSDictionary*)verificationStatus {
    return _lastVerifyStatus ?: @{
        @"command": @"",
        @"state": @"idle",
        @"exitCode": [NSNull null],
        @"passed": @NO
    };
}

- (NSDictionary*)contextSnapshotPayload {
    NSDictionary* git = [self safeGitStatusInfo] ?: @{};
    NSArray* problems = [self safeProblemsList] ?: @[];
    return @{
        @"activeFile": [self safeActiveFilePath] ?: @"",
        @"openFiles": [self safeOpenFilePaths] ?: @[],
        @"dirtyFiles": DirtyFilePathsFromTabs([self safeOpenTabs] ?: @[]),
        @"currentBranch": git[@"branch"] ?: @"",
        @"recentSearches": [self safeSessionLastSearches] ?: @[],
        @"recentCommands": [self safeSessionRecentCommands] ?: @[],
        @"problemCount": @(problems.count),
        @"changes": [self currentChangesInfo]
    };
}

- (NSArray<NSString*>*)verificationFailureLines {
    NSMutableArray* failures = [NSMutableArray array];
    NSString* output = [self safeTerminalOutput] ?: @"";
    NSArray<NSString*>* markers = @[@"error:", @"failed", @"failure", @"FAILED", @"Error:", @"Assertion"];
    [output enumerateLinesUsingBlock:^(NSString* line, BOOL*) {
        for (NSString* marker in markers) {
            if ([line rangeOfString:marker options:NSCaseInsensitiveSearch].location != NSNotFound) {
                [failures addObject:line];
                break;
            }
        }
    }];
    if (failures.count > 100) {
        return [failures subarrayWithRange:NSMakeRange(failures.count - 100, 100)];
    }
    return failures;
}

- (BOOL)path:(NSString*)path isAllowedByScope:(NSDictionary*)scope {
    NSString* ws = [self safeWorkspacePath];
    NSString* absPath = AbsolutePathForRPCPath(path, ws);
    if (!PathIsInsideWorkspace(absPath, ws)) return NO;
    std::error_code ec;
    std::filesystem::path rel = std::filesystem::relative(std::filesystem::path(StdStringFromNSString(absPath)), std::filesystem::path(StdStringFromNSString(ws)), ec);
    if (ec) return NO;
    std::string relPath = rel.string();
    std::string filename = std::filesystem::path(relPath).filename().string();
    NSArray* includes = scope[@"include"] ?: @[];
    NSArray* excludes = scope[@"exclude"] ?: @[];
    if (AnyPatternMatches(excludes, relPath, filename)) return NO;
    if (includes.count > 0 && !AnyPatternMatches(includes, relPath, filename)) return NO;
    return YES;
}

- (BOOL)dirtyBufferExistsAtPath:(NSString*)path {
    NSString* ws = [self safeWorkspacePath];
    NSString* absPath = AbsolutePathForRPCPath(path, ws);
    for (id tab in [self safeOpenTabs] ?: @[]) {
        NSString* tabPath = [tab valueForKey:@"path"];
        BOOL dirty = [[tab valueForKey:@"dirty"] boolValue];
        if (dirty && [tabPath isEqualToString:absPath]) return YES;
    }
    return NO;
}

- (NSDictionary*)repairContextForFailure:(NSString*)failure params:(NSDictionary*)params outErrCode:(NSString**)outErrCode outErrMsg:(NSString**)outErrMsg {
    NSString* ws = [self safeWorkspacePath];
    if (ws.length == 0) {
        if (outErrCode) *outErrCode = @"invalid_request";
        if (outErrMsg) *outErrMsg = @"No open workspace.";
        return nil;
    }

    NSMutableArray* files = [NSMutableArray array];
    NSArray* requestedFiles = params[@"files"] ?: @[];
    if (![requestedFiles isKindOfClass:[NSArray class]]) {
        if (outErrCode) *outErrCode = @"invalid_params";
        if (outErrMsg) *outErrMsg = @"files must be an array.";
        return nil;
    }

    for (NSDictionary* file in requestedFiles) {
        if (![file isKindOfClass:[NSDictionary class]]) {
            if (outErrCode) *outErrCode = @"invalid_params";
            if (outErrMsg) *outErrMsg = @"Every files entry must be an object.";
            return nil;
        }
        NSString* path = file[@"path"];
        if (![path isKindOfClass:[NSString class]]) {
            if (outErrCode) *outErrCode = @"invalid_params";
            if (outErrMsg) *outErrMsg = @"Every files entry requires string path.";
            return nil;
        }
        NSString* absPath = AbsolutePathForRPCPath(path, ws);
        if (absPath.length == 0) {
            if (outErrCode) *outErrCode = @"invalid_params";
            if (outErrMsg) *outErrMsg = @"Every files entry requires path.";
            return nil;
        }
        if (!PathIsInsideWorkspace(absPath, ws)) {
            if (outErrCode) *outErrCode = @"outside_workspace";
            if (outErrMsg) *outErrMsg = @"Repair context file path is outside workspace.";
            return nil;
        }
        NSString* full = [self safeTextForFileAtPath:absPath];
        if (!full) {
            if (outErrCode) *outErrCode = @"invalid_request";
            if (outErrMsg) *outErrMsg = [NSString stringWithFormat:@"Repair context file is not readable: %@", path];
            return nil;
        }
        NSArray<NSString*>* lines = LinesFromText(full);
        NSMutableArray* ranges = [NSMutableArray array];
        NSArray* requestedRanges = file[@"ranges"] ?: @[];
        if (![requestedRanges isKindOfClass:[NSArray class]]) {
            if (outErrCode) *outErrCode = @"invalid_params";
            if (outErrMsg) *outErrMsg = @"ranges must be an array.";
            return nil;
        }
        for (NSDictionary* range in requestedRanges) {
            if (![range isKindOfClass:[NSDictionary class]]) {
                if (outErrCode) *outErrCode = @"invalid_params";
                if (outErrMsg) *outErrMsg = @"Every ranges entry must be an object.";
                return nil;
            }
            if (range[@"startLine"] == nil || range[@"endLine"] == nil) {
                if (outErrCode) *outErrCode = @"invalid_params";
                if (outErrMsg) *outErrMsg = @"Repair context ranges require startLine and endLine.";
                return nil;
            }
            NSInteger start = [range[@"startLine"] integerValue];
            NSInteger end = [range[@"endLine"] integerValue];
            if (start <= 0 || end <= 0) {
                if (outErrCode) *outErrCode = @"invalid_params";
                if (outErrMsg) *outErrMsg = @"Repair context range lines must be positive integers.";
                return nil;
            }
            NSString* text = TextForLineRange(lines, start, end);
            if (!text) {
                if (outErrCode) *outErrCode = @"invalid_range";
                if (outErrMsg) *outErrMsg = @"Repair context range is outside the file.";
                return nil;
            }
            [ranges addObject:@{ @"startLine": @(start), @"endLine": @(end), @"text": text }];
        }
        [files addObject:@{ @"path": path ?: @"", @"ranges": ranges }];
    }
    return @{
        @"failure": failure ?: @"unknown",
        @"files": files,
        @"diagnostics": params[@"diagnostics"] ?: ([self safeProblemsList] ?: @[]),
        @"failures": [self verificationFailureLines]
    };
}

- (NSString*)permissionLevelForMethod:(NSString*)method params:(NSDictionary*)params {
    if ([method isEqualToString:@"approval.list"] || [method isEqualToString:@"approval.get"]) {
        return @"Read";
    }
    if ([method isEqualToString:@"approval.resolve"]) {
        return @"Execute";
    }

    if ([method isEqualToString:@"git.discard"] ||
        [method isEqualToString:@"git.commit"] ||
        [method isEqualToString:@"changes.revertFile"] ||
        [method isEqualToString:@"workspace.openFolder"]) {
        return @"Destructive";
    }
    
    if ([method isEqualToString:@"editor.applyPatch"]) {
        BOOL confirmParam = [params[@"confirm"] boolValue];
        if (confirmParam) {
            return @"Destructive";
        }
    }
    if ([method isEqualToString:@"patch.apply"] || [method isEqualToString:@"patch.applyBatch"]) {
        if ([params[@"confirm"] boolValue]) {
            return @"Destructive";
        }
    }
    if ([method isEqualToString:@"combo.run"]) {
        NSDictionary* combo = params[@"combo"] ?: params;
        NSDictionary* policy = combo[@"policy"] ?: @{};
        for (NSString* perm in policy[@"permissions"] ?: @[]) {
            if (PermissionRank(perm) >= PermissionRank(@"destructive")) return @"Destructive";
        }
        for (NSDictionary* step in combo[@"steps"] ?: @[]) {
            NSString* chip = [self chipNameForStep:step];
            NSDictionary* meta = [self metadataForChip:chip];
            if (PermissionRank(meta[@"permission"] ?: @"read") >= PermissionRank(@"execute")) return @"Execute";
        }
        return @"Edit";
    }
    
    if ([method isEqualToString:@"terminal.run"]) {
        NSString* cwd = params[@"cwd"];
        NSString* ws = [self safeWorkspacePath];
        if (cwd && ws) {
            std::error_code ec;
            NSString* checkedCwd = AbsolutePathForRPCPath(cwd, ws);
            std::filesystem::path cwdPath(StdStringFromNSString(checkedCwd));
            std::filesystem::path wsPath(StdStringFromNSString(ws));
            auto cwdAbs = std::filesystem::weakly_canonical(cwdPath, ec);
            if (ec) return @"Destructive";
            auto wsAbs = std::filesystem::weakly_canonical(wsPath, ec);
            if (ec) return @"Destructive";
            auto rel = std::filesystem::relative(cwdAbs, wsAbs, ec);
            if (ec || rel.string().rfind("..", 0) == 0 || rel.is_absolute()) {
                return @"Destructive";
            }
        }
        return @"Execute";
    }

    if ([method isEqualToString:@"terminal.status"] ||
        [method isEqualToString:@"terminal.jobs"] ||
        [method isEqualToString:@"terminal.history"] ||
        [method isEqualToString:@"terminal.getOutput"]) {
        return @"Read";
    }
    
    if ([method hasPrefix:@"terminal."] ||
        [method isEqualToString:@"verify.run"] ||
        [method isEqualToString:@"task.runLoop"] ||
        [method isEqualToString:@"edit.executePlan"] ||
        [method isEqualToString:@"combo.run"] ||
        [method isEqualToString:@"language.lint"] ||
        [method isEqualToString:@"language.format"]) {
        return @"Execute";
    }
    
    if ([method isEqualToString:@"editor.insertText"] || 
        [method isEqualToString:@"editor.replaceSelection"] || 
        [method isEqualToString:@"editor.replaceRange"] || 
        [method isEqualToString:@"editor.applyPatch"] || 
        [method isEqualToString:@"patch.apply"] ||
        [method isEqualToString:@"patch.applyBatch"] ||
        [method isEqualToString:@"file.write"] ||
        [method isEqualToString:@"file.create"] ||
        [method isEqualToString:@"patch.revertLast"] ||
        [method isEqualToString:@"combo.rollback"] ||
        [method isEqualToString:@"task.step"] ||
        [method isEqualToString:@"git.stage"] || 
        [method isEqualToString:@"git.unstage"] ||
        [method isEqualToString:@"editor.closeFile"] ||
        [method isEqualToString:@"problems.open"] ||
        [method isEqualToString:@"problems.clearSource"] ||
        [method isEqualToString:@"editor.setSelection"] ||
        [method isEqualToString:@"recovery.deleteBackup"] ||
        [method isEqualToString:@"recovery.prune"]) {
        return @"Edit";
    }
    
    return @"Read";
}

- (void)executeMethod:(NSString*)method 
               params:(NSDictionary*)params 
            outResult:(NSDictionary**)outResult 
           outErrCode:(NSString**)outErrCode 
          outErrMsg:(NSString**)outErrMsg
             outPaths:(NSString**)outPaths {

    if ([method hasPrefix:@"memory."] ||
        [method hasPrefix:@"runtime."] ||
        [method isEqualToString:@"workspace.activity"] ||
        [method isEqualToString:@"patch.apply"] ||
        [method isEqualToString:@"patch.applyBatch"] ||
        [method isEqualToString:@"operation.status"] ||
        [method isEqualToString:@"workspace.revision"]) {
        [self ensureMemoryServiceForWorkspace];
    }
    
    NSString* path = params[@"path"];
    if (path &&
        ![method isEqualToString:@"workspace.openFolder"] &&
        ![method hasPrefix:@"shell."] &&
        ![method isEqualToString:@"diff.validatePatch"] &&
        ![method isEqualToString:@"diff.applyPatchPreview"] &&
        ![method isEqualToString:@"patch.validate"] &&
        ![method isEqualToString:@"patch.preview"]) {
        NSString* ws = [self safeWorkspacePath];
        NSString* checkedPath = AbsolutePathForRPCPath(path, ws);
        *outPaths = checkedPath;
        if (ws && !PathIsInsideWorkspace(checkedPath, ws)) {
            *outErrCode = @"outside_workspace";
            *outErrMsg = @"Target path is outside active workspace folder.";
            return;
        }
    }

    if ([method isEqualToString:@"rpc.ping"]) {
        *outResult = @{ @"pong": @YES, @"server": @"DietCodeControlServer", @"version": kDietCodeAppVersion };
        return;
    }

    if ([method isEqualToString:@"rpc.version"]) {
        *outResult = @{
            @"appVersion": kDietCodeAppVersion,
            @"controlProtocolVersion": MacControlContractVersionsDictionary()[@"controlProtocol"],
            @"transactionSchemaVersion": MacControlContractVersionsDictionary()[@"transactionSchema"],
            @"contractVersions": MacControlContractVersionsDictionary(),
            @"supportedRollbackSchemas": @[@"1.6.2"],
            @"supportedInspectOnlySchemas": @[@"1.6.1"]
        };
        return;
    }

    if ([method isEqualToString:@"rpc.methods"]) {
        NSMutableArray* names = [NSMutableArray array];
        for (NSDictionary* desc in [self rpcMethodDescriptions]) {
            [names addObject:desc[@"name"]];
        }
        *outResult = @{ @"methods": names };
        return;
    }

    if ([method isEqualToString:@"rpc.describe"]) {
        NSString* targetMethod = params[@"method"];
        NSArray* methods = nil;
        if (targetMethod.length > 0) {
            NSDictionary* desc = [self descriptionForRPCMethod:targetMethod];
            if (desc.count == 0) {
                *outErrCode = @"method_not_found";
                *outErrMsg = [NSString stringWithFormat:@"The method '%@' is not defined.", targetMethod];
                return;
            }
            methods = @[desc];
        } else {
            methods = [self rpcMethodDescriptions];
        }
        *outResult = @{
            @"methods": methods,
            @"contractVersions": MacControlContractVersionsDictionary(),
        };
        return;
    }

    if ([method isEqualToString:@"chip.list"]) {
        *outResult = @{ @"schemaVersion": @"1.6", @"chips": [self chipRegistry] };
        return;
    }

    if ([method isEqualToString:@"chip.describe"]) {
        NSString* chip = params[@"chip"];
        NSDictionary* meta = [self metadataForChip:chip];
        if (!meta) {
            *outErrCode = @"unknown_chip";
            *outErrMsg = @"Unknown chip.";
            return;
        }
        *outResult = @{ @"schemaVersion": @"1.6", @"chip": meta };
        return;
    }

    if ([method isEqualToString:@"tool.registry"]) {
        *outResult = MacControlToolRegistryPayload();
        return;
    }

    if ([method isEqualToString:@"tool.capabilities"]) {
        *outResult = MacControlToolCapabilitiesSummary();
        return;
    }

    if ([method hasPrefix:@"approval."]) {
        [self executeApprovalMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
        return;
    }

    // Route based on namespace prefixes to respective categories
    if ([method hasPrefix:@"runtime."] || [method isEqualToString:@"workspace.activity"]) {
        [self executeRuntimeMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"memory."]) {
        [self executeMemoryMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"shell."]) {
        [self executeShellMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"workspace."] || [method hasPrefix:@"file."] || [method hasPrefix:@"search."] || [method hasPrefix:@"operation."]) {
        [self executeFileMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"editor."] || [method hasPrefix:@"buffers."] || [method hasPrefix:@"changes."] || [method hasPrefix:@"diff."] || [method hasPrefix:@"patch."]) {
        [self executeEditorMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"git."]) {
        [self executeGitMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else if ([method hasPrefix:@"terminal."] || [method hasPrefix:@"verify."]) {
        [self executeTerminalMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    } else {
        [self executeContextMethod:method params:params outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg outPaths:outPaths];
    }

    if (!*outErrCode && !*outResult) {
        *outErrCode = @"method_not_found";
        *outErrMsg = [NSString stringWithFormat:@"The method '%@' is not defined.", method];
    }
}

- (void)recordMalformedRequestOnConnection:(DietCodeClientConnection*)conn clientFd:(int)clientFd reqId:(NSString*)reqId {
    BOOL shouldClose = NO;
    @synchronized(self) {
        conn.malformedRequestCount++;
        if (conn.malformedRequestCount > kMaxMalformedRequestsPerConnection) {
            shouldClose = YES;
        }
    }
    if (shouldClose) {
        [self sendError:reqId code:@"malformed_request_flood" message:@"Too many malformed requests on this connection." method:@"invalid" phase:@"connection_close" queue:nil durationMs:-1 clientFd:clientFd];
        shutdown(clientFd, SHUT_RDWR);
    }
}

- (NSString*)queueLabelForMethod:(NSString*)method background:(BOOL)background {
    if (!background) return @"com.dietcode.runtime.main";
    return [self isReadQueueMethod:method] ? @"com.dietcode.runtime.read" : @"com.dietcode.runtime.execution";
}

- (void)logRuntimeDiagnostic:(NSString*)requestId
                      method:(NSString*)method
                       phase:(NSString*)phase
                          ok:(BOOL)ok
                  stringCode:(NSString*)stringCode
                       queue:(NSString*)queue
                  durationMs:(long long)durationMs {
    NSMutableDictionary* fields = [NSMutableDictionary dictionary];
    fields[@"request_id"] = requestId.length > 0 ? requestId : @"unknown";
    fields[@"method"] = method.length > 0 ? method : @"unknown";
    fields[@"phase"] = phase.length > 0 ? phase : @"unknown";
    fields[@"ok"] = @(ok);
    if (stringCode.length > 0) fields[@"string_code"] = stringCode;
    if (queue.length > 0) fields[@"queue"] = queue;
    if (durationMs >= 0) fields[@"duration_ms"] = @(durationMs);
    MacControlAppendRuntimeDiagnosticLine(fields);
}

// INVARIANT: C-RPC-04 — success payloads are JSON-sanitized before sendResponse.
- (void)sendSuccess:(NSString*)reqId result:(NSDictionary*)result clientFd:(int)clientFd {
    [self sendSuccess:reqId result:result method:nil phase:@"response_success" queue:nil durationMs:-1 clientFd:clientFd];
}

- (void)sendSuccess:(NSString*)reqId
             result:(NSDictionary*)result
             method:(NSString*)method
              phase:(NSString*)phase
              queue:(NSString*)queue
         durationMs:(long long)durationMs
           clientFd:(int)clientFd {
    NSError* sanitizeError = nil;
    NSDictionary* safeResult = MacControlJsonSanitizedDictionary(result ?: @{}, &sanitizeError);
    if (!safeResult) {
        [self sendError:reqId
                   code:@"response_serialization_failed"
                message:sanitizeError.localizedDescription ?: @"Result payload is not JSON-serializable."
                 method:method
                  phase:@"serialization_fallback"
                  queue:queue
             durationMs:durationMs
               clientFd:clientFd];
        return;
    }
    NSDictionary* resp = @{
        @"id": reqId,
        @"ok": @YES,
        @"result": safeResult
    };
    [self logRuntimeDiagnostic:reqId method:method ?: @"unknown" phase:phase ?: @"response_success" ok:YES stringCode:nil queue:queue durationMs:durationMs];
    [self sendResponse:resp clientFd:clientFd];
}

- (void)sendError:(NSString*)reqId code:(id)code message:(NSString*)message clientFd:(int)clientFd {
    [self sendError:reqId code:code message:message method:nil phase:@"response_error" queue:nil durationMs:-1 clientFd:clientFd];
}

- (void)sendError:(NSString*)reqId
             code:(id)code
          message:(NSString*)message
           method:(NSString*)method
            phase:(NSString*)phase
            queue:(NSString*)queue
       durationMs:(long long)durationMs
         clientFd:(int)clientFd {
    NSNumber* numericCode = @(-32603);
    NSString* stringCode = @"internal_error";
    if ([code isKindOfClass:[NSNumber class]]) {
        numericCode = code;
        if ([code integerValue] == -32601) stringCode = @"method_not_found";
        else if ([code integerValue] == -32600) stringCode = @"invalid_request";
    } else if ([code isKindOfClass:[NSString class]]) {
        stringCode = code;
        if ([stringCode isEqualToString:@"invalid_request"]) numericCode = @(-32600);
        else if ([stringCode isEqualToString:@"method_not_found"]) numericCode = @(-32601);
        else if ([stringCode isEqualToString:@"invalid_params"] || [stringCode isEqualToString:@"invalid_range"]) numericCode = @(-32602);
        else if ([stringCode isEqualToString:@"request_too_large"] || [stringCode isEqualToString:@"response_too_large"] || [stringCode isEqualToString:@"too_many_results"] || [stringCode isEqualToString:@"file_too_large"]) numericCode = @(413);
        else if ([stringCode isEqualToString:@"not_found"]) numericCode = @(404);
        else if ([stringCode isEqualToString:@"already_exists"]) numericCode = @(409);
        else if ([stringCode isEqualToString:@"outside_workspace"] || [stringCode isEqualToString:@"outside_scope"]) numericCode = @(4001);
        else if ([stringCode isEqualToString:@"lock_conflict"] || [stringCode isEqualToString:@"dirty_buffer_conflict"]) numericCode = @(4002);
        else if ([stringCode isEqualToString:@"budget_exceeded"]) numericCode = @(4003);
        else if ([stringCode isEqualToString:@"semantic_disabled"] || [stringCode isEqualToString:@"ranked_search_disabled"]) numericCode = @(4008);
        else if ([stringCode isEqualToString:@"verification_failed"] || [stringCode isEqualToString:@"verify_failed"] || [stringCode isEqualToString:@"patch_failed"] || [stringCode isEqualToString:@"stale_content"] || [stringCode isEqualToString:@"symlink_target"] || [stringCode isEqualToString:@"coherence_mismatch"]) numericCode = @(4004);
        else if ([stringCode isEqualToString:@"rollback_conflict"] || [stringCode isEqualToString:@"rollback_failed"]) numericCode = @(4005);
        else if ([stringCode isEqualToString:@"permission_denied"]) numericCode = @(4006);
        else if ([stringCode isEqualToString:@"task_not_active"]) numericCode = @(4007);
        else if ([stringCode isEqualToString:@"approval_invalid"] || [stringCode isEqualToString:@"approval_resolve_failed"]) numericCode = @(4010);
        else if ([stringCode isEqualToString:@"response_serialization_failed"]) numericCode = @(-32603);
        else if ([stringCode isEqualToString:@"connection_limit_exceeded"] ||
                 [stringCode isEqualToString:@"too_many_pending"] ||
                 [stringCode isEqualToString:@"malformed_request_flood"] ||
                 [stringCode isEqualToString:@"nested_call_timeout"]) numericCode = @(429);
    }
    
    NSString* resolvedReqId = reqId.length > 0 ? reqId : @"unknown";
    NSDictionary* meta = MacControlRpcErrorDiagnosticMetadata(stringCode);
    NSMutableDictionary* error = [NSMutableDictionary dictionaryWithDictionary:@{
        @"code": numericCode,
        @"string_code": stringCode,
        @"message": message ?: @"",
        @"request_id": resolvedReqId,
        @"category": meta[@"category"] ?: @"domain",
        @"retryable": meta[@"retryable"] ?: @NO,
        @"recovery_hint": meta[@"recovery_hint"] ?: @"rg string_code docs/error-codes.md",
        @"nextRecommendedCommand": meta[@"nextRecommendedCommand"] ?: @"tool.registry",
    }];
    if (phase.length > 0) error[@"phase"] = phase;
    if (queue.length > 0) error[@"queue"] = queue;

    if ([stringCode isEqualToString:@"coherence_mismatch"]) {
        NSDictionary* detail = _workspaceState.lastCoherenceMismatchDetail;
        if (detail.count > 0) {
            error[@"coherence"] = detail;
            if (detail[@"reason"]) error[@"reason"] = detail[@"reason"];
            if (detail[@"changedPaths"]) error[@"changedPaths"] = detail[@"changedPaths"];
            if (detail[@"currentWorkspaceRevision"]) error[@"currentWorkspaceRevision"] = detail[@"currentWorkspaceRevision"];
            if (detail[@"requiredAction"]) error[@"requiredAction"] = detail[@"requiredAction"];
        }
    }

    NSDictionary* resp = @{
        @"id": resolvedReqId,
        @"ok": @NO,
        @"error": error
    };
    [self logRuntimeDiagnostic:resolvedReqId method:method ?: @"unknown" phase:phase ?: @"response_error" ok:NO stringCode:stringCode queue:queue durationMs:durationMs];
    [self sendResponse:resp clientFd:clientFd];
}

// INVARIANT: C-RPC-01 — every response path writes exactly one newline-terminated JSON line.
- (void)sendResponse:(NSDictionary*)responseObj clientFd:(int)clientFd {
    NSError* err = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:responseObj options:0 error:&err];
    NSString* responseId = RequestIdString(responseObj[@"id"]);
    if (err || !data) {
        NSDictionary* meta = MacControlRpcErrorDiagnosticMetadata(@"response_serialization_failed");
        NSDictionary* failResp = @{
            @"id": responseId,
            @"ok": @NO,
            @"error": @{
                @"code": @(-32603),
                @"string_code": @"response_serialization_failed",
                @"message": err.localizedDescription ?: @"Failed to serialize RPC response.",
                @"request_id": responseId,
                @"phase": @"serialization_fallback",
                @"category": meta[@"category"] ?: @"serialization",
                @"retryable": meta[@"retryable"] ?: @NO,
                @"recovery_hint": meta[@"recovery_hint"] ?: @"reduce_response_payload",
            }
        };
        [self logRuntimeDiagnostic:responseId method:@"unknown" phase:@"serialization_fallback" ok:NO stringCode:@"response_serialization_failed" queue:nil durationMs:-1];
        NSData* failData = [NSJSONSerialization dataWithJSONObject:failResp options:0 error:nil];
        if (failData) {
            NSMutableData* lineData = [failData mutableCopy];
            [lineData appendBytes:"\n" length:1];
            @synchronized(self) {
                write(clientFd, lineData.bytes, lineData.length);
            }
        }
        return;
    }
    if (data.length > kMaxResponseBytes && [responseObj[@"ok"] boolValue]) {
        NSDictionary* meta = MacControlRpcErrorDiagnosticMetadata(@"response_too_large");
        NSDictionary* limitResp = @{
            @"id": responseId,
            @"ok": @NO,
            @"error": @{
                @"code": @(413),
                @"string_code": @"response_too_large",
                @"message": @"Response exceeds maximum allowed size.",
                @"request_id": responseId,
                @"phase": @"serialization_fallback",
                @"category": meta[@"category"] ?: @"serialization",
                @"retryable": meta[@"retryable"] ?: @NO,
                @"recovery_hint": meta[@"recovery_hint"] ?: @"reduce_response_payload",
            }
        };
        [self logRuntimeDiagnostic:responseId method:@"unknown" phase:@"serialization_fallback" ok:NO stringCode:@"response_too_large" queue:nil durationMs:-1];
        data = [NSJSONSerialization dataWithJSONObject:limitResp options:0 error:&err];
        if (err || !data) {
            const char* fallback = "{\"id\":\"unknown\",\"ok\":false,\"error\":{\"code\":413,\"string_code\":\"response_too_large\",\"message\":\"Response exceeds maximum allowed size.\",\"request_id\":\"unknown\",\"phase\":\"serialization_fallback\",\"category\":\"serialization\",\"retryable\":false,\"recovery_hint\":\"reduce_response_payload\"}}\n";
            @synchronized(self) {
                write(clientFd, fallback, strlen(fallback));
            }
            return;
        }
    }
    
    NSMutableData* lineData = [data mutableCopy];
    [lineData appendBytes:"\n" length:1];
    
    @synchronized(self) {
        write(clientFd, lineData.bytes, lineData.length);
    }
}

- (void)appendLogLine:(NSString*)line {
    if (_windowController) {
        if ([NSThread isMainThread]) {
            [_windowController appendControlLogLine:line];
            return;
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            [_windowController appendControlLogLine:line];
        });
        return;
    }
    if (line.length > 0) {
        NSLog(@"%@", line);
        [self notifyStructuredEvent:@"kernel.log" detail:line payload:nil];
    }
}

- (void)logAuditMethod:(NSString*)method 
                caller:(NSString*)caller 
            permission:(NSString*)permission 
              duration:(long long)duration 
                result:(NSString*)result 
                  paths:(NSString*)paths {
    @synchronized (self) {
        NSString* homeDir = NSHomeDirectory();
        NSString* dietcodeDir = [homeDir stringByAppendingPathComponent:@".dietcode"];
        NSString* logPath = [dietcodeDir stringByAppendingPathComponent:@"control_audit.log"];
        
        NSString* logPath3 = [dietcodeDir stringByAppendingPathComponent:@"control_audit.log.3"];
        NSString* logPath2 = [dietcodeDir stringByAppendingPathComponent:@"control_audit.log.2"];
        NSString* logPath1 = [dietcodeDir stringByAppendingPathComponent:@"control_audit.log.1"];
        
        NSArray* pathsToCheck = @[logPath, logPath1, logPath2, logPath3];
        for (NSString* p in pathsToCheck) {
            struct stat st;
            if (lstat([p UTF8String], &st) == 0) {
                if (S_ISLNK(st.st_mode) || st.st_uid != getuid()) {
                    unlink([p UTF8String]);
                }
            }
        }
        
        NSFileManager* fm = [NSFileManager defaultManager];
        NSError* attrErr = nil;
        NSDictionary* attrs = [fm attributesOfItemAtPath:logPath error:&attrErr];
        if (attrs) {
            unsigned long long size = [attrs fileSize];
            if (size >= kMaxAuditLogBytes) {
                if ([fm fileExistsAtPath:logPath3]) {
                    [fm removeItemAtPath:logPath3 error:nil];
                }
                if ([fm fileExistsAtPath:logPath2]) {
                    [fm moveItemAtPath:logPath2 toPath:logPath3 error:nil];
                }
                if ([fm fileExistsAtPath:logPath1]) {
                    [fm moveItemAtPath:logPath1 toPath:logPath2 error:nil];
                }
                if ([fm fileExistsAtPath:logPath]) {
                    [fm moveItemAtPath:logPath toPath:logPath1 error:nil];
                }
            }
        }
        
        NSDateFormatter* formatter = [[NSDateFormatter alloc] init];
        [formatter setDateFormat:@"yyyy-MM-dd HH:mm:ss"];
        NSString* timestamp = [formatter stringFromDate:[NSDate date]];
        
        NSString* logLine = [NSString stringWithFormat:@"[%@] caller: %@ | method: %@ | permission: %@ | duration: %lldms | result: %@ | paths: %@\n",
                             timestamp, caller, method, permission, duration, result, paths ?: @""];
        
        if (logLine.length > 8192) {
            logLine = [[logLine substringToIndex:8191] stringByAppendingString:@"\n"];
        }
        
        std::ofstream out([logPath UTF8String], std::ios::app);
        if (out.is_open()) {
            out << [logLine UTF8String];
            out.close();
        }
    }
}

- (void)notifyEvent:(NSString*)type detail:(NSString*)detail {
    [self notifyStructuredEvent:type detail:detail payload:nil];
}

- (void)notifyStructuredEvent:(NSString*)type detail:(NSString*)detail payload:(NSDictionary*)payload {
    NSString* eventType = type ?: @"unknown";
    NSString* eventDetail = detail ?: @"";
    NSDateFormatter* iso = [[NSDateFormatter alloc] init];
    iso.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    iso.dateFormat = @"yyyy-MM-dd'T'HH:mm:ss.SSSZ";
    NSString* timestamp = [iso stringFromDate:[NSDate date]];

    NSDictionary* structuredEvent = nil;
    @synchronized(self) {
        _eventSequence += 1;
        NSMutableDictionary* eventRecord = [@{
            @"id": [NSString stringWithFormat:@"evt-%lld", (long long)_eventSequence],
            @"sequence": @(_eventSequence),
            @"timestamp": timestamp,
            @"type": eventType,
            @"source": @"kernel",
            @"detail": eventDetail,
        } mutableCopy];
        if ([payload isKindOfClass:[NSDictionary class]] && payload.count > 0) {
            eventRecord[@"payload"] = payload;
        }
        structuredEvent = [eventRecord copy];
        [_eventRingBuffer addObject:structuredEvent];
        static const NSInteger kMaxEventRingSize = 500;
        while ((NSInteger)_eventRingBuffer.count > kMaxEventRingSize) {
            [_eventRingBuffer removeObjectAtIndex:0];
        }
    }

    NSDictionary* notification = @{
        @"method": @"event.emitted",
        @"params": structuredEvent,
    };
    NSData* data = [NSJSONSerialization dataWithJSONObject:notification options:0 error:nil];
    if (!data) return;

    NSMutableData* frame = [data mutableCopy];
    [frame appendBytes:"\n" length:1];

    @synchronized(self) {
        NSMutableArray* deadConns = [NSMutableArray array];
        for (DietCodeClientConnection* conn in [_activeConnections allValues]) {
            if ([conn.subscriptions containsObject:eventType] || [conn.subscriptions containsObject:@"*"]) {
                ssize_t written = write(conn.fd, frame.bytes, frame.length);
                if (written < 0) {
                    if (errno == EPIPE || errno == EBADF) {
                        [deadConns addObject:@(conn.fd)];
                    }
                }
            }
        }
        for (NSNumber* fdNum in deadConns) {
            DietCodeClientConnection* conn = _activeConnections[fdNum];
            if (conn) {
                close(conn.fd);
                [_activeConnections removeObjectForKey:fdNum];
            }
        }
    }
}

@end
