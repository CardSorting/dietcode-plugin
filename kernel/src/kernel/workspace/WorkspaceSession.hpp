#pragma once

#include "kernel/workspace/WorkspaceFileOps.hpp"
#include "kernel/workspace/WorkspaceIndex.hpp"
#include "kernel/workspace/WorkspacePatchOps.hpp"
#include "kernel/workspace/WorkspaceVerifyOps.hpp"
#include "kernel/workspace/WorkspaceTypes.hpp"

#include "filesystem/GitService.hpp"

#include <mutex>
#include <string>
#include <vector>

namespace dietcode::kernel::workspace {

class WorkspaceSession {
public:
    WorkspaceSession();

    void setWorkspaceRoot(std::string root);
    [[nodiscard]] const std::string& workspaceRoot() const;

    void setEditorTextOverlay(EditorTextOverlay overlay);
    [[nodiscard]] EditorTextOverlay editorTextOverlay() const;

    void setAgentAutonomyLevel(int level);
    [[nodiscard]] int agentAutonomyLevel() const;

    void appendRecentCommand(const std::string& command);
    void appendRecentSearch(const std::string& query);
    void clearSessionHistory();
    [[nodiscard]] std::vector<std::string> recentCommands() const;
    [[nodiscard]] std::vector<std::string> recentSearches() const;

    [[nodiscard]] PathResult resolvePath(const std::string& path) const;
    [[nodiscard]] TextResult readText(const std::string& path) const;
    [[nodiscard]] WriteResult writeText(const std::string& path, const std::string& contents) const;
    [[nodiscard]] WriteResult replaceRange(const std::string& path,
                                           std::size_t startOffset,
                                           std::size_t length,
                                           const std::string& replacement) const;

    [[nodiscard]] PatchApplyResult applyPatch(const std::string& path,
                                              const std::string& patchText) const;

    [[nodiscard]] VerifyStatus runVerification(const std::string& command,
                                               const std::string& cwd = "");
    [[nodiscard]] VerifyStatus verificationStatus() const;

    [[nodiscard]] std::vector<FileEntry> listFiles(const std::string& relativeDir,
                                                    bool recursive) const;
    [[nodiscard]] std::vector<FileEntry> findFiles(const std::vector<std::string>& patterns) const;
    [[nodiscard]] std::vector<GrepMatch> grepLiteral(const std::string& query,
                                                     bool caseSensitive,
                                                     int maxResults) const;

    [[nodiscard]] dietcode::filesystem::GitStatusResult gitStatus() const;
    [[nodiscard]] std::string gitDiff(const std::string& path, bool staged) const;

    [[nodiscard]] WorkspaceFileOps& fileOps() { return fileOps_; }
    [[nodiscard]] const WorkspaceFileOps& fileOps() const { return fileOps_; }

private:
    mutable std::mutex mutex_;
    WorkspaceFileOps fileOps_;
    WorkspaceIndex index_;
    WorkspacePatchOps patchOps_;
    WorkspaceVerifyOps verifyOps_;
    EditorTextOverlay editorOverlay_;
    int agentAutonomyLevel_{1};
    std::vector<std::string> recentCommands_;
    std::vector<std::string> recentSearches_;
};

} // namespace dietcode::kernel::workspace
