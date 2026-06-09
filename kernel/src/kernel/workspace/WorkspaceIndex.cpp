#include "kernel/workspace/WorkspaceIndex.hpp"

#include <algorithm>
#include <filesystem>
#include <cctype>
#include <fnmatch.h>
#include <system_error>

namespace dietcode::kernel::workspace {

namespace {

#ifndef FNM_CASEFOLD
#define FNM_CASEFOLD 0
#endif

bool matchesAnyPattern(const std::string& relPath,
                       const std::string& filename,
                       const std::vector<std::string>& patterns) {
    for (const auto& pattern : patterns) {
        if (fnmatch(pattern.c_str(), relPath.c_str(), FNM_CASEFOLD) == 0 ||
            fnmatch(pattern.c_str(), filename.c_str(), FNM_CASEFOLD) == 0) {
            return true;
        }
    }
    return false;
}

std::string lowerAscii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

} // namespace

WorkspaceIndex::WorkspaceIndex(const WorkspaceFileOps& fileOps) : fileOps_(fileOps) {}

std::vector<FileEntry> WorkspaceIndex::listFiles(const std::string& relativeDir,
                                                 bool recursive,
                                                 const std::vector<std::string>& excludePatterns) const {
    std::vector<FileEntry> entries;
    const auto resolved = fileOps_.resolvePath(relativeDir.empty() ? "." : relativeDir);
    if (!resolved.ok) {
        return entries;
    }

    std::vector<std::string> excludes = excludePatterns;
    excludes.insert(excludes.end(), {".git", "build", "dist", "node_modules", "DerivedData", ".next", "__pycache__"});

    std::error_code ec;
    const std::filesystem::path root(resolved.absolutePath);
    if (!std::filesystem::exists(root, ec)) {
        return entries;
    }

    auto visit = [&](const std::filesystem::directory_entry& entry, int depth, bool& skipRecursion) {
        (void)depth;
        if (entry.is_symlink(ec)) {
            skipRecursion = true;
            return;
        }
        const auto abs = entry.path();
        if (!fileOps_.isInsideWorkspace(abs)) {
            return;
        }
        std::error_code relEc;
        const auto rel = std::filesystem::relative(abs, fileOps_.workspaceRoot(), relEc);
        if (relEc) {
            return;
        }
        const std::string relStr = rel.string();
        const std::string filename = abs.filename().string();
        if (matchesAnyPattern(relStr, filename, excludes)) {
            if (entry.is_directory(ec)) {
                skipRecursion = true;
            }
            return;
        }

        FileEntry fileEntry;
        fileEntry.relativePath = relStr;
        fileEntry.absolutePath = abs.string();
        fileEntry.isDirectory = entry.is_directory(ec);
        if (entry.is_regular_file(ec)) {
            if (auto size = fileOps_.fileSize(abs)) {
                fileEntry.sizeBytes = *size;
            }
        }
        entries.push_back(std::move(fileEntry));
    };

    if (recursive) {
        for (auto it = std::filesystem::recursive_directory_iterator(
                 root, std::filesystem::directory_options::skip_permission_denied, ec);
             it != std::filesystem::recursive_directory_iterator();
             ++it) {
            if (ec) {
                ec.clear();
                continue;
            }
            bool skipRecursion = false;
            visit(*it, static_cast<int>(it.depth()), skipRecursion);
            if (skipRecursion) {
                it.disable_recursion_pending();
            }
        }
    } else {
        for (auto it = std::filesystem::directory_iterator(
                 root, std::filesystem::directory_options::skip_permission_denied, ec);
             it != std::filesystem::directory_iterator();
             ++it) {
            if (ec) {
                ec.clear();
                continue;
            }
            bool skipRecursion = false;
            visit(*it, 0, skipRecursion);
        }
    }

    std::sort(entries.begin(), entries.end(), [](const FileEntry& a, const FileEntry& b) {
        return a.relativePath < b.relativePath;
    });
    return entries;
}

std::vector<FileEntry> WorkspaceIndex::findFiles(const std::vector<std::string>& globPatterns,
                                                 const std::vector<std::string>& excludePatterns) const {
    auto all = listFiles(".", true, excludePatterns);
    if (globPatterns.empty()) {
        return all;
    }
    std::vector<FileEntry> matched;
    for (const auto& entry : all) {
        if (entry.isDirectory) {
            continue;
        }
        const std::string filename = std::filesystem::path(entry.relativePath).filename().string();
        if (matchesAnyPattern(entry.relativePath, filename, globPatterns)) {
            matched.push_back(entry);
        }
    }
    return matched;
}

std::vector<GrepMatch> WorkspaceIndex::grepLiteral(const std::string& query,
                                                   bool caseSensitive,
                                                   int maxResults,
                                                   const EditorTextOverlay& overlay) const {
    std::vector<GrepMatch> matches;
    if (query.empty() || maxResults <= 0 || fileOps_.workspaceRoot().empty()) {
        return matches;
    }

    const auto files = findFiles({"**/*"}, {});
    const std::string needle = caseSensitive ? query : lowerAscii(query);

    for (const auto& file : files) {
        if (static_cast<int>(matches.size()) >= maxResults) {
            break;
        }
        const auto text = fileOps_.readText(std::filesystem::path(file.absolutePath), overlay);
        if (!text.ok) {
            continue;
        }

        std::string content = text.text;
        std::size_t offset = 0;
        std::size_t lineNumber = 1;
        std::size_t lineStart = 0;
        while (offset <= content.size()) {
            std::size_t newline = content.find('\n', offset);
            if (newline == std::string::npos) {
                newline = content.size();
            }
            const std::string line = content.substr(lineStart, newline - lineStart);
            const std::string haystack = caseSensitive ? line : lowerAscii(line);
            const auto pos = haystack.find(needle);
            if (pos != std::string::npos) {
                GrepMatch match;
                match.path = file.relativePath;
                match.line = static_cast<int>(lineNumber);
                match.column = static_cast<int>(pos + 1);
                match.lineText = line;
                matches.push_back(match);
                if (static_cast<int>(matches.size()) >= maxResults) {
                    break;
                }
            }
            if (newline == content.size()) {
                break;
            }
            offset = newline + 1;
            lineStart = offset;
            ++lineNumber;
        }
    }

    return matches;
}

} // namespace dietcode::kernel::workspace
