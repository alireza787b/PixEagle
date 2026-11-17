#include <pixeagle/neutral_release.hpp>
#include <pixeagle/owned_mode_contract.hpp>
#include <pixeagle/navigation_heading.hpp>
#include <pixeagle/source_sample.hpp>
#include <gtest/gtest.h>

using namespace pixeagle;

// Typed native contract fixtures; these do not simulate ModeBase registration.
static OwnershipContext context() {
    return {Identity{"follow", "aircraft", "connection", 1, 1}, {0, 1}, {0, 2},
            7, 1000000, 2000000, 2500000, 4, 23, 99};
}

static NativeActivationEvidence evidence(const OwnershipContext& source) {
    NativeActivationEvidence value;
    value.token = source.token; value.incarnation = source.incarnation;
    value.source_revision = source.source_revision; value.source_epoch = source.source_epoch;
    value.acquired_epoch = value.actual_epoch = value.vehicle_epoch = source.acquired_epoch;
    value.registration_id = value.current_registration_id = source.registration_id;
    value.source_mode = source.source_mode;
    value.mode = value.actual_mode = value.vehicle_mode = source.mode;
    value.fresh = value.aircraft_matches = value.armed = value.owner_active = true;
    value.state = OwnershipReceiptState::Acquired;
    return value;
}

TEST(NeutralRelease, MulticopterRequiresNoFwEnvelopeAndCommandsOnlyZeroVelocityAndYaw) {
    const auto value = std::get<MulticopterObjective>(neutralReleaseObjective(Phase::Multicopter, NAN, NAN, NAN, NAN));
    EXPECT_DOUBLE_EQ(value.north, 0.); EXPECT_DOUBLE_EQ(value.east, 0.);
    ASSERT_TRUE(value.down); EXPECT_DOUBLE_EQ(*value.down, 0.);
    EXPECT_FALSE(value.altitude_amsl); EXPECT_FALSE(value.altitude_reference_generation); EXPECT_DOUBLE_EQ(value.yaw_rate, 0.);
}

TEST(NeutralRelease, FixedWingUsesCurrentNativeCourseTrimAndLevelPathWithoutAnAltitudeTarget) {
    const auto value = std::get<FixedWingObjective>(neutralReleaseObjective(Phase::FixedWing, .3, 12., 18., 30.));
    EXPECT_DOUBLE_EQ(value.course, .3); EXPECT_DOUBLE_EQ(value.equivalent_airspeed, 18.);
    ASSERT_TRUE(value.height_rate); EXPECT_DOUBLE_EQ(*value.height_rate, 0.);
    EXPECT_FALSE(value.altitude_amsl);
}

TEST(NeutralRelease, NativeLoadMinimumAndMaximumConstrainTrimWithoutArbitraryLimits) {
    EXPECT_DOUBLE_EQ(std::get<FixedWingObjective>(neutralReleaseObjective(Phase::FixedWing,
        .3, 24., 18., 30.)).equivalent_airspeed, 24.);
    EXPECT_DOUBLE_EQ(std::get<FixedWingObjective>(neutralReleaseObjective(Phase::FixedWing,
        .3, 12., 35., 30.)).equivalent_airspeed, 30.);
}

TEST(NeutralRelease, MissingNativeFwFrameNeverFallsBackToTailsitterMcHeading) {
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .3, NAN, true, .01, .01, 1.));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .3, 1.2, false, .01, .01, 1.));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .3, 1.2, true, 1., .01, 1.));
    EXPECT_THROW(neutralReleaseObjective(Phase::Transition, NAN, 12., 18., 30.), std::invalid_argument);
}

TEST(NeutralRelease, InvalidPhaseOrNativeEnvelopeCannotProduceNeutralFwTranslation) {
    EXPECT_THROW(neutralReleaseObjective(Phase::Unknown, .3, 12., 18., 30.), std::invalid_argument);
    EXPECT_THROW(neutralReleaseObjective(Phase::FixedWing, .3, 31., 18., 30.), std::invalid_argument);
    EXPECT_THROW(neutralReleaseObjective(Phase::FixedWing, .3, 12., 0., 30.), std::invalid_argument);
    EXPECT_THROW(neutralReleaseObjective(Phase::FixedWing, .3, 12., INFINITY, 30.), std::invalid_argument);
}

TEST(NeutralRelease, BothTransitionDirectionsRequireExplicitCoherentNativeHelperEvidence) {
    for (const auto direction : {TransitionDirection::ToFixedWing, TransitionDirection::ToMulticopter}) {
        EXPECT_TRUE(transitionDirectionsAgree(true, direction, direction));
        EXPECT_FALSE(transitionDirectionsAgree(false, direction, direction));
        EXPECT_FALSE(transitionDirectionsAgree(true, direction, TransitionDirection::Unknown));
        const auto value = std::get<TransitionObjective>(neutralReleaseObjective(Phase::Transition, .7, 12., 18., 30.));
        EXPECT_DOUBLE_EQ(value.course, .7); EXPECT_DOUBLE_EQ(value.equivalent_airspeed, 18.);
    }
    EXPECT_FALSE(transitionDirectionsAgree(true, TransitionDirection::ToFixedWing, TransitionDirection::ToMulticopter));
    EXPECT_FALSE(transitionDirectionsAgree(true, TransitionDirection::ToMulticopter, TransitionDirection::ToFixedWing));
    EXPECT_FALSE(transitionDirectionsAgree(true, TransitionDirection::Unknown, TransitionDirection::Unknown));
}

TEST(NeutralRelease, EitherFreshPositivePhaseExitEndsPursuitBeforeBothSourcesAgree) {
    EXPECT_TRUE(observedPursuitPhaseExit(Phase::Multicopter, true, true, Phase::Multicopter, false, Phase::Unknown));
    EXPECT_TRUE(observedPursuitPhaseExit(Phase::FixedWing, false, false, Phase::Unknown, true, Phase::Transition));
    EXPECT_TRUE(observedPursuitPhaseExit(Phase::Multicopter, true, false, Phase::FixedWing, false, Phase::Unknown));
    EXPECT_FALSE(observedPursuitPhaseExit(Phase::Multicopter, false, true, Phase::FixedWing, false, Phase::Transition));
    EXPECT_FALSE(observedPursuitPhaseExit(Phase::Unknown, true, true, Phase::FixedWing, true, Phase::Transition));
}

TEST(NeutralRelease, StopEofExpiryAndPhaseExitAllLatchTheSameTerminalContextWithoutRenewal) {
    for (const auto reason : {"stop", "eof", "expiry", "phase_exit"}) {
        SCOPED_TRACE(reason);
        auto source = context();
        const auto original_wire = source.wire("runtime");
        const auto deadline = source.expires;
        CommandLease lease;
        lease.acquire(source.identity, 10., 10.3);
        lease.submit({source.identity, 1, 10., 10.3, FixedWingObjective{1.2, 25., -4., {}}}, 10.1, Phase::FixedWing);
        if (std::string(reason) == "expiry") { EXPECT_EQ(lease.current(10.3, Phase::FixedWing, true, true, false), nullptr); }
        source.endPursuit(lease);
        EXPECT_FALSE(lease.identity());
        EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
        EXPECT_EQ(source.wire("runtime"), original_wire);
        EXPECT_EQ(source.expires, deadline);
        EXPECT_TRUE(neutralDrainPermitted(source, evidence(source)));
        // A return to the starting phase or a new guidance generation cannot restart pursuit.
        auto replacement = source.identity; ++replacement.guidance_generation;
        EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
        EXPECT_THROW(lease.submit({replacement, 2, 10.1, 10.3, FixedWingObjective{1.2, 25., -4., {}}},
                                 10.1, Phase::FixedWing), std::invalid_argument);
        source.endPursuit(lease);
        EXPECT_EQ(source.expires, deadline);
        const auto neutral = std::get<FixedWingObjective>(neutralReleaseObjective(Phase::FixedWing, .3, 12., 18., 30.));
        EXPECT_DOUBLE_EQ(neutral.course, .3); EXPECT_DOUBLE_EQ(neutral.equivalent_airspeed, 18.);
        EXPECT_DOUBLE_EQ(*neutral.height_rate, 0.); EXPECT_FALSE(neutral.altitude_amsl);
    }
}

TEST(NeutralRelease, ReleasingWithOwnerActiveFalseStillAllowsExactOriginalNeutralDrain) {
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    auto status = evidence(source); status.owner_active = false;
    EXPECT_FALSE(neutralDrainPermitted(source, status));
    status.state = OwnershipReceiptState::Releasing;
    EXPECT_TRUE(neutralDrainPermitted(source, status));
    status.state = OwnershipReceiptState::Other;
    EXPECT_FALSE(neutralDrainPermitted(source, status));
}

TEST(NeutralRelease, IneligibleHoldKeepsNeutralCleanupPossibleWithoutRestoringPursuit) {
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    const auto status = evidence(source); // Native refused Hold: exact owner remains Acquired.
    EXPECT_TRUE(neutralDrainPermitted(source, status));
    EXPECT_THROW(source.requirePursuit(), std::invalid_argument);
    EXPECT_FALSE(lease.identity());
}

TEST(NeutralRelease, TakeoverReplacementStaleDisarmAndRescueStopAllNeutralPublication) {
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    for (int change = 0; change < 15; ++change) {
        SCOPED_TRACE(change);
        auto status = evidence(source);
        if (change == 0) status.actual_mode = 4;
        if (change == 1) ++status.actual_epoch;
        if (change == 2) ++status.vehicle_epoch;
        if (change == 3) ++status.acquired_epoch;
        if (change == 4) ++status.current_registration_id;
        if (change == 5) ++status.registration_id;
        if (change == 6) ++status.token[0];
        if (change == 7) ++status.incarnation[0];
        if (change == 8) status.fresh = false;
        if (change == 9) status.armed = false;
        if (change == 10) status.rescue = true;
        if (change == 11) status.aircraft_matches = false;
        if (change == 12) status.state = OwnershipReceiptState::Other; // Explicit same-ID takeover retires firmware receipt.
        if (change == 13) ++status.source_revision;
        if (change == 14) ++status.vehicle_mode;
        EXPECT_FALSE(neutralDrainPermitted(source, status));
    }
    source.observeIncarnation({0, 3});
    EXPECT_FALSE(neutralDrainPermitted(source, evidence(source)));
}

TEST(NeutralRelease, DuplicateAndReorderedObservationsCannotRenewCleanupFreshness) {
    struct Sample { std::uint64_t timestamp; };
    SourceSample<Sample> sample;
    ASSERT_TRUE(sample.update({100}, 10.));
    EXPECT_FALSE(sample.update({100}, 10.5));
    EXPECT_FALSE(sample.update({99}, 10.8));
    auto source = context(); CommandLease lease; source.endPursuit(lease);
    auto status = evidence(source);
    status.fresh = sample.fresh(11.01, 1.);
    EXPECT_FALSE(neutralDrainPermitted(source, status));
    EXPECT_EQ(sample.received(), 10.);
}

static NativeActivationEvidence startupCheckpoint(const OwnershipContext& source) {
    auto value = evidence(source);
    value.token = {};
    value.source_revision = value.source_epoch = value.registration_id = value.acquired_epoch = 0;
    value.source_mode = value.mode = 0;
    value.actual_mode = value.vehicle_mode = source.source_mode;
    value.actual_epoch = value.vehicle_epoch = source.source_epoch;
    value.intention_revision = source.source_revision;
    value.owner_active = false;
    value.state = OwnershipReceiptState::Other;
    value.ownership_fresh = value.vehicle_fresh = value.vehicle_armed = true;
    return value;
}

TEST(ActivationWait, VehicleActivationBeforeCorrelatedReceiptDoesNotEndOrAuthorizeStartup) {
    auto source = context(); source.acquired_epoch = 0;
    auto status = startupCheckpoint(source);
    status.vehicle_mode = source.mode;
    status.vehicle_epoch = 2000000;
    EXPECT_TRUE(startupActivationMayWait(source, status, 10.1, 10.5));
    EXPECT_FALSE(exactOriginalActivation(source, status));
    // Pending receipt is not an acquisition ACK or permission to publish.
    auto pending = evidence(source);
    pending.state = OwnershipReceiptState::Pending;
    pending.actual_mode = source.source_mode; pending.actual_epoch = source.source_epoch;
    pending.vehicle_epoch = 2000000;
    pending.ownership_fresh = pending.vehicle_fresh = pending.vehicle_armed = true;
    EXPECT_TRUE(startupActivationMayWait(source, pending, 10.2, 10.5));
    EXPECT_FALSE(exactOriginalActivation(source, pending));
    // A delayed exact original receipt completes only the ownership proof; no deadline moves.
    source.acquired_epoch = 2000000;
    auto confirmed = evidence(source);
    confirmed.ownership_fresh = confirmed.vehicle_fresh = confirmed.vehicle_armed = true;
    EXPECT_TRUE(startupActivationMayWait(source, confirmed, 10.4, 10.5));
    EXPECT_TRUE(exactOriginalActivation(source, confirmed));
    EXPECT_FALSE(startupActivationMayWait(source, confirmed, 10.5, 10.5));
}

TEST(ActivationWait, ReceiptBeforeVehicleSubscriberAlsoWaitsWithoutUnprovedOutput) {
    auto source = context();
    auto status = evidence(source);
    status.ownership_fresh = status.vehicle_fresh = status.vehicle_armed = true;
    status.vehicle_mode = source.source_mode; status.vehicle_epoch = source.source_epoch;
    EXPECT_TRUE(startupActivationMayWait(source, status, 10.1, 10.5));
    EXPECT_FALSE(exactOriginalActivation(source, status));
    status.vehicle_mode = source.mode; status.vehicle_epoch = source.acquired_epoch;
    EXPECT_TRUE(startupActivationMayWait(source, status, 10.2, 10.5));
    EXPECT_TRUE(exactOriginalActivation(source, status));
}

TEST(ActivationWait, StopExpiryOrTerminalReceiptCannotResumeThePendingStart) {
    auto source = context(); source.acquired_epoch = 0;
    auto status = startupCheckpoint(source);
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.5, 10.5));
    CommandLease lease; source.endPursuit(lease);
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.2, 10.5));
    source = context(); source.acquired_epoch = 0;
    status = evidence(source);
    status.ownership_fresh = status.vehicle_fresh = status.vehicle_armed = true;
    status.vehicle_mode = source.source_mode; status.vehicle_epoch = source.source_epoch;
    status.state = OwnershipReceiptState::Other; // Matched cancelled/rejected/expired/superseded receipt.
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.2, 10.5));
    status.state = OwnershipReceiptState::Releasing;
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.2, 10.5));
}

TEST(ActivationWait, PilotModeSameIdNewEpochRescueDisarmAndReplacementEndTheWait) {
    auto source = context();
    for (int change = 0; change < 8; ++change) {
        SCOPED_TRACE(change);
        auto status = evidence(source);
        status.ownership_fresh = status.vehicle_fresh = status.vehicle_armed = true;
        if (change == 0) status.vehicle_mode = 5;
        if (change == 1) ++status.vehicle_epoch;
        if (change == 2) status.vehicle_rescue = true;
        if (change == 3) status.vehicle_armed = false;
        if (change == 4) ++status.current_registration_id;
        if (change == 5) ++status.incarnation[0];
        if (change == 6) status.state = OwnershipReceiptState::Other;
        if (change == 7) { status.token = {}; status.intention_revision = source.source_revision + 1; }
        EXPECT_FALSE(startupActivationMayWait(source, status, 10.2, 10.5));
    }
}

TEST(ActivationWait, MissingCorrelationWaitsOnlyWithinOriginalBudgetWithoutInventingAReceipt) {
    auto source = context(); source.acquired_epoch = 0;
    auto status = startupCheckpoint(source);
    status.ownership_fresh = false;
    EXPECT_TRUE(startupActivationMayWait(source, status, 10.2, 10.5));
    EXPECT_FALSE(exactOriginalActivation(source, status));
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.5, 10.5));
    EXPECT_FALSE(startupActivationMayWait(source, status, NAN, 10.5));
    EXPECT_FALSE(startupActivationMayWait(source, status, 10.2, INFINITY));
    EXPECT_EQ(source.acquired_epoch, 0u);
}
