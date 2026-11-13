#pragma once

#include <pixeagle/local_protocol.hpp>
#include <pixeagle/source_sample.hpp>
#include <pixeagle/neutral_release.hpp>
#include <px4_msgs/msg/airspeed_validated.hpp>
#include <px4_msgs/msg/fixed_wing_guidance_status.hpp>
#include <px4_msgs/msg/vehicle_attitude.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <px4_ros2/utils/message_version.hpp>
#include <rclcpp/rclcpp.hpp>
#include <vector>
#include <tuple>

namespace pixeagle {

class AircraftObservations {
public:
    AircraftObservations(rclcpp::Node& node, double timeout_s);
    void bind(const Json& binding, double now);
    Json snapshot(const px4_msgs::msg::VehicleStatus& status, Phase phase, bool rescue,
                  double phase_received, double now) const;
    bool bindingMatches(const Identity& identity) const;
    std::optional<float> altitudeHoldDown(const Identity& identity, double altitude_amsl,
                                         std::uint64_t generation, double now) const;
    std::string firmware(double now) const;
    Json health(double now) const;
    Json pose(double now) const;
    Json commandFeedback(double now) const;
    Json attitudeTiming(double now) const;
    std::optional<NativeNeutralInput> neutralFlightData(
        const px4_msgs::msg::VehicleStatus& status, double now) const;
private:
    friend class AircraftObservationsTest;
    std::optional<std::uint64_t> altitudeReferenceGeneration(double now) const;
    template<class Message> void subscribe(rclcpp::Node& node, const std::string& topic, SourceSample<Message>& sample) {
        subscribe(node, topic, sample, [](const Message& message) { return message.timestamp; });
    }
    template<class Message, class SampleTimestamp> void subscribe(
            rclcpp::Node& node, const std::string& topic, SourceSample<Message>& sample, SampleTimestamp sample_timestamp) {
        _subscriptions.push_back(node.create_subscription<Message>(
            topic + px4_ros2::getMessageNameVersion<Message>(), rclcpp::SensorDataQoS(),
            [&sample, sample_timestamp](typename Message::ConstSharedPtr message) {
                sample.update(*message, clock(), sample_timestamp(*message));
            }));
    }
    static double clock();
    const double _timeout;
    Json _binding;
    SourceSample<px4_msgs::msg::VehicleAttitude> _attitude;
    SourceSample<px4_msgs::msg::VehicleLocalPosition> _position;
    SourceSample<px4_msgs::msg::AirspeedValidated> _airspeed;
    SourceSample<px4_msgs::msg::FixedWingGuidanceStatus> _envelope;
    std::vector<rclcpp::SubscriptionBase::SharedPtr> _subscriptions;
    mutable std::optional<std::tuple<std::uint64_t, std::uint32_t, std::uint8_t>> _reference;
    mutable std::uint64_t _reference_generation{};
    mutable ObservationProgress _progress;
};

} // namespace pixeagle
