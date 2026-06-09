#import "MacControlServer+Private.hpp"
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#else
#import "DietCodeWindowController+ControlHost.h"
#endif
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"
#import "SubprocessRunner.hpp"

#include <vector>
#include <string>

@implementation DietCodeControlServer (Terminal)

- (void)executeTerminalMethod:(NSString*)method 
                       params:(NSDictionary*)params 
                    outResult:(NSDictionary**)outResult 
                   outErrCode:(NSString**)outErrCode 
                  outErrMsg:(NSString**)outErrMsg
                     outPaths:(NSString**)outPaths {
    
    // Terminal commands
    if ([method isEqualToString:@"terminal.status"]) {
        pid_t pid = [self safeTerminalPid];
        *outResult = @{
            @"pid": @(pid),
            @"running": @(pid > 0),
            @"outputLength": @(([self safeTerminalOutput] ?: @"").length)
        };
        return;
    }

    if ([method isEqualToString:@"terminal.jobs"]) {
        pid_t pid = [self safeTerminalPid];
        // Mirroring exact logic from MacControlServer.mm
        NSArray* jobs = pid > 0 ? @[@{ @"id": @"terminal", @"pid": @(pid), @"status": @"running" }] : @[];
        *outResult = @{ @"jobs": jobs };
        return;
    }

    if ([method isEqualToString:@"terminal.history"]) {
        *outResult = @{ @"commands": [self safeSessionRecentCommands] ?: @[] };
        return;
    }

    if ([method isEqualToString:@"terminal.run"]) {
        NSString* command = params[@"command"];
        if (![command isKindOfClass:[NSString class]] || command.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"command string required and must be non-empty.";
            return;
        }
        NSString* ws = [self safeWorkspacePath];
        id cwdParam = params[@"cwd"];
        if (cwdParam != nil && ![cwdParam isKindOfClass:[NSString class]]) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"cwd must be a string when provided.";
            return;
        }
        NSString* cwd = cwdParam;
        if (cwd.length > 0 && ws.length > 0) {
            cwd = AbsolutePathForRPCPath(cwd, ws);
        }
        BOOL show = params[@"show"] ? [params[@"show"] boolValue] : YES;
        
        NSString* errStr = nil;
        if (self.isKernelMode || !self.windowController) {
            *outErrCode = @"ui_unavailable";
            *outErrMsg = @"Interactive terminal is unavailable in kernel mode. Use shell.run.";
            return;
        }
        BOOL ok = [(id)self.windowController runTerminalCommand:command cwd:cwd show:show errorOut:&errStr];
        if (!ok) {
            *outErrCode = @"terminal_failed";
            *outErrMsg = errStr ?: @"Failed to start terminal command.";
            return;
        }
        *outResult = @{ @"run": @YES, @"pid": @([self safeTerminalPid]) };
        return;
    }
    
    if ([method isEqualToString:@"terminal.stop"]) {
        if (!self.isKernelMode && self.windowController) {
            [(id)self.windowController stopTerminalCommand];
        }
        *outResult = @{ @"stopped": @YES };
        return;
    }
    
    if ([method isEqualToString:@"terminal.getOutput"]) {
        NSString* output = [self safeTerminalOutput] ?: @"";
        *outResult = @{ @"output": output };
        return;
    }
    
    if ([method isEqualToString:@"terminal.clear"]) {
        if (!self.isKernelMode && self.windowController) {
            [(id)self.windowController clearTerminalOutput];
        }
        *outResult = @{ @"cleared": @YES };
        return;
    }

    // Verification commands
    if ([method isEqualToString:@"verify.run"]) {
        NSString* command = params[@"command"] ?: @"";
        if (![command isKindOfClass:[NSString class]] || command.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"command string required and must be non-empty.";
            return;
        }
        NSArray<NSString*>* allowed = VerifyCommandsAllowlist();
        if (!VerifyCommandIsAllowed(command, allowed)) {
            *outErrCode = @"invalid_params";
            *outErrMsg = [NSString stringWithFormat:@"verify.run command must match one of the AgentVerifyCommands prefixes: %@.", [allowed componentsJoinedByString:@", "]];
            return;
        }
        NSString* ws = [self safeWorkspacePath];
        if (ws.length == 0) {
            *outErrCode = @"invalid_request";
            *outErrMsg = @"No open workspace.";
            return;
        }
        id cwdParam = params[@"cwd"];
        if (cwdParam != nil && ![cwdParam isKindOfClass:[NSString class]]) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"cwd must be a string when provided.";
            return;
        }
        NSString* cwd = AbsolutePathForRPCPath(cwdParam ?: ws, ws);
        if (cwd.length > 0 && !PathIsInsideWorkspace(cwd, ws)) {
            *outErrCode = @"outside_workspace";
            *outErrMsg = @"verify.run cwd must be inside workspace.";
            return;
        }
        NSString* taskId = params[@"taskId"];
        if (![taskId isKindOfClass:[NSString class]]) taskId = @"";
        NSDictionary* result = [self runVerificationCommand:command cwd:cwd];
        if ([result[@"passed"] boolValue]) {
            [_workspaceState bumpVerifyRevision];
        }
        [self notifyVerifyResult:result taskId:taskId];
        *outResult = result;
        return;
    }

    if ([method isEqualToString:@"verify.last"] || [method isEqualToString:@"verify.status"]) {
        NSDictionary* status = [self verificationStatus];
        if ([method isEqualToString:@"verify.last"]) {
            *outResult = @{
                @"command": status[@"command"] ?: @"",
                @"exitCode": status[@"exitCode"] ?: [NSNull null],
                @"startedAt": status[@"startedAt"] ?: @"",
                @"finishedAt": status[@"finishedAt"] ?: @"",
                @"durationMs": status[@"durationMs"] ?: @0,
                @"status": status
            };
        } else {
            *outResult = @{ @"command": _lastVerifyCommand ?: @"", @"status": status };
        }
        return;
    }

    if ([method isEqualToString:@"verify.failures"]) {
        *outResult = @{
            @"failures": [self verificationFailureLines],
            @"problems": [self safeProblemsList] ?: @[],
            @"status": [self verificationStatus]
        };
        return;
    }
}

@end
