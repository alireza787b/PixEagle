#include <pixeagle/navigation_heading.hpp>
#include <gtest/gtest.h>
#include <limits>

using namespace pixeagle;

TEST(NavigationHeading, FixedWingUsesNativeControllerFrameInsteadOfPhysicalMcHeading) {
    EXPECT_DOUBLE_EQ(*navigationHeading(Phase::FixedWing, 2.4, -.3, true, .01, .05, .5), -.3);
    EXPECT_DOUBLE_EQ(*navigationHeading(Phase::FixedWing, NAN, -.3, true, .01, .05, .5), -.3);
    EXPECT_DOUBLE_EQ(*navigationHeading(Phase::Multicopter, 2.4, -.3, true, .01, .05, .5), 2.4);
    EXPECT_DOUBLE_EQ(*navigationHeading(Phase::Transition, 2.4, -.3, true, .01, .05, .5), 2.4);
}

TEST(NavigationHeading, FixedWingCannotFallbackToAnIncompatibleOrStaleFrame) {
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .2, -.3, false, .01, .05, .5));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .2, -.3, true, .4, .2, .5));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .2, -.3, true, -.01, .05, .5));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .2, -.3, true, .01, -.05, .5));
    EXPECT_FALSE(navigationHeading(Phase::FixedWing, .2, std::numeric_limits<double>::quiet_NaN(), true, .01, .05, .5));
    EXPECT_FALSE(navigationHeading(Phase::Unknown, .2, -.3, true, .01, .05, .5));
}

TEST(NavigationHeading, MulticopterDoesNotDependOnTheUnusedFwFrame) {
    EXPECT_DOUBLE_EQ(*navigationHeading(Phase::Multicopter, .4, NAN, false, NAN, NAN, .5), .4);
    EXPECT_FALSE(navigationHeading(Phase::Multicopter, NAN, .4, true, .01, .01, .5));
}
