#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace dietcode::kernel::workspace {

struct PathResult {
    bool ok{false};
    std::string absolutePath;
    std::string relativePath;
    std::string error;
};

struct TextResult {
    bool ok{false};
    std::string text;
    std::string readSource; // "editor" | "disk"
    std::string error;
};

struct WriteResult {
    bool ok{false};
    std::string error;
};

struct FileEntry {
    std::string relativePath;
    std::string absolutePath;
    bool isDirectory{false};
    std::int64_t sizeBytes{0};
};

struct PatchApplyResult {
    bool ok{false};
    std::string channel; // "disk" | "editor"
    std::string error;
};

struct VerifyStatus {
    std::string command;
    std::string state; // idle | running | complete
    int exitCode{-1};
    bool passed{false};
    bool timedOut{false};
    std::string stdoutText;
    std::string stderrText;
    std::int64_t durationMs{0};
};

using EditorTextOverlay = std::function<std::optional<std::string>(const std::string& absolutePath)>;

} // namespace dietcode::kernel::workspace
