#import "MacControlWindowBridge.hpp"
#import "WorkspaceSessionBridge.hpp"

@implementation DietCodeControlWindowBridge {
    DietCodeWorkspaceSession* _workspaceSession;
}

- (instancetype)initWithWorkspaceSession:(DietCodeWorkspaceSession*)session
                        windowController:(DietCodeWindowController*)controller {
    (void)controller;
    self = [super init];
    if (self) {
        _workspaceSession = session;
    }
    return self;
}

- (DietCodeWorkspaceSession*)workspaceSession {
    return _workspaceSession;
}

- (NSString*)workspacePath {
    return [_workspaceSession workspacePath];
}

- (NSString*)textForFileAtPath:(NSString*)path {
    NSString* readSource = nil;
    NSString* error = nil;
    return [_workspaceSession readTextAtPath:path readSource:&readSource error:&error];
}

- (BOOL)replaceTextInRange:(NSRange)range withText:(NSString*)text forFileAtPath:(NSString*)path {
    NSString* readSource = nil;
    NSString* error = nil;
    NSString* current = [_workspaceSession readTextAtPath:path readSource:&readSource error:&error];
    if (!current) return NO;
    if (range.location + range.length > current.length) return NO;
    NSMutableString* updated = [current mutableCopy];
    [updated replaceCharactersInRange:range withString:text ?: @""];
    return [_workspaceSession writeTextAtPath:path content:updated error:&error];
}

- (NSArray<NSString*>*)openFilePaths {
    return @[];
}

- (NSArray<NSDictionary*>*)problemsList {
    return @[];
}

- (NSString*)activeFilePath {
    return @"";
}

- (NSArray*)openTabs {
    return @[];
}

- (NSDictionary*)gitStatusInfo {
    return [_workspaceSession gitStatusDictionary];
}

- (NSString*)gitDiffForFile:(NSString*)path {
    return [_workspaceSession gitDiffForFile:path staged:NO];
}

- (BOOL)applyPatchAtPath:(NSString*)path patchString:(NSString*)patchString errorOut:(NSString**)errorOut {
    return [_workspaceSession applyPatchAtPath:path patchString:patchString error:errorOut];
}

- (NSDictionary*)activeSelectionInfo {
    return @{};
}

- (NSString*)terminalOutput {
    return @"";
}

- (NSArray*)sessionRecentCommands {
    return [_workspaceSession recentCommands];
}

- (NSArray*)sessionLastSearches {
    return [_workspaceSession recentSearches];
}

- (pid_t)terminalPid {
    return 0;
}

- (NSArray*)languageDiagnosticsForPath:(NSString*)path {
    (void)path;
    return @[];
}

- (NSInteger)agentAutonomyLevel {
    return [_workspaceSession agentAutonomyLevel];
}

- (NSString*)hoverAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column {
    (void)path; (void)line; (void)column;
    return nil;
}

- (NSArray*)completionsAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column {
    (void)path; (void)line; (void)column;
    return nil;
}

- (NSDictionary*)definitionAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column {
    (void)path; (void)line; (void)column;
    return nil;
}

- (NSArray*)lspSymbolsForFile:(NSString*)path {
    (void)path;
    return nil;
}

@end
