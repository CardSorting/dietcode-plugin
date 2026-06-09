#pragma once

#include "kernel/workspace/WorkspaceTypes.hpp"

#include <mutex>
#include <string>

namespace dietcode::kernel::workspace {

class WorkspaceVerifyOps {
public:
    [[nodiscard]] VerifyStatus runCommand(const std::string& command,
                                          const std::string& workingDirectory,
                                          double timeoutSeconds = 60.0);

    [[nodiscard]] VerifyStatus lastStatus() const;

private:
    mutable std::mutex mutex_;
    VerifyStatus lastStatus_;
};

} // namespace dietcode::kernel::workspace
