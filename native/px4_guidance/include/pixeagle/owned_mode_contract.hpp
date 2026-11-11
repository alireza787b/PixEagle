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
constexpr std::uint8_t ownership_contract_version = 1;
constexpr std::uint64_t maximum_ownership_window_us = 500000;

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

struct OwnershipContext {
    Identity identity;
    OwnershipToken token{}, incarnation{};
    std::uint64_t source_revision{}, source_epoch{}, acquired_epoch{}, expires{};
    std::uint8_t source_mode{}, mode{};
    std::uint64_t registration_id{};
    bool retired{};

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
            {"mode_id", mode}, {"activation_timestamp", acquired_epoch}};
    }
};

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
