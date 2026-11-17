#pragma once

#include <pixeagle/command_lease.hpp>
#include <pixeagle/phase_observation.hpp>
#include <algorithm>

namespace pixeagle {

struct NativeNeutralInput {
    double fw_heading{}, minimum_eas{}, trim_eas{}, maximum_eas{};
};

// Neutral cleanup has no target, prior pursuit objective, altitude hold or speed override.
inline Objective neutralReleaseObjective(Phase phase, double native_fw_heading,
                                         double minimum, double trim, double maximum) {
    if (phase == Phase::Multicopter) return MulticopterObjective{};
    if (phase != Phase::FixedWing && phase != Phase::Transition)
        throw std::invalid_argument("native_neutral_phase_unavailable");
    for (double value : {native_fw_heading, minimum, trim, maximum})
        if (!std::isfinite(value)) throw std::invalid_argument("native_neutral_envelope_invalid");
    if (!(0. < minimum && minimum <= maximum && trim > 0.))
        throw std::invalid_argument("native_neutral_envelope_invalid");
    const auto speed = std::clamp(trim, minimum, maximum);
    Objective result = phase == Phase::Transition ? Objective{TransitionObjective{native_fw_heading, speed}}
        : Objective{FixedWingObjective{native_fw_heading, speed, 0., {}}};
    validate(result);
    return result;
}

} // namespace pixeagle
