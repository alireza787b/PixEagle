#include <pixeagle/owned_mode_contract.hpp>
#include <gtest/gtest.h>
#include <functional>
#include <vector>

using namespace pixeagle;

namespace {
constexpr std::uint8_t hold_mode = 4;

OwnershipContext context() {
    return {Identity{"follow-a", "aircraft-a", "connection-a", 1, 1}, {0, 1}, {0, 2},
            7, 100, 200, 500, hold_mode, 23, 99};
}

NativeActivationEvidence evidence(const OwnershipContext& source) {
    NativeActivationEvidence value;
    value.token = source.token; value.incarnation = source.incarnation;
    value.source_revision = source.source_revision; value.source_epoch = source.source_epoch;
    value.acquired_epoch = value.actual_epoch = value.vehicle_epoch = source.acquired_epoch;
    value.registration_id = value.current_registration_id = source.registration_id;
    value.source_mode = source.source_mode;
    value.mode = value.actual_mode = value.vehicle_mode = source.mode;
    value.fresh = value.ownership_fresh = value.aircraft_matches = value.armed = value.owner_active = true;
    value.state = OwnershipReceiptState::Acquired;
    return value;
}

NativeActivationEvidence released(const OwnershipContext& source) {
    auto value = evidence(source);
    value.state = OwnershipReceiptState::Released;
    value.owner_active = false;
    value.actual_mode = hold_mode;
    value.actual_epoch = source.acquired_epoch + 1;
    return value;
}

void acquirePursuit(CommandLease& lease, const OwnershipContext& source) {
    lease.acquire(source.identity, 10., 10.3);
    lease.submit({source.identity, 1, 10., 10.3, FixedWingObjective{1.2, 25., -4., {}}}, 10.1, Phase::FixedWing);
    ASSERT_NE(lease.current(10.1, Phase::FixedWing, true, true, false), nullptr);
}
} // namespace

TEST(TerminalRelease, NativeHoldWithoutOriginalTerminalProofCannotResolveRelease) {
    auto source = context(); CommandLease lease; acquirePursuit(lease, source);
    source.endPursuit(lease);
    auto status = evidence(source);
    status.actual_mode = hold_mode; status.actual_epoch = source.acquired_epoch + 1;
    EXPECT_FALSE(source.observeTerminalRelease(status, hold_mode, lease));
    EXPECT_TRUE(source.releasePending());
    EXPECT_TRUE(source.acquisitionOutstanding());
    EXPECT_TRUE(source.pursuit_ended);
    EXPECT_EQ(source.releaseReceipt("runtime", hold_mode, status.actual_epoch).at("outcome"), "unconfirmed");
    EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
}

TEST(TerminalRelease, DroppedReleaseCanRetryOnlyWithinItsFrozenNativeWindow) {
    auto source = context(); CommandLease lease; acquirePursuit(lease, source);
    source.endPursuit(lease);
    const auto status = evidence(source);
    const std::uint64_t issued = 1000000, expires = 1500000;
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, issued, expires, issued));
    for (const auto clock : {1100000u, 1200000u, 1400000u}) {
        EXPECT_TRUE(releaseRetransmissionPermitted(source, status, issued, expires, clock));
        EXPECT_FALSE(lease.identity());
        EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
    }
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, issued, expires, expires));
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, issued, expires, expires + 1));
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, 0, expires, 1100000));
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, issued, expires + 1, 1100000));
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, expires, issued, 1100000));
    EXPECT_TRUE(source.observeTerminalRelease(released(source), hold_mode, lease));
    EXPECT_FALSE(releaseRetransmissionPermitted(source, status, issued, expires, 1100000));
}

TEST(TerminalRelease, ReleaseRetransmissionCannotFollowStaleReplacementOrTakeoverEvidence) {
    const std::vector<std::function<void(NativeActivationEvidence&)>> changes{
        [](auto& v) { v.fresh = false; },
        [](auto& v) { v.aircraft_matches = false; }, [](auto& v) { ++v.acquired_epoch; },
        [](auto& v) { ++v.vehicle_epoch; }, [](auto& v) { v.vehicle_mode = hold_mode; },
        [](auto& v) { v.rescue = true; }, [](auto& v) { v.armed = false; },
        [](auto& v) { ++v.registration_id; }, [](auto& v) { v.incarnation = {1, 1}; },
        [](auto& v) { v.state = OwnershipReceiptState::Superseded; },
        [](auto& v) { v.owner_active = false; },
    };
    for (const auto& change : changes) {
        auto source = context(); CommandLease lease; source.endPursuit(lease);
        auto status = evidence(source); change(status);
        EXPECT_FALSE(releaseRetransmissionPermitted(source, status, 1000000, 1500000, 1100000));
    }
}

TEST(TerminalRelease, FirstExactReceiptResolvesPendingAndRevokesPursuitInEitherCallbackOrder) {
    for (const bool sdk_deactivates_first : {false, true}) {
        SCOPED_TRACE(sdk_deactivates_first);
        auto source = context(); CommandLease lease; acquirePursuit(lease, source);
        if (sdk_deactivates_first) source.endPursuit(lease);
        ASSERT_TRUE(source.observeTerminalRelease(released(source), hold_mode, lease));
        EXPECT_FALSE(lease.identity());
        EXPECT_TRUE(source.pursuit_ended);
        EXPECT_FALSE(source.releasePending());
        EXPECT_FALSE(source.acquisitionOutstanding());
        const auto receipt = source.releaseReceipt("runtime", 23, source.acquired_epoch);
        EXPECT_EQ(receipt.at("outcome"), "hold_confirmed");
        EXPECT_EQ(receipt.at("observed_nav_state"), hold_mode);
        EXPECT_EQ(receipt.at("observed_nav_state_timestamp"), source.acquired_epoch + 1);
        EXPECT_EQ(receipt.at("acquisition"), source.wire("runtime"));
        // A late SDK deactivate callback repeats the fence, never the release request.
        source.endPursuit(lease);
        EXPECT_FALSE(source.releasePending());
        EXPECT_FALSE(source.acquisitionOutstanding());
        EXPECT_EQ(source.releaseReceipt("runtime", 23, 9999), receipt);
        EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
        EXPECT_FALSE(exactOriginalActivation(source, evidence(source)));
        EXPECT_FALSE(neutralDrainPermitted(source, evidence(source)));
        EXPECT_FALSE(startupActivationMayWait(source, evidence(source), 10.1, 10.3));
    }
}

TEST(TerminalRelease, ProvenOriginalReleaseDoesNotBlinkOrAdoptLaterStaleResetDisarmOrReplacementStatus) {
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    ASSERT_TRUE(source.observeTerminalRelease(released(source), hold_mode, lease));
    const auto receipt = source.releaseReceipt("runtime", 0, 0);
    for (int change = 0; change < 6; ++change) {
        SCOPED_TRACE(change);
        auto status = evidence(source);
        if (change == 0) status.fresh = status.ownership_fresh = false;
        if (change == 1) source.observeIncarnation({0, 3});
        if (change == 2) status.armed = false;
        if (change == 3) { status.rescue = true; status.state = OwnershipReceiptState::Superseded; }
        if (change == 4) { ++status.token[0]; ++status.acquired_epoch; }
        if (change == 5) { status.actual_mode = hold_mode; status.actual_epoch = 10000; }
        EXPECT_TRUE(source.observeTerminalRelease(status, hold_mode, lease));
        EXPECT_FALSE(source.releasePending());
        EXPECT_FALSE(lease.identity());
        EXPECT_EQ(source.releaseReceipt("runtime", status.actual_mode, status.actual_epoch), receipt);
        EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
        EXPECT_FALSE(exactOriginalActivation(source, status));
        EXPECT_FALSE(neutralDrainPermitted(source, status));
    }
}

TEST(TerminalRelease, ForeignStaleInvalidOrUncorrelatedTerminalStatusNeverResolvesOriginal) {
    for (int change = 0; change < 13; ++change) {
        SCOPED_TRACE(change);
        auto source = context(); CommandLease lease; source.endPursuit(lease);
        auto status = released(source);
        if (change == 0) status.ownership_fresh = false;
        if (change == 1) status.aircraft_matches = false;
        if (change == 2) ++status.token[0];
        if (change == 3) ++status.incarnation[0];
        if (change == 4) ++status.source_revision;
        if (change == 5) ++status.source_epoch;
        if (change == 6) ++status.source_mode;
        if (change == 7) ++status.mode;
        if (change == 8) ++status.registration_id;
        if (change == 9) ++status.acquired_epoch;
        if (change == 10) status.ownership_rescue = true;
        if (change == 11) status.actual_epoch = source.acquired_epoch;
        if (change == 12) status.actual_mode = source.mode;
        EXPECT_FALSE(source.observeTerminalRelease(status, hold_mode, lease));
        EXPECT_TRUE(source.releasePending());
        EXPECT_FALSE(source.terminal_release);
        EXPECT_TRUE(source.acquisitionOutstanding());
        // Refusal is not remembered as a receipt; a later genuine one may resolve it.
        EXPECT_TRUE(source.observeTerminalRelease(released(source), hold_mode, lease));
        EXPECT_FALSE(source.acquisitionOutstanding());
    }
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    source.observeIncarnation({0, 3});
    EXPECT_FALSE(source.observeTerminalRelease(released(source), hold_mode, lease));
    EXPECT_TRUE(source.releasePending());
    EXPECT_TRUE(source.acquisitionOutstanding());
}

TEST(TerminalRelease, OriginalTerminalReceiptDoesNotRequireASeparateCurrentVehicleOrPhaseObservation) {
    auto source = context(); CommandLease lease; acquirePursuit(lease, source);
    auto status = released(source);
    status.fresh = status.vehicle_fresh = status.armed = false;
    status.vehicle_rescue = status.rescue = true;
    ASSERT_TRUE(status.ownership_fresh);
    ASSERT_FALSE(status.ownership_rescue);
    EXPECT_TRUE(source.observeTerminalRelease(status, hold_mode, lease));
    EXPECT_FALSE(source.acquisitionOutstanding());
    EXPECT_FALSE(lease.identity());
    EXPECT_EQ(source.releaseReceipt("runtime", 0, 0).at("outcome"), "hold_confirmed");
}

TEST(TerminalRelease, ContradictoryActiveOwnerNeverCompletesAnyTerminalOutcome) {
    for (const auto state : {OwnershipReceiptState::Released, OwnershipReceiptState::Cancelled,
            OwnershipReceiptState::Rejected, OwnershipReceiptState::Expired, OwnershipReceiptState::Superseded}) {
        for (const bool acquired : {false, true}) {
            if (state == OwnershipReceiptState::Released && !acquired) continue;
            auto source = context(); if (!acquired) source.acquired_epoch = 0;
            CommandLease lease; source.endPursuit(lease);
            auto status = released(source);
            status.state = state; status.owner_active = true;
            if (!acquired) status.actual_epoch = source.source_epoch;
            EXPECT_FALSE(source.observeTerminalRelease(status, hold_mode, lease));
            EXPECT_FALSE(source.terminal_release);
            EXPECT_TRUE(source.releasePending());
            EXPECT_TRUE(source.acquisitionOutstanding());
            EXPECT_EQ(source.releaseReceipt("runtime", hold_mode, status.actual_epoch).at("outcome"), "unconfirmed");
            // A later coherent receipt can resolve the original; refusal is not cached.
            status.owner_active = false;
            EXPECT_TRUE(source.observeTerminalRelease(status, hold_mode, lease));
            EXPECT_FALSE(source.acquisitionOutstanding());
        }
    }
}

TEST(TerminalRelease, HoldConfirmationRequiresAnActivationStrictlyAfterTheOriginalSourceEpoch) {
    for (const auto acquired_epoch : {0u, 99u, 100u}) {
        auto source = context(); source.acquired_epoch = acquired_epoch;
        CommandLease lease; source.endPursuit(lease);
        const auto status = released(source);
        ASSERT_FALSE(status.owner_active);
        ASSERT_GT(status.actual_epoch, source.acquired_epoch);
        EXPECT_FALSE(source.observeTerminalRelease(status, hold_mode, lease));
        EXPECT_FALSE(source.terminal_release);
        EXPECT_TRUE(source.releasePending());
        EXPECT_TRUE(source.acquisitionOutstanding());
        EXPECT_EQ(source.releaseReceipt("runtime", hold_mode, status.actual_epoch).at("outcome"), "unconfirmed");
    }
}

TEST(TerminalRelease, UnacquiredCancellationExpiryAndLostAckOutcomesPreserveZeroActivation) {
    for (const auto state : {OwnershipReceiptState::Cancelled, OwnershipReceiptState::Rejected,
            OwnershipReceiptState::Expired, OwnershipReceiptState::Superseded}) {
        for (const bool acquired : {false, true}) {
            auto source = context(); if (!acquired) source.acquired_epoch = 0;
            CommandLease lease;
            auto status = evidence(source);
            status.state = state; status.owner_active = false;
            status.actual_mode = source.source_mode;
            status.actual_epoch = acquired ? source.acquired_epoch + 1 : source.source_epoch;
            ASSERT_TRUE(source.observeTerminalRelease(status, hold_mode, lease));
            EXPECT_FALSE(source.releasePending());
            const auto receipt = source.releaseReceipt("runtime", 0, 0);
            EXPECT_EQ(receipt.at("outcome"), "owner_already_released");
            EXPECT_EQ(receipt.at("acquisition").at("activation_timestamp"), acquired ? 200 : 0);
            // A later pilot Hold cannot rewrite a superseded/cancelled outcome.
            EXPECT_TRUE(source.observeTerminalRelease(released(source), hold_mode, lease));
            EXPECT_EQ(source.releaseReceipt("runtime", hold_mode, 9999), receipt);
            EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
        }
    }
}

TEST(TerminalRelease, OriginalAProofCannotCompleteOrResumeNewBWithEqualPublicSessionIdentity) {
    auto original = context(); CommandLease old_lease;
    ASSERT_TRUE(original.observeTerminalRelease(released(original), hold_mode, old_lease));
    auto replacement = context(); replacement.token = {8, 9}; replacement.source_revision += 2;
    replacement.source_epoch = 300; replacement.acquired_epoch = 400;
    ASSERT_TRUE(original.identity == replacement.identity);
    CommandLease lease; acquirePursuit(lease, replacement);
    EXPECT_FALSE(replacement.observeTerminalRelease(released(original), hold_mode, lease));
    EXPECT_FALSE(replacement.pursuit_ended);
    EXPECT_EQ(replacement.releaseReceipt("runtime", 23, 400).at("outcome"), "unconfirmed");
    EXPECT_NO_THROW(replacement.requirePursuit());
    EXPECT_NE(lease.current(10.1, Phase::FixedWing, true, true, false), nullptr);
    EXPECT_THROW(replacement.requireToken(original.token), std::invalid_argument);
    EXPECT_THROW(original.requirePursuit(), std::invalid_argument);
    EXPECT_FALSE(exactOriginalActivation(original, evidence(original)));
}
