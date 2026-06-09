#import "MacControlSocketSafety.hpp"

#include "domain/control/ControlRuntimeLimits.hpp"

#include <sys/stat.h>
#include <unistd.h>

namespace dietcode::platform::macos {

static NSString* IssueForStat(const char* pathCStr, mode_t expectedFileMode, BOOL requireFile) {
    struct stat st;
    if (lstat(pathCStr, &st) != 0) {
        return nil;
    }
    if (S_ISLNK(st.st_mode)) {
        return @"socket_symlink";
    }
    if (st.st_uid != getuid()) {
        return @"socket_wrong_owner";
    }
    if (requireFile && !S_ISREG(st.st_mode) && !S_ISSOCK(st.st_mode)) {
        return @"socket_unsafe_type";
    }
    mode_t actualMode = st.st_mode & 0777;
    if (actualMode != 0 && actualMode != expectedFileMode) {
        return @"socket_unsafe_permissions";
    }
    return nil;
}

NSString* MacControlSocketPathIssue(NSString* path) {
    if (path.length == 0) return @"socket_unsafe_path";
    return IssueForStat([path UTF8String], dietcode::domain::control::kSocketFileMode, YES);
}

NSString* MacControlDietcodeDirIssue(NSString* path) {
    if (path.length == 0) return @"socket_unsafe_path";
    struct stat st;
    if (lstat([path UTF8String], &st) != 0) {
        return nil;
    }
    if (S_ISLNK(st.st_mode)) {
        return @"socket_symlink";
    }
    if (st.st_uid != getuid()) {
        return @"socket_wrong_owner";
    }
    if (!S_ISDIR(st.st_mode)) {
        return @"socket_unsafe_type";
    }
    mode_t actualMode = st.st_mode & 0777;
    if (actualMode != 0 && actualMode != dietcode::domain::control::kDietcodeDirMode) {
        return @"socket_unsafe_permissions";
    }
    return nil;
}

} // namespace dietcode::platform::macos
