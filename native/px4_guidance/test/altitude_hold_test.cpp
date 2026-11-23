#include <pixeagle/aircraft_observations.hpp>
#include <pixeagle/multicopter_setpoint.hpp>
#include <gtest/gtest.h>
#include <limits>

namespace pixeagle {

class AircraftObservationsTest : public testing::Test {
protected:
    static void SetUpTestSuite() { rclcpp::init(0, nullptr); }
    static void TearDownTestSuite() { rclcpp::shutdown(); }
    void SetUp() override {
        node = std::make_shared<rclcpp::Node>("altitude_reference_test");
        observations = std::make_unique<AircraftObservations>(*node, .5);
        position.timestamp = 1000000;
        position.ref_timestamp = 100;
        position.xy_valid = position.z_valid = position.v_xy_valid = position.v_z_valid = position.z_global = true;
        position.ref_alt = 500.; position.z = -17.; position.heading = .2;
        envelope.timestamp = 1000000; envelope.autopilot_uid = 42;
        envelope.home_altitude_valid = true; envelope.home_altitude_amsl = 490.;
        envelope.minimum_equivalent_airspeed = 14.; envelope.trim_equivalent_airspeed = 18.;
        envelope.maximum_equivalent_airspeed = 30.; envelope.climb_rate_limit = 3.; envelope.sink_rate_limit = 3.;
        envelope.bank_limit = .5; envelope.vertical_acceleration_limit = 2.; envelope.altitude_response_time = 2.;
        px4_msgs::msg::VehicleAttitude attitude{};
        attitude.timestamp = attitude.timestamp_sample = 1000000; attitude.q[0] = 1.;
        envelope.attitude_source_publication_us = 1000000;
        envelope.attitude_source_sample_us = 999000;
        envelope.attitude_source_quaternion[0] = 1.;
        observations->_attitude.update(attitude, 10., attitude.timestamp_sample);
        update(10.);
        observations->bind({{"aircraft_uid", "42"}, {"connection_generation", "connection"},
                            {"telemetry_generation", 1u}}, 10.);
    }
    void update(double now) {
        observations->_position.update(position, now);
        observations->updateGuidanceStatus(envelope, now);
    }
    Json snapshot(double now = 10.1) {
        px4_msgs::msg::VehicleStatus status{};
        return observations->snapshot(status, Phase::Multicopter, false, 10., now);
    }
    std::shared_ptr<rclcpp::Node> node;
    std::unique_ptr<AircraftObservations> observations;
    px4_msgs::msg::VehicleLocalPosition position{};
    px4_msgs::msg::FixedWingGuidanceStatus envelope{};
    Identity identity{"follow", "42", "connection", 1, 1};
};

TEST_F(AircraftObservationsTest, RawSourceAttitudeUsesItsOriginalSampleReceiptAndPhysicalQuaternion) {
    const auto first = observations->sourceAttitude(10.1);
    ASSERT_FALSE(first.is_null());
    EXPECT_EQ(first.at("sample_timestamp_us"), 999000);
    EXPECT_EQ(first.at("publication_timestamp_us"), 1000000);
    EXPECT_EQ(first.at("quaternion_wxyz"), (Json::array({1., 0., 0., 0.})));
    EXPECT_EQ(first.at("time_basis"), "px4_source_us");
    envelope.timestamp += 100000;
    update(10.2);
    EXPECT_EQ(observations->sourceAttitude(10.2).at("received_at_monotonic_s"), 10.);
    EXPECT_TRUE(observations->sourceAttitude(10.501).is_null());
}

TEST_F(AircraftObservationsTest, RawSampleCanProgressWhileItsNativePublicationTimestampRepeats) {
    envelope.timestamp += 100000;
    envelope.attitude_source_sample_us = 1000000;
    update(10.2);
    const auto sample = observations->sourceAttitude(10.2);
    ASSERT_FALSE(sample.is_null());
    EXPECT_EQ(sample.at("sample_timestamp_us"), 1000000);
    EXPECT_EQ(sample.at("publication_timestamp_us"), 1000000);
    EXPECT_EQ(sample.at("received_at_monotonic_s"), 10.2);
}

TEST_F(AircraftObservationsTest, ConflictingSameSampleResetCannotReviveWithoutSourceProgress) {
    envelope.timestamp += 100000;
    envelope.attitude_source_quat_reset_counter = 1;
    update(10.2);
    EXPECT_TRUE(observations->sourceAttitude(10.2).is_null());
    envelope.timestamp += 100000;
    update(10.3);
    EXPECT_TRUE(observations->sourceAttitude(10.3).is_null());
    envelope.timestamp += 100000;
    envelope.attitude_source_sample_us = envelope.attitude_source_publication_us = 1001000;
    update(10.4);
    ASSERT_FALSE(observations->sourceAttitude(10.4).is_null());
    EXPECT_EQ(observations->sourceAttitude(10.4).at("quat_reset_counter"), 1);
}

TEST_F(AircraftObservationsTest, InvalidRawClockOrderAndQuaternionRefuseSourceAssociation) {
    envelope.timestamp += 100000;
    envelope.attitude_source_publication_us = 998000;
    update(10.2);
    EXPECT_TRUE(observations->sourceAttitude(10.2).is_null());
    envelope.timestamp += 100000;
    envelope.attitude_source_publication_us = envelope.attitude_source_sample_us = 1001000;
    envelope.attitude_source_quaternion[0] = NAN;
    update(10.3);
    EXPECT_TRUE(observations->sourceAttitude(10.3).is_null());
}

TEST_F(AircraftObservationsTest, ConvertsFrozenAmslUsingCurrentLocalReferenceWithoutReanchoring) {
    const auto state = snapshot();
    ASSERT_FALSE(state.is_null());
    const auto generation = state.at("altitude_reference_generation").get<std::uint64_t>();
    EXPECT_EQ(observations->altitudeHoldDown(identity, 517.5, generation, 10.1), -17.5f);
    position.timestamp++; position.z = -20.; update(10.2);
    EXPECT_EQ(observations->altitudeHoldDown(identity, 517.5, generation, 10.2), -17.5f);
    EXPECT_EQ(snapshot(10.2).at("altitude_reference_generation"), generation);
}

TEST_F(AircraftObservationsTest, PublicationQueryDetectsResetWithoutAnInterveningSnapshot) {
    auto generation = snapshot().at("altitude_reference_generation").get<std::uint64_t>();
    for (int reset = 0; reset < 3; ++reset) {
        position.timestamp++; envelope.timestamp++;
        if (reset == 0) { position.ref_timestamp++; position.ref_alt += 2.; }
        if (reset == 1) envelope.home_update_count++;
        if (reset == 2) position.z_reset_counter++;
        update(10.2 + reset * .05);
        EXPECT_FALSE(observations->altitudeHoldDown(identity, 517.5, generation, 10.3));
        const auto state = snapshot(10.3);
        ASSERT_FALSE(state.is_null());
        EXPECT_EQ(state.at("altitude_reference_generation"), generation + 1);
        ++generation;
        EXPECT_EQ(observations->altitudeHoldDown(identity, 517.5, generation, 10.3), -15.5f);
    }
}

TEST_F(AircraftObservationsTest, MissingStaleInvalidOrChangedBindingCannotPublishAltitude) {
    const auto generation = snapshot().at("altitude_reference_generation").get<std::uint64_t>();
    EXPECT_FALSE(observations->altitudeHoldDown(identity, 517., generation, 10.501));
    EXPECT_FALSE(observations->altitudeHoldDown(identity, 517., generation, 9.9));
    auto changed = identity; changed.connection = "replacement";
    EXPECT_FALSE(observations->altitudeHoldDown(changed, 517., generation, 10.1));
    changed = identity; changed.telemetry_generation++;
    EXPECT_FALSE(observations->altitudeHoldDown(changed, 517., generation, 10.1));
    for (double invalid : {double(NAN), double(INFINITY), std::numeric_limits<double>::max()})
        EXPECT_FALSE(observations->altitudeHoldDown(identity, invalid, generation, 10.1));
    position.timestamp++; position.z_global = false; update(10.2);
    EXPECT_FALSE(observations->altitudeHoldDown(identity, 517., generation, 10.2));
    position.timestamp++; position.z_global = true; envelope.timestamp++; envelope.autopilot_uid = 43; update(10.3);
    EXPECT_FALSE(observations->altitudeHoldDown(identity, 517., generation, 10.3));
}

TEST_F(AircraftObservationsTest, FreshPositionCannotRenewStaleEnvelopeOrOverflowLocalConversion) {
    const auto generation = snapshot().at("altitude_reference_generation").get<std::uint64_t>();
    position.timestamp++; update(10.6);
    EXPECT_FALSE(observations->altitudeHoldDown(identity, 517., generation, 10.6));
    envelope.timestamp++; position.timestamp++;
    position.ref_alt = -std::numeric_limits<float>::max(); update(10.7);
    EXPECT_FALSE(observations->altitudeHoldDown(identity, std::numeric_limits<float>::max(), generation, 10.7));
}

TEST(MulticopterAltitudeSetpoint, RealSdkKeepsHorizontalVelocityAndVerticalPositionExclusive) {
    const auto setpoint = multicopterAltitudeSetpoint({2., -3., std::nullopt, .2, 517.5, 7u}, -17.5f);
    EXPECT_EQ(setpoint.velocity_ned_m_s_x, 2.f); EXPECT_EQ(setpoint.velocity_ned_m_s_y, -3.f);
    EXPECT_EQ(setpoint.position_ned_m_z, -17.5f); EXPECT_FALSE(setpoint.velocity_ned_m_s_z);
    EXPECT_FALSE(setpoint.position_ned_m_x); EXPECT_FALSE(setpoint.position_ned_m_y);
    EXPECT_EQ(setpoint.yaw_rate_ned_rad_s, .2f); EXPECT_FALSE(setpoint.yaw_ned_rad);
    EXPECT_FALSE(setpoint.acceleration_ned_m_s2_x); EXPECT_FALSE(setpoint.acceleration_ned_m_s2_y);
    EXPECT_FALSE(setpoint.acceleration_ned_m_s2_z);
    EXPECT_THROW(multicopterAltitudeSetpoint({}, 0.f), std::invalid_argument);
    EXPECT_THROW(multicopterAltitudeSetpoint({2., -3., std::nullopt, .2, 517.5, 7u}, NAN), std::invalid_argument);
}

} // namespace pixeagle
