#pragma once

#import <Cocoa/Cocoa.h>

@class DietCodeKernelRuntime;

@interface DietCodeKernelAppDelegate : NSObject <NSApplicationDelegate>

@property(nonatomic, strong) DietCodeKernelRuntime* runtime;

@end
