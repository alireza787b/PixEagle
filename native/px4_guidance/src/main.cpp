#include <pixeagle/aircraft_observations.hpp>
#include <pixeagle/external_mode.hpp>
#include <pixeagle/phase_hold.hpp>
#include <pixeagle/local_server.hpp>
#include <px4_ros2/components/message_compatibility_check.hpp>
#include <chrono>
#include <iostream>
#include <random>
#include <sstream>

namespace {
double clockSeconds() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
std::string runtimeId() {
    std::random_device random;
    std::ostringstream result;
    result << std::hex << random() << random() << random() << random();
    return result.str();
}
}

int main(int argc, char** argv) {
    using namespace pixeagle;
    rclcpp::init(argc, argv);
    int result = 1;
    try {
        auto node = std::make_shared<rclcpp::Node>("pixeagle_native_guidance");
        const auto path = node->declare_parameter<std::string>("socket_path", "/run/pixeagle/guidance.sock");
        const auto timeout = node->declare_parameter<double>("status_timeout_s", 1.);
        const auto request_timeout = node->declare_parameter<double>("request_timeout_s", .5);
        const auto runtime = runtimeId();
        std::optional<px4_msgs::msg::VehicleStatus> initial;
        auto probe = node->create_subscription<px4_msgs::msg::VehicleStatus>(
            "fmu/out/vehicle_status" + px4_ros2::getMessageNameVersion<px4_msgs::msg::VehicleStatus>(),
            rclcpp::SensorDataQoS(), [&](px4_msgs::msg::VehicleStatus::ConstSharedPtr status) { initial = *status; });
        const auto discovery_deadline = clockSeconds() + 10.;
        rclcpp::executors::SingleThreadedExecutor executor;
        executor.add_node(node);
        while (rclcpp::ok() && !initial && clockSeconds() < discovery_deadline) executor.spin_once(std::chrono::milliseconds(20));
        if (!initial) throw std::runtime_error("native_aircraft_discovery_timeout");
        probe.reset();
        // The actual aircraft declares VTOL capability; no mounting preset or
        // operator-entered aircraft type can select this command contract.
        ExternalMode mode(*node, timeout, request_timeout, initial->is_vtol);
        AircraftObservations observations(*node, timeout);
        mode.setPhaseHoldProvider([&](Phase phase, const std::optional<Objective>& previous) -> std::optional<Objective> {
            const auto state = observations.snapshot(mode.status(), phase, mode.rescue(), mode.phaseReceived(), clockSeconds());
            if (state.is_null()) return {};
            const auto& envelope = state.at("fixed_wing_envelope");
            return phaseHold(phase, previous, state.at("navigation_heading_rad").get<double>(),
                envelope.at("minimum_eas_m_s").get<double>(), envelope.at("trim_eas_m_s").get<double>(),
                envelope.at("maximum_eas_m_s").get<double>());
        });
        if (!mode.doRegister()) throw std::runtime_error("native_registration_failed");
        if (!px4_ros2::messageCompatibilityCheck(*node, {{"fmu/out/fixed_wing_guidance_status", "FixedWingGuidanceStatus"},
                {"fmu/out/owned_mode_status", "OwnedModeStatus"}, {"fmu/in/owned_mode_request", "OwnedModeRequest"}}))
            throw std::runtime_error("native_firmware_contract_mismatch");
        std::optional<std::uint64_t> pending_request;
        std::optional<Identity> pending_identity;
        double engage_expires{};
        LocalServer server(path, [&](const Request& request) -> std::optional<Json> {
            const double now = clockSeconds();
            if (request.operation == "hello") {
                exactFields(request.payload, {});
                const auto firmware = observations.firmware(now);
                if (firmware.empty()) throw std::invalid_argument("native_firmware_not_observed");
                if (firmware != PIXEAGLE_EXPECTED_FIRMWARE_HASH)
                    throw std::invalid_argument("native_firmware_revision_mismatch");
                return Json{{"runtime_id", runtime}, {"px4_firmware", firmware}, {"external_mode_api_version", 2},
                    {"fixed_wing_supported", true}, {"vtol_transition_supported", initial->is_vtol},
                    {"unrestricted_speed_supported", false}, {"owned_mode_supported", mode.ownedContractAvailable()},
                    {"owned_mode_id", mode.id()}};
            }
            if (request.operation == "bind") {
                if (pending_identity) throw std::invalid_argument("native_session_already_owned");
                exactFields(request.payload, {"binding"});
                observations.bind(request.payload.at("binding"), now);
                return Json{{"bound", true}};
            }
            auto snapshot = mode.fresh() ? observations.snapshot(mode.status(), mode.observedPhase(), mode.rescue(),
                                                                 mode.phaseReceived(), now) : Json(nullptr);
            if (request.operation == "observe") {
                exactFields(request.payload, {});
                const auto health = mode.phaseSourceHealth();
                const auto optional_number = [](std::optional<double> value) -> Json {
                    return value ? Json(*value) : Json(nullptr);
                };
                return Json{{"runtime_id", runtime}, {"fresh", !snapshot.is_null()},
                    {"owner_confirmed", mode.observedOwner()}, {"rescue_active", mode.rescue()},
                    {"aircraft_state", snapshot}, {"publications", mode.publications()},
                    {"attitude_timing", snapshot.is_null() ? Json(nullptr) : observations.attitudeTiming(now)},
                    {"source_health", observations.health(now)}, {"phase_status_fresh", mode.fresh()},
                    {"phase_source_health", {
                        {"vehicle_status_age_s", optional_number(health.vehicle_age_s)},
                        {"vtol_status_age_s", optional_number(health.vtol_age_s)},
                        {"vehicle_status_timeout_s", health.vehicle_timeout_s},
                        {"vtol_status_timeout_s", optional_number(health.vtol_timeout_s)}}},
                    {"vehicle_pose", observations.pose(now)},
                    {"native_guidance_feedback", observations.commandFeedback(now)},
                    {"phase_hold_active", mode.phaseHoldActive()}, {"phase_hold_failure", mode.phaseHoldFailure()},
                    {"nav_state", mode.status().nav_state}, {"nav_state_timestamp", mode.status().nav_state_timestamp},
                    {"release_receipt", mode.releaseReceipt(runtime)}};
            }
            if (request.operation == "engage") {
                exactFields(request.payload, {"identity", "token", "runtime_id", "expires_at_monotonic_s"});
                if (request.payload.at("runtime_id") != runtime) throw std::invalid_argument("native_runtime_changed");
                const auto identity = decodeIdentity(request.payload.at("identity"));
                const auto token = decodeOwnershipToken(request.payload.at("token"));
                if (!observations.bindingMatches(identity) || snapshot.is_null())
                    throw std::invalid_argument("native_aircraft_context_unavailable");
                if (!pending_request || *pending_request != request.request_id) {
                    if (pending_identity) throw std::invalid_argument("native_session_already_owned");
                    engage_expires = finiteNumber(request.payload.at("expires_at_monotonic_s"));
                    if (engage_expires <= now || engage_expires > now + request_timeout)
                        throw std::invalid_argument("native_engagement_expired");
                    Objective hold;
                    if (mode.observedPhase() == Phase::FixedWing) {
                        hold = FixedWingObjective{snapshot.at("navigation_heading_rad").get<double>(),
                            snapshot.at("fixed_wing_envelope").at("trim_eas_m_s").get<double>(), {},
                            snapshot.at("altitude_amsl_m").get<double>()};
                    } else if (mode.observedPhase() == Phase::Multicopter && initial->is_vtol) {
                        hold = MulticopterObjective{};
                    } else throw std::invalid_argument("native_engagement_phase_unsupported");
                    mode.requestActivation(identity, token, std::move(hold), engage_expires);
                    pending_identity = identity;
                    pending_request = request.request_id;
                }
                if (mode.observedOwner()) {
                    mode.acquire(identity, engage_expires);
                    pending_request.reset();
                    return Json{{"owner_confirmed", true}, {"acquisition", mode.acquisition(runtime)}, {"runtime_id", runtime}};
                }
                if (now >= engage_expires) throw std::invalid_argument("native_engagement_expired");
                return {};
            }
            if (request.operation == "intent") {
                const auto token = decodeOwnershipToken(request.payload.at("token"));
                const auto intent = decodeIntent(request.payload);
                if (snapshot.is_null() || !observations.bindingMatches(intent.identity))
                    throw std::invalid_argument("native_aircraft_context_unavailable");
                mode.submit(intent, token);
                return Json{{"accepted_sequence", intent.sequence}, {"owner_confirmed", mode.observedOwner()},
                    {"publications", mode.publications()}};
            }
            if (request.operation == "phase") {
                exactFields(request.payload, {"previous_identity", "identity", "token"});
                const auto token = decodeOwnershipToken(request.payload.at("token"));
                const auto previous = decodeIdentity(request.payload.at("previous_identity"));
                const auto next = decodeIdentity(request.payload.at("identity"));
                if (!observations.bindingMatches(next) || snapshot.is_null())
                    throw std::invalid_argument("native_aircraft_context_unavailable");
                mode.advance(previous, next, token);
                pending_identity = next;
                return Json{{"accepted_generation", next.guidance_generation}, {"owner_confirmed", true}};
            }
            if (request.operation == "handoff") {
                exactFields(request.payload, {"identity", "token", "reason"});
                const auto identity = decodeIdentity(request.payload.at("identity"));
                const auto token = decodeOwnershipToken(request.payload.at("token"));
                nonemptyString(request.payload.at("reason"));
                if (!pending_request || *pending_request != request.request_id) {
                    if (!pending_identity || !(*pending_identity == identity)) throw std::invalid_argument("native_session_stale");
                    pending_identity.reset();
                    pending_request = request.request_id;
                    mode.requestHandoff(identity, token);
                }
                const auto receipt = mode.releaseReceipt(runtime);
                if (receipt.at("outcome") != "unconfirmed") { pending_request.reset(); return receipt; }
                if (!mode.fresh()) return receipt;
                return {};
            }
            throw std::invalid_argument("native_operation_unsupported");
        }, [&] { pending_request.reset(); pending_identity.reset(); mode.disconnect(); }, request_timeout);
        auto timer = node->create_wall_timer(std::chrono::milliseconds(5), [&] {
            server.poll(clockSeconds());
        });
        RCLCPP_INFO(node->get_logger(), "Native guidance ready; mode=%u runtime=%s", mode.id(), runtime.c_str());
        executor.spin();
        mode.disconnect();
        result = 0;
    } catch (const std::exception& error) {
        std::cerr << "PixEagle native guidance: " << error.what() << '\n';
    }
    rclcpp::shutdown();
    return result;
}
