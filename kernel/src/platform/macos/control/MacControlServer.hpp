#pragma once

#import <Cocoa/Cocoa.h>

#ifdef DIETCODE_KERNEL_BUILD
#import "DietCodeWindowController+ControlHost.h"
#else
@class DietCodeWindowController;
#endif
@class DietCodeWorkspaceSession;

@interface DietCodeControlServer : NSObject

@property (nonatomic, assign, readonly) BOOL isRunning;
@property (nonatomic, assign, readonly) BOOL isKernelMode;
@property (nonatomic, weak, readonly) DietCodeWindowController* windowController;
@property (nonatomic, strong, readonly) DietCodeWorkspaceSession* workspaceSession;

- (instancetype)initWithWorkspaceSession:(DietCodeWorkspaceSession*)session;
#if !defined(DIETCODE_KERNEL_BUILD)
- (instancetype)initWithWindowController:(DietCodeWindowController*)controller;
#endif
- (void)start;
- (void)stop;
- (void)appendLogLine:(NSString*)line;
- (void)notifyEvent:(NSString*)type detail:(NSString*)detail;
- (void)notifyStructuredEvent:(NSString*)type detail:(NSString*)detail payload:(NSDictionary*)payload;

@end
