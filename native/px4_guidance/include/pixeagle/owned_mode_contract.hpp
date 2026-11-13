#pragma once

#include <pixeagle/local_protocol.hpp>
#include <array>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>

namespace pixeagle {

using OwnershipToken = std::array<std::uint64_t, 2>;
constexpr std::uint8_t ownership_contract_version = 2;
constexpr std::uint64_t maximum_ownership_window_us = 500000;

inline std::uint64_t requireOwnRegistration(std::uint64_t own, std::uint64_t current) {
    if (own == 0 || own != current) throw std::invalid_argument("native_mode_registration_unavailable");
    return own;
}

class RegistrationProof {
public:
    bool ready() const { return _confirmed && !_retired; }
    bool retired() const { return _retired; }
    bool matchesSource(std::uint64_t uid, std::uint8_t system, std::uint8_t component) const {
        return _confirmed && uid == _uid && system == _system && component == _component;
    }
    void observe(std::uint64_t own, std::uint64_t current, OwnershipToken incarnation,
                 std::uint64_t uid, std::uint8_t system, std::uint8_t component, bool progresses) {
        if (_retired || (incarnation[0] == 0 && incarnation[1] == 0)) return;
        if (_confirmed && (!matchesSource(uid, system, component) || incarnation != _incarnation)) {
            _retired = true;
            return;
        }
        if (!progresses) return;
        if (_confirmed) {
            if (own != _own || current != _own) _retired = true;
        } else if (own != 0 && own == current) {
            _own = own;
            _incarnation = incarnation;
            _uid = uid;
            _system = system;
            _component = component;
            _confirmed = true;
        }
    }
private:
    OwnershipToken _incarnation{};
    std::uint64_t _own{}, _uid{};
    std::uint8_t _system{}, _component{};
    bool _confirmed{}, _retired{};
};

inline std::string encodeOwnershipToken(const OwnershipToken& token) {
    std::ostringstream value;
    value << std::hex << std::setfill('0') << std::setw(16) << token[0] << std::setw(16) << token[1];
    return value.str();
}

inline OwnershipToken decodeOwnershipToken(const Json& value) {
    if (!value.is_string()) throw std::invalid_argument("native_ownership_token_invalid");
    const auto text = value.get<std::string>();
    if (text.size() != 32 || text.find_first_not_of("0123456789abcdef") != std::string::npos)
        throw std::invalid_argument("native_ownership_token_invalid");
    OwnershipToken token{std::stoull(text.substr(0, 16), nullptr, 16), std::stoull(text.substr(16), nullptr, 16)};
    if (token[0] == 0 && token[1] == 0) throw std::invalid_argument("native_ownership_token_invalid");
    return token;
}

struct NativeStartContext {
    std::string runtime;
    Json binding;
    OwnershipToken incarnation{};
    std::uint8_t mode{}, source_mode{};
    std::uint64_t registration{}, intention_revision{}, source_epoch{}, phase_instance{}, phase_revision{};
    Phase phase{Phase::Unknown};

    Json wire() const {
        return {{"version", 1u}, {"runtime_id", runtime}, {"binding", binding},
            {"firmware_incarnation", encodeOwnershipToken(incarnation)}, {"mode_id", mode},
            {"registration_id", registration}, {"intention_revision", intention_revision},
            {"source_nav_state", source_mode}, {"source_nav_state_timestamp", source_epoch},
            {"phase", phase == Phase::Multicopter ? "multicopter" : "fixed_wing"},
            {"phase_source_instance", phase_instance}, {"phase_revision", phase_revision}};
    }
    bool bindingMatches(const Identity& identity) const {
        return binding.at("aircraft_uid") == identity.aircraft && binding.at("connection_generation") == identity.connection
            && binding.at("telemetry_generation") == identity.telemetry_generation;
    }
};

inline NativeStartContext decodeStartContext(const Json& value) {
    exactFields(value, {"version", "runtime_id", "binding", "firmware_incarnation", "mode_id", "registration_id",
        "intention_revision", "source_nav_state", "source_nav_state_timestamp", "phase", "phase_source_instance", "phase_revision"});
    const auto& binding = value.at("binding");
    exactFields(binding, {"aircraft_uid", "connection_generation", "telemetry_generation"});
    nonemptyString(binding.at("aircraft_uid"));
    nonemptyString(binding.at("connection_generation"));
    unsignedInteger(binding.at("telemetry_generation"));
    const auto phase = nonemptyString(value.at("phase"));
    const auto mode = unsignedInteger(value.at("mode_id"));
    const auto source_mode = unsignedInteger(value.at("source_nav_state"));
    NativeStartContext result{nonemptyString(value.at("runtime_id")), binding,
        decodeOwnershipToken(value.at("firmware_incarnation")), static_cast<std::uint8_t>(mode), static_cast<std::uint8_t>(source_mode),
        unsignedInteger(value.at("registration_id")), unsignedInteger(value.at("intention_revision")),
        unsignedInteger(value.at("source_nav_state_timestamp")), unsignedInteger(value.at("phase_source_instance")),
        unsignedInteger(value.at("phase_revision")),
        phase == "multicopter" ? Phase::Multicopter : phase == "fixed_wing" ? Phase::FixedWing : Phase::Unknown};
    if (unsignedInteger(value.at("version")) != 1 || mode < 23 || mode > 30 || source_mode > 255 || mode == source_mode
            || result.registration == 0 || result.source_epoch == 0 || result.phase == Phase::Unknown
            || ((result.phase_instance == 0) != (result.phase_revision == 0)))
        throw std::invalid_argument("native_start_context_invalid");
    return result;
}

enum class OwnershipReceiptState { Pending, Acquired, Releasing, Released, Cancelled, Rejected, Expired, Superseded, Other };
enum class TerminalReleaseOutcome { HoldConfirmed, OwnerAlreadyReleased };

struct TerminalReleaseObservation {
    TerminalReleaseOutcome outcome;
    std::uint8_t mode;
    std::uint64_t epoch;
};

struct NativeActivationEvidence;

struct OwnershipContext {
    Identity identity;
    OwnershipToken token{}, incarnation{};
    std::uint64_t source_revision{}, source_epoch{}, acquired_epoch{}, expires{};
    std::uint8_t source_mode{}, mode{};
    std::uint64_t registration_id{};
    bool retired{}, pursuit_ended{};
    std::optional<TerminalReleaseObservation> terminal_release{};
    std::optional<NativeStartContext> start_context{};

    void endPursuit(CommandLease& lease) { pursuit_ended = true; lease.revoke(); }
    void requirePursuit() const {
        if (pursuit_ended) throw std::invalid_argument("native_pursuit_ended");
    }
    bool releasePending() const { return pursuit_ended && !terminal_release; }
    bool acquisitionOutstanding() const { return !terminal_release; }
    bool observeTerminalRelease(const NativeActivationEvidence& evidence, std::uint8_t hold_mode, CommandLease& lease);

    void observeIncarnation(const OwnershipToken& received) {
        if ((received[0] != 0 || received[1] != 0) && received != incarnation) retired = true;
    }
    bool observePublication(std::uint64_t previous_publication, OwnershipToken previous_incarnation,
                            std::uint64_t previous_clock, std::uint64_t publication,
                            OwnershipToken received_incarnation, std::uint64_t clock);
    void requireToken(const OwnershipToken& received) const {
        if (received != token) throw std::invalid_argument("native_session_stale");
    }

    bool matches(const OwnershipToken& received_token, const OwnershipToken& received_incarnation,
                 std::uint64_t revision, std::uint64_t epoch, std::uint8_t from, std::uint8_t target,
                 std::uint64_t registration) const {
        return !retired && token == received_token && incarnation == received_incarnation && source_revision == revision
            && source_epoch == epoch && source_mode == from && mode == target && registration_id == registration;
    }

    Json wire(const std::string& runtime) const {
        const Json binding{{"aircraft_uid", identity.aircraft}, {"connection_generation", identity.connection},
                           {"telemetry_generation", identity.telemetry_generation}};
        const Json session{{"follow_session_id", identity.session}, {"binding", binding},
                           {"guidance_generation", identity.guidance_generation}};
        return {{"runtime_id", runtime}, {"identity", session}, {"token", encodeOwnershipToken(token)},
            {"firmware_incarnation", encodeOwnershipToken(incarnation)}, {"source_revision", source_revision},
            {"source_nav_state", source_mode}, {"source_nav_state_timestamp", source_epoch},
            {"mode_id", mode}, {"activation_timestamp", acquired_epoch},
            {"start_context", start_context ? start_context->wire() : Json(nullptr)}};
    }

    Json releaseReceipt(const std::string& runtime, std::uint8_t observed_mode, std::uint64_t observed_epoch) const {
        const auto outcome = terminal_release
            ? terminal_release->outcome == TerminalReleaseOutcome::HoldConfirmed ? "hold_confirmed" : "owner_already_released"
            : "unconfirmed";
        return {{"acquisition", wire(runtime)}, {"outcome", outcome},
            {"observed_nav_state", terminal_release ? terminal_release->mode : observed_mode},
            {"observed_nav_state_timestamp", terminal_release ? terminal_release->epoch : observed_epoch}};
    }
};

struct NativeActivationEvidence {
    OwnershipToken token{}, incarnation{};
    std::uint64_t source_revision{}, source_epoch{}, acquired_epoch{}, actual_epoch{}, vehicle_epoch{};
    std::uint64_t registration_id{}, current_registration_id{}, intention_revision{};
    std::uint8_t source_mode{}, mode{}, actual_mode{}, vehicle_mode{};
    bool fresh{}, aircraft_matches{}, armed{}, rescue{}, owner_active{};
    bool ownership_fresh{}, ownership_rescue{}, vehicle_fresh{}, vehicle_armed{}, vehicle_rescue{};
    OwnershipReceiptState state{OwnershipReceiptState::Other};
};

inline std::optional<TerminalReleaseObservation> classifyTerminalRelease(const OwnershipContext& context,
        const NativeActivationEvidence& evidence, std::uint8_t hold_mode) {
    if (!evidence.ownership_fresh || !evidence.aircraft_matches || evidence.owner_active
            || evidence.acquired_epoch != context.acquired_epoch
            || !context.matches(evidence.token, evidence.incarnation, evidence.source_revision, evidence.source_epoch,
                                evidence.source_mode, evidence.mode, evidence.registration_id)) return std::nullopt;
    if (evidence.state == OwnershipReceiptState::Released && context.acquired_epoch > context.source_epoch
            && evidence.actual_mode == hold_mode
            && evidence.actual_epoch > context.acquired_epoch && !evidence.ownership_rescue)
        return TerminalReleaseObservation{TerminalReleaseOutcome::HoldConfirmed, evidence.actual_mode, evidence.actual_epoch};
    if (evidence.state == OwnershipReceiptState::Cancelled || evidence.state == OwnershipReceiptState::Rejected
            || evidence.state == OwnershipReceiptState::Expired || evidence.state == OwnershipReceiptState::Superseded)
        return TerminalReleaseObservation{TerminalReleaseOutcome::OwnerAlreadyReleased, evidence.actual_mode, evidence.actual_epoch};
    return std::nullopt;
}

inline bool OwnershipContext::observeTerminalRelease(const NativeActivationEvidence& evidence, std::uint8_t hold_mode,
                                                      CommandLease& lease) {
    if (!terminal_release) terminal_release = classifyTerminalRelease(*this, evidence, hold_mode);
    if (!terminal_release) return false;
    // A proven original departure is historical fact, never current command authority.
    endPursuit(lease);
    return true;
}

inline bool exactOriginalActivation(const OwnershipContext& context, const NativeActivationEvidence& evidence) {
    return !context.terminal_release && evidence.fresh && evidence.aircraft_matches && evidence.armed && !evidence.rescue
        && context.acquired_epoch > 0 && evidence.acquired_epoch == context.acquired_epoch
        && evidence.actual_mode == context.mode && evidence.vehicle_mode == context.mode
        && evidence.actual_epoch == context.acquired_epoch && evidence.vehicle_epoch == context.acquired_epoch
        && evidence.current_registration_id == context.registration_id
        && context.matches(evidence.token, evidence.incarnation, evidence.source_revision, evidence.source_epoch,
                           evidence.source_mode, evidence.mode, evidence.registration_id);
}

inline bool neutralDrainPermitted(const OwnershipContext& context, const NativeActivationEvidence& evidence) {
    return context.pursuit_ended && exactOriginalActivation(context, evidence)
        && ((evidence.state == OwnershipReceiptState::Acquired && evidence.owner_active)
            || evidence.state == OwnershipReceiptState::Releasing);
}

// Waiting is not authority: only exactOriginalActivation may authorize startup
// publication. This uses the original engagement deadline, never another timer.
inline bool startupActivationMayWait(const OwnershipContext& context, const NativeActivationEvidence& evidence,
                                     double now, double original_deadline) {
    if (context.retired || context.pursuit_ended || !std::isfinite(now) || !std::isfinite(original_deadline)
            || now >= original_deadline || evidence.vehicle_rescue
            || (evidence.vehicle_fresh && (!evidence.vehicle_armed || !evidence.aircraft_matches))) return false;
    if (evidence.vehicle_fresh) {
        const bool source = evidence.vehicle_mode == context.source_mode && evidence.vehicle_epoch == context.source_epoch;
        const bool activating = evidence.vehicle_mode == context.mode && evidence.vehicle_epoch > context.source_epoch
            && (context.acquired_epoch == 0 || evidence.vehicle_epoch == context.acquired_epoch);
        if (!source && !activating) return false;
    }
    if (evidence.ownership_fresh) {
        if (evidence.incarnation != context.incarnation || evidence.current_registration_id != context.registration_id)
            return false;
        const bool matching = context.matches(evidence.token, evidence.incarnation, evidence.source_revision,
            evidence.source_epoch, evidence.source_mode, evidence.mode, evidence.registration_id);
        if (matching) {
            if (!evidence.armed || evidence.rescue) return false;
            if (evidence.state == OwnershipReceiptState::Acquired) {
                if (evidence.acquired_epoch <= context.source_epoch || evidence.actual_mode != context.mode
                        || evidence.actual_epoch != evidence.acquired_epoch
                        || (context.acquired_epoch != 0 && evidence.acquired_epoch != context.acquired_epoch)) return false;
            } else if (evidence.state != OwnershipReceiptState::Pending) return false;
        } else if (evidence.intention_revision != context.source_revision
                || evidence.actual_mode != context.source_mode || evidence.actual_epoch != context.source_epoch) return false;
    }
    return true;
}

inline bool ownershipPublicationProgresses(std::uint64_t previous_publication, OwnershipToken previous_incarnation,
                                         std::uint64_t previous_clock, std::uint64_t publication,
                                         OwnershipToken incarnation, std::uint64_t clock) {
    return publication > previous_publication && clock > 0
        && (incarnation != previous_incarnation || clock > previous_clock);
}

inline bool OwnershipContext::observePublication(std::uint64_t previous_publication, OwnershipToken previous_incarnation,
                                                std::uint64_t previous_clock, std::uint64_t publication,
                                                OwnershipToken received_incarnation, std::uint64_t clock) {
    // A verified firmware restart retires the old acquisition even when its clock reset.
    observeIncarnation(received_incarnation);
    return ownershipPublicationProgresses(previous_publication, previous_incarnation, previous_clock,
                                         publication, received_incarnation, clock);
}

inline std::uint64_t ownershipDeadline(std::uint64_t clock, double now, double deadline) {
    if (clock == 0 || !std::isfinite(now) || !std::isfinite(deadline) || deadline <= now)
        throw std::invalid_argument("native_ownership_request_expired");
    const double remaining_us = std::min((deadline - now) * 1e6, static_cast<double>(maximum_ownership_window_us));
    const auto remaining = static_cast<std::uint64_t>(remaining_us);
    if (remaining == 0 || clock > std::numeric_limits<std::uint64_t>::max() - remaining)
        throw std::invalid_argument("native_ownership_request_expired");
    return clock + remaining;
}

} // namespace pixeagle
