#pragma once

#include "kernel/workspace/WorkspaceFileOps.hpp"
#include "kernel/workspace/WorkspaceTypes.hpp"

#include <string>
#include <vector>

namespace dietcode::kernel::workspace {

struct GrepMatch {
    std::string path;
    int line{0};
    int column{0};
    std::string lineText;
};

class WorkspaceIndex {
public:
    explicit WorkspaceIndex(const WorkspaceFileOps& fileOps);

    [[nodiscard]] std::vector<FileEntry> listFiles(const std::string& relativeDir,
                                                   bool recursive,
                                                   const std::vector<std::string>& excludePatterns = {}) const;

    [[nodiscard]] std::vector<FileEntry> findFiles(const std::vector<std::string>& globPatterns,
                                                   const std::vector<std::string>& excludePatterns = {}) const;

    [[nodiscard]] std::vector<GrepMatch> grepLiteral(const std::string& query,
                                                     bool caseSensitive,
                                                     int maxResults,
                                                     const EditorTextOverlay& overlay = {}) const;

private:
    const WorkspaceFileOps& fileOps_;
};

} // namespace dietcode::kernel::workspace
