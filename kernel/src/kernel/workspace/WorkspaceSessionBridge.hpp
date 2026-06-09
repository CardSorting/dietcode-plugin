#pragma once

#import <Foundation/Foundation.h>

namespace dietcode::kernel::workspace {
class WorkspaceSession;
}

@interface DietCodeWorkspaceSession : NSObject

@property(nonatomic, assign, readonly) BOOL hasWorkspace;
@property(nonatomic, copy, readonly) NSString* workspacePath;

- (instancetype)initWithSession:(dietcode::kernel::workspace::WorkspaceSession*)session;
- (dietcode::kernel::workspace::WorkspaceSession*)cppSession;

- (void)setWorkspaceRoot:(NSString*)path;
- (NSString*)readTextAtPath:(NSString*)path readSource:(NSString**)readSourceOut error:(NSString**)errorOut;
- (BOOL)writeTextAtPath:(NSString*)path content:(NSString*)content error:(NSString**)errorOut;
- (BOOL)applyPatchAtPath:(NSString*)path patchString:(NSString*)patchString error:(NSString**)errorOut;
- (NSDictionary*)runVerificationCommand:(NSString*)command cwd:(NSString*)cwd;
- (NSDictionary*)verificationStatus;
- (NSDictionary*)gitStatusDictionary;
- (NSString*)gitDiffForFile:(NSString*)path staged:(BOOL)staged;

- (void)setAgentAutonomyLevel:(NSInteger)level;
- (NSInteger)agentAutonomyLevel;
- (NSArray<NSString*>*)recentCommands;
- (NSArray<NSString*>*)recentSearches;
- (void)appendRecentCommand:(NSString*)command;
- (void)appendRecentSearch:(NSString*)query;
- (void)clearSessionHistory;

@end
