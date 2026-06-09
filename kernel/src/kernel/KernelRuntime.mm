#import "KernelRuntime.hpp"
#import "MacControlServer.hpp"
#import "WorkspaceSessionBridge.hpp"

@implementation DietCodeKernelRuntime

- (instancetype)init {
    self = [super init];
    if (self) {
        _workspaceSession = [[DietCodeWorkspaceSession alloc] init];
        [_workspaceSession setAgentAutonomyLevel:3];
        _controlServer = [[DietCodeControlServer alloc] initWithWorkspaceSession:_workspaceSession];
    }
    return self;
}

- (void)openWorkspace:(NSString*)path {
    [_workspaceSession setWorkspaceRoot:path];
}

- (void)start {
    [_controlServer start];
}

- (void)stop {
    [_controlServer stop];
}

@end
