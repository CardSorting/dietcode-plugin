#pragma once

#import <Cocoa/Cocoa.h>

@class DietCodeWindowController;
@class DietCodeWorkspaceSession;

@interface DietCodeControlWindowBridge : NSObject

- (instancetype)initWithWorkspaceSession:(DietCodeWorkspaceSession*)session
                        windowController:(DietCodeWindowController*)controller;
@property(nonatomic, strong, readonly) DietCodeWorkspaceSession* workspaceSession;
- (NSString*)workspacePath;
- (NSString*)textForFileAtPath:(NSString*)path;
- (BOOL)replaceTextInRange:(NSRange)range withText:(NSString*)text forFileAtPath:(NSString*)path;
- (NSArray<NSString*>*)openFilePaths;
- (NSArray<NSDictionary*>*)problemsList;
- (NSString*)activeFilePath;
- (NSArray*)openTabs;
- (NSDictionary*)gitStatusInfo;
- (NSString*)gitDiffForFile:(NSString*)path;
- (BOOL)applyPatchAtPath:(NSString*)path patchString:(NSString*)patchString errorOut:(NSString**)errorOut;
- (NSDictionary*)activeSelectionInfo;
- (NSString*)terminalOutput;
- (NSArray*)sessionRecentCommands;
- (NSArray*)sessionLastSearches;
- (pid_t)terminalPid;
- (NSArray*)languageDiagnosticsForPath:(NSString*)path;
- (NSInteger)agentAutonomyLevel;

// LSP & Advanced Language Methods
- (NSString*)hoverAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column;
- (NSArray*)completionsAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column;
- (NSDictionary*)definitionAtLocation:(NSString*)path line:(NSInteger)line column:(NSInteger)column;
- (NSArray*)lspSymbolsForFile:(NSString*)path;

@end
