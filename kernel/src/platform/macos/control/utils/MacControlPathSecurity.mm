#import "MacControlPathSecurity.hpp"
#import "MacControlSupport.hpp"
#include <fnmatch.h>

namespace dietcode::platform::macos {

NSString* AbsolutePathForRPCPath(NSString* path, NSString* workspace) {
    if (path.length == 0) return path;
    if ([path isAbsolutePath] || workspace.length == 0) return path;
    return [workspace stringByAppendingPathComponent:path];
}

BOOL PathIsInsideWorkspace(NSString* path, NSString* workspace) {
    if (path.length == 0 || workspace.length == 0) return NO;
    std::error_code ec;
    std::filesystem::path p(StdStringFromNSString(path));
    std::filesystem::path ws = std::filesystem::canonical(std::filesystem::path(StdStringFromNSString(workspace)), ec);
    if (ec) return NO;
    
    std::filesystem::path resolvedPath;
    if (std::filesystem::exists(p)) {
        resolvedPath = std::filesystem::canonical(p, ec);
        if (ec) return NO;
    } else {
        std::filesystem::path parent = p.parent_path();
        if (parent.empty()) {
            parent = ".";
        }
        std::filesystem::path parentCanonical = std::filesystem::weakly_canonical(parent, ec);
        if (ec) return NO;
        resolvedPath = parentCanonical / p.filename();
    }
    
    // Explicitly reject if resolved path is a symlink pointing outside
    if (std::filesystem::is_symlink(resolvedPath, ec)) {
        std::filesystem::path target = std::filesystem::read_symlink(resolvedPath, ec);
        if (!ec) {
            std::filesystem::path targetAbsolute = target.is_absolute() ? target : (resolvedPath.parent_path() / target);
            std::filesystem::path targetCanonical = std::filesystem::weakly_canonical(targetAbsolute, ec);
            if (!ec) {
                auto rel = std::filesystem::relative(targetCanonical, ws, ec);
                if (ec || rel.string().rfind("..", 0) == 0 || rel.is_absolute()) {
                    return NO;
                }
            }
        }
    }
    
    auto rel = std::filesystem::relative(resolvedPath, ws, ec);
    if (ec) return NO;
    std::string relStr = rel.string();
    return relStr == "." || (relStr.rfind("..", 0) != 0 && !rel.is_absolute());
}

BOOL AnyPatternMatches(NSArray<NSString*>* patterns, const std::string& relPath, const std::string& filename) {
    for (NSString* pattern in patterns ?: @[]) {
        std::string pat = StdStringFromNSString(pattern);
        if (fnmatch(pat.c_str(), relPath.c_str(), FNM_CASEFOLD) == 0 ||
            fnmatch(pat.c_str(), filename.c_str(), FNM_CASEFOLD) == 0) {
            return YES;
        }
        std::filesystem::path p(relPath);
        for (const auto& part : p) {
            if (fnmatch(pat.c_str(), part.string().c_str(), FNM_CASEFOLD) == 0) {
                return YES;
            }
        }
    }
    return NO;
}

BOOL ShouldSkipSearchPath(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* includes, NSArray<NSString*>* excludes) {
    std::string filename = path.filename().string();
    NSArray* defaultExcludes = @[@".git", @"build", @"dist", @"node_modules", @"DerivedData", @".next", @"__pycache__"];
    if (AnyPatternMatches(defaultExcludes, relPath, filename) || AnyPatternMatches(excludes, relPath, filename)) {
        return YES;
    }
    if (includes.count > 0 && !AnyPatternMatches(includes, relPath, filename)) {
        return YES;
    }
    return NO;
}

BOOL PathIsSymlink(NSString* path) {
    if (path.length == 0) return NO;
    std::error_code ec;
    return std::filesystem::is_symlink(std::filesystem::path(StdStringFromNSString(path)), ec);
}

NSDictionary* PathSymlinkMetadata(NSString* path, NSString* workspace) {
    if (path.length == 0) {
        return @{ @"isSymlink": @NO, @"symlinkTarget": @"", @"insideWorkspace": @NO, @"pathEscapesWorkspace": @NO };
    }
    std::error_code ec;
    std::filesystem::path p(StdStringFromNSString(path));
    BOOL isSymlink = std::filesystem::is_symlink(p, ec);
    NSString* target = @"";
    BOOL escapes = NO;
    BOOL inside = PathIsInsideWorkspace(path, workspace);
    if (isSymlink && !ec) {
        std::filesystem::path linkTarget = std::filesystem::read_symlink(p, ec);
        if (!ec) {
            target = NSStringFromStdString(linkTarget.string());
            std::filesystem::path resolved = linkTarget.is_absolute() ? linkTarget : (p.parent_path() / linkTarget);
            std::filesystem::path canonical = std::filesystem::weakly_canonical(resolved, ec);
            if (!ec && workspace.length > 0) {
                std::filesystem::path ws = std::filesystem::canonical(std::filesystem::path(StdStringFromNSString(workspace)), ec);
                if (!ec) {
                    auto rel = std::filesystem::relative(canonical, ws, ec);
                    escapes = ec || rel.string().rfind("..", 0) == 0 || rel.is_absolute();
                }
            }
        }
    }
    return @{
        @"isSymlink": @(isSymlink),
        @"symlinkTarget": target ?: @"",
        @"insideWorkspace": @(inside),
        @"pathEscapesWorkspace": @(escapes)
    };
}

BOOL ShouldPruneSearchDirectory(const std::filesystem::path& path, const std::string& relPath, NSArray<NSString*>* excludes) {
    std::string filename = path.filename().string();
    NSArray* defaultExcludes = @[@".git", @"build", @"dist", @"node_modules", @"DerivedData", @".next", @"__pycache__"];
    return AnyPatternMatches(defaultExcludes, relPath, filename) || AnyPatternMatches(excludes, relPath, filename);
}

} // namespace dietcode::platform::macos
