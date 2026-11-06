#include <pixeagle/external_mode.hpp>
#include <pixeagle/phase_observation.hpp>
#include <px4_ros2/utils/message_version.hpp>
#include <chrono>

namespace pixeagle {

double ExternalMode::monotonicSeconds() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

ExternalMode::ExternalMode(rclcpp::Node& node, double status_timeout_s, bool is_vtol)
    : ModeBase(node, Settings{"PixEagle Vector"}.userSelectable(false)),
      _status_timeout_s(status_timeout_s), _is_vtol(is_vtol) {
    if (!std::isfinite(status_timeout_s) || status_timeout_s <= 0.)
        throw std::invalid_argument("native_status_timeout_invalid");
    if (is_vtol) {
        _trajectory = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
        _vtol = std::make_shared<px4_ros2::VTOL>(*this);
    }
    _fixed_wing = std::make_shared<px4_ros2::FwLateralLongitudinalSetpointType>(*this);
    setSetpointUpdateRate(30.f);
    _command_publisher = node.create_publisher<px4_msgs::msg::VehicleCommand>(
        "fmu/in/vehicle_command" + px4_ros2::getMessageNameVersion<px4_msgs::msg::VehicleCommand>(), 1);
    _status_subscription = node.create_subscription<px4_msgs::msg::VehicleStatus>(
        "fmu/out/vehicle_status" + px4_ros2::getMessageNameVersion<px4_msgs::msg::VehicleStatus>(),
        rclcpp::SensorDataQoS(), [this](px4_msgs::msg::VehicleStatus::ConstSharedPtr message) {
            // Reordered/duplicate packets cannot renew source freshness.
            if (message->timestamp <= _status.timestamp) return;
            _status = *message;
            _status_received = monotonicSeconds();
            if (!observedOwner()) revoke();
        });
    _vtol_subscription = node.create_subscription<px4_msgs::msg::VtolVehicleStatus>(
        "fmu/out/vtol_vehicle_status" + px4_ros2::getMessageNameVersion<px4_msgs::msg::VtolVehicleStatus>(),
        rclcpp::SensorDataQoS(), [this](px4_msgs::msg::VtolVehicleStatus::ConstSharedPtr message) {
            if (message->timestamp <= _vtol_status.timestamp) return;
            _vtol_status = *message;
            _vtol_received = monotonicSeconds();
            if (rescue()) revoke();
        });
}

bool ExternalMode::fresh() const {
    const double now = monotonicSeconds();
    // This guards publication ownership, not the separately timestamped
    // high-rate pose or target observations.
    return _status.is_vtol == _is_vtol && now >= _status_received && now - _status_received < _status_timeout_s
        && (!_status.is_vtol || (now >= _vtol_received && now - _vtol_received < _status_timeout_s));
}

bool ExternalMode::rescue() const {
    return _status.failsafe || _status.failsafe_and_user_took_over
        || (_status.is_vtol && _vtol_status.fixed_wing_system_failure);
}

bool ExternalMode::observedOwner() const {
    return fresh() && !rescue() && _status.nav_state == id()
        && _status.arming_state == px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED;
}

Phase ExternalMode::observedPhase() const {
    using Status = px4_msgs::msg::VehicleStatus;
    const auto vehicle_phase = _status.vehicle_type == Status::VEHICLE_TYPE_ROTARY_WING ? Phase::Multicopter
        : _status.vehicle_type == Status::VEHICLE_TYPE_FIXED_WING ? Phase::FixedWing : Phase::Unknown;
    auto vtol_phase = Phase::Unknown;
    if (_status.is_vtol) {
        using Vtol = px4_msgs::msg::VtolVehicleStatus;
        if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_FW
                || _vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_MC)
            vtol_phase = Phase::Transition;
        else if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_MC) vtol_phase = Phase::Multicopter;
        else if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_FW) vtol_phase = Phase::FixedWing;
    }
    return resolveObservedPhase(fresh(), rescue(), _status.is_vtol, _status.in_transition_mode, vehicle_phase, vtol_phase);
}

void ExternalMode::acquire(const Identity& identity, double expires) {
    if (!observedOwner()) throw std::invalid_argument("native_ownership_not_confirmed");
    _lease.acquire(identity, monotonicSeconds(), expires);
    _activation_hold.reset();
    _last_objective.reset();
    _phase_hold_failure.clear();
}

void ExternalMode::advance(const Identity& previous, const Identity& next) {
    if (!observedOwner()) { revoke(); throw std::invalid_argument("native_ownership_lost"); }
    _lease.advance(previous, next);
}

void ExternalMode::submit(Intent intent) {
    if (!observedOwner()) { revoke(); throw std::invalid_argument("native_ownership_lost"); }
    _lease.submit(std::move(intent), monotonicSeconds(), observedPhase());
}

void ExternalMode::revoke() {
    _lease.revoke();
    _phase_hold_active = false;
    _last_objective.reset();
}
void ExternalMode::onDeactivate() { revoke(); _activation_hold.reset(); }

void ExternalMode::requestMode(std::uint8_t mode) {
    if (!fresh() || rescue()) throw std::invalid_argument("native_state_unavailable");
    px4_msgs::msg::VehicleCommand command{};
    command.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_SET_NAV_STATE;
    command.target_system = _status.system_id;
    command.target_component = _status.component_id;
    // MAV_COMP_ID_ONBOARD_COMPUTER; this mode is not a mode executor.
    constexpr std::uint16_t companion_component_id = 191;
    command.source_component = companion_component_id;
    command.from_external = true;
    command.param1 = mode;
    command.param2 = _status.nav_state;
    command.param5 = static_cast<double>(_status.nav_state_timestamp);
    _command_publisher->publish(command);
}

void ExternalMode::requestActivation(Objective hold, double expires) {
    const auto now = monotonicSeconds();
    if (_lease.identity() || _activation_hold || !fresh() || rescue()
            || _status.arming_state != px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED
            || !std::isfinite(expires) || expires <= now || phaseOf(hold) != observedPhase())
        throw std::invalid_argument("native_engagement_invalid");
    validate(hold);
    _hold_requested = false;
    _activation_hold = std::move(hold);
    _activation_expires = expires;
    requestMode(static_cast<std::uint8_t>(id()));
}

void ExternalMode::stopOwnedMode() {
    _activation_hold.reset();
    revoke();
    if (observedOwner() && !_hold_requested) {
        _handoff_from_epoch = _status.nav_state_timestamp;
        requestMode(px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER);
        _hold_requested = true;
    }
}

bool ExternalMode::requestHandoff(const Identity& identity) {
    if (!owns(identity)) throw std::invalid_argument("native_session_stale");
    const bool owner = observedOwner();
    stopOwnedMode();
    return owner;
}

void ExternalMode::disconnect() {
    // Do not send any mode command after takeover. The firmware compare/change
    // also rejects a queued Hold if takeover occurs after this local check.
    stopOwnedMode();
}

bool ExternalMode::holdObserved() const {
    return _hold_requested && fresh() && !rescue()
        && _status.nav_state == px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER
        && _status.nav_state_timestamp > _handoff_from_epoch;
}

void ExternalMode::updateSetpoint(float /*dt_s*/) {
    const auto phase = observedPhase();
    const Intent* intent = _lease.current(monotonicSeconds(), phase, observedOwner(), fresh(), rescue());
    _phase_hold_active = false;
    if (intent) { publish(intent->objective); return; }
    if (_lease.identity()) {
        // current() has checked ownership, source freshness, rescue and expiry.
        // A phase edge clears the old intent but retains its original lease.
        try {
            const auto hold = _phase_hold_provider ? _phase_hold_provider(phase, _last_objective) : std::nullopt;
            if (hold && phaseOf(*hold) == phase) {
                validate(*hold);
                _phase_hold_active = true;
                publish(*hold);
                return;
            }
            _phase_hold_failure = "native_phase_hold_observation_unavailable";
        } catch (const std::exception& error) {
            _phase_hold_failure = error.what();
        }
        stopOwnedMode();
        return;
    }
    if (_activation_hold && monotonicSeconds() < _activation_expires && observedOwner()
            && phaseOf(*_activation_hold) == observedPhase()) {
        publish(*_activation_hold);
        return;
    }
    if (!_lease.identity()) stopOwnedMode();
}

void ExternalMode::publish(const Objective& objective) {
    if (const auto* fw = std::get_if<FixedWingObjective>(&objective)) {
        px4_ros2::FwLateralLongitudinalSetpoint setpoint;
        setpoint.withCourse(static_cast<float>(fw->course)).withEquivalentAirspeed(static_cast<float>(fw->equivalent_airspeed));
        if (fw->height_rate) setpoint.withHeightRate(static_cast<float>(*fw->height_rate));
        else setpoint.withAltitude(static_cast<float>(*fw->altitude_amsl));
        // Use normal native longitudinal configuration. Experimental path
        // priority/upper-policy needs the owner-bound firmware extension.
        _fixed_wing->update(setpoint);
    } else if (const auto* mc = std::get_if<MulticopterObjective>(&objective)) {
        if (!_trajectory) { revoke(); return; }
        _trajectory->update(Eigen::Vector3f(mc->north, mc->east, mc->down), {}, {}, static_cast<float>(mc->yaw_rate));
    } else {
        if (!_trajectory || !_vtol) { revoke(); return; }
        const auto& transition = std::get<TransitionObjective>(objective);
        const auto native_state = _vtol->getCurrentState();
        if (native_state == px4_ros2::VTOL::State::TransitionToFixedWing
                || native_state == px4_ros2::VTOL::State::TransitionToMulticopter) {
            _trajectory->update(Eigen::Vector3f(NAN, NAN, 0.f), _vtol->computeAccelerationSetpointDuringTransition());
            _fixed_wing->updateWithHeightRate(0.f, static_cast<float>(transition.course),
                                              static_cast<float>(transition.equivalent_airspeed));
        } else if (native_state == px4_ros2::VTOL::State::Multicopter) {
            _trajectory->update(Eigen::Vector3f::Zero(), {}, {}, 0.f);
        } else if (native_state == px4_ros2::VTOL::State::FixedWing) {
            _fixed_wing->updateWithHeightRate(0.f, static_cast<float>(transition.course),
                                              static_cast<float>(transition.equivalent_airspeed));
        } else {
            revoke(); return;
        }
    }
    _last_objective = objective;
    ++_publications;
}

} // namespace pixeagle
