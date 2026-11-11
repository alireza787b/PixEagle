#pragma once

#include <cmath>
#include <cstdint>
#include <optional>

namespace pixeagle {

// Aggregate progress follows accepted source arrivals, never snapshot polls.
// It is independent of the oldest component's measurement-freshness clock.
class ObservationProgress {
public:
    std::uint64_t observe(double received) {
        if (std::isfinite(received) && received >= 0. && received > _received) {
            _received = received;
            ++_sequence;
        }
        return _sequence;
    }
private:
    double _received{-1.};
    std::uint64_t _sequence{};
};

// Packet progress and measurement progress have separate receipt clocks.
// Republishing an old sample cannot renew its first measurement receipt.
// Reordered packets are ignored. A reset source cannot refresh the retained
// sample until it progresses beyond it; freshness then expires normally.
template<class Message> class SourceSample {
public:
    bool update(const Message& message, double received) {
        return update(message, received, message.timestamp);
    }
    bool update(const Message& message, double received, std::uint64_t sample_timestamp) {
        if (!std::isfinite(received) || received < 0. || message.timestamp == 0) return false;
        if (_value && message.timestamp < _value->timestamp) { ++_reordered; return false; }
        if (_value && (message.timestamp == _value->timestamp || received < _received)) return false;
        _value = message;
        _received = received;
        _sample_valid = sample_timestamp > 0 && sample_timestamp <= message.timestamp;
        if (_sample_valid && sample_timestamp > _sample_timestamp) {
            _sample_timestamp = sample_timestamp;
            _sample_received = received;
        } else if (_sample_valid && sample_timestamp < _sample_timestamp) {
            _sample_valid = false;
        }
        return true;
    }
    bool fresh(double now, double timeout) const {
        return _value && std::isfinite(now) && std::isfinite(timeout) && timeout > 0.
            && now >= _received && now - _received <= timeout;
    }
    bool sampleFresh(double now, double timeout) const {
        if (!fresh(now, timeout) || !_sample_valid || now < _sample_received
                || now - _sample_received > timeout) return false;
        const double processing_age = double(_value->timestamp - _sample_timestamp) * 1e-6;
        return processing_age + now - _received <= timeout;
    }
    const std::optional<Message>& value() const { return _value; }
    double received() const { return _received; }
    double sampleReceived() const { return _sample_received; }
    std::uint64_t reorderedPackets() const { return _reordered; }
private:
    std::optional<Message> _value;
    double _received{-1.};
    std::uint64_t _sample_timestamp{};
    double _sample_received{-1.};
    bool _sample_valid{};
    std::uint64_t _reordered{};
};

} // namespace pixeagle
