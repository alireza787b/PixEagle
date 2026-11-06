#include <pixeagle/phase_observation.hpp>
#include <gtest/gtest.h>

using namespace pixeagle;

TEST(PhaseObservation, EitherPositiveTransitionSourcePausesPursuit) {
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
