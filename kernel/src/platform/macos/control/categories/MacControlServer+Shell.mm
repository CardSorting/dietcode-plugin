#import "MacControlServer+Private.hpp"
#import "MacControlShellService.hpp"

@implementation DietCodeControlServer (Shell)

- (void)executeShellMethod:(NSString*)method
                   params:(NSDictionary*)params
                outResult:(NSDictionary**)outResult
               outErrCode:(NSString**)outErrCode
                  outErrMsg:(NSString**)outErrMsg
                 outPaths:(NSString**)outPaths {
    (void)outPaths;
    NSString* ws = [self safeWorkspacePath];
    if (ws.length == 0) {
        *outErrCode = @"workspace_not_open";
        *outErrMsg = @"No workspace is open.";
        return;
    }
    MacControlShellService* shellService = [[MacControlShellService alloc] initWithWorkspaceState:_workspaceState];
    [shellService executeMethod:method params:params workspace:ws outResult:outResult outErrCode:outErrCode outErrMsg:outErrMsg];
}

@end
