#pragma once

#import <Cocoa/Cocoa.h>

namespace dietcode::platform::macos {

// SAFETY: Returns nil when safe; otherwise a stable string_code (socket_symlink, socket_wrong_owner, socket_unsafe_permissions).
NSString* MacControlSocketPathIssue(NSString* path);
NSString* MacControlDietcodeDirIssue(NSString* path);

} // namespace dietcode::platform::macos
