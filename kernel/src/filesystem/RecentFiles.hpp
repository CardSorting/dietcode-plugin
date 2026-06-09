#pragma once

#include <algorithm>
#include <filesystem>
#include <utility>
#include <vector>

namespace dietcode::filesystem {

class RecentFiles {
public:
    static constexpr std::size_t kMaxRecent = 25;

    void add(std::filesystem::path path) {
        // LRU dedup: remove existing entry if present, then prepend.
        entries_.erase(
            std::remove(entries_.begin(), entries_.end(), path),
            entries_.end());
        entries_.insert(entries_.begin(), std::move(path));
        if (entries_.size() > kMaxRecent) {
            entries_.resize(kMaxRecent);
        }
    }

    [[nodiscard]] const std::vector<std::filesystem::path>& entries() const noexcept {
        return entries_;
    }

    void clear() noexcept { entries_.clear(); }

private:
    std::vector<std::filesystem::path> entries_;
};

} // namespace dietcode::filesystem
