#include <pixeagle/aircraft_observations.hpp>
#include <pixeagle/navigation_heading.hpp>
#include <pixeagle/neutral_release.hpp>
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <limits>

namespace pixeagle {

double AircraftObservations::clock() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

AircraftObservations::AircraftObservations(rclcpp::Node& node, double timeout_s) : _timeout(timeout_s) {
    if (!std::isfinite(timeout_s) || timeout_s <= 0.) throw std::invalid_argument("native_status_timeout_invalid");
    subscribe(node, "fmu/out/vehicle_attitude", _attitude,
              [](const px4_msgs::msg::VehicleAttitude& message) { return message.timestamp_sample; });
    subscribe(node, "fmu/out/vehicle_local_position", _position);
    subscribe(node, "fmu/out/airspeed_validated", _airspeed);
    subscribe(node, "fmu/out/fixed_wing_guidance_status", _envelope);
}

void AircraftObservations::bind(const Json& binding, double now) {
    exactFields(binding, {"aircraft_uid", "connection_generation", "telemetry_generation"});
    nonemptyString(binding.at("aircraft_uid"));
    nonemptyString(binding.at("connection_generation"));
    unsignedInteger(binding.at("telemetry_generation"));
    if (!_envelope.fresh(now, _timeout)
            || std::to_string(_envelope.value()->autopilot_uid) != binding.at("aircraft_uid").get<std::string>())
        throw std::invalid_argument("native_aircraft_identity_unconfirmed");
    _binding = binding;
}

bool AircraftObservations::bindingMatches(const Identity& identity) const {
    return !_binding.is_null() && _binding.at("aircraft_uid") == identity.aircraft
        && _binding.at("connection_generation") == identity.connection
        && _binding.at("telemetry_generation") == identity.telemetry_generation;
}

std::optional<std::uint64_t> AircraftObservations::altitudeReferenceGeneration(double now) const {
    if (_binding.is_null() || !_position.fresh(now, _timeout) || !_envelope.fresh(now, _timeout)) return {};
    const auto& p = *_position.value();
    const auto& e = *_envelope.value();
    if (!(p.xy_valid && p.z_valid && p.v_xy_valid && p.v_z_valid && p.z_global && e.home_altitude_valid)
            || std::to_string(e.autopilot_uid) != _binding.at("aircraft_uid").get<std::string>()) return {};
    for (double value : {double(p.vx), double(p.vy), double(p.vz), double(p.z), double(p.ref_alt),
                         double(e.home_altitude_amsl)})
        if (!std::isfinite(value)) return {};
    const auto reference = std::make_tuple(p.ref_timestamp, e.home_update_count, p.z_reset_counter);
    if (!_reference || *_reference != reference) {
        if (_reference_generation == std::numeric_limits<std::uint64_t>::max()) return {};
        _reference = reference;
        ++_reference_generation;
    }
    return _reference_generation;
}

std::optional<float> AircraftObservations::altitudeHoldDown(const Identity& identity, double altitude_amsl,
                                                          std::uint64_t generation, double now) const {
    if (!bindingMatches(identity) || !nativeFloatRepresentable(altitude_amsl)) return {};
    const auto current = altitudeReferenceGeneration(now);
    if (!current || *current != generation) return {};
    const double down = double(_position.value()->ref_alt) - altitude_amsl;
    if (!nativeFloatRepresentable(down)) return {};
    return static_cast<float>(down);
}

Json AircraftObservations::health(double now) const {
    return {{"bound", !_binding.is_null()},
        {"out_of_order_packets", _attitude.reorderedPackets() + _position.reorderedPackets()
            + _airspeed.reorderedPackets() + _envelope.reorderedPackets()},
        {"attitude_fresh", _attitude.fresh(now, _timeout)}, {"position_fresh", _position.fresh(now, _timeout)},
        {"envelope_fresh", _envelope.fresh(now, _timeout)},
        {"airspeed_fresh", _airspeed.fresh(now, _timeout)},
        {"position_valid", _position.value() && _position.value()->xy_valid && _position.value()->z_valid
            && _position.value()->v_xy_valid && _position.value()->v_z_valid && _position.value()->z_global},
        {"home_altitude_valid", _envelope.value() && _envelope.value()->home_altitude_valid}};
}

Json AircraftObservations::pose(double now) const {
    if (!_position.fresh(now, _timeout) || !_attitude.fresh(now, _timeout)) return nullptr;
    const auto& p = *_position.value();
    const auto& q = _attitude.value()->q;
    if (!p.xy_valid || !p.z_valid) return nullptr;
    for (double value : {double(p.x), double(p.y), double(p.z), double(q[0]), double(q[1]), double(q[2]), double(q[3])})
        if (!std::isfinite(value)) return nullptr;
    return {{"vehicle_ned", {p.x, p.y, p.z}}, {"quaternion_wxyz", q}, {"px4_timestamp_us", p.timestamp},
        {"observed_at_monotonic_s", std::min(_position.received(), _attitude.received())}, {"source", "px4_dds_observed"}};
}

Json AircraftObservations::attitudeTiming(double now) const {
    if (!_attitude.sampleFresh(now, _timeout)) return nullptr;
    const auto& a = *_attitude.value();
    return {{"publication_timestamp_us", a.timestamp}, {"sample_timestamp_us", a.timestamp_sample},
        {"publication_received_at_monotonic_s", _attitude.received()},
        {"sample_received_at_monotonic_s", _attitude.sampleReceived()},
        {"quat_reset_counter", a.quat_reset_counter}, {"time_basis", "px4_uxrce_adjusted_us"}};
}

Json AircraftObservations::commandFeedback(double now) const {
    if (!_envelope.fresh(now, _timeout)) return nullptr;
    const auto& e = *_envelope.value();
    const auto finite = [](float value) { return std::isfinite(value) ? Json(value) : Json(nullptr); };
    return {{"observed_at_monotonic_s", _envelope.received()}, {"controller_active", e.controller_active},
        {"requested_eas_m_s", finite(e.requested_equivalent_airspeed)},
        {"effective_eas_m_s", finite(e.effective_equivalent_airspeed)},
        {"underspeed_ratio", finite(e.underspeed_ratio)}, {"airspeed_control_enabled", e.airspeed_control_enabled},
        {"fixed_wing_heading_rad", finite(e.fixed_wing_heading)},
        {"fixed_wing_forward_ned", e.fixed_wing_forward_ned},
        {"fixed_wing_frame_is_tailsitter", e.fixed_wing_frame_is_tailsitter},
        {"fixed_wing_attitude_age_s", finite(e.fixed_wing_attitude_sample_age)},
        {"nav_state", e.nav_state}, {"nav_state_timestamp", e.nav_state_timestamp}};
}

std::string AircraftObservations::firmware(double now) const {
    if (!_envelope.fresh(now, _timeout)) return {};
    std::ostringstream value;
    value << std::hex << std::setw(16) << std::setfill('0') << _envelope.value()->firmware_git_hash;
    return value.str();
}

std::optional<NativeNeutralInput> AircraftObservations::neutralFlightData(
        const px4_msgs::msg::VehicleStatus& status, double now) const {
    if (_binding.is_null() || !_envelope.fresh(now, _timeout) || !_position.fresh(now, _timeout)) return {};
    const auto& e = *_envelope.value();
    const auto& p = *_position.value();
    if (std::to_string(e.autopilot_uid) != _binding.at("aircraft_uid").get<std::string>()
            || !p.xy_valid || !p.v_xy_valid || !std::isfinite(p.heading)) return {};
    // The FW half of a transition needs PX4's FW frame, never the MC transition heading.
    const auto heading = navigationHeading(Phase::FixedWing, NAN, e.fixed_wing_heading,
        e.fixed_wing_frame_is_tailsitter == status.is_vtol_tailsitter,
        e.fixed_wing_attitude_sample_age, now - _envelope.received(), _timeout);
    if (!heading) return {};
    return NativeNeutralInput{*heading, e.minimum_equivalent_airspeed,
                              e.trim_equivalent_airspeed, e.maximum_equivalent_airspeed};
}

Json AircraftObservations::snapshot(const px4_msgs::msg::VehicleStatus& status, Phase phase, bool rescue,
                                    double phase_received, double now) const {
    if (_binding.is_null() || phase == Phase::Unknown
            || !_attitude.fresh(now, _timeout) || !_position.fresh(now, _timeout)
            || !_envelope.fresh(now, _timeout)) return nullptr;
    const auto& p = *_position.value();
    const auto& e = *_envelope.value();
    const auto& q = _attitude.value()->q;
    const auto heading = navigationHeading(phase, p.heading, e.fixed_wing_heading,
        e.fixed_wing_frame_is_tailsitter == status.is_vtol_tailsitter,
        e.fixed_wing_attitude_sample_age, now - _envelope.received(), _timeout);
    if (!heading) return nullptr;
    if (!(p.xy_valid && p.z_valid && p.v_xy_valid && p.v_z_valid && p.z_global && e.home_altitude_valid)
            || std::to_string(e.autopilot_uid) != _binding.at("aircraft_uid").get<std::string>()) return nullptr;
    for (double value : {double(p.vx), double(p.vy), double(p.vz), double(p.ref_alt), double(p.z), double(e.home_altitude_amsl),
                         double(q[0]), double(q[1]), double(q[2]), double(q[3])})
        if (!std::isfinite(value)) return nullptr;
    const double norm = std::hypot(std::hypot(q[0], q[1]), std::hypot(q[2], q[3]));
    if (std::abs(norm - 1.) > .001) return nullptr;
    Json envelope{{"minimum_eas_m_s", e.minimum_equivalent_airspeed}, {"trim_eas_m_s", e.trim_equivalent_airspeed},
        {"maximum_eas_m_s", e.maximum_equivalent_airspeed}, {"climb_rate_m_s", e.climb_rate_limit},
        {"sink_rate_m_s", e.sink_rate_limit}, {"bank_limit_rad", e.bank_limit},
        {"source", "px4_native_performance_model"}, {"revision", std::to_string(e.parameter_revision)},
        {"vertical_acceleration_limit_m_s2", e.vertical_acceleration_limit},
        {"altitude_response_time_s", e.altitude_response_time}};
    // An invalid controller envelope cannot become a fabricated fallback limit.
    for (const char* name : {"minimum_eas_m_s", "trim_eas_m_s", "maximum_eas_m_s", "climb_rate_m_s",
            "sink_rate_m_s", "bank_limit_rad", "vertical_acceleration_limit_m_s2", "altitude_response_time_s"}) {
        const auto value = envelope.at(name).get<double>();
        if (!std::isfinite(value) || value <= 0.) return nullptr;
    }
    Json air{{"source", "unavailable"}, {"equivalent_m_s", nullptr}, {"true_m_s", nullptr},
        {"observed_at_monotonic_s", std::max(0., _airspeed.received())}, {"valid", false}};
    if (_airspeed.fresh(now, _timeout)) {
        const auto& a = *_airspeed.value();
        using Air = px4_msgs::msg::AirspeedValidated;
        // Only the source selected and qualified by PX4 is eligible. A low
        // valid sensor reading is retained; groundspeed cannot replace it.
        const bool sensor = a.airspeed_source >= Air::SOURCE_SENSOR_1 && a.airspeed_source <= Air::SOURCE_SENSOR_3;
        const bool wind = a.airspeed_source == Air::SOURCE_GROUND_MINUS_WIND;
        if ((sensor || wind) && std::isfinite(a.calibrated_airspeed_m_s) && a.calibrated_airspeed_m_s >= 0.) {
            air["source"] = sensor ? "sensor" : "ground_minus_wind";
            air["equivalent_m_s"] = a.calibrated_airspeed_m_s;
            if (std::isfinite(a.true_airspeed_m_s) && a.true_airspeed_m_s >= 0.) air["true_m_s"] = a.true_airspeed_m_s;
            air["valid"] = true;
        }
    }
    const auto phase_name = phase == Phase::Multicopter ? "multicopter" : phase == Phase::FixedWing ? "fixed_wing" : "vtol_transition";
    const double altitude = double(p.ref_alt) - p.z;
    const auto reference_generation = altitudeReferenceGeneration(now);
    if (!reference_generation) return nullptr;
    const auto sequence = _progress.observe(std::max({phase_received, _position.received(), _attitude.received(),
        _envelope.received(), _airspeed.received()}));
    return {{"binding", _binding}, {"sequence", sequence}, {"source", "px4_dds_native"},
        {"observed_at_monotonic_s", std::min({_position.received(), _attitude.received(), _envelope.received()})},
        {"phase", phase_name}, {"is_vtol", status.is_vtol}, {"is_tailsitter", status.is_vtol_tailsitter},
        {"rescue_active", rescue}, {"attitude_body_to_ned", {{"w", q[0]}, {"x", q[1]}, {"y", q[2]}, {"z", q[3]}}},
        {"velocity_ned_m_s", {{"x", p.vx}, {"y", p.vy}, {"z", p.vz}}},
        {"relative_altitude_m", altitude - e.home_altitude_amsl}, {"altitude_amsl_m", altitude},
        {"navigation_heading_rad", *heading}, {"airspeed", air}, {"fixed_wing_envelope", envelope},
        {"altitude_reference_generation", *reference_generation}};
}

} // namespace pixeagle
