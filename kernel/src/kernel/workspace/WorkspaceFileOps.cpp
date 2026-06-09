#include "kernel/workspace/WorkspaceFileOps.hpp"

#include <algorithm>
#include <cctype>
#include <system_error>

namespace dietcode::kernel::workspace {

namespace {

bool isBinaryText(const std::string& text) {
    std::size_t checkLen = std::min<std::size_t>(text.size(), 8192);
    for (std::size_t i = 0; i < checkLen; ++i) {
        unsigned char c = static_cast<unsigned char>(text[i]);
        if (c == 0) {
            return true;
        }
    }
    return false;
}

std::filesystem::path makeAbsolute(const std::string& workspaceRoot, const std::string& path) {
    std::filesystem::path input(path);
    if (input.is_absolute() || workspaceRoot.empty()) {
        return input;
    }
    return std::filesystem::path(workspaceRoot) / input;
}

} // namespace

WorkspaceFileOps::WorkspaceFileOps(std::string workspaceRoot)
    : workspaceRoot_(std::move(workspaceRoot)) {}

void WorkspaceFileOps::setWorkspaceRoot(std::string root) {
    workspaceRoot_ = std::move(root);
}

PathResult WorkspaceFileOps::resolvePath(const std::string& path) const {
    PathResult result;
    if (path.empty()) {
        result.error = "Path is empty.";
        return result;
    }

    std::filesystem::path absolute = makeAbsolute(workspaceRoot_, path);
    result.absolutePath = absolute.string();

    if (!workspaceRoot_.empty()) {
        if (!isInsideWorkspace(absolute)) {
            result.error = "Path is outside workspace.";
            return result;
        }
    }

    std::error_code ec;
    if (workspaceRoot_.empty()) {
        result.ok = true;
        result.relativePath = absolute.filename().string();
        return result;
    }

    std::filesystem::path wsCanonical = std::filesystem::weakly_canonical(workspaceRoot_, ec);
    if (ec) {
        result.error = "Workspace root is invalid.";
        return result;
    }

    std::filesystem::path resolved = absolute;
    if (std::filesystem::exists(absolute, ec)) {
        resolved = std::filesystem::weakly_canonical(absolute, ec);
    } else {
        std::filesystem::path parent = absolute.parent_path();
        if (parent.empty()) {
            parent = ".";
        }
        resolved = std::filesystem::weakly_canonical(parent, ec) / absolute.filename();
    }

    auto rel = std::filesystem::relative(resolved, wsCanonical, ec);
    result.ok = !ec;
    result.relativePath = rel.string();
    result.absolutePath = resolved.string();
    if (!result.ok) {
        result.error = "Could not resolve path relative to workspace.";
    }
    return result;
}

bool WorkspaceFileOps::isInsideWorkspace(const std::filesystem::path& absolutePath) const {
    if (workspaceRoot_.empty()) {
        return false;
    }

    std::error_code ec;
    std::filesystem::path ws = std::filesystem::canonical(workspaceRoot_, ec);
    if (ec) {
        return false;
    }

    std::filesystem::path resolvedPath;
    if (std::filesystem::exists(absolutePath, ec)) {
        resolvedPath = std::filesystem::canonical(absolutePath, ec);
        if (ec) {
            return false;
        }
    } else {
        std::filesystem::path parent = absolutePath.parent_path();
        if (parent.empty()) {
            parent = ".";
        }
        std::filesystem::path parentCanonical = std::filesystem::weakly_canonical(parent, ec);
        if (ec) {
            return false;
        }
        resolvedPath = parentCanonical / absolutePath.filename();
    }

    if (std::filesystem::is_symlink(resolvedPath, ec)) {
        std::filesystem::path target = std::filesystem::read_symlink(resolvedPath, ec);
        if (!ec) {
            std::filesystem::path targetAbsolute =
                target.is_absolute() ? target : (resolvedPath.parent_path() / target);
            std::filesystem::path targetCanonical = std::filesystem::weakly_canonical(targetAbsolute, ec);
            if (!ec) {
                auto rel = std::filesystem::relative(targetCanonical, ws, ec);
                if (ec || rel.string().rfind("..", 0) == 0 || rel.is_absolute()) {
                    return false;
                }
            }
        }
    }

    auto rel = std::filesystem::relative(resolvedPath, ws, ec);
    if (ec) {
        return false;
    }
    const std::string relStr = rel.string();
    return relStr == "." || (relStr.rfind("..", 0) != 0 && !rel.is_absolute());
}

bool WorkspaceFileOps::isSymlink(const std::filesystem::path& absolutePath) const {
    std::error_code ec;
    return std::filesystem::is_symlink(absolutePath, ec);
}

TextResult WorkspaceFileOps::readText(const std::filesystem::path& absolutePath,
                                      const EditorTextOverlay& overlay) const {
    TextResult result;
    if (overlay) {
        if (auto editorText = overlay(absolutePath.string())) {
            if (!editorText->empty()) {
                if (isBinaryText(*editorText)) {
                    result.error = "Editor buffer contains binary content.";
                    return result;
                }
                result.ok = true;
                result.text = *editorText;
                result.readSource = "editor";
                return result;
            }
        }
    }

    auto disk = fileService_.readTextFile(absolutePath);
    if (!disk.ok) {
        result.error = disk.error;
        return result;
    }
    if (isBinaryText(disk.contents)) {
        result.error = "File appears to be binary.";
        return result;
    }
    result.ok = true;
    result.text = std::move(disk.contents);
    result.readSource = "disk";
    return result;
}

WriteResult WorkspaceFileOps::writeText(const std::filesystem::path& absolutePath,
                                        const std::string& contents) const {
    WriteResult result;
    auto write = fileService_.writeTextFile(absolutePath, contents);
    result.ok = write.ok;
    result.error = write.error;
    return result;
}

WriteResult WorkspaceFileOps::replaceRange(const std::filesystem::path& absolutePath,
                                             std::size_t startOffset,
                                             std::size_t length,
                                             const std::string& replacement,
                                             const EditorTextOverlay& overlay) const {
    auto current = readText(absolutePath, overlay);
    WriteResult result;
    if (!current.ok) {
        result.error = current.error;
        return result;
    }
    if (startOffset + length > current.text.size()) {
        result.error = "Replace range exceeds file length.";
        return result;
    }
    std::string updated = current.text;
    updated.replace(startOffset, length, replacement);
    return writeText(absolutePath, updated);
}

bool WorkspaceFileOps::exists(const std::filesystem::path& absolutePath) const {
    return fileService_.exists(absolutePath);
}

std::optional<std::int64_t> WorkspaceFileOps::fileSize(const std::filesystem::path& absolutePath) const {
    std::error_code ec;
    if (!std::filesystem::exists(absolutePath, ec)) {
        return std::nullopt;
    }
    auto size = std::filesystem::file_size(absolutePath, ec);
    if (ec) {
        return std::nullopt;
    }
    return static_cast<std::int64_t>(size);
}

} // namespace dietcode::kernel::workspace
