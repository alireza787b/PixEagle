#pragma once

#include <pixeagle/command_lease.hpp>
#include <optional>

namespace pixeagle {

// Pinned Commander publishes vehicle status on change or every 500 ms;
// VTOL status is published on change or at 1 Hz.
// The periodic sample interval is separate from the transport-delay allowance.
inline constexpr double vehicle_status_heartbeat_s = .5;
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
    return fresh(vehicle_received, vehicle_status_heartbeat_s + delay_allowance_s)
        && (!is_vtol || fresh(vtol_received, vtol_status_heartbeat_s + delay_allowance_s));
}

enum class TransitionDirection { Unknown, ToFixedWing, ToMulticopter };

inline bool transitionDirectionsAgree(bool transition_announced, TransitionDirection accepted,
                                      TransitionDirection helper) {
    return transition_announced && accepted != TransitionDirection::Unknown && accepted == helper;
}

inline bool observedPursuitPhaseExit(Phase initial, bool vehicle_fresh, bool transition_announced,
                                     Phase vehicle_phase, bool vtol_fresh, Phase vtol_phase) {
    if (initial == Phase::Unknown) return false;
    return (vehicle_fresh && (transition_announced || (vehicle_phase != Phase::Unknown && vehicle_phase != initial)))
        || (vtol_fresh && vtol_phase != Phase::Unknown && vtol_phase != initial);
}

// VehicleStatus and VtolVehicleStatus arrive independently. Positive transition
// evidence ends pursuit; settled operation requires both sources to agree.
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
