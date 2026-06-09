#pragma once

#import <Cocoa/Cocoa.h>

@interface DietCodeBufferStateService : NSObject

// Get snapshot of open buffer states, selections, dirty flags, and unsaved diffs
+ (NSArray<NSDictionary*>*)snapshotForTabs:(NSArray*)tabs;

// Calculate unsaved diff for a specific open tab
+ (NSString*)unsavedDiffForTab:(id)tab;

@end
