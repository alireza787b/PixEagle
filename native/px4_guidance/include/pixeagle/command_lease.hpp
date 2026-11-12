#pragma once

#include <cmath>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>

namespace pixeagle {

enum class Phase { Unknown, Multicopter, FixedWing, Transition };

struct Identity {
    std::string session;
    std::string aircraft;
    std::string connection;
    std::uint64_t telemetry_generation{};
    std::uint64_t guidance_generation{};

    bool operator==(const Identity& other) const {
        return session == other.session && aircraft == other.aircraft && connection == other.connection
            && telemetry_generation == other.telemetry_generation && guidance_generation == other.guidance_generation;
    }
};

struct FixedWingObjective {
    double course{};
    double equivalent_airspeed{};
    std::optional<double> height_rate;
    std::optional<double> altitude_amsl;
};

struct MulticopterObjective {
    double north{}, east{}, down{}, yaw_rate{};
};

// Transition objectives do not request a transition. PX4's VTOL helper supplies
// the native acceleration setpoints for the already observed transition.
struct TransitionObjective {
    double course{};
    double equivalent_airspeed{};
};

using Objective = std::variant<FixedWingObjective, MulticopterObjective, TransitionObjective>;

inline Phase phaseOf(const Objective& objective) {
    if (std::holds_alternative<FixedWingObjective>(objective)) return Phase::FixedWing;
    if (std::holds_alternative<MulticopterObjective>(objective)) return Phase::Multicopter;
    return Phase::Transition;
}

inline void validate(const Objective& objective) {
    const auto finite = [](double value) {
        // The native PX4 interface uses float. A finite JSON double must also
        // remain finite at that boundary, without an arbitrary speed ceiling.
        if (!std::isfinite(value) || !std::isfinite(static_cast<float>(value)))
            throw std::invalid_argument("native_value_not_representable");
    };
    if (const auto* fw = std::get_if<FixedWingObjective>(&objective)) {
        finite(fw->course);
        finite(fw->equivalent_airspeed);
        if (fw->equivalent_airspeed <= 0 || fw->height_rate.has_value() == fw->altitude_amsl.has_value())
            throw std::invalid_argument("native_fixed_wing_contract_invalid");
        finite(fw->height_rate ? *fw->height_rate : *fw->altitude_amsl);
    } else if (const auto* mc = std::get_if<MulticopterObjective>(&objective)) {
        for (double value : {mc->north, mc->east, mc->down, mc->yaw_rate}) finite(value);
    } else {
        const auto& transition = std::get<TransitionObjective>(objective);
        finite(transition.course);
        finite(transition.equivalent_airspeed);
        if (transition.equivalent_airspeed <= 0) throw std::invalid_argument("native_transition_speed_invalid");
    }
}

struct Intent {
    Identity identity;
    std::uint64_t sequence{};
    double created{}, expires{};
    Objective objective;
};

class CommandLease {
public:
    void acquire(Identity identity, double now, double expires) {
        if (!std::isfinite(now) || !std::isfinite(expires) || expires <= now)
            throw std::invalid_argument("native_intent_expired");
        if (_identity || identity.session.empty() || identity.aircraft.empty() || identity.connection.empty())
            throw std::invalid_argument("native_session_invalid");
        _identity = std::move(identity);
        _expires = expires;
        _contract_phase.reset();
        _last_sequence.reset();
    }

    void submit(Intent intent, double now, Phase observed_phase) {
        if (!_identity || !(*_identity == intent.identity)) throw std::invalid_argument("native_session_stale");
        if (observed_phase == Phase::Unknown) { revoke(); throw std::invalid_argument("native_phase_unknown"); }
        if (observed_phase == Phase::Transition) { revoke(); throw std::invalid_argument("native_transition_pursuit_unsupported"); }
        if (_contract_phase && *_contract_phase != observed_phase) {
            revoke();
            throw std::invalid_argument("native_phase_changed");
        }
        if (now >= _expires) { revoke(); throw std::invalid_argument("native_intent_expired"); }
        if (!std::isfinite(now) || !std::isfinite(intent.created) || !std::isfinite(intent.expires)
                || intent.created > now || now >= intent.expires || intent.expires <= intent.created)
            throw std::invalid_argument("native_intent_expired");
        if (_last_sequence && intent.sequence <= *_last_sequence) throw std::invalid_argument("native_intent_obsolete");
        if (observed_phase == Phase::Unknown || phaseOf(intent.objective) != observed_phase)
            throw std::invalid_argument("native_command_phase_mismatch");
        validate(intent.objective);
        _contract_phase = observed_phase;
        _last_sequence = intent.sequence;
        _expires = intent.expires;
        _intent = std::move(intent);
    }

    const Intent* current(double now, Phase phase, bool owner, bool fresh, bool rescue) {
        if (!owner || !fresh || rescue || phase == Phase::Unknown || phase == Phase::Transition || !std::isfinite(now)) { revoke(); return nullptr; }
        if (now >= _expires) { revoke(); return nullptr; }
        if (!_intent) return nullptr;
        if (now < _intent->created || now >= _intent->expires) { revoke(); return nullptr; }
        if (phaseOf(_intent->objective) != phase) { revoke(); return nullptr; }
        return &*_intent;
    }

    void revoke() { _identity.reset(); _intent.reset(); _last_sequence.reset(); _contract_phase.reset(); }
    const std::optional<Identity>& identity() const { return _identity; }

private:
    double _expires{};
    std::optional<Phase> _contract_phase;
    std::optional<Identity> _identity;
    std::optional<std::uint64_t> _last_sequence;
    std::optional<Intent> _intent;
};

} // namespace pixeagle
