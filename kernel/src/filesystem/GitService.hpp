#pragma once

#include <string>
#include <vector>

namespace dietcode::filesystem {

struct GitChange {
    std::string status; // "M", "A", "D", "??", etc.
    std::string path;   // Relative path to workspace
    bool staged;        // True if staged
};

struct GitStatusResult {
    std::string branch;
    std::vector<GitChange> changes;
};

class GitService {
public:
    static GitStatusResult getStatus(const std::string& workspacePath);
    static bool stageFile(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut);
    static bool unstageFile(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut);
    static bool discardChanges(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut);
    static std::string getDiff(const std::string& workspacePath, const std::string& relativePath, bool staged);
    static bool commit(const std::string& workspacePath, const std::string& message, std::string& errorOut);
};

} // namespace dietcode::filesystem
