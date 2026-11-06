#include <pixeagle/phase_hold.hpp>
#include <gtest/gtest.h>

using namespace pixeagle;

TEST(PhaseHold, MulticopterNeverRetainsPreviousFwTranslationOrYaw) {
    const auto hold = phaseHold(Phase::Multicopter, FixedWingObjective{1., 20., -4., {}}, .3, 12., 18., 30.);
    const auto& mc = std::get<MulticopterObjective>(hold);
    EXPECT_DOUBLE_EQ(mc.north, 0.); EXPECT_DOUBLE_EQ(mc.east, 0.);
    EXPECT_DOUBLE_EQ(mc.down, 0.); EXPECT_DOUBLE_EQ(mc.yaw_rate, 0.);
}

TEST(PhaseHold, TransitionRetainsFeasibleCourseWithNativeForwardSpeed) {
    const auto hold = phaseHold(Phase::Transition, FixedWingObjective{1.2, 40., -4., {}}, .3, 12., 18., 30.);
    const auto& transition = std::get<TransitionObjective>(hold);
    EXPECT_DOUBLE_EQ(transition.course, 1.2);
    EXPECT_DOUBLE_EQ(transition.equivalent_airspeed, 30.);
    const auto first = std::get<TransitionObjective>(phaseHold(Phase::Transition, MulticopterObjective{}, .3, 12., 18., 30.));
    EXPECT_DOUBLE_EQ(first.course, .3); EXPECT_DOUBLE_EQ(first.equivalent_airspeed, 18.);
}

TEST(PhaseHold, FixedWingLevelsVerticalPathAndPreservesAnExistingAltitudeHold) {
    const auto level = std::get<FixedWingObjective>(phaseHold(Phase::FixedWing,
        TransitionObjective{1.2, 18.}, .3, 12., 18., 30.));
    EXPECT_DOUBLE_EQ(level.course, 1.2); EXPECT_DOUBLE_EQ(*level.height_rate, 0.);
    EXPECT_FALSE(level.altitude_amsl);
    const auto altitude = std::get<FixedWingObjective>(phaseHold(Phase::FixedWing,
        FixedWingObjective{1.2, 18., {}, 500.}, .3, 12., 18., 30.));
    EXPECT_DOUBLE_EQ(*altitude.altitude_amsl, 500.); EXPECT_FALSE(altitude.height_rate);
}

TEST(PhaseHold, InvalidPhaseOrEnvelopeCannotProduceAReplacementObjective) {
    EXPECT_THROW(phaseHold(Phase::Unknown, {}, .3, 12., 18., 30.), std::invalid_argument);
    EXPECT_THROW(phaseHold(Phase::FixedWing, {}, NAN, 12., 18., 30.), std::invalid_argument);
    EXPECT_THROW(phaseHold(Phase::FixedWing, {}, .3, 31., 18., 30.), std::invalid_argument);
    EXPECT_THROW(phaseHold(Phase::FixedWing, {}, .3, 12., 0., 30.), std::invalid_argument);
}

TEST(PhaseHold, NativeLoadDependentMinimumCanExceedTrim) {
    const auto initial = std::get<FixedWingObjective>(phaseHold(Phase::FixedWing,
        {}, .3, 24., 18., 30.));
    EXPECT_DOUBLE_EQ(initial.equivalent_airspeed, 24.);
    const auto retained = std::get<TransitionObjective>(phaseHold(Phase::Transition,
        FixedWingObjective{1.2, 20., -4., {}}, .3, 24., 18., 30.));
    EXPECT_DOUBLE_EQ(retained.equivalent_airspeed, 24.);
    EXPECT_DOUBLE_EQ(retained.course, 1.2);
}

TEST(PhaseHold, HoldingCannotRenewTheExistingLeaseAcrossAContractChange) {
    const Identity identity{"follow", "aircraft", "connection", 1, 1};
    CommandLease lease;
    lease.acquire(identity, 10., 10.3);
    const Objective previous = FixedWingObjective{1.2, 18., -3., {}};
    lease.submit({identity, 1, 10., 10.3, previous}, 10.1, Phase::FixedWing);
    for (const double now : {10.15, 10.2, 10.29}) {
        EXPECT_EQ(lease.current(now, Phase::Transition, true, true, false), nullptr);
        ASSERT_TRUE(lease.identity());
        EXPECT_EQ(phaseOf(phaseHold(Phase::Transition, previous, .3, 12., 18., 30.)), Phase::Transition);
    }
    EXPECT_EQ(lease.current(10.3, Phase::Transition, true, true, false), nullptr);
    EXPECT_FALSE(lease.identity());
}
