#pragma once

#include <cmath>
#include <cstdint>
#include <optional>

namespace pixeagle {

// Progress belongs to the source packet, not to its polling/publication rate.
// Reordered packets are ignored. A reset source cannot refresh the retained
// sample until it progresses beyond it; freshness then expires normally.
template<class Message> class SourceSample {
public:
    bool update(const Message& message, double received) {
        if (!std::isfinite(received) || received < 0. || message.timestamp == 0) return false;
        if (_value && message.timestamp < _value->timestamp) { ++_reordered; return false; }
        if (_value && (message.timestamp == _value->timestamp || received < _received)) return false;
        _value = message;
        _received = received;
        return true;
    }
    bool fresh(double now, double timeout) const {
        return _value && std::isfinite(now) && std::isfinite(timeout) && timeout > 0.
            && now >= _received && now - _received <= timeout;
    }
    const std::optional<Message>& value() const { return _value; }
    double received() const { return _received; }
    std::uint64_t reorderedPackets() const { return _reordered; }
private:
    std::optional<Message> _value;
    double _received{-1.};
    std::uint64_t _reordered{};
};

} // namespace pixeagle
