#pragma once

#import <Cocoa/Cocoa.h>
#include <filesystem>
#include <fnmatch.h>
#include <string>

#ifndef FNM_CASEFOLD
#define FNM_CASEFOLD 0
#endif

namespace dietcode::platform::macos {

NSString* AbsolutePathForRPCPath(NSString* path, NSString* workspace);
BOOL PathIsInsideWorkspace(NSString* path, NSString* workspace);
BOOL AnyPatternMatches(NSArray<NSString*>* patterns, const std::string& relPath, const std::string& filename);
BOOL ShouldSkipSearchPath(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* includes, NSArray<NSString*>* excludes);
BOOL ShouldPruneSearchDirectory(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* excludes);
NSDictionary* PathSymlinkMetadata(NSString* path, NSString* workspace);
BOOL PathIsSymlink(NSString* path);

} // namespace dietcode::platform::macos
