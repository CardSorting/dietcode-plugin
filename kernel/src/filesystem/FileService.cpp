#include "filesystem/FileService.hpp"

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <system_error>
#include <utility>

#ifdef __APPLE__
#include <unistd.h>
#endif

namespace dietcode::filesystem {

static constexpr std::uintmax_t kMaxReadableFileSize = 50ULL * 1024 * 1024; // 50 MB

FileReadResult FileService::readTextFile(const std::filesystem::path& path) const {
    // Guard against opening excessively large files that would OOM.
    std::error_code sizeEc;
    const auto fileSize = std::filesystem::file_size(path, sizeEc);
    if (!sizeEc && fileSize > kMaxReadableFileSize) {
        return FileReadResult{false, {}, "File too large to open (" + std::to_string(fileSize / (1024 * 1024)) + " MB). Maximum is 50 MB."};
    }

    std::ifstream file(path, std::ios::binary);
    if (!file) {
        return FileReadResult{false, {}, "Could not open the file for reading."};
    }

    std::string contents((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    if (file.bad()) {
        return FileReadResult{false, {}, "The file could not be read completely."};
    }

    return FileReadResult{true, std::move(contents), {}};
}

FileWriteResult FileService::writeTextFile(const std::filesystem::path& path, const std::string& contents) const {
    auto timestamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path tempPath = path.parent_path() / (path.filename().string() + ".tmp." + std::to_string(timestamp));

    std::error_code remove_ec;
    std::filesystem::remove(tempPath, remove_ec);

    std::ofstream file(tempPath, std::ios::binary | std::ios::trunc);
    if (!file) {
        return FileWriteResult{false, "Could not open the temporary file for writing."};
    }

    file.write(contents.data(), static_cast<std::streamsize>(contents.size()));
    if (!file) {
        file.close();
        std::error_code ec;
        std::filesystem::remove(tempPath, ec);
        return FileWriteResult{false, "The file could not be written completely."};
    }

    // Flush the C++ stream buffer, then fsync the underlying fd to ensure
    // data is durable on disk before we rename. Without this, a power loss
    // after rename can leave a zero-length file on APFS/HFS+.
    file.flush();
#ifdef __APPLE__
    if (FILE* cFile = std::fopen(tempPath.c_str(), "r")) {
        ::fsync(::fileno(cFile));
        std::fclose(cFile);
    }
#endif
    file.close();

    std::error_code ec;
    std::filesystem::rename(tempPath, path, ec);
    if (ec) {
        std::error_code remove_ec;
        std::filesystem::remove(tempPath, remove_ec);
        return FileWriteResult{false, "Could not replace the original file atomically: " + ec.message()};
    }

    return FileWriteResult{true, {}};
}

bool FileService::exists(const std::filesystem::path& path) const {
    std::error_code error;
    return std::filesystem::exists(path, error);
}

} // namespace dietcode::filesystem
