#include "kernel/workspace/WorkspacePatchOps.hpp"

#include "filesystem/FileService.hpp"
#include "platform/macos/services/SubprocessRunner.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>

namespace dietcode::kernel::workspace {

PatchApplyResult WorkspacePatchOps::applyUnifiedPatch(const std::string& absolutePath,
                                                      const std::string& beforeText,
                                                      const std::string& patchText) const {
    PatchApplyResult result;
    if (absolutePath.empty() || beforeText.empty() || patchText.empty()) {
        result.error = "Invalid patch apply inputs.";
        return result;
    }

    const auto tempDir = std::filesystem::temp_directory_path();
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    const std::filesystem::path tempSrc =
        tempDir / ("dietcode_apply_src_" + std::to_string(stamp) + ".txt");
    const std::filesystem::path tempDiff =
        tempDir / ("dietcode_apply_diff_" + std::to_string(stamp) + ".diff");

    {
        std::ofstream src(tempSrc, std::ios::binary | std::ios::trunc);
        if (!src) {
            result.error = "Failed to write temp source file.";
            return result;
        }
        src.write(beforeText.data(), static_cast<std::streamsize>(beforeText.size()));
    }
    {
        std::ofstream diff(tempDiff, std::ios::binary | std::ios::trunc);
        if (!diff) {
            std::error_code ec;
            std::filesystem::remove(tempSrc, ec);
            result.error = "Failed to write temp patch file.";
            return result;
        }
        diff.write(patchText.data(), static_cast<std::streamsize>(patchText.size()));
    }

    using dietcode::platform::macos::SubprocessRunner;
    auto patchRes = SubprocessRunner::run(
        "/usr/bin/patch",
        {"--silent", tempSrc.string(), tempDiff.string()},
        "",
        10.0);

    dietcode::filesystem::FileService files;
    auto patched = files.readTextFile(tempSrc);

    std::error_code ec;
    std::filesystem::remove(tempSrc, ec);
    std::filesystem::remove(tempDiff, ec);

    if (patchRes.exitCode != 0 || !patched.ok) {
        result.error = patchRes.stdErr.empty() ? "Disk patch failed." : patchRes.stdErr;
        return result;
    }

    auto write = files.writeTextFile(std::filesystem::path(absolutePath), patched.contents);
    if (!write.ok) {
        result.error = write.error;
        return result;
    }

    result.ok = true;
    result.channel = "disk";
    return result;
}

} // namespace dietcode::kernel::workspace
