#include "kernel/workspace/WorkspaceVerifyOps.hpp"

#include "platform/macos/services/SubprocessRunner.hpp"

#include <chrono>

namespace dietcode::kernel::workspace {

VerifyStatus WorkspaceVerifyOps::runCommand(const std::string& command,
                                              const std::string& workingDirectory,
                                              double timeoutSeconds) {
    VerifyStatus running;
    running.command = command;
    running.state = "running";
    running.exitCode = -1;
    running.passed = false;

    {
        std::lock_guard<std::mutex> lock(mutex_);
        lastStatus_ = running;
    }

    using dietcode::platform::macos::SubprocessRunner;
    const auto started = std::chrono::steady_clock::now();
    auto res = SubprocessRunner::run("/bin/zsh", {"-c", command}, workingDirectory, timeoutSeconds);
    const auto finished = std::chrono::steady_clock::now();

    VerifyStatus complete;
    complete.command = command;
    complete.state = "complete";
    complete.timedOut = res.timedOut;
    complete.stdoutText = res.stdOut;
    complete.stderrText = res.stdErr;
    complete.durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(finished - started).count();

    if (res.timedOut) {
        complete.exitCode = -2;
        complete.passed = false;
    } else {
        complete.exitCode = res.exitCode;
        complete.passed = res.exitCode == 0;
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);
        lastStatus_ = complete;
    }
    return complete;
}

VerifyStatus WorkspaceVerifyOps::lastStatus() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return lastStatus_;
}

} // namespace dietcode::kernel::workspace
