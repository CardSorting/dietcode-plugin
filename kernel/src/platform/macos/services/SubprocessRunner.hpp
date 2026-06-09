#pragma once

#include <string>
#include <vector>
#include <optional>

namespace dietcode::platform::macos {

struct SubprocessResult {
    int exitCode = -1;
    std::string stdOut;
    std::string stdErr;
    bool timedOut = false;
};

class SubprocessRunner {
public:
    static SubprocessResult run(
        const std::string& launchPath,
        const std::vector<std::string>& args,
        const std::string& workingDirectory = "",
        double timeoutSeconds = 30.0
    );
};

} // namespace dietcode::platform::macos
