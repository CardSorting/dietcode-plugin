#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace dietcode::filesystem {

struct FileTreeNode {
    std::filesystem::path path;
    std::string displayName;
    bool directory{false};
    bool expanded{false};
    std::vector<FileTreeNode> children;
};

} // namespace dietcode::filesystem
