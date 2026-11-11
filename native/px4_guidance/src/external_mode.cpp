#include <pixeagle/external_mode.hpp>
#include <pixeagle/phase_observation.hpp>
#include <px4_ros2/utils/message_version.hpp>
#include <chrono>

namespace pixeagle {

double ExternalMode::monotonicSeconds() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

ExternalMode::ExternalMode(rclcpp::Node& node, double status_timeout_s, double request_timeout_s, bool is_vtol)
    : ModeBase(node, Settings{"PixEagle Vector"}.userSelectable(false)),
      _status_timeout_s(status_timeout_s), _request_timeout_s(request_timeout_s), _is_vtol(is_vtol) {
    if (!std::isfinite(status_timeout_s) || status_timeout_s <= 0.)
        throw std::invalid_argument("native_status_timeout_invalid");
    if (!std::isfinite(request_timeout_s) || request_timeout_s <= 0.)
        throw std::invalid_argument("native_request_timeout_invalid");
    if (is_vtol) {
        _trajectory = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
        _vtol = std::make_shared<px4_ros2::VTOL>(*this);
    }
    _fixed_wing = std::make_shared<px4_ros2::FwLateralLongitudinalSetpointType>(*this);
    setSetpointUpdateRate(30.f);
    _ownership_publisher = node.create_publisher<px4_msgs::msg::OwnedModeRequest>(
        "fmu/in/owned_mode_request" + px4_ros2::getMessageNameVersion<px4_msgs::msg::OwnedModeRequest>(), 4);
    _ownership_subscription = node.create_subscription<px4_msgs::msg::OwnedModeStatus>(
        "fmu/out/owned_mode_status" + px4_ros2::getMessageNameVersion<px4_msgs::msg::OwnedModeStatus>(),
        rclcpp::SensorDataQoS(), [this](px4_msgs::msg::OwnedModeStatus::ConstSharedPtr message) {
            if (message->contract_version != ownership_contract_version
                    || (message->incarnation[0] == 0 && message->incarnation[1] == 0)) return;
            if (_ownership_context && std::to_string(message->autopilot_uid) != _ownership_context->identity.aircraft) return;
            const bool progresses = _ownership_context
                ? _ownership_context->observePublication(_ownership_status.timestamp, _ownership_status.incarnation,
                    _ownership_status.source_clock_us, message->timestamp, message->incarnation, message->source_clock_us)
                : ownershipPublicationProgresses(_ownership_status.timestamp, _ownership_status.incarnation,
                    _ownership_status.source_clock_us, message->timestamp, message->incarnation, message->source_clock_us);
            if (_ownership_context && _ownership_context->retired) revoke();
            if (!progresses) return;
            _ownership_status = *message;
            _ownership_received = monotonicSeconds();
            observeOwnership();
            if (!observedOwner()) revoke();
        });
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
    return _status.is_vtol == _is_vtol
        && phaseSourcesFresh(now, _status_received, _vtol_received, _is_vtol, _status_timeout_s);
}

PhaseSourceHealth ExternalMode::phaseSourceHealth() const {
    const double now = monotonicSeconds();
    const auto age = [now](double received) -> std::optional<double> {
        return received >= 0. && now >= received ? std::optional<double>{now - received} : std::nullopt;
    };
    return {age(_status_received), _is_vtol ? age(_vtol_received) : std::nullopt, _status_timeout_s,
        _is_vtol ? std::optional<double>{vtol_status_heartbeat_s + _status_timeout_s} : std::nullopt};
}

bool ExternalMode::rescue() const {
    return _status.failsafe || _status.failsafe_and_user_took_over
        || (_status.is_vtol && _vtol_status.fixed_wing_system_failure);
}

bool ExternalMode::observedOwner() const {
    if (!_ownership_context || _ownership_context->retired || !ownedContractAvailable()) return false;
    const auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    return fresh() && !rescue() && status.owner_active
        && std::to_string(status.autopilot_uid) == context.identity.aircraft
        && context.acquired_epoch > 0 && context.acquired_epoch == status.acquired_nav_state_timestamp
        && context.matches(status.token, status.incarnation, status.source_revision,
                           status.source_nav_state_timestamp, status.source_nav_state, status.mode_id, status.registration_id)
        && status.nav_state == context.mode && status.nav_state_timestamp == context.acquired_epoch
        && _status.nav_state == context.mode && _status.nav_state_timestamp == context.acquired_epoch
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
    if (!observedOwner() || !_ownership_context || !(_ownership_context->identity == identity))
        throw std::invalid_argument("native_ownership_not_confirmed");
    _lease.acquire(identity, monotonicSeconds(), expires);
    _activation_hold.reset();
    _last_objective.reset();
    _phase_hold_failure.clear();
}

void ExternalMode::advance(const Identity& previous, const Identity& next, OwnershipToken token) {
    if (!_ownership_context) throw std::invalid_argument("native_session_stale");
    _ownership_context->requireToken(token);
    if (!observedOwner()) { revoke(); throw std::invalid_argument("native_ownership_lost"); }
    _lease.advance(previous, next);
}

void ExternalMode::submit(Intent intent, OwnershipToken token) {
    if (!_ownership_context) throw std::invalid_argument("native_session_stale");
    _ownership_context->requireToken(token);
    if (!observedOwner()) { revoke(); throw std::invalid_argument("native_ownership_lost"); }
    _lease.submit(std::move(intent), monotonicSeconds(), observedPhase());
}

void ExternalMode::revoke() {
    _lease.revoke();
    _phase_hold_active = false;
    _last_objective.reset();
}
void ExternalMode::onDeactivate() { revoke(); _activation_hold.reset(); }

bool ExternalMode::ownedStatusFresh() const {
    const auto now = monotonicSeconds();
    return _ownership_received >= 0. && now >= _ownership_received && now - _ownership_received < _status_timeout_s;
}

bool ExternalMode::ownedContractAvailable() const {
    return ownedStatusFresh() && _ownership_status.available
        && _ownership_status.contract_version == ownership_contract_version
        && _ownership_status.source_clock_us > 0
        && (_ownership_status.incarnation[0] != 0 || _ownership_status.incarnation[1] != 0);
}

void ExternalMode::observeOwnership() {
    if (!_ownership_context || _ownership_context->retired || !ownedContractAvailable()) return;
    auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    if (!context.matches(status.token, status.incarnation, status.source_revision,
                         status.source_nav_state_timestamp, status.source_nav_state, status.mode_id, status.registration_id)) return;
    if (context.acquired_epoch == 0 && status.acquired_nav_state_timestamp > 0) {
        // This is the original firmware-correlated epoch, including a terminal receipt.
        // It is never copied from current VehicleStatus or a replacement activation.
        context.acquired_epoch = status.acquired_nav_state_timestamp;
    }
}

bool ExternalMode::acquisitionOutstanding() const {
    if (!_ownership_context) return false;
    if (_ownership_context->retired) return true;
    const auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    if (!ownedContractAvailable() || !context.matches(status.token, status.incarnation, status.source_revision,
            status.source_nav_state_timestamp, status.source_nav_state, status.mode_id, status.registration_id)) return true;
    return status.state == status.STATE_PENDING || status.state == status.STATE_ACQUIRED || status.state == status.STATE_RELEASING;
}

Json ExternalMode::acquisition(const std::string& runtime) const {
    return _ownership_context ? _ownership_context->wire(runtime) : Json(nullptr);
}

Json ExternalMode::releaseReceipt(const std::string& runtime) const {
    if (!_ownership_context) return nullptr;
    const auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    std::string outcome = "unconfirmed";
    if (!context.retired && ownedContractAvailable() && std::to_string(status.autopilot_uid) == context.identity.aircraft
            && context.matches(status.token, status.incarnation, status.source_revision,
            status.source_nav_state_timestamp, status.source_nav_state, status.mode_id, status.registration_id)) {
        if (status.state == status.STATE_RELEASED && status.nav_state == px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER
                && status.nav_state_timestamp > context.acquired_epoch && !status.rescue_active) outcome = "hold_confirmed";
        else if (status.state == status.STATE_CANCELLED || status.state == status.STATE_REJECTED
                || status.state == status.STATE_EXPIRED || status.state == status.STATE_SUPERSEDED) outcome = "owner_already_released";
    }
    return {{"acquisition", context.wire(runtime)}, {"outcome", outcome},
        {"observed_nav_state", status.nav_state}, {"observed_nav_state_timestamp", status.nav_state_timestamp}};
}

void ExternalMode::requestOwnership(bool release) {
    if (!_ownership_context || _ownership_context->retired || !ownedContractAvailable()) throw std::invalid_argument("native_ownership_contract_unavailable");
    auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    if (context.incarnation != status.incarnation) throw std::invalid_argument("native_ownership_incarnation_changed");
    if (std::to_string(status.autopilot_uid) != context.identity.aircraft || status.system_id != _status.system_id
            || status.component_id != _status.component_id) throw std::invalid_argument("native_ownership_aircraft_changed");
    if (release && _release_request) return;
    px4_msgs::msg::OwnedModeRequest request{};
    request.contract_version = ownership_contract_version;
    request.operation = release ? request.OPERATION_RELEASE : request.OPERATION_ACQUIRE;
    request.incarnation = context.incarnation;
    request.token = context.token;
    request.source_revision = context.source_revision;
    request.source_nav_state = context.source_mode;
    request.source_nav_state_timestamp = context.source_epoch;
    request.mode_id = context.mode;
    request.registration_id = context.registration_id;
    request.acquired_nav_state_timestamp = release ? context.acquired_epoch : 0;
    request.source_clock_us = status.source_clock_us;
    const auto now = monotonicSeconds();
    request.expires_at_us = release ? ownershipDeadline(request.source_clock_us, now, now + _request_timeout_s) : context.expires;
    request.target_system = _status.system_id;
    request.target_component = _status.component_id;
    if (release) _release_request = request;
    _ownership_publisher->publish(request);
}

void ExternalMode::requestActivation(const Identity& identity, OwnershipToken token, Objective hold, double expires) {
    const auto now = monotonicSeconds();
    if (token[0] == 0 && token[1] == 0) throw std::invalid_argument("native_ownership_token_invalid");
    if (_lease.identity() || _activation_hold || acquisitionOutstanding() || !fresh() || rescue() || !ownedContractAvailable()
            || _status.nav_state == id() || _ownership_status.nav_state != _status.nav_state
            || _ownership_status.nav_state_timestamp != _status.nav_state_timestamp
            || _status.arming_state != px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED
            || !std::isfinite(expires) || expires <= now || phaseOf(hold) != observedPhase())
        throw std::invalid_argument("native_engagement_invalid");
    validate(hold);
    if (std::to_string(_ownership_status.autopilot_uid) != identity.aircraft || _ownership_status.system_id != _status.system_id
            || _ownership_status.component_id != _status.component_id) throw std::invalid_argument("native_ownership_aircraft_changed");
    const auto first_external = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL1;
    const auto last_external = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL8;
    if (id() < first_external || id() > last_external
            || _ownership_status.registration_ids[id() - first_external] == 0)
        throw std::invalid_argument("native_mode_registration_unavailable");
    _ownership_context = OwnershipContext{identity, token, _ownership_status.incarnation,
        _ownership_status.intention_revision, _status.nav_state_timestamp, 0,
        ownershipDeadline(_ownership_status.source_clock_us, now, expires), _status.nav_state, static_cast<std::uint8_t>(id()),
        _ownership_status.registration_ids[id() - first_external]};
    _release_request.reset();
    _activation_hold = std::move(hold);
    _activation_expires = expires;
    requestOwnership(false);
}

void ExternalMode::stopOwnedMode() {
    _activation_hold.reset();
    revoke();
    if (!_ownership_context || _release_request || !acquisitionOutstanding()) return;
    try { requestOwnership(true); } catch (const std::invalid_argument&) { /* Receipt stays unconfirmed. */ }
}

bool ExternalMode::requestHandoff(const Identity& identity, OwnershipToken token) {
    if (!_ownership_context || _ownership_context->identity.session != identity.session
            || _ownership_context->identity.aircraft != identity.aircraft
            || _ownership_context->identity.connection != identity.connection
            || _ownership_context->identity.telemetry_generation != identity.telemetry_generation)
        throw std::invalid_argument("native_session_stale");
    _ownership_context->requireToken(token);
    const bool owner = observedOwner();
    stopOwnedMode();
    return owner;
}

void ExternalMode::disconnect() {
    // Do not send any mode command after takeover. The firmware compare/change
    // also rejects a queued Hold if takeover occurs after this local check.
    stopOwnedMode();
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
