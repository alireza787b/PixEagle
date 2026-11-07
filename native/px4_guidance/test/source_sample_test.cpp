#include <pixeagle/source_sample.hpp>
#include <gtest/gtest.h>

namespace {
struct Sample { std::uint64_t timestamp{}; int value{}; };
}

TEST(ObservationProgress, APhaseArrivalCanAdvanceAnOtherwiseUnchangedPoseSnapshot) {
    pixeagle::ObservationProgress progress;
    EXPECT_EQ(progress.observe(100.), 1u);
    EXPECT_EQ(progress.observe(100.), 1u);
    EXPECT_EQ(progress.observe(100.01), 2u);
    EXPECT_EQ(progress.observe(100.02), 3u);
}

TEST(ObservationProgress, MissingReorderedAndInvalidArrivalsCannotCreateProgress) {
    pixeagle::ObservationProgress progress;
    EXPECT_EQ(progress.observe(-1.), 0u);
    EXPECT_EQ(progress.observe(NAN), 0u);
    EXPECT_EQ(progress.observe(100.), 1u);
    EXPECT_EQ(progress.observe(99.), 1u);
    EXPECT_EQ(progress.observe(INFINITY), 1u);
}

TEST(SourceSample, PollingAndDuplicatePacketsCannotRenewFreshness) {
    pixeagle::SourceSample<Sample> sample;
    EXPECT_TRUE(sample.update({100, 1}, 10.));
    EXPECT_FALSE(sample.update({100, 2}, 10.5));
    EXPECT_EQ(sample.value()->value, 1);
    EXPECT_TRUE(sample.fresh(10.1, .2));
    EXPECT_FALSE(sample.fresh(10.3, .2));
    EXPECT_FALSE(sample.fresh(9., .2));
}

TEST(SourceSample, ReorderedPacketsCannotRefreshButNewProgressRecovers) {
    pixeagle::SourceSample<Sample> sample;
    ASSERT_TRUE(sample.update({100, 1}, 10.));
    EXPECT_FALSE(sample.update({99, 2}, 10.1));
    EXPECT_EQ(sample.reorderedPackets(), 1u);
    EXPECT_FALSE(sample.fresh(11.1, 1.));
    EXPECT_TRUE(sample.update({101, 3}, 11.2));
    EXPECT_TRUE(sample.fresh(11.2, 1.));
}

TEST(SourceSample, ResetStreamCannotRenewThePreResetSample) {
    pixeagle::SourceSample<Sample> sample;
    ASSERT_TRUE(sample.update({10000, 1}, 10.));
    EXPECT_FALSE(sample.update({10, 2}, 10.1));
    EXPECT_FALSE(sample.update({20, 2}, 11.1));
    EXPECT_FALSE(sample.fresh(11.1, 1.));
}
