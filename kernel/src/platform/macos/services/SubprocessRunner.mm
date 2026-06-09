#import "SubprocessRunner.hpp"
#import <Foundation/Foundation.h>

namespace dietcode::platform::macos {

SubprocessResult SubprocessRunner::run(
    const std::string& launchPath,
    const std::vector<std::string>& args,
    const std::string& workingDirectory,
    double timeoutSeconds
) {
    SubprocessResult result;
    
    @autoreleasepool {
        NSTask* task = [[NSTask alloc] init];
        [task setLaunchPath:[NSString stringWithUTF8String:launchPath.c_str()]];
        
        NSMutableArray* nsArgs = [NSMutableArray arrayWithCapacity:args.size()];
        for (const auto& arg : args) {
            [nsArgs addObject:[NSString stringWithUTF8String:arg.c_str()]];
        }
        [task setArguments:nsArgs];
        
        if (!workingDirectory.empty()) {
            [task setCurrentDirectoryPath:[NSString stringWithUTF8String:workingDirectory.c_str()]];
        }
        
        NSPipe* outPipe = [NSPipe pipe];
        NSPipe* errPipe = [NSPipe pipe];
        [task setStandardOutput:outPipe];
        [task setStandardError:errPipe];
        
        dispatch_semaphore_t sema = dispatch_semaphore_create(0);
        
        task.terminationHandler = ^(NSTask*) {
            dispatch_semaphore_signal(sema);
        };
        
        @try {
            [task launch];
        } @catch (NSException* e) {
            result.stdErr = [[e reason] UTF8String] ?: "Unknown launch exception";
            result.exitCode = -1;
            return result;
        }
        
        dispatch_time_t timeout = dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeoutSeconds * NSEC_PER_SEC));
        if (dispatch_semaphore_wait(sema, timeout) != 0) {
            // Timeout
            result.timedOut = YES;
            [task terminate];
            // Wait a bit for it to actually terminate
            dispatch_semaphore_wait(sema, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)));
        }
        
        NSData* outData = [[outPipe fileHandleForReading] readDataToEndOfFile];
        NSData* errData = [[errPipe fileHandleForReading] readDataToEndOfFile];
        
        if (outData) {
            result.stdOut = std::string((const char*)[outData bytes], [outData length]);
        }
        if (errData) {
            result.stdErr = std::string((const char*)[errData bytes], [errData length]);
        }
        
        if (!result.timedOut) {
            result.exitCode = task.terminationStatus;
        }
    }
    
    return result;
}

} // namespace dietcode::platform::macos
