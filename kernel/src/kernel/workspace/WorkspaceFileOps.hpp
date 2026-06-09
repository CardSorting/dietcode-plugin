#pragma once

#include "kernel/workspace/WorkspaceTypes.hpp"

#include "filesystem/FileService.hpp"

#include <filesystem>
#include <string>

namespace dietcode::kernel::workspace {

class WorkspaceFileOps {
public:
    explicit WorkspaceFileOps(std::string workspaceRoot);

    [[nodiscard]] const std::string& workspaceRoot() const { return workspaceRoot_; }
    void setWorkspaceRoot(std::string root);

    [[nodiscard]] PathResult resolvePath(const std::string& path) const;
    [[nodiscard]] bool isInsideWorkspace(const std::filesystem::path& absolutePath) const;
    [[nodiscard]] bool isSymlink(const std::filesystem::path& absolutePath) const;

    [[nodiscard]] TextResult readText(const std::filesystem::path& absolutePath,
                                      const EditorTextOverlay& overlay = {}) const;
    [[nodiscard]] WriteResult writeText(const std::filesystem::path& absolutePath,
                                          const std::string& contents) const;
    [[nodiscard]] WriteResult replaceRange(const std::filesystem::path& absolutePath,
                                             std::size_t startOffset,
                                             std::size_t length,
                                             const std::string& replacement,
                                             const EditorTextOverlay& overlay = {}) const;

    [[nodiscard]] bool exists(const std::filesystem::path& absolutePath) const;
    [[nodiscard]] std::optional<std::int64_t> fileSize(const std::filesystem::path& absolutePath) const;

private:
    std::string workspaceRoot_;
    dietcode::filesystem::FileService fileService_;
};

} // namespace dietcode::kernel::workspace
