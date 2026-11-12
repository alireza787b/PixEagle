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
    setAutomaticUnregister(false);
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
                    || (message->incarnation[0] == 0 && message->incarnation[1] == 0)
                    || message->timestamp == 0 || message->source_clock_us == 0) return;
            const bool progresses = _ownership_context
                ? _ownership_context->observePublication(_ownership_status.timestamp, _ownership_status.incarnation,
                    _ownership_status.source_clock_us, message->timestamp, message->incarnation, message->source_clock_us)
                : ownershipPublicationProgresses(_ownership_status.timestamp, _ownership_status.incarnation,
                    _ownership_status.source_clock_us, message->timestamp, message->incarnation, message->source_clock_us);
            if (_ownership_context && _ownership_context->retired) revoke();
            const auto first = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL1;
            const auto last = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL8;
            if (id() >= first && id() <= last) {
                _registration_proof.observe(registrationRequestId(), message->registration_ids[id() - first],
                    message->incarnation, message->autopilot_uid, message->system_id, message->component_id, progresses);
                if (_registration_proof.retired()) {
                    _activation_hold.reset();
                    if (_ownership_context) _ownership_context->retired = true;
                    revoke();
                    throw std::runtime_error("native_registration_lost");
                }
            }
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
            endPursuitOnPhaseExit();
            if (!observedOwner()) revoke();
        });
    _vtol_subscription = node.create_subscription<px4_msgs::msg::VtolVehicleStatus>(
        "fmu/out/vtol_vehicle_status" + px4_ros2::getMessageNameVersion<px4_msgs::msg::VtolVehicleStatus>(),
        rclcpp::SensorDataQoS(), [this](px4_msgs::msg::VtolVehicleStatus::ConstSharedPtr message) {
            if (message->timestamp <= _vtol_status.timestamp) return;
            _vtol_status = *message;
            _vtol_received = monotonicSeconds();
            endPursuitOnPhaseExit();
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

NativeActivationEvidence ExternalMode::activationEvidence() const {
    NativeActivationEvidence result;
    if (!_ownership_context) return result;
    const auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    using Status = px4_msgs::msg::VehicleStatus;
    if (context.mode < Status::NAVIGATION_STATE_EXTERNAL1 || context.mode > Status::NAVIGATION_STATE_EXTERNAL8) return result;
    result.token = status.token;
    result.incarnation = status.incarnation;
    result.source_revision = status.source_revision;
    result.source_epoch = status.source_nav_state_timestamp;
    result.acquired_epoch = status.acquired_nav_state_timestamp;
    result.actual_epoch = status.nav_state_timestamp;
    result.vehicle_epoch = _status.nav_state_timestamp;
    result.registration_id = status.registration_id;
    result.current_registration_id = status.registration_ids[context.mode - Status::NAVIGATION_STATE_EXTERNAL1];
    result.intention_revision = status.intention_revision;
    result.source_mode = status.source_nav_state;
    result.mode = status.mode_id;
    result.actual_mode = status.nav_state;
    result.vehicle_mode = _status.nav_state;
    result.ownership_fresh = ownedContractAvailable();
    result.ownership_rescue = status.rescue_active;
    result.vehicle_fresh = phaseSourcesFresh(monotonicSeconds(), _status_received, -1., false, _status_timeout_s);
    result.fresh = fresh() && result.ownership_fresh && _registration_proof.ready();
    result.aircraft_matches = std::to_string(status.autopilot_uid) == context.identity.aircraft
        && status.system_id == _status.system_id && status.component_id == _status.component_id;
    result.vehicle_armed = _status.arming_state == Status::ARMING_STATE_ARMED;
    result.vehicle_rescue = rescue();
    result.armed = status.armed && result.vehicle_armed;
    result.rescue = status.rescue_active || result.vehicle_rescue;
    result.owner_active = status.owner_active;
    switch (status.state) {
    case status.STATE_PENDING: result.state = OwnershipReceiptState::Pending; break;
    case status.STATE_ACQUIRED: result.state = OwnershipReceiptState::Acquired; break;
    case status.STATE_RELEASING: result.state = OwnershipReceiptState::Releasing; break;
    case status.STATE_RELEASED: result.state = OwnershipReceiptState::Released; break;
    case status.STATE_CANCELLED: result.state = OwnershipReceiptState::Cancelled; break;
    case status.STATE_REJECTED: result.state = OwnershipReceiptState::Rejected; break;
    case status.STATE_EXPIRED: result.state = OwnershipReceiptState::Expired; break;
    case status.STATE_SUPERSEDED: result.state = OwnershipReceiptState::Superseded; break;
    default: break;
    }
    return result;
}

bool ExternalMode::observedOwner() const {
    if (!_registration_proof.ready() || !_ownership_context) return false;
    const auto evidence = activationEvidence();
    return exactOriginalActivation(*_ownership_context, evidence)
        && evidence.state == OwnershipReceiptState::Acquired && evidence.owner_active;
}

Phase ExternalMode::vehiclePhase() const {
    using Status = px4_msgs::msg::VehicleStatus;
    return _status.vehicle_type == Status::VEHICLE_TYPE_ROTARY_WING ? Phase::Multicopter
        : _status.vehicle_type == Status::VEHICLE_TYPE_FIXED_WING ? Phase::FixedWing : Phase::Unknown;
}

Phase ExternalMode::vtolPhase() const {
    using Vtol = px4_msgs::msg::VtolVehicleStatus;
    if (!_is_vtol) return Phase::Unknown;
    if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_FW
            || _vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_MC) return Phase::Transition;
    if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_MC) return Phase::Multicopter;
    if (_vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_FW) return Phase::FixedWing;
    return Phase::Unknown;
}

Phase ExternalMode::observedPhase() const {
    return resolveObservedPhase(fresh(), rescue(), _status.is_vtol, _status.in_transition_mode, vehiclePhase(), vtolPhase());
}

void ExternalMode::endPursuitOnPhaseExit() {
    if (!_ownership_context || _ownership_context->pursuit_ended) return;
    const double now = monotonicSeconds();
    const auto recent = [now](double received, double budget) {
        return received >= 0. && now >= received && now - received < budget;
    };
    if (observedPursuitPhaseExit(_engagement_phase, recent(_status_received, _status_timeout_s),
            _status.in_transition_mode, vehiclePhase(), _is_vtol
            && recent(_vtol_received, vtol_status_heartbeat_s + _status_timeout_s), vtolPhase())) stopOwnedMode();
}

bool ExternalMode::transitionDirectionConfirmed() const {
    if (!_vtol || observedPhase() != Phase::Transition) return false;
    using Vtol = px4_msgs::msg::VtolVehicleStatus;
    const auto accepted = _vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_FW
        ? TransitionDirection::ToFixedWing : _vtol_status.vehicle_vtol_state == Vtol::VEHICLE_VTOL_STATE_TRANSITION_TO_MC
        ? TransitionDirection::ToMulticopter : TransitionDirection::Unknown;
    const auto state = _vtol->getCurrentState();
    const auto helper = state == px4_ros2::VTOL::State::TransitionToFixedWing ? TransitionDirection::ToFixedWing
        : state == px4_ros2::VTOL::State::TransitionToMulticopter ? TransitionDirection::ToMulticopter
        : TransitionDirection::Unknown;
    return transitionDirectionsAgree(_status.in_transition_mode, accepted, helper);
}

void ExternalMode::acquire(const Identity& identity, double expires) {
    endPursuitOnPhaseExit();
    if (_ownership_context) _ownership_context->requirePursuit();
    if (!observedOwner() || !_ownership_context || !(_ownership_context->identity == identity))
        throw std::invalid_argument("native_ownership_not_confirmed");
    _lease.acquire(identity, monotonicSeconds(), expires);
    _neutral_drain_failure.clear();
}

void ExternalMode::submit(Intent intent, OwnershipToken token) {
    if (!_ownership_context) throw std::invalid_argument("native_session_stale");
    _ownership_context->requireToken(token);
    endPursuitOnPhaseExit();
    _ownership_context->requirePursuit();
    if (!observedOwner()) { revoke(); throw std::invalid_argument("native_ownership_lost"); }
    _lease.submit(std::move(intent), monotonicSeconds(), observedPhase());
    _activation_hold.reset();
}

void ExternalMode::revoke() {
    _lease.revoke();
    _neutral_drain_active = false;
}
void ExternalMode::onDeactivate() {
    if (_ownership_context) _ownership_context->endPursuit(_lease);
    revoke();
    _activation_hold.reset();
}

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
    if (!_ownership_context || _ownership_context->terminal_release || _ownership_context->retired || !ownedContractAvailable()) return;
    auto& context = *_ownership_context;
    const auto& status = _ownership_status;
    if (!context.matches(status.token, status.incarnation, status.source_revision,
                         status.source_nav_state_timestamp, status.source_nav_state, status.mode_id, status.registration_id)) return;
    if (context.acquired_epoch == 0 && status.acquired_nav_state_timestamp > 0) {
        // This is the original firmware-correlated epoch, including a terminal receipt.
        // It is never copied from current VehicleStatus or a replacement activation.
        context.acquired_epoch = status.acquired_nav_state_timestamp;
    }
    if (context.observeTerminalRelease(activationEvidence(), px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_AUTO_LOITER, _lease)) {
        _activation_hold.reset();
        revoke();
        _neutral_drain_failure.clear();
    }
}

bool ExternalMode::acquisitionOutstanding() const {
    return _ownership_context && _ownership_context->acquisitionOutstanding();
}

Json ExternalMode::acquisition(const std::string& runtime) const {
    return _ownership_context ? _ownership_context->wire(runtime) : Json(nullptr);
}

Json ExternalMode::releaseReceipt(const std::string& runtime) const {
    if (!_ownership_context) return nullptr;
    return _ownership_context->releaseReceipt(runtime, _ownership_status.nav_state, _ownership_status.nav_state_timestamp);
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
    if (_lease.identity() || _activation_hold || acquisitionOutstanding() || !fresh() || rescue() || !registrationConfirmed()
            || _status.nav_state == id() || _ownership_status.nav_state != _status.nav_state
            || _ownership_status.nav_state_timestamp != _status.nav_state_timestamp
            || _status.arming_state != px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED
            || !std::isfinite(expires) || expires <= now || phaseOf(hold) == Phase::Transition
            || phaseOf(hold) != observedPhase())
        throw std::invalid_argument("native_engagement_invalid");
    validate(hold);
    if (std::to_string(_ownership_status.autopilot_uid) != identity.aircraft || _ownership_status.system_id != _status.system_id
            || _ownership_status.component_id != _status.component_id) throw std::invalid_argument("native_ownership_aircraft_changed");
    const auto first_external = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL1;
    const auto last_external = px4_msgs::msg::VehicleStatus::NAVIGATION_STATE_EXTERNAL8;
    if (id() < first_external || id() > last_external)
        throw std::invalid_argument("native_mode_registration_unavailable");
    const auto own_registration = requireOwnRegistration(registrationRequestId(),
        _ownership_status.registration_ids[id() - first_external]);
    _ownership_context = OwnershipContext{identity, token, _ownership_status.incarnation,
        _ownership_status.intention_revision, _status.nav_state_timestamp, 0,
        ownershipDeadline(_ownership_status.source_clock_us, now, expires), _status.nav_state, static_cast<std::uint8_t>(id()),
        own_registration};
    _release_request.reset();
    _engagement_phase = phaseOf(hold);
    _neutral_drain_failure.clear();
    _activation_hold = std::move(hold);
    _activation_expires = expires;
    requestOwnership(false);
}

void ExternalMode::stopOwnedMode() {
    if (_ownership_context) _ownership_context->endPursuit(_lease);
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
    // EOF ends pursuit. Cleanup remains tied to the original acquisition;
    // firmware rejects it if authority changed after our last observation.
    stopOwnedMode();
}

void ExternalMode::drainNeutral() {
    _neutral_drain_active = false;
    if (_ownership_context && _ownership_context->terminal_release) return;
    if (!_ownership_context || !neutralDrainPermitted(*_ownership_context, activationEvidence())) {
        _neutral_drain_failure = "native_release_owner_unconfirmed";
        return;
    }
    const auto phase = observedPhase();
    if (phase == Phase::Transition && !transitionDirectionConfirmed()) {
        _neutral_drain_failure = "native_transition_direction_unconfirmed";
        return;
    }
    try {
        Objective objective{MulticopterObjective{}};
        if (phase != Phase::Multicopter) {
            const auto input = _neutral_provider ? _neutral_provider() : std::nullopt;
            if (!input) {
                _neutral_drain_failure = "native_neutral_observation_unavailable";
                return;
            }
            objective = neutralReleaseObjective(phase, input->fw_heading,
                input->minimum_eas, input->trim_eas, input->maximum_eas);
        }
        validate(objective);
        _neutral_drain_active = publish(objective);
        _neutral_drain_failure = _neutral_drain_active ? "" : "native_neutral_publication_unavailable";
    } catch (const std::exception& error) {
        _neutral_drain_failure = error.what();
    }
}

void ExternalMode::updateSetpoint(float /*dt_s*/) {
    _neutral_drain_active = false;
    endPursuitOnPhaseExit();
    if (_ownership_context && _ownership_context->pursuit_ended) {
        if (_ownership_context->terminal_release) return;
        // If stale ownership evidence prevented the first release dispatch,
        // try only that original release when it becomes qualified. Once sent,
        // stopOwnedMode preserves the same request and finite deadline.
        stopOwnedMode();
        drainNeutral();
        return;
    }
    const auto now = monotonicSeconds();
    const auto phase = observedPhase();
    // VehicleStatus can activate ModeBase before its correlated receipt reaches
    // this subscriber or main acquires the lease. Waiting never authorizes output.
    if (_activation_hold && _ownership_context) {
        if (startupActivationMayWait(*_ownership_context, activationEvidence(), now, _activation_expires)) {
            if (observedOwner() && phaseOf(*_activation_hold) == phase) publish(*_activation_hold);
            return;
        }
        stopOwnedMode();
        drainNeutral();
        return;
    }
    const Intent* intent = _lease.current(now, phase, observedOwner(), fresh(), rescue());
    if (intent && publish(intent->objective)) return;
    stopOwnedMode();
    drainNeutral();
}

bool ExternalMode::publish(const Objective& objective) {
    if (const auto* fw = std::get_if<FixedWingObjective>(&objective)) {
        px4_ros2::FwLateralLongitudinalSetpoint setpoint;
        setpoint.withCourse(static_cast<float>(fw->course)).withEquivalentAirspeed(static_cast<float>(fw->equivalent_airspeed));
        if (fw->height_rate) setpoint.withHeightRate(static_cast<float>(*fw->height_rate));
        else setpoint.withAltitude(static_cast<float>(*fw->altitude_amsl));
        // Use normal native longitudinal configuration. Experimental path
        // priority/upper-policy needs the owner-bound firmware extension.
        _fixed_wing->update(setpoint);
    } else if (const auto* mc = std::get_if<MulticopterObjective>(&objective)) {
        if (!_trajectory) { revoke(); return false; }
        _trajectory->update(Eigen::Vector3f(mc->north, mc->east, mc->down), {}, {}, static_cast<float>(mc->yaw_rate));
    } else {
        if (!_trajectory || !_vtol || !transitionDirectionConfirmed()) return false;
        const auto& transition = std::get<TransitionObjective>(objective);
        const auto acceleration = _vtol->computeAccelerationSetpointDuringTransition();
        if (!std::isfinite(acceleration.x()) || !std::isfinite(acceleration.y())) return false;
        _trajectory->update(Eigen::Vector3f(NAN, NAN, 0.f), acceleration);
        _fixed_wing->updateWithHeightRate(0.f, static_cast<float>(transition.course),
                                          static_cast<float>(transition.equivalent_airspeed));
    }
    ++_publications;
    return true;
}

} // namespace pixeagle
