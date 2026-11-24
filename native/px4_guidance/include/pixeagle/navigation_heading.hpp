#pragma once

#include <pixeagle/command_lease.hpp>

namespace pixeagle {

// FW heading is supplied by PX4 after its native tailsitter conversion. This
// selector deliberately performs no attitude or mount transform itself.
inline std::optional<double> navigationHeading(Phase phase, double mc_heading, double fw_heading,
                                               bool fw_frame_matches, double fw_attitude_age,
                                               double status_age, double timeout) {
    if (!std::isfinite(timeout) || timeout <= 0.) return {};
    if (phase == Phase::FixedWing) {
        if (!fw_frame_matches || !std::isfinite(fw_heading) || !std::isfinite(fw_attitude_age)
                || !std::isfinite(status_age) || fw_attitude_age < 0. || status_age < 0.
                || fw_attitude_age + status_age > timeout) return {};
        return fw_heading;
    }
    if ((phase == Phase::Multicopter || phase == Phase::Transition) && std::isfinite(mc_heading))
        return mc_heading;
    return {};
}

} // namespace pixeagle
