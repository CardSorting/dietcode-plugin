#import "MacControlServer+Private.hpp"
#ifndef DIETCODE_KERNEL_BUILD
#import "MacWindow.hpp"
#else
#import "DietCodeWindowController+ControlHost.h"
#endif
#include "filesystem/GitService.hpp"
#import "MacControlSupport.hpp"
#import "MacControlPathSecurity.hpp"

@implementation DietCodeControlServer (Git)

- (void)executeGitMethod:(NSString*)method 
                  params:(NSDictionary*)params 
               outResult:(NSDictionary**)outResult 
              outErrCode:(NSString**)outErrCode 
             outErrMsg:(NSString**)outErrMsg
                outPaths:(NSString**)outPaths {
    
    if ([method isEqualToString:@"git.status"]) {
        NSDictionary* info = [self safeGitStatusInfo];
        *outResult = info;
        return;
    }
    
    if ([method isEqualToString:@"git.diff"]) {
        NSString* targetPath = params[@"path"] ?: @"";
        NSString* diff = [self safeGitDiffForFile:targetPath];
        *outResult = @{ @"diff": diff };
        return;
    }
    
    if ([method isEqualToString:@"git.stage"]) {
        NSString* targetPath = params[@"path"];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [(id)self.windowController gitStageFile:targetPath errorOut:&errStr];
        } else {
            std::string err;
            ok = dietcode::filesystem::GitService::stageFile(std::string([[self safeWorkspacePath] UTF8String]), std::string([targetPath UTF8String]), err);
            if (!ok) errStr = [NSString stringWithUTF8String:err.c_str()];
        }
        if (!ok) {
            *outErrCode = @"git_failed";
            *outErrMsg = errStr ?: @"Failed to stage file.";
            return;
        }
        *outResult = @{ @"staged": @YES };
        return;
    }
    
    if ([method isEqualToString:@"git.unstage"]) {
        NSString* targetPath = params[@"path"];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [(id)self.windowController gitUnstageFile:targetPath errorOut:&errStr];
        } else {
            std::string err;
            ok = dietcode::filesystem::GitService::unstageFile(std::string([[self safeWorkspacePath] UTF8String]), std::string([targetPath UTF8String]), err);
            if (!ok) errStr = [NSString stringWithUTF8String:err.c_str()];
        }
        if (!ok) {
            *outErrCode = @"git_failed";
            *outErrMsg = errStr ?: @"Failed to unstage file.";
            return;
        }
        *outResult = @{ @"unstaged": @YES };
        return;
    }
    
    if ([method isEqualToString:@"git.discard"]) {
        NSString* targetPath = params[@"path"];
        if (!targetPath) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"path parameter required.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [(id)self.windowController gitDiscardFile:targetPath errorOut:&errStr];
        } else {
            std::string err;
            ok = dietcode::filesystem::GitService::discardChanges(std::string([[self safeWorkspacePath] UTF8String]), std::string([targetPath UTF8String]), err);
            if (!ok) errStr = [NSString stringWithUTF8String:err.c_str()];
        }
        if (!ok) {
            *outErrCode = @"git_failed";
            *outErrMsg = errStr ?: @"Failed to discard file changes.";
            return;
        }
        *outResult = @{ @"discarded": @YES };
        return;
    }
    
    if ([method isEqualToString:@"git.commit"]) {
        NSString* message = params[@"message"];
        if (!message || message.length == 0) {
            *outErrCode = @"invalid_params";
            *outErrMsg = @"message parameter required.";
            return;
        }
        NSString* errStr = nil;
        BOOL ok = NO;
        if (self.windowController) {
            ok = [(id)self.windowController gitCommitWithMessage:message errorOut:&errStr];
        } else {
            std::string err;
            ok = dietcode::filesystem::GitService::commit(std::string([[self safeWorkspacePath] UTF8String]), std::string([message UTF8String]), err);
            if (!ok) errStr = [NSString stringWithUTF8String:err.c_str()];
        }
        if (!ok) {
            *outErrCode = @"git_failed";
            *outErrMsg = errStr ?: @"Failed to commit staged changes.";
            return;
        }
        *outResult = @{ @"committed": @YES };
        return;
    }
}

@end
