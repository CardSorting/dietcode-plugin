#pragma once

namespace dietcode::platform {

class Window {
public:
    virtual ~Window() = default;
    virtual void show() = 0;
};

} // namespace dietcode::platform
