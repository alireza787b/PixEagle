#pragma once

#include <pixeagle/command_lease.hpp>

namespace pixeagle {

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
