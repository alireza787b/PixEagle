#include <pixeagle/command_lease.hpp>
#include <gtest/gtest.h>
#include <limits>

using namespace pixeagle;

static Identity identity() { return {"follow", "aircraft", "connection", 1, 1}; }
static Intent intent() { return {identity(), 1, 10., 10.3, FixedWingObjective{0., 18., 0., {}}}; }

TEST(CommandLease, ChecksExpiryAtEveryPublication) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3);
    lease.submit(intent(), 10.1, Phase::FixedWing);
    EXPECT_NE(lease.current(10.2, Phase::FixedWing, true, true, false), nullptr);
    EXPECT_EQ(lease.current(10.3, Phase::FixedWing, true, true, false), nullptr);
    EXPECT_FALSE(lease.identity());
    EXPECT_THROW(lease.submit(intent(), 10.1, Phase::FixedWing), std::invalid_argument);
}

TEST(CommandLease, QueuedRequestsCannotRenewTheLease) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3);
    EXPECT_THROW(lease.submit(intent(), 10.31, Phase::FixedWing), std::invalid_argument);
    EXPECT_THROW(lease.submit(intent(), 9.9, Phase::FixedWing), std::invalid_argument);
}

TEST(CommandLease, SessionIdentityCannotBeReplacedWithinAnAcquisition) {
    CommandLease lease;
    auto first = identity(), next = first;
    next.guidance_generation++;
    lease.acquire(first, 10., 10.3);
    lease.submit(intent(), 10.1, Phase::FixedWing);
    auto updated = intent(); updated.identity = next; updated.sequence = 0;
    EXPECT_THROW(lease.submit(updated, 10.1, Phase::FixedWing), std::invalid_argument);
    EXPECT_NE(lease.current(10.2, Phase::FixedWing, true, true, false), nullptr);
    EXPECT_EQ(*lease.identity(), first);
}

TEST(CommandLease, TakeoverRescueAndStaleStateRevokeRatherThanResume) {
    for (int condition = 0; condition < 3; ++condition) {
        CommandLease lease;
        lease.acquire(identity(), 10., 10.3); lease.submit(intent(), 10.1, Phase::FixedWing);
        EXPECT_EQ(lease.current(10.2, Phase::FixedWing, condition != 0, condition != 1, condition == 2), nullptr);
        EXPECT_EQ(lease.current(10.21, Phase::FixedWing, true, true, false), nullptr);
        EXPECT_FALSE(lease.identity());
    }
}

TEST(CommandLease, PhaseChangesInvalidatePreviousObjective) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3); lease.submit(intent(), 10.1, Phase::FixedWing);
    EXPECT_EQ(lease.current(10.2, Phase::Transition, true, true, false), nullptr);
    EXPECT_EQ(lease.current(10.21, Phase::FixedWing, true, true, false), nullptr);
    EXPECT_FALSE(lease.identity());
}

TEST(CommandLease, PhaseCannotChangeBeforeThePublicationTimerObservesIt) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3);
    lease.submit(intent(), 10.1, Phase::FixedWing);
    auto next = intent(); next.sequence++;
    next.objective = MulticopterObjective{0., 0., 0., 0.};
    EXPECT_THROW(lease.submit(next, 10.2, Phase::Multicopter), std::invalid_argument);
    EXPECT_EQ(lease.current(10.21, Phase::Multicopter, true, true, false), nullptr);
    auto generation = identity(); generation.guidance_generation++;
    next.identity = generation;
    EXPECT_THROW(lease.submit(next, 10.21, Phase::Multicopter), std::invalid_argument);
    EXPECT_EQ(lease.current(10.22, Phase::Multicopter, true, true, false), nullptr);
    EXPECT_FALSE(lease.identity());
}

TEST(CommandLease, TransitionCanOnlyBeAnInternalNeutralObjectiveNotPursuit) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3);
    auto transition = intent(); transition.objective = TransitionObjective{.3, 18.};
    EXPECT_THROW(lease.submit(transition, 10.1, Phase::Transition), std::invalid_argument);
    EXPECT_FALSE(lease.identity());
    EXPECT_THROW(lease.submit(intent(), 10.2, Phase::FixedWing), std::invalid_argument);
}

TEST(CommandLease, RejectsReorderingAndContractMismatch) {
    CommandLease lease;
    lease.acquire(identity(), 10., 10.3); lease.submit(intent(), 10.1, Phase::FixedWing);
    EXPECT_THROW(lease.submit(intent(), 10.2, Phase::FixedWing), std::invalid_argument);
    for (const auto objective : {FixedWingObjective{0., 18., 0., 100.}, FixedWingObjective{0., 0., 0., {}},
                                FixedWingObjective{0., std::numeric_limits<double>::max(), 0., {}}}) {
        auto next = intent(); next.sequence++; next.objective = objective;
        EXPECT_THROW(lease.submit(next, 10.2, Phase::FixedWing), std::invalid_argument);
        EXPECT_NE(lease.current(10.2, Phase::FixedWing, true, true, false), nullptr);
    }
}

TEST(CommandLease, AltitudeHoldCannotCombineVerticalVelocityOrOmitGeneration) {
    EXPECT_NO_THROW(validate(MulticopterObjective{1., 2., 3., .4}));
    EXPECT_NO_THROW(validate(MulticopterObjective{1., 2., std::nullopt, .4, 517., 3u}));
    EXPECT_THROW(validate(MulticopterObjective{1., 2., 0., .4, 517., 3u}), std::invalid_argument);
    EXPECT_THROW(validate(MulticopterObjective{1., 2., std::nullopt, .4, 517., {}}), std::invalid_argument);
    EXPECT_THROW(validate(MulticopterObjective{1., 2., std::nullopt, .4}), std::invalid_argument);
    EXPECT_THROW(validate(MulticopterObjective{1., 2., 0., .4, {}, 3u}), std::invalid_argument);
    for (const double invalid : {double(NAN), double(INFINITY), double(-INFINITY), std::numeric_limits<double>::max()}) {
        EXPECT_THROW(validate(MulticopterObjective{1., 2., std::nullopt, .4, invalid, 3u}), std::invalid_argument);
        EXPECT_THROW(validate(MulticopterObjective{1., 2., invalid, .4}), std::invalid_argument);
    }
}

TEST(CommandLease, RevocationRemovesHeldAltitudeAndCannotBeReopenedByLateIntent) {
    CommandLease lease;
    lease.acquire(identity(), 10., 11.);
    Intent hold{identity(), 1, 10., 10.3, MulticopterObjective{1., 2., std::nullopt, .4, 517., 3u}};
    lease.submit(hold, 10.01, Phase::Multicopter);
    ASSERT_NE(lease.current(10.02, Phase::Multicopter, true, true, false), nullptr);
    lease.revoke();
    EXPECT_EQ(lease.current(10.03, Phase::Multicopter, true, true, false), nullptr);
    EXPECT_THROW(lease.submit(hold, 10.04, Phase::Multicopter), std::invalid_argument);
}
