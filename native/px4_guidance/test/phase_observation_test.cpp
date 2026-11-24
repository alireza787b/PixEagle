#include <pixeagle/phase_observation.hpp>
#include <gtest/gtest.h>

using namespace pixeagle;

TEST(PhaseObservation, NormalVtolHeartbeatCadenceCannotExpireBetweenSamples) {
    for (int tick = 0; tick < 100; ++tick) {
        const double now = 10. + tick * .05;
        const double vehicle_received = std::floor(now * 2.) / 2. - .01;
        const double vtol_received = std::floor(now) - .01;
        EXPECT_TRUE(phaseSourcesFresh(now, vehicle_received, vtol_received, true, 1.));
    }
}

TEST(PhaseObservation, EachPhaseSourceIncludesOnlyItsOwnHeartbeatAndDeliveryAllowance) {
    EXPECT_TRUE(phaseSourcesFresh(10., 9.8, 8.8, true, 1.));
    EXPECT_TRUE(phaseSourcesFresh(10., 8.8, 9.8, true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 8.5, 9.8, true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, 8., true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, -1., true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, 10.1, true, 1.));
    EXPECT_TRUE(phaseSourcesFresh(10., 9.8, -1., false, 1.));
    EXPECT_TRUE(phaseSourcesFresh(10., 8.51, -1., false, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 8.5, -1., false, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 10.1, -1., false, 1.));
}

TEST(PhaseObservation, SourceTimeoutInputsCannotBeNonfiniteOrNonpositive) {
    EXPECT_FALSE(phaseSourcesFresh(NAN, 9.8, 9.8, true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., NAN, 9.8, true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, NAN, true, 1.));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, 9.8, true, INFINITY));
    EXPECT_FALSE(phaseSourcesFresh(10., 9.8, 9.8, true, 0.));
}

TEST(PhaseObservation, EitherPositiveTransitionSourceIdentifiesPhaseExit) {
    EXPECT_EQ(resolveObservedPhase(true, false, true, false, Phase::Multicopter, Phase::Transition), Phase::Transition);
    EXPECT_EQ(resolveObservedPhase(true, false, true, true, Phase::Multicopter, Phase::Multicopter), Phase::Transition);
    EXPECT_EQ(resolveObservedPhase(true, false, true, false, Phase::FixedWing, Phase::Multicopter), Phase::Transition);
    EXPECT_EQ(resolveObservedPhase(true, false, true, false, Phase::Multicopter, Phase::FixedWing), Phase::Transition);
}

TEST(PhaseObservation, SettledPhaseRequiresFreshAgreementAndNoRescue) {
    EXPECT_EQ(resolveObservedPhase(true, false, true, false, Phase::FixedWing, Phase::FixedWing), Phase::FixedWing);
    EXPECT_EQ(resolveObservedPhase(true, false, true, false, Phase::Multicopter, Phase::Multicopter), Phase::Multicopter);
    EXPECT_EQ(resolveObservedPhase(false, false, true, false, Phase::FixedWing, Phase::FixedWing), Phase::Unknown);
    EXPECT_EQ(resolveObservedPhase(true, true, true, false, Phase::FixedWing, Phase::FixedWing), Phase::Unknown);
    EXPECT_EQ(resolveObservedPhase(true, false, true, true, Phase::FixedWing, Phase::Unknown), Phase::Unknown);
}
