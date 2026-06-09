#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace dietcode::filesystem {

struct FileReadResult {
    bool ok{false};
    std::string contents;
    std::string error;
};

struct FileWriteResult {
    bool ok{false};
    std::string error;
};

class FileService {
public:
    [[nodiscard]] FileReadResult readTextFile(const std::filesystem::path& path) const;
    [[nodiscard]] FileWriteResult writeTextFile(const std::filesystem::path& path, const std::string& contents) const;
    [[nodiscard]] bool exists(const std::filesystem::path& path) const;
};

} // namespace dietcode::filesystem
