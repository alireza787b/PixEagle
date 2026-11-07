#pragma once

#include <pixeagle/command_lease.hpp>
#include <optional>

namespace pixeagle {

// Pinned PX4 publishes VTOL status immediately on change, otherwise at 1 Hz.
// The periodic sample interval is separate from the transport-delay allowance.
inline constexpr double vtol_status_heartbeat_s = 1.;

struct PhaseSourceHealth {
    std::optional<double> vehicle_age_s;
    std::optional<double> vtol_age_s;
    double vehicle_timeout_s;
    std::optional<double> vtol_timeout_s;
};

inline bool phaseSourcesFresh(double now, double vehicle_received, double vtol_received,
                              bool is_vtol, double delay_allowance_s) {
    if (!std::isfinite(now) || !std::isfinite(delay_allowance_s) || delay_allowance_s <= 0.) return false;
    const auto fresh = [now](double received, double timeout) {
        return std::isfinite(received) && received >= 0. && now >= received && now - received < timeout;
    };
    return fresh(vehicle_received, delay_allowance_s)
        && (!is_vtol || fresh(vtol_received, vtol_status_heartbeat_s + delay_allowance_s));
}

// VehicleStatus and VtolVehicleStatus arrive independently. Positive transition
// evidence pauses pursuit; settled pursuit requires both sources to agree.
inline Phase resolveObservedPhase(bool fresh, bool rescue, bool is_vtol, bool transition_announced,
                                  Phase vehicle_phase, Phase vtol_phase) {
    if (!fresh || rescue || vehicle_phase == Phase::Unknown) return Phase::Unknown;
    if (!is_vtol) return vehicle_phase;
    if (vtol_phase == Phase::Unknown) return Phase::Unknown;
    if (transition_announced || vtol_phase == Phase::Transition || vehicle_phase != vtol_phase)
        return Phase::Transition;
    return vehicle_phase;
}

} // namespace pixeagle
