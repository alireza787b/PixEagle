#pragma once

#include <pixeagle/phase_observation.hpp>
#include <pixeagle/owned_mode_contract.hpp>
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <px4_ros2/control/setpoint_types/fixedwing/lateral_longitudinal.hpp>
#include <px4_ros2/control/vtol.hpp>
#include <px4_msgs/msg/vtol_vehicle_status.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <px4_msgs/msg/owned_mode_request.hpp>
#include <px4_msgs/msg/owned_mode_status.hpp>
#include <functional>
#include <algorithm>

namespace pixeagle {

// Registered once, including both command contracts. The protocol owner runs on
// the same ROS executor; no MAVSDK publisher participates in this mode.
class ExternalMode final : public px4_ros2::ModeBase {
public:
    explicit ExternalMode(rclcpp::Node& node, double status_timeout_s, double request_timeout_s, bool is_vtol);
    void onDeactivate() override;
    void updateSetpoint(float dt_s) override;

    void acquire(const Identity& identity, double expires);
    void advance(const Identity& previous, const Identity& next, OwnershipToken token);
    void submit(Intent intent, OwnershipToken token);
    void revoke();
    bool observedOwner() const;
    Phase observedPhase() const;
    bool fresh() const;
    PhaseSourceHealth phaseSourceHealth() const;
    double phaseReceived() const { return _is_vtol ? std::max(_status_received, _vtol_received) : _status_received; }
    bool rescue() const;
    const px4_msgs::msg::VehicleStatus& status() const { return _status; }
    bool owns(const Identity& identity) const { return _lease.identity() && *_lease.identity() == identity; }
    void requestActivation(const Identity& identity, OwnershipToken token, Objective hold, double expires);
    bool requestHandoff(const Identity& identity, OwnershipToken token);
    void disconnect();
    bool ownedContractAvailable() const;
    Json acquisition(const std::string& runtime) const;
    Json releaseReceipt(const std::string& runtime) const;
    bool acquisitionOutstanding() const;
    std::uint64_t publications() const { return _publications; }
    using PhaseHoldProvider = std::function<std::optional<Objective>(Phase, const std::optional<Objective>&)>;
    void setPhaseHoldProvider(PhaseHoldProvider provider) { _phase_hold_provider = std::move(provider); }
    bool phaseHoldActive() const { return _phase_hold_active; }
    const std::string& phaseHoldFailure() const { return _phase_hold_failure; }

private:
    static double monotonicSeconds();
    void requestOwnership(bool release);
    void observeOwnership();
    bool ownedStatusFresh() const;
    void publish(const Objective& objective);
    void stopOwnedMode();
    std::shared_ptr<px4_ros2::TrajectorySetpointType> _trajectory;
    std::shared_ptr<px4_ros2::FwLateralLongitudinalSetpointType> _fixed_wing;
    std::shared_ptr<px4_ros2::VTOL> _vtol;
    rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr _status_subscription;
    rclcpp::Subscription<px4_msgs::msg::VtolVehicleStatus>::SharedPtr _vtol_subscription;
    rclcpp::Publisher<px4_msgs::msg::OwnedModeRequest>::SharedPtr _ownership_publisher;
    rclcpp::Subscription<px4_msgs::msg::OwnedModeStatus>::SharedPtr _ownership_subscription;
    px4_msgs::msg::OwnedModeStatus _ownership_status{};
    double _ownership_received{-1.};
    std::optional<OwnershipContext> _ownership_context;
    std::optional<px4_msgs::msg::OwnedModeRequest> _release_request;
    px4_msgs::msg::VehicleStatus _status{};
    px4_msgs::msg::VtolVehicleStatus _vtol_status{};
    double _status_received{-1.}, _vtol_received{-1.};
    const double _status_timeout_s;
    const double _request_timeout_s;
    const bool _is_vtol;
    CommandLease _lease;
    PhaseHoldProvider _phase_hold_provider;
    std::optional<Objective> _last_objective;
    bool _phase_hold_active{};
    std::string _phase_hold_failure;
    std::optional<Objective> _activation_hold;
    double _activation_expires{};
    std::uint64_t _publications{};
};

} // namespace pixeagle
