#pragma once

#include <filesystem>
#include <string>
#include <functional>
#include <system_error>

namespace dietcode::filesystem {

inline std::string displayName(const std::filesystem::path& path) {
    if (path.filename().empty()) {
        return path.string();
    }
    return path.filename().string();
}

/**
 * Shared utility for traversing directory contents.
 * Handles permission errors gracefully and provides a consistent interface.
 */
inline void traverseDirectory(const std::filesystem::path& root, 
                             std::function<void(const std::filesystem::directory_entry&, int depth, bool& skipRecursion, bool& stop)> callback,
                             bool recursive = true) {
    std::error_code ec;
    if (!std::filesystem::exists(root, ec)) return;

    auto options = std::filesystem::directory_options::skip_permission_denied;

    if (recursive) {
        for (auto it = std::filesystem::recursive_directory_iterator(root, options, ec);
             it != std::filesystem::recursive_directory_iterator();
             ++it) {
            if (ec) {
                ec.clear();
                continue;
            }
            
            bool skipRecursion = false;
            bool stop = false;
            callback(*it, it.depth(), skipRecursion, stop);
            if (stop) break;
            if (skipRecursion) {
                it.disable_recursion_pending();
            }
        }
    } else {
        for (auto it = std::filesystem::directory_iterator(root, options, ec);
             it != std::filesystem::directory_iterator();
             ++it) {
            if (ec) {
                ec.clear();
                continue;
            }
            bool skipRecursion = false;
            bool stop = false;
            callback(*it, 0, skipRecursion, stop);
            if (stop) break;
        }
    }
}

} // namespace dietcode::filesystem
