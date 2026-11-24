#pragma once

#include <pixeagle/local_protocol.hpp>
#include <functional>
#include <optional>
#include <string>

namespace pixeagle {

// Poll from the same executor that owns the mode. All I/O is nonblocking and
// bounded, so a slow or stopped backend cannot block setpoint timers.
class LocalServer {
public:
    using Handler = std::function<std::optional<Json>(const Request&)>;
    using Disconnect = std::function<void()>;
    LocalServer(std::string path, Handler handler, Disconnect disconnect, double reply_timeout_s);
    ~LocalServer();
    LocalServer(const LocalServer&) = delete;
    LocalServer& operator=(const LocalServer&) = delete;
    void poll(double now);

private:
    void closePeer();
    void flush();
    int _listener{-1}, _peer{-1};
    std::string _path, _input, _output;
    Handler _handler;
    Disconnect _disconnect;
    std::optional<Request> _pending;
    std::optional<std::uint64_t> _last_request;
    std::optional<std::uint64_t> _generation;
    double _pending_since{}, _output_since{};
    const double _reply_timeout_s;
};

} // namespace pixeagle
