#pragma once

#import <Foundation/Foundation.h>

@class MacControlWorkspaceState;

// SHELL: Pass IX — agent-safe shell wrappers (read-only, workspace-bound, explicit cwd).
@interface MacControlShellService : NSObject

- (instancetype)initWithWorkspaceState:(MacControlWorkspaceState*)workspaceState;

- (void)executeMethod:(NSString*)method
               params:(NSDictionary*)params
            workspace:(NSString*)workspacePath
            outResult:(NSDictionary**)outResult
           outErrCode:(NSString**)outErrCode
            outErrMsg:(NSString**)outErrMsg;

@end
