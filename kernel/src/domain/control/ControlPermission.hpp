#pragma once

#include <algorithm>
#include <cctype>
#include <utility>
#include <string>

namespace dietcode::domain::control {

enum class PermissionLevel {
    Read = 0,
    Edit = 1,
    Execute = 2,
    Destructive = 3,
    External = 4,
};

inline std::string lowerAscii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

inline PermissionLevel permissionLevelFromString(std::string value) {
    value = lowerAscii(std::move(value));
    if (value == "edit") return PermissionLevel::Edit;
    if (value == "execute") return PermissionLevel::Execute;
    if (value == "destructive") return PermissionLevel::Destructive;
    if (value == "external") return PermissionLevel::External;
    return PermissionLevel::Read;
}

inline int permissionRank(PermissionLevel level) {
    return static_cast<int>(level);
}

inline int permissionRankFromString(std::string value) {
    return permissionRank(permissionLevelFromString(std::move(value)));
}

} // namespace dietcode::domain::control
