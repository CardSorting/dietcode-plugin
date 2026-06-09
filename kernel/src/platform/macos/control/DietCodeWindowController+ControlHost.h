#pragma once

#import <Cocoa/Cocoa.h>

// Minimal control-host declaration for dietcode-kernel RPC glue.
// The full editor implementation was removed with legacy_ui; this header
// satisfies type references in the headless kernel build.
@interface DietCodeWindowController : NSWindowController

- (void)setControlActiveCommand:(NSString*)command caller:(NSString*)caller;
- (void)appendControlLogLine:(NSString*)line;
- (void)openWorkspaceFolder:(NSString*)path;
- (void)openFileAtPath:(NSString*)path line:(NSInteger)line column:(NSInteger)column;
- (NSString*)textForFileAtPath:(NSString*)path;
- (BOOL)writeFileAtPath:(NSString*)path content:(NSString*)content errorOut:(NSString**)errorOut;
- (void)showBottomPanelTab:(NSString*)tabName;

- (BOOL)setActiveSelectionStart:(NSInteger)start end:(NSInteger)end;
- (BOOL)insertTextAtActiveCursor:(NSString*)text;
- (BOOL)replaceActiveSelectionWithText:(NSString*)text;
- (void)saveFileAtPath:(NSString*)path;
- (void)closeFileAtPath:(NSString*)path;

- (BOOL)gitStageFile:(NSString*)path errorOut:(NSString**)errorOut;
- (BOOL)gitUnstageFile:(NSString*)path errorOut:(NSString**)errorOut;
- (BOOL)gitDiscardFile:(NSString*)path errorOut:(NSString**)errorOut;
- (BOOL)gitCommitWithMessage:(NSString*)message errorOut:(NSString**)errorOut;

- (BOOL)runTerminalCommand:(NSString*)command cwd:(NSString*)cwd show:(BOOL)show errorOut:(NSString**)errorOut;
- (void)stopTerminalCommand;
- (void)clearTerminalOutput;

- (void)problemsOpen:(NSString*)problemId;
- (void)problemsClearSource:(NSString*)source;
- (void)formatFileAtPath:(NSString*)path;
- (void)lintFileAtPath:(NSString*)path;

@property(nonatomic, assign) BOOL isHeadless;

@end
