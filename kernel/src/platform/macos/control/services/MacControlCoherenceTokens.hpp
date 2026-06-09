#pragma once

#import <Foundation/Foundation.h>

@class DietCodeControlWindowBridge;

static const NSInteger kCoherenceMaxTasks = 40;
static const NSInteger kCoherenceMaxAnchorsPerTask = 100;
static const NSTimeInterval kCoherenceTokenTTLSeconds = 30.0 * 60.0;

// INVARIANT: Task-scoped coherence tokens — compact proof of observed workspace state before mutation.
@interface MacControlCoherenceRegistry : NSObject

/** Issue or refresh a token after a read/status call. Returns response `coherence` payload (may be nil without taskId). */
- (NSDictionary*)issueForTask:(NSString*)taskId
                          paths:(NSArray<NSString*>*)paths
              workspaceRevision:(NSInteger)workspaceRevision
                 verifyRevision:(NSInteger)verifyRevision
                      workspace:(NSString*)workspacePath
                   windowBridge:(DietCodeControlWindowBridge*)windowBridge;

/** Latest coherence payload for a task (e.g. workspace.status without new paths). */
- (NSDictionary*)payloadForTask:(NSString*)taskId
              workspaceRevision:(NSInteger)workspaceRevision
                 verifyRevision:(NSInteger)verifyRevision;

/**
 * Validate mutation params when taskId is set.
 * Returns NO and fills outDetail when stale. Clears outDetail on success.
 */
- (BOOL)validateMutationParams:(NSDictionary*)params
             workspaceRevision:(NSInteger)workspaceRevision
                verifyRevision:(NSInteger)verifyRevision
                     workspace:(NSString*)workspacePath
                  windowBridge:(DietCodeControlWindowBridge*)windowBridge
                      outDetail:(NSDictionary**)outDetail
                      outMessage:(NSString**)outMessage;

@end

/** Format anchor hash for wire (`fnv1a:<hex>`). */
NSString* MacControlCoherenceAnchorHash(NSString* rawHash);

/** Strip algorithm prefix for comparison. */
NSString* MacControlCoherenceRawHash(NSString* anchoredHash);
