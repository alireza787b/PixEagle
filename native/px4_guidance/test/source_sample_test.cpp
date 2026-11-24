#include <pixeagle/source_sample.hpp>
#include <gtest/gtest.h>

namespace {
struct Sample { std::uint64_t timestamp{}; int value{}; };
struct AttitudePacket {
    std::uint64_t timestamp{};
    std::uint64_t timestamp_sample{};
    std::uint8_t quat_reset_counter{};
    int quaternion_marker{};
};
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

TEST(SourceSample, RepublishingAnAttitudeRetainsItsFirstSampleReceipt) {
    pixeagle::SourceSample<AttitudePacket> sample;
    ASSERT_TRUE(sample.update({1000000, 990000, 255, 1}, 10., 990000));
    ASSERT_TRUE(sample.update({1010000, 990000, 0, 2}, 10.5, 990000));
    EXPECT_EQ(sample.value()->quat_reset_counter, 0);
    EXPECT_EQ(sample.value()->quaternion_marker, 2);
    EXPECT_EQ(sample.received(), 10.5);
    EXPECT_EQ(sample.sampleReceived(), 10.);
    EXPECT_TRUE(sample.sampleFresh(10.6, 1.));
    EXPECT_FALSE(sample.sampleFresh(11.01, 1.));
    EXPECT_TRUE(sample.fresh(11.01, 1.));
}

TEST(SourceSample, DuplicatePublicationCannotReplaceItsQuaternionOrSampleClock) {
    pixeagle::SourceSample<AttitudePacket> sample;
    ASSERT_TRUE(sample.update({1000000, 990000, 1, 2}, 10., 990000));
    EXPECT_FALSE(sample.update({1000000, 1000000, 2, 99}, 10.1, 1000000));
    EXPECT_EQ(sample.value()->quaternion_marker, 2);
    EXPECT_EQ(sample.value()->timestamp_sample, 990000u);
    EXPECT_EQ(sample.sampleReceived(), 10.);
}

TEST(SourceSample, ProcessingAgeConsumesTheFreshnessBudgetWithoutClockConversion) {
    for (const std::uint64_t offset : {std::uint64_t{0}, std::uint64_t{1700000000000000}}) {
        pixeagle::SourceSample<AttitudePacket> sample;
        ASSERT_TRUE(sample.update({offset + 1000000, offset + 100000, 0, 1}, 10., offset + 100000));
        EXPECT_TRUE(sample.sampleFresh(10.05, 1.));
        EXPECT_FALSE(sample.sampleFresh(10.2, 1.));
        EXPECT_TRUE(sample.fresh(10.2, 1.));
    }
}

TEST(SourceSample, InvalidOrReorderedSampleTimeCannotRefreshAValidMeasurement) {
    pixeagle::SourceSample<AttitudePacket> sample;
    ASSERT_TRUE(sample.update({1000000, 900000, 0, 1}, 10., 900000));
    for (const auto timestamp : {std::uint64_t{0}, std::uint64_t{1200000}, std::uint64_t{800000}}) {
        ASSERT_TRUE(sample.update({sample.value()->timestamp + 1, timestamp, 0, 2}, 10.1, timestamp));
        EXPECT_FALSE(sample.sampleFresh(10.1, 1.));
        EXPECT_EQ(sample.sampleReceived(), 10.);
    }
    ASSERT_TRUE(sample.update({1300000, 1100000, 0, 3}, 10.2, 1100000));
    EXPECT_EQ(sample.sampleReceived(), 10.2);
    EXPECT_TRUE(sample.sampleFresh(10.2, 1.));
    EXPECT_FALSE(sample.sampleFresh(10.1, 1.));
}

TEST(SourceSample, InvalidReceiptAndFreshnessClocksCannotRenewTheSample) {
    pixeagle::SourceSample<AttitudePacket> sample;
    ASSERT_TRUE(sample.update({1000000, 990000, 255, 1}, 10., 990000));
    for (const double received : {-1., 9., double(NAN), double(INFINITY)}) {
        EXPECT_FALSE(sample.update({1010000, 1000000, 0, 2}, received, 1000000));
        EXPECT_EQ(sample.received(), 10.);
        EXPECT_EQ(sample.sampleReceived(), 10.);
        EXPECT_EQ(sample.value()->quat_reset_counter, 255);
    }
    EXPECT_FALSE(sample.sampleFresh(9.9, 1.));
    EXPECT_FALSE(sample.sampleFresh(NAN, 1.));
    EXPECT_FALSE(sample.sampleFresh(INFINITY, 1.));
    EXPECT_FALSE(sample.sampleFresh(10., 0.));
    EXPECT_FALSE(sample.sampleFresh(10., NAN));
    EXPECT_FALSE(sample.sampleFresh(10., INFINITY));
    EXPECT_FALSE(sample.sampleFresh(11.01, 1.));
}
