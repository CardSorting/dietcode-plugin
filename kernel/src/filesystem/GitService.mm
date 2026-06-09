#import <Foundation/Foundation.h>
#include "GitService.hpp"
#include "platform/macos/services/SubprocessRunner.hpp"
#include <sstream>
#include <filesystem>
#include <iostream>

using namespace dietcode::platform::macos;

namespace dietcode::filesystem {

static std::string runCommand(const std::string& dir, const std::string& launchPath, const std::vector<std::string>& args, int* exitCodeOut = nullptr) {
    SubprocessResult res = SubprocessRunner::run(launchPath, args, dir, 10.0);
    
    if (exitCodeOut) {
        *exitCodeOut = res.exitCode;
    }
    
    if (res.timedOut) {
        return "Command timed out";
    }
    
    return res.stdOut;
}

GitStatusResult GitService::getStatus(const std::string& workspacePath) {
    GitStatusResult result;
    result.branch = "";
    
    // Check if it is a git repository
    int exitCode = 0;
    runCommand(workspacePath, "/usr/bin/git", {"rev-parse", "--is-inside-work-tree"}, &exitCode);
    if (exitCode != 0) {
        return result; // Not a git repo
    }
    
    // Get current branch
    std::string branchOut = runCommand(workspacePath, "/usr/bin/git", {"symbolic-ref", "--short", "HEAD"}, &exitCode);
    if (exitCode != 0) {
        // Detached HEAD or other issue, try rev-parse
        branchOut = runCommand(workspacePath, "/usr/bin/git", {"rev-parse", "--abbrev-ref", "HEAD"}, &exitCode);
    }
    
    // Clean branch name
    if (exitCode == 0 && !branchOut.empty()) {
        // Strip newlines
        while (!branchOut.empty() && (branchOut.back() == '\n' || branchOut.back() == '\r')) {
            branchOut.pop_back();
        }
        result.branch = branchOut;
    } else {
        result.branch = "HEAD (detached)";
    }
    
    // Get porcelain status
    std::string statusOut = runCommand(workspacePath, "/usr/bin/git", {"status", "--porcelain", "-u"});
    std::stringstream ss(statusOut);
    std::string line;
    while (std::getline(ss, line)) {
        if (line.length() < 4) continue;
        
        char stageChar = line[0];
        char workChar = line[1];
        std::string p = line.substr(3);
        
        // Handle renames: old_path -> new_path
        size_t renamePos = p.find(" -> ");
        if (renamePos != std::string::npos) {
            p = p.substr(renamePos + 4);
        }
        
        // Strip surrounding quotes if any
        if (p.size() >= 2 && p.front() == '"' && p.back() == '"') {
            p = p.substr(1, p.size() - 2);
        }
        
        // Staged status
        if (stageChar != ' ' && stageChar != '?') {
            GitChange change;
            change.status = std::string(1, stageChar);
            change.path = p;
            change.staged = true;
            result.changes.push_back(change);
        }
        
        // Unstaged/Worktree status
        if (workChar != ' ' || (stageChar == '?' && workChar == '?')) {
            GitChange change;
            if (stageChar == '?' && workChar == '?') {
                change.status = "??";
            } else {
                change.status = std::string(1, workChar);
            }
            change.path = p;
            change.staged = false;
            result.changes.push_back(change);
        }
    }
    
    return result;
}

bool GitService::stageFile(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut) {
    int exitCode = 0;
    std::string out = runCommand(workspacePath, "/usr/bin/git", {"add", relativePath}, &exitCode);
    if (exitCode != 0) { errorOut = out.empty() ? "git add failed (exit " + std::to_string(exitCode) + ")" : out; }
    return exitCode == 0;
}

bool GitService::unstageFile(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut) {
    int exitCode = 0;
    std::string out = runCommand(workspacePath, "/usr/bin/git", {"reset", "HEAD", relativePath}, &exitCode);
    if (exitCode != 0) { errorOut = out.empty() ? "git reset HEAD failed (exit " + std::to_string(exitCode) + ")" : out; }
    return exitCode == 0;
}

bool GitService::discardChanges(const std::string& workspacePath, const std::string& relativePath, std::string& errorOut) {
    std::filesystem::path fullPath = std::filesystem::path(workspacePath) / relativePath;

    // Check if the file is untracked
    GitStatusResult status = getStatus(workspacePath);
    bool untracked = false;
    for (const auto& c : status.changes) {
        if (c.path == relativePath && c.status == "??") {
            untracked = true;
            break;
        }
    }

    if (untracked) {
        std::error_code ec;
        std::filesystem::remove(fullPath, ec);
        if (ec) { errorOut = "Failed to remove untracked file: " + ec.message(); }
        return !ec;
    } else {
        int exitCode = 0;
        std::string out = runCommand(workspacePath, "/usr/bin/git", {"checkout", "--", relativePath}, &exitCode);
        if (exitCode != 0) { errorOut = out.empty() ? "git checkout failed (exit " + std::to_string(exitCode) + ")" : out; }
        return exitCode == 0;
    }
}

std::string GitService::getDiff(const std::string& workspacePath, const std::string& relativePath, bool staged) {
    // Check if the file is untracked
    GitStatusResult status = getStatus(workspacePath);
    bool untracked = false;
    for (const auto& c : status.changes) {
        if (c.path == relativePath && c.status == "??") {
            untracked = true;
            break;
        }
    }
    
    if (untracked) {
        // Diff against /dev/null for untracked files
        int exitCode = 0;
        std::string diff = runCommand(workspacePath, "/usr/bin/git", {
            "diff", "--no-index", "/dev/null", relativePath
        }, &exitCode);
        // git diff --no-index exits with 1 if there are differences, which is normal
        return diff;
    } else {
        int exitCode = 0;
        std::vector<std::string> args;
        if (staged) {
            args = {"diff", "--cached", "--", relativePath};
        } else {
            args = {"diff", "--", relativePath};
        }
        return runCommand(workspacePath, "/usr/bin/git", args, &exitCode);
    }
}

bool GitService::commit(const std::string& workspacePath, const std::string& message, std::string& errorOut) {
    int exitCode = 0;
    std::string out = runCommand(workspacePath, "/usr/bin/git", {
        "commit", "-m", message
    }, &exitCode);
    
    if (exitCode != 0) {
        errorOut = out;
        return false;
    }
    return true;
}

} // namespace dietcode::filesystem
