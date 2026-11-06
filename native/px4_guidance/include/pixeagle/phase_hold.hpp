#pragma once

#include <pixeagle/command_lease.hpp>
#include <algorithm>

namespace pixeagle {

// Holding during a contract change uses native envelope observations. The
// caller must first validate the existing lease; this function cannot renew it.
inline Objective phaseHold(Phase phase, const std::optional<Objective>& previous, double heading,
                           double minimum, double trim, double maximum) {
    if (phase == Phase::Multicopter) return MulticopterObjective{};
    if (phase != Phase::FixedWing && phase != Phase::Transition)
        throw std::invalid_argument("native_phase_hold_unavailable");
    for (double value : {heading, minimum, trim, maximum})
        if (!std::isfinite(value)) throw std::invalid_argument("native_phase_hold_envelope_invalid");
    // PX4 raises the minimum with load factor; it may exceed trim in a turn.
    if (!(0. < minimum && minimum <= maximum && 0. < trim && trim <= maximum))
        throw std::invalid_argument("native_phase_hold_envelope_invalid");
    double course = heading, speed = trim;
    std::optional<double> altitude;
    if (previous) {
        validate(*previous);
        if (const auto* fw = std::get_if<FixedWingObjective>(&*previous)) {
            course = fw->course;
            speed = fw->equivalent_airspeed;
            altitude = fw->altitude_amsl;
        } else if (const auto* transition = std::get_if<TransitionObjective>(&*previous)) {
            course = transition->course;
            speed = transition->equivalent_airspeed;
        }
    }
    speed = std::clamp(speed, minimum, maximum);
    Objective result = phase == Phase::Transition ? Objective{TransitionObjective{course, speed}}
        : Objective{FixedWingObjective{course, speed, altitude ? std::optional<double>{} : 0., altitude}};
    validate(result);
    return result;
}

} // namespace pixeagle
