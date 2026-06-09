#pragma once

#include <filesystem>
#include <optional>

namespace dietcode::platform {

class FileDialog {
public:
    virtual ~FileDialog() = default;
    virtual std::optional<std::filesystem::path> openFile() = 0;
    virtual std::optional<std::filesystem::path> saveFile() = 0;
};

} // namespace dietcode::platform
