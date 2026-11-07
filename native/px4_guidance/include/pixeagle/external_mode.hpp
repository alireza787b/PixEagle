#pragma once

#include <pixeagle/phase_observation.hpp>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <px4_ros2/control/setpoint_types/fixedwing/lateral_longitudinal.hpp>
#include <px4_ros2/control/vtol.hpp>
#include <px4_msgs/msg/vtol_vehicle_status.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <functional>
#include <algorithm>

namespace pixeagle {

// Registered once, including both command contracts. The protocol owner runs on
// the same ROS executor; no MAVSDK publisher participates in this mode.
class ExternalMode final : public px4_ros2::ModeBase {
public:
    explicit ExternalMode(rclcpp::Node& node, double status_timeout_s, bool is_vtol);
    void onDeactivate() override;
    void updateSetpoint(float dt_s) override;

    void acquire(const Identity& identity, double expires);
    void advance(const Identity& previous, const Identity& next);
    void submit(Intent intent);
    void revoke();
    bool observedOwner() const;
    Phase observedPhase() const;
    bool fresh() const;
    PhaseSourceHealth phaseSourceHealth() const;
    double phaseReceived() const { return _is_vtol ? std::max(_status_received, _vtol_received) : _status_received; }
    bool rescue() const;
    const px4_msgs::msg::VehicleStatus& status() const { return _status; }
    bool owns(const Identity& identity) const { return _lease.identity() && *_lease.identity() == identity; }
    void requestActivation(Objective hold, double expires);
    bool requestHandoff(const Identity& identity);
    void disconnect();
    bool holdObserved() const;
    std::uint64_t publications() const { return _publications; }
    using PhaseHoldProvider = std::function<std::optional<Objective>(Phase, const std::optional<Objective>&)>;
    void setPhaseHoldProvider(PhaseHoldProvider provider) { _phase_hold_provider = std::move(provider); }
    bool phaseHoldActive() const { return _phase_hold_active; }
    const std::string& phaseHoldFailure() const { return _phase_hold_failure; }

private:
    static double monotonicSeconds();
    void requestMode(std::uint8_t mode);
    void publish(const Objective& objective);
    void stopOwnedMode();
    std::shared_ptr<px4_ros2::TrajectorySetpointType> _trajectory;
    std::shared_ptr<px4_ros2::FwLateralLongitudinalSetpointType> _fixed_wing;
    std::shared_ptr<px4_ros2::VTOL> _vtol;
    rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr _status_subscription;
    rclcpp::Subscription<px4_msgs::msg::VtolVehicleStatus>::SharedPtr _vtol_subscription;
    rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr _command_publisher;
    px4_msgs::msg::VehicleStatus _status{};
    px4_msgs::msg::VtolVehicleStatus _vtol_status{};
    double _status_received{-1.}, _vtol_received{-1.};
    const double _status_timeout_s;
    const bool _is_vtol;
    CommandLease _lease;
    PhaseHoldProvider _phase_hold_provider;
    std::optional<Objective> _last_objective;
    bool _phase_hold_active{};
    std::string _phase_hold_failure;
    std::optional<Objective> _activation_hold;
    double _activation_expires{};
    bool _hold_requested{};
    std::uint64_t _handoff_from_epoch{};
    std::uint64_t _publications{};
};

} // namespace pixeagle
