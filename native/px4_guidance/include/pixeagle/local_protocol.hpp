#pragma once

#include <pixeagle/command_lease.hpp>
#include <nlohmann/json.hpp>
#include <set>

namespace pixeagle {

using Json = nlohmann::json;
constexpr std::uint64_t kProtocolVersion = 5;
constexpr std::size_t kMaximumMessageBytes = 65536;

inline void exactFields(const Json& object, const std::set<std::string>& names) {
    if (!object.is_object() || object.size() != names.size()) throw std::invalid_argument("native_fields_invalid");
    for (const auto& name : names) if (!object.contains(name)) throw std::invalid_argument("native_fields_invalid");
}

inline std::uint64_t unsignedInteger(const Json& value) {
    if (!value.is_number_unsigned()) throw std::invalid_argument("native_integer_invalid");
    return value.get<std::uint64_t>();
}

inline double finiteNumber(const Json& value) {
    if (!value.is_number()) throw std::invalid_argument("native_number_invalid");
    const auto result = value.get<double>();
    if (!std::isfinite(result)) throw std::invalid_argument("native_number_invalid");
    return result;
}

inline std::string nonemptyString(const Json& value) {
    if (!value.is_string()) throw std::invalid_argument("native_string_invalid");
    auto result = value.get<std::string>();
    if (result.empty() || result.size() > 128) throw std::invalid_argument("native_string_invalid");
    return result;
}

struct AltitudeReference {
    double altitude_amsl;
    std::uint64_t generation;
};

inline AltitudeReference decodeAltitudeReference(const Json& value) {
    exactFields(value, {"altitude_amsl_m", "reference_generation"});
    const auto altitude = finiteNumber(value.at("altitude_amsl_m"));
    if (!nativeFloatRepresentable(altitude))
        throw std::invalid_argument("native_value_not_representable");
    return {altitude, unsignedInteger(value.at("reference_generation"))};
}

inline Identity decodeIdentity(const Json& value) {
    exactFields(value, {"follow_session_id", "binding", "guidance_generation"});
    const auto& binding = value.at("binding");
    exactFields(binding, {"aircraft_uid", "connection_generation", "telemetry_generation"});
    return {nonemptyString(value.at("follow_session_id")), nonemptyString(binding.at("aircraft_uid")),
            nonemptyString(binding.at("connection_generation")), unsignedInteger(binding.at("telemetry_generation")),
            unsignedInteger(value.at("guidance_generation"))};
}

inline Objective decodeObjective(const Json& value, Phase phase) {
    if (phase == Phase::FixedWing) {
        exactFields(value, {"course_rad", "equivalent_airspeed_m_s", "height_rate_m_s", "altitude_amsl_m", "upper_speed_policy"});
        if (value.at("upper_speed_policy") != "px4_configured_max")
            throw std::invalid_argument("unrestricted_speed_not_supported");
        return FixedWingObjective{
            finiteNumber(value.at("course_rad")), finiteNumber(value.at("equivalent_airspeed_m_s")),
            value.at("height_rate_m_s").is_null() ? std::nullopt : std::optional<double>{finiteNumber(value.at("height_rate_m_s"))},
            value.at("altitude_amsl_m").is_null() ? std::nullopt : std::optional<double>{finiteNumber(value.at("altitude_amsl_m"))}};
    }
    if (phase == Phase::Multicopter) {
        if (value.contains("altitude_amsl_m") || value.contains("altitude_reference_generation")) {
            exactFields(value, {"velocity_north_m_s", "velocity_east_m_s", "altitude_amsl_m",
                               "altitude_reference_generation", "yaw_rate_rad_s"});
            return MulticopterObjective{finiteNumber(value.at("velocity_north_m_s")),
                finiteNumber(value.at("velocity_east_m_s")), std::nullopt, finiteNumber(value.at("yaw_rate_rad_s")),
                finiteNumber(value.at("altitude_amsl_m")), unsignedInteger(value.at("altitude_reference_generation"))};
        }
        exactFields(value, {"velocity_north_m_s", "velocity_east_m_s", "velocity_down_m_s", "yaw_rate_rad_s"});
        return MulticopterObjective{finiteNumber(value.at("velocity_north_m_s")), finiteNumber(value.at("velocity_east_m_s")),
                                     finiteNumber(value.at("velocity_down_m_s")), finiteNumber(value.at("yaw_rate_rad_s"))};
    }
    throw std::invalid_argument("native_phase_unknown");
}

inline Intent decodeIntent(const Json& payload) {
    exactFields(payload, {"identity", "token", "sequence", "created_at_monotonic_s", "expires_at_monotonic_s", "phase", "command"});
    nonemptyString(payload.at("token"));
    const auto phase_name = nonemptyString(payload.at("phase"));
    const auto phase = phase_name == "fixed_wing" ? Phase::FixedWing
        : phase_name == "multicopter" ? Phase::Multicopter : Phase::Unknown;
    auto result = Intent{decodeIdentity(payload.at("identity")), unsignedInteger(payload.at("sequence")),
                        finiteNumber(payload.at("created_at_monotonic_s")), finiteNumber(payload.at("expires_at_monotonic_s")),
                        decodeObjective(payload.at("command"), phase)};
    validate(result.objective);
    return result;
}

struct Request {
    std::uint64_t request_id, generation;
    std::string operation;
    Json payload;
};

inline Request decodeRequest(const std::string& raw) {
    if (raw.empty() || raw.size() > kMaximumMessageBytes) throw std::invalid_argument("native_message_oversized");
    auto object = Json::parse(raw);
    exactFields(object, {"protocol_version", "request_id", "generation", "operation", "payload"});
    if (unsignedInteger(object.at("protocol_version")) != kProtocolVersion) throw std::invalid_argument("native_protocol_unsupported");
    if (!object.at("payload").is_object()) throw std::invalid_argument("native_payload_invalid");
    return {unsignedInteger(object.at("request_id")), unsignedInteger(object.at("generation")),
            nonemptyString(object.at("operation")), object.at("payload")};
}

inline std::string encodeReply(const Request& request, const Json& payload) {
    return Json{{"protocol_version", kProtocolVersion}, {"request_id", request.request_id}, {"generation", request.generation},
                {"success", true}, {"payload", payload}}.dump() + "\n";
}

inline std::string encodeError(const Request& request, const std::string& code) {
    return Json{{"protocol_version", kProtocolVersion}, {"request_id", request.request_id}, {"generation", request.generation},
                {"success", false}, {"error_code", code}}.dump() + "\n";
}

} // namespace pixeagle
