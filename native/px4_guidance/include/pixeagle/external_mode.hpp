#pragma once

#include <pixeagle/phase_observation.hpp>
#include <pixeagle/owned_mode_contract.hpp>
#include <pixeagle/neutral_release.hpp>
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
    bool registrationConfirmed() const { return _registration_proof.ready() && ownedContractAvailable(); }
    Json acquisition(const std::string& runtime) const;
    Json releaseReceipt(const std::string& runtime) const;
    bool acquisitionOutstanding() const;
    std::uint64_t publications() const { return _publications; }
    using NeutralProvider = std::function<std::optional<NativeNeutralInput>()>;
    void setNeutralProvider(NeutralProvider provider) { _neutral_provider = std::move(provider); }
    bool releasePending() const { return _ownership_context && _ownership_context->release_pending; }
    bool neutralDrainActive() const { return _neutral_drain_active; }
    const std::string& neutralDrainFailure() const { return _neutral_drain_failure; }

private:
    static double monotonicSeconds();
    void requestOwnership(bool release);
    void observeOwnership();
    bool ownedStatusFresh() const;
    bool publish(const Objective& objective);
    void stopOwnedMode();
    NativeActivationEvidence activationEvidence() const;
    void endPursuitOnPhaseExit();
    void drainNeutral();
    bool transitionDirectionConfirmed() const;
    Phase vehiclePhase() const;
    Phase vtolPhase() const;
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
    RegistrationProof _registration_proof;
    std::optional<px4_msgs::msg::OwnedModeRequest> _release_request;
    px4_msgs::msg::VehicleStatus _status{};
    px4_msgs::msg::VtolVehicleStatus _vtol_status{};
    double _status_received{-1.}, _vtol_received{-1.};
    const double _status_timeout_s;
    const double _request_timeout_s;
    const bool _is_vtol;
    CommandLease _lease;
    NeutralProvider _neutral_provider;
    Phase _engagement_phase{Phase::Unknown};
    bool _neutral_drain_active{};
    std::string _neutral_drain_failure;
    std::optional<Objective> _activation_hold;
    double _activation_expires{};
    std::uint64_t _publications{};
};

} // namespace pixeagle
