#include <pixeagle/local_server.hpp>
#include <gtest/gtest.h>
#include <array>
#include <filesystem>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

using namespace pixeagle;

static Json identityJson() {
    return {{"follow_session_id", "follow"}, {"guidance_generation", 1u},
            {"binding", {{"aircraft_uid", "aircraft"}, {"connection_generation", "connection"}, {"telemetry_generation", 1u}}}};
}

static Json requestJson(std::uint64_t id = 1) {
    return {{"protocol_version", 2u}, {"request_id", id}, {"generation", 1u},
            {"operation", "observe"}, {"payload", Json::object()}};
}

TEST(LocalProtocol, StrictIdentityAndEnvelope) {
    auto value = identityJson();
    EXPECT_EQ(decodeIdentity(value).guidance_generation, 1u);
    value["guidance_generation"] = true;
    EXPECT_THROW(decodeIdentity(value), std::invalid_argument);
    value["guidance_generation"] = 1.;
    EXPECT_THROW(decodeIdentity(value), std::invalid_argument);
    auto request = requestJson(); request["protocol_version"] = true;
    EXPECT_THROW(decodeRequest(request.dump()), std::invalid_argument);
    request = requestJson(); request["extra"] = 1;
    EXPECT_THROW(decodeRequest(request.dump()), std::invalid_argument);
    EXPECT_THROW(decodeRequest(std::string(kMaximumMessageBytes + 1, ' ')), std::invalid_argument);
}

TEST(LocalProtocol, AllCommandContractsAndNoSilentSpeedPolicyDowngrade) {
    Json payload{{"identity", identityJson()}, {"token", "00000000000000000000000000000001"}, {"sequence", 1u}, {"created_at_monotonic_s", 10.},
                 {"expires_at_monotonic_s", 10.3}, {"phase", "fixed_wing"},
                 {"command", {{"course_rad", .3}, {"equivalent_airspeed_m_s", 18.}, {"height_rate_m_s", 0.},
                              {"altitude_amsl_m", nullptr}, {"upper_speed_policy", "px4_configured_max"}}}};
    EXPECT_EQ(phaseOf(decodeIntent(payload).objective), Phase::FixedWing);
    payload["command"]["upper_speed_policy"] = "no_upper_speed_bound";
    EXPECT_THROW(decodeIntent(payload), std::invalid_argument);
    payload["phase"] = "multicopter";
    payload["command"] = {{"velocity_north_m_s", 1.}, {"velocity_east_m_s", 2.},
                           {"velocity_down_m_s", -1.}, {"yaw_rate_rad_s", .1}};
    EXPECT_EQ(phaseOf(decodeIntent(payload).objective), Phase::Multicopter);
    payload["phase"] = "vtol_transition";
    payload["command"] = {{"course_rad", .3}, {"equivalent_airspeed_m_s", 18.}};
    EXPECT_EQ(phaseOf(decodeIntent(payload).objective), Phase::Transition);
    payload["command"]["equivalent_airspeed_m_s"] = true;
    EXPECT_THROW(decodeIntent(payload), std::invalid_argument);
}

class LocalServerTest : public testing::Test {
protected:
    void SetUp() override {
        std::array<char, 40> pattern{};
        std::strcpy(pattern.data(), "/tmp/pixeagle-native-XXXXXX");
        const char* created = mkdtemp(pattern.data());
        ASSERT_NE(created, nullptr);
        directory = created;
        path = directory + "/control.sock";
    }
    void TearDown() override {
        if (peer >= 0) close(peer);
        std::filesystem::remove_all(directory);
    }
    void connectPeer() {
        peer = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
        ASSERT_GE(peer, 0);
        sockaddr_un address{};
        address.sun_family = AF_UNIX;
        std::strcpy(address.sun_path, path.c_str());
        ASSERT_EQ(connect(peer, reinterpret_cast<sockaddr*>(&address), sizeof(address)), 0);
    }
    void sendRequest(const Json& request) {
        const auto raw = request.dump() + "\n";
        ASSERT_EQ(send(peer, raw.data(), raw.size(), MSG_NOSIGNAL), static_cast<ssize_t>(raw.size()));
    }
    Json receive() {
        std::array<char, kMaximumMessageBytes> buffer{};
        const auto size = recv(peer, buffer.data(), buffer.size(), MSG_DONTWAIT);
        if (size <= 0) return nullptr;
        return Json::parse(std::string(buffer.data(), size));
    }
    std::string directory, path;
    int peer{-1};
};

TEST_F(LocalServerTest, UsesRealLocalSocketAndDisconnectInvalidatesOwnership) {
    int disconnected = 0, actions = 0;
    LocalServer server(path, [&](const Request& request) -> std::optional<Json> {
        ++actions;
        return Json{{"fresh", true}, {"operation", request.operation}};
    }, [&] { ++disconnected; }, .5);
    connectPeer(); sendRequest(requestJson()); server.poll(10.);
    const auto reply = receive();
    ASSERT_TRUE(reply.is_object());
    EXPECT_EQ(reply.at("request_id"), 1u);
    EXPECT_TRUE(reply.at("success").get<bool>());
    EXPECT_EQ(actions, 1);
    close(peer); peer = -1;
    server.poll(10.01);
    EXPECT_EQ(disconnected, 1);
}

TEST_F(LocalServerTest, DuplicateRequestsCloseConnectionWithoutExecutingAgain) {
    int actions = 0, disconnected = 0;
    LocalServer server(path, [&](const Request&) -> std::optional<Json> { ++actions; return Json::object(); },
                       [&] { ++disconnected; }, .5);
    connectPeer(); sendRequest(requestJson()); server.poll(10.); receive();
    sendRequest(requestJson()); server.poll(10.1);
    EXPECT_EQ(actions, 1);
    EXPECT_EQ(disconnected, 1);
}

TEST_F(LocalServerTest, PendingOperationTimeoutRevokesRatherThanReplaying) {
    int disconnected = 0;
    LocalServer server(path, [](const Request&) -> std::optional<Json> { return {}; },
                       [&] { ++disconnected; }, .5);
    connectPeer(); sendRequest(requestJson()); server.poll(10.);
    EXPECT_EQ(disconnected, 0);
    server.poll(10.5);
    EXPECT_EQ(disconnected, 1);
}

TEST_F(LocalServerTest, DisconnectDuringPendingOperationRevokesWithoutWaitingForTimeout) {
    int disconnected = 0;
    LocalServer server(path, [](const Request&) -> std::optional<Json> { return {}; },
                       [&] { ++disconnected; }, .5);
    connectPeer(); sendRequest(requestJson()); server.poll(10.);
    EXPECT_EQ(disconnected, 0);
    close(peer); peer = -1;
    server.poll(10.001);
    EXPECT_EQ(disconnected, 1);
}

TEST_F(LocalServerTest, NeverOverwritesAnExistingSocketOrFile) {
    LocalServer server(path, [](const Request&) -> std::optional<Json> { return Json::object(); }, [] {}, .5);
    EXPECT_THROW((LocalServer{path, [](const Request&) -> std::optional<Json> { return {}; }, [] {}, .5}), std::runtime_error);
    connectPeer(); sendRequest(requestJson()); server.poll(10.);
    EXPECT_TRUE(receive().at("success").get<bool>());
}
