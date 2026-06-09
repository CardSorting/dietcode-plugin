#pragma once

#include "kernel/workspace/WorkspaceTypes.hpp"

#include <string>

namespace dietcode::kernel::workspace {

class WorkspacePatchOps {
public:
    [[nodiscard]] PatchApplyResult applyUnifiedPatch(const std::string& absolutePath,
                                                     const std::string& beforeText,
                                                     const std::string& patchText) const;
};

} // namespace dietcode::kernel::workspace
