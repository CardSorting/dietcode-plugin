#include "KernelAppDelegate.hpp"
#include "KernelRuntime.hpp"

#import <Cocoa/Cocoa.h>

@implementation DietCodeKernelAppDelegate

- (instancetype)init {
    self = [super init];
    if (self) {
        self.runtime = [[DietCodeKernelRuntime alloc] init];
    }
    return self;
}

- (void)applicationDidFinishLaunching:(NSNotification*)notification {
    (void)notification;
    [self.runtime start];
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication*)sender {
    (void)sender;
    [self.runtime stop];
    return NSTerminateNow;
}

@end
