#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlServer;
@class DietCodeWorkspaceSession;

@interface DietCodeKernelRuntime : NSObject

@property(nonatomic, strong, readonly) DietCodeWorkspaceSession* workspaceSession;
@property(nonatomic, strong, readonly) DietCodeControlServer* controlServer;

- (void)openWorkspace:(NSString*)path;
- (void)start;
- (void)stop;

@end
