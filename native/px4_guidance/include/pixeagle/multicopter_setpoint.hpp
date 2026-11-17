#pragma once

#include <pixeagle/command_lease.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>

namespace pixeagle {

// Resolution of the AMSL reference belongs to AircraftObservations, not the SDK.
inline px4_ros2::TrajectorySetpoint multicopterAltitudeSetpoint(const MulticopterObjective& objective, float down) {
    validate(Objective{objective});
    if (!objective.altitude_amsl || !std::isfinite(down))
        throw std::invalid_argument("native_altitude_reference_unavailable");
    px4_ros2::TrajectorySetpoint setpoint;
    setpoint.withHorizontalVelocity(Eigen::Vector2f(objective.north, objective.east))
        .withPositionZ(down).withYawRate(static_cast<float>(objective.yaw_rate));
    return setpoint;
}

} // namespace pixeagle
