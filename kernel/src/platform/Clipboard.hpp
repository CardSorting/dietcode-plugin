#pragma once

#include <string>

namespace dietcode::platform {

class Clipboard {
public:
    virtual ~Clipboard() = default;
    virtual void setText(const std::string& text) = 0;
    virtual std::string text() const = 0;
};

} // namespace dietcode::platform
