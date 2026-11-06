#include <pixeagle/local_server.hpp>
#include <array>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace pixeagle {

LocalServer::LocalServer(std::string path, Handler handler, Disconnect disconnect, double reply_timeout_s)
    : _path(std::move(path)), _handler(std::move(handler)), _disconnect(std::move(disconnect)),
      _reply_timeout_s(reply_timeout_s) {
    if (!std::isfinite(reply_timeout_s) || reply_timeout_s <= 0.) throw std::invalid_argument("native_timeout_invalid");
    const auto parent = std::filesystem::path(_path).parent_path();
    struct stat info{};
    if (!std::filesystem::path(_path).is_absolute() || lstat(parent.c_str(), &info) != 0
            || !S_ISDIR(info.st_mode) || info.st_uid != geteuid() || (info.st_mode & 0022))
        throw std::invalid_argument("native_socket_directory_not_private");
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    if (_path.size() >= sizeof(address.sun_path)) throw std::invalid_argument("native_socket_path_too_long");
    std::memcpy(address.sun_path, _path.c_str(), _path.size() + 1);
    _listener = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (_listener < 0) throw std::runtime_error("native_socket_unavailable");
    if (bind(_listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        close(_listener); _listener = -1;
        throw std::runtime_error("native_socket_path_unavailable");
    }
    if (chmod(_path.c_str(), 0600) != 0 || listen(_listener, 1) != 0) {
        close(_listener); _listener = -1; unlink(_path.c_str());
        throw std::runtime_error("native_socket_unavailable");
    }
}

LocalServer::~LocalServer() {
    closePeer();
    if (_listener >= 0) { close(_listener); unlink(_path.c_str()); }
}

void LocalServer::closePeer() {
    if (_peer >= 0) {
        close(_peer); _peer = -1;
        _disconnect();
    }
    _pending.reset(); _last_request.reset(); _generation.reset();
    _input.clear(); _output.clear();
}

void LocalServer::flush() {
    if (_output.empty() || _peer < 0) return;
    const auto count = send(_peer, _output.data(), _output.size(), MSG_NOSIGNAL | MSG_DONTWAIT);
    if (count > 0) _output.erase(0, count);
    else if (count == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) closePeer();
}

void LocalServer::poll(double now) {
    if (!std::isfinite(now)) { closePeer(); return; }
    if (_peer < 0) {
        const int peer = accept4(_listener, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
        if (peer < 0) return;
        ucred credentials{};
        socklen_t size = sizeof(credentials);
        if (getsockopt(peer, SOL_SOCKET, SO_PEERCRED, &credentials, &size) != 0 || credentials.uid != geteuid()) {
            close(peer); return;
        }
        _peer = peer;
    }
    // Pending engagement/handoff must not hide EOF until its reply deadline.
    // A closed ownership socket is an immediate revocation, including when
    // unread bytes precede the peer's FIN.
    pollfd connection{_peer, POLLRDHUP, 0};
    if (::poll(&connection, 1, 0) > 0 && (connection.revents & (POLLRDHUP | POLLHUP | POLLERR))) {
        closePeer(); return;
    }
    if (!_output.empty()) {
        if (now - _output_since >= _reply_timeout_s) { closePeer(); return; }
        flush();
        if (!_output.empty() || _peer < 0) return;
    }
    if (!_pending) {
        std::array<char, 4096> buffer{};
        const auto count = recv(_peer, buffer.data(), buffer.size(), MSG_DONTWAIT);
        if (count == 0) { closePeer(); return; }
        if (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) { closePeer(); return; }
        if (count > 0) _input.append(buffer.data(), count);
        if (_input.size() > kMaximumMessageBytes) { closePeer(); return; }
        const auto newline = _input.find('\n');
        if (newline == std::string::npos) return;
        try {
            auto request = decodeRequest(_input.substr(0, newline));
            _input.erase(0, newline + 1);
            if ((_last_request && request.request_id <= *_last_request)
                    || (_generation && request.generation != *_generation)) {
                closePeer(); return;
            }
            _last_request = request.request_id; _generation = request.generation;
            _pending = std::move(request); _pending_since = now;
        } catch (const std::exception&) { closePeer(); return; }
    }
    if (now - _pending_since >= _reply_timeout_s) { closePeer(); return; }
    try {
        auto result = _handler(*_pending);
        if (!result) return;
        _output = encodeReply(*_pending, *result);
    } catch (const std::invalid_argument& error) {
        _output = encodeError(*_pending, error.what());
    } catch (const std::exception&) {
        _output = encodeError(*_pending, "native_request_failed");
    }
    _pending.reset();
    if (_output.size() > kMaximumMessageBytes) { closePeer(); return; }
    _output_since = now;
    flush();
}

} // namespace pixeagle
