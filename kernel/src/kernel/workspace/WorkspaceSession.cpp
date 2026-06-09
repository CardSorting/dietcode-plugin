#include "kernel/workspace/WorkspaceSession.hpp"

namespace dietcode::kernel::workspace {

WorkspaceSession::WorkspaceSession()
    : fileOps_("")
    , index_(fileOps_) {}

void WorkspaceSession::setWorkspaceRoot(std::string root) {
    std::lock_guard<std::mutex> lock(mutex_);
    fileOps_.setWorkspaceRoot(std::move(root));
}

const std::string& WorkspaceSession::workspaceRoot() const {
    return fileOps_.workspaceRoot();
}

void WorkspaceSession::setEditorTextOverlay(EditorTextOverlay overlay) {
    std::lock_guard<std::mutex> lock(mutex_);
    editorOverlay_ = std::move(overlay);
}

EditorTextOverlay WorkspaceSession::editorTextOverlay() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return editorOverlay_;
}

void WorkspaceSession::setAgentAutonomyLevel(int level) {
    std::lock_guard<std::mutex> lock(mutex_);
    agentAutonomyLevel_ = level;
}

int WorkspaceSession::agentAutonomyLevel() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return agentAutonomyLevel_;
}

void WorkspaceSession::appendRecentCommand(const std::string& command) {
    if (command.empty()) {
        return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    recentCommands_.insert(recentCommands_.begin(), command);
    if (recentCommands_.size() > 50) {
        recentCommands_.resize(50);
    }
}

void WorkspaceSession::appendRecentSearch(const std::string& query) {
    if (query.empty()) {
        return;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    recentSearches_.insert(recentSearches_.begin(), query);
    if (recentSearches_.size() > 50) {
        recentSearches_.resize(50);
    }
}

void WorkspaceSession::clearSessionHistory() {
    std::lock_guard<std::mutex> lock(mutex_);
    recentCommands_.clear();
    recentSearches_.clear();
}

std::vector<std::string> WorkspaceSession::recentCommands() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recentCommands_;
}

std::vector<std::string> WorkspaceSession::recentSearches() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return recentSearches_;
}

PathResult WorkspaceSession::resolvePath(const std::string& path) const {
    return fileOps_.resolvePath(path);
}

TextResult WorkspaceSession::readText(const std::string& path) const {
    const auto resolved = fileOps_.resolvePath(path);
    if (!resolved.ok) {
        TextResult result;
        result.error = resolved.error;
        return result;
    }
    return fileOps_.readText(std::filesystem::path(resolved.absolutePath), editorTextOverlay());
}

WriteResult WorkspaceSession::writeText(const std::string& path, const std::string& contents) const {
    const auto resolved = fileOps_.resolvePath(path);
    if (!resolved.ok) {
        WriteResult result;
        result.error = resolved.error;
        return result;
    }
    if (fileOps_.isSymlink(std::filesystem::path(resolved.absolutePath))) {
        return WriteResult{false, "Cannot write through symlink path."};
    }
    return fileOps_.writeText(std::filesystem::path(resolved.absolutePath), contents);
}

WriteResult WorkspaceSession::replaceRange(const std::string& path,
                                           std::size_t startOffset,
                                           std::size_t length,
                                           const std::string& replacement) const {
    const auto resolved = fileOps_.resolvePath(path);
    if (!resolved.ok) {
        WriteResult result;
        result.error = resolved.error;
        return result;
    }
    return fileOps_.replaceRange(
        std::filesystem::path(resolved.absolutePath), startOffset, length, replacement, editorTextOverlay());
}

PatchApplyResult WorkspaceSession::applyPatch(const std::string& path, const std::string& patchText) const {
    PatchApplyResult result;
    const auto resolved = fileOps_.resolvePath(path);
    if (!resolved.ok) {
        result.error = resolved.error;
        return result;
    }
    if (fileOps_.isSymlink(std::filesystem::path(resolved.absolutePath))) {
        result.error = "Cannot apply patch through symlink path.";
        return result;
    }
    const auto before = readText(path);
    if (!before.ok) {
        result.error = before.error;
        return result;
    }
    return patchOps_.applyUnifiedPatch(resolved.absolutePath, before.text, patchText);
}

VerifyStatus WorkspaceSession::runVerification(const std::string& command, const std::string& cwd) {
    const std::string runCwd = cwd.empty() ? workspaceRoot() : cwd;
    return verifyOps_.runCommand(command, runCwd);
}

VerifyStatus WorkspaceSession::verificationStatus() const {
    return verifyOps_.lastStatus();
}

std::vector<FileEntry> WorkspaceSession::listFiles(const std::string& relativeDir, bool recursive) const {
    return index_.listFiles(relativeDir, recursive);
}

std::vector<FileEntry> WorkspaceSession::findFiles(const std::vector<std::string>& patterns) const {
    return index_.findFiles(patterns);
}

std::vector<GrepMatch> WorkspaceSession::grepLiteral(const std::string& query,
                                                     bool caseSensitive,
                                                     int maxResults) const {
    return index_.grepLiteral(query, caseSensitive, maxResults, editorTextOverlay());
}

dietcode::filesystem::GitStatusResult WorkspaceSession::gitStatus() const {
    if (workspaceRoot().empty()) {
        return {};
    }
    return dietcode::filesystem::GitService::getStatus(workspaceRoot());
}

std::string WorkspaceSession::gitDiff(const std::string& path, bool staged) const {
    if (workspaceRoot().empty()) {
        return {};
    }
    const auto resolved = fileOps_.resolvePath(path);
    if (!resolved.ok) {
        return {};
    }
    return dietcode::filesystem::GitService::getDiff(workspaceRoot(), resolved.relativePath, staged);
}

} // namespace dietcode::kernel::workspace
