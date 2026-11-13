#include <pixeagle/owned_mode_contract.hpp>
#include <gtest/gtest.h>
#include <fstream>
#include <limits>

using namespace pixeagle;

static OwnershipContext context() {
    auto result = OwnershipContext{Identity{"follow-a", "aircraft-a", "1", 1, 1}, {0, 1}, {0, 2}, 7, 1000000, 2000000,
            1500000, 4, 23, 99};
    result.start_context = NativeStartContext{"test-adapter", {{"aircraft_uid", "aircraft-a"},
        {"connection_generation", "1"}, {"telemetry_generation", 1u}}, {0, 2}, 23, 4, 99, 7, 1000000, 0, 0, Phase::FixedWing};
    return result;
}

TEST(OwnedModeContract, GoldenAcquisitionAndReceiptUseTheOriginalIdentity) {
    std::ifstream file(PIXEAGLE_OWNERSHIP_PROTOCOL_FIXTURE);
    ASSERT_TRUE(file.good());
    const auto fixture = Json::parse(file);
    EXPECT_EQ(fixture.at("protocol_version"), kProtocolVersion);
    EXPECT_EQ(fixture.at("capabilities").at("external_mode_api_version"), 2);
    EXPECT_EQ(fixture.at("capabilities").at("multicopter_altitude_hold_supported"), true);
    EXPECT_EQ(context().wire("test-adapter"), fixture.at("acquisition"));
    EXPECT_EQ(fixture.at("release_receipt").at("acquisition"), fixture.at("acquisition"));
    auto source = context();
    auto current_intent = source.identity;
    current_intent.guidance_generation = 9;
    EXPECT_NE(source.identity.guidance_generation, current_intent.guidance_generation);
    EXPECT_EQ(source.wire("test-adapter").at("identity").at("guidance_generation"), 1);
}

TEST(OwnedModeContract, TokensAreFiniteExact128BitValuesWithoutWeakFallback) {
    const OwnershipToken maximum{std::numeric_limits<std::uint64_t>::max(), std::numeric_limits<std::uint64_t>::max()};
    EXPECT_EQ(decodeOwnershipToken(encodeOwnershipToken(maximum)), maximum);
    for (const Json& invalid : {Json(nullptr), Json(1), Json(true), Json(""), Json("1"),
            Json("00000000000000000000000000000000"), Json("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF")}) {
        EXPECT_THROW(decodeOwnershipToken(invalid), std::invalid_argument);
    }
}

TEST(OwnedModeContract, SourceClockDeadlineUsesOnlyTheRemainingRequestBudget) {
    EXPECT_EQ(ownershipDeadline(1000000, 10., 10.5), 1500000);
    EXPECT_LE(ownershipDeadline(1000000, 10.4, 10.5), 1100000);
    EXPECT_GE(ownershipDeadline(1000000, 10.4, 10.5), 1099990);
    EXPECT_EQ(ownershipDeadline(1000000, 10., 12.), 1500000);
    EXPECT_THROW(ownershipDeadline(1000000, 10.5, 10.5), std::invalid_argument);
    EXPECT_THROW(ownershipDeadline(0, 10., 10.5), std::invalid_argument);
    EXPECT_THROW(ownershipDeadline(std::numeric_limits<std::uint64_t>::max(), 10., 10.5), std::invalid_argument);
    EXPECT_THROW(ownershipDeadline(1000000, NAN, 10.5), std::invalid_argument);
}

TEST(OwnedModeContract, PublicationOrderAndIncarnationRetirementCannotBeReversed) {
    const OwnershipToken original{0, 2}, replacement{0, 3};
    EXPECT_FALSE(ownershipPublicationProgresses(100, original, 1000, 100, original, 1000));
    EXPECT_FALSE(ownershipPublicationProgresses(100, original, 1000, 99, replacement, 10));
    EXPECT_TRUE(ownershipPublicationProgresses(100, original, 1000, 101, replacement, 10));
    EXPECT_FALSE(ownershipPublicationProgresses(101, replacement, 10, 100, original, 1000));
    auto source = context();
    source.observeIncarnation(original);
    EXPECT_FALSE(source.retired);
    source.observeIncarnation(replacement);
    EXPECT_TRUE(source.retired);
    source.observeIncarnation(original);
    EXPECT_TRUE(source.retired);
    EXPECT_FALSE(source.matches(source.token, original, source.source_revision, source.source_epoch,
                                source.source_mode, source.mode, source.registration_id));
}

TEST(OwnedModeContract, ReplacementRegistrationCannotMatchTheOriginalReceipt) {
    const auto source = context();
    EXPECT_TRUE(source.matches(source.token, source.incarnation, source.source_revision, source.source_epoch,
                               source.source_mode, source.mode, 99));
    EXPECT_FALSE(source.matches(source.token, source.incarnation, source.source_revision, source.source_epoch,
                                source.source_mode, source.mode, 100));
}

TEST(OwnedModeContract, AcquisitionRequiresItsOwnSuccessfulRegistrationBeforeContextCreation) {
    EXPECT_EQ(requireOwnRegistration(99, 99), 99u);
    EXPECT_THROW(requireOwnRegistration(99, 100), std::invalid_argument);
    EXPECT_THROW(requireOwnRegistration(99, 0), std::invalid_argument);
    EXPECT_THROW(requireOwnRegistration(0, 99), std::invalid_argument);
    EXPECT_THROW(requireOwnRegistration(0, 0), std::invalid_argument);
    // Losing current eligibility does not invalidate an original terminal receipt.
    const auto original = context();
    EXPECT_TRUE(original.matches(original.token, original.incarnation, original.source_revision,
        original.source_epoch, original.source_mode, original.mode, 99));
}

TEST(OwnedModeContract, RegistrationProofNeverAdoptsPreRegistrationOrReplacementStatus) {
    RegistrationProof proof;
    const OwnershipToken incarnation{7, 8};
    for (const auto own : {0u, 99u}) {
        for (const auto current : {0u, 100u}) {
            proof.observe(own, current, incarnation, 10, 1, 1, true);
            EXPECT_FALSE(proof.ready());
            EXPECT_FALSE(proof.retired());
        }
    }
    proof.observe(99, 99, incarnation, 10, 1, 1, false);
    EXPECT_FALSE(proof.ready());
    proof.observe(99, 99, {}, 10, 1, 1, true);
    EXPECT_FALSE(proof.ready());
    proof.observe(99, 99, incarnation, 10, 1, 1, true);
    EXPECT_TRUE(proof.ready());
}

TEST(OwnedModeContract, ProgressingRegistrationRemovalOrReusePermanentlyRetiresProof) {
    for (const auto replacement : {0u, 100u}) {
        RegistrationProof proof;
        const OwnershipToken incarnation{7, 8};
        proof.observe(99, 99, incarnation, 10, 1, 1, true);
        const bool old = ownershipPublicationProgresses(100, incarnation, 1000, 99, incarnation, 900);
        ASSERT_FALSE(old);
        proof.observe(99, replacement, incarnation, 10, 1, 1, old);
        EXPECT_TRUE(proof.ready());
        proof.observe(99, replacement, incarnation, 10, 1, 1, true);
        EXPECT_TRUE(proof.retired());
        EXPECT_FALSE(proof.ready());
        proof.observe(99, 99, incarnation, 10, 1, 1, true);
        EXPECT_FALSE(proof.ready());
    }
}

TEST(OwnedModeContract, VerifiedRegistrationIncarnationChangeRetiresBeforeClockResetFiltering) {
    RegistrationProof proof;
    const OwnershipToken original{7, 8}, changed{9, 10};
    proof.observe(99, 99, original, 10, 1, 1, true);
    proof.observe(99, 99, changed, 10, 1, 1, false);
    EXPECT_TRUE(proof.retired());
    proof.observe(99, 99, original, 10, 1, 1, true);
    EXPECT_FALSE(proof.ready());
}

TEST(OwnedModeContract, ConfirmedUidSystemOrComponentConflictPermanentlyRetiresRegistration) {
    const std::array<std::array<std::uint64_t, 3>, 3> replacements{{{11, 1, 1}, {10, 2, 1}, {10, 1, 2}}};
    for (const auto& source : replacements) {
        for (const bool progresses : {false, true}) {
            RegistrationProof proof;
            const auto original = context();
            proof.observe(99, 99, original.incarnation, 10, 1, 1, true);
            CommandLease lease;
            lease.acquire(original.identity, 10., 11.);
            lease.submit({original.identity, 1, 10., 11., FixedWingObjective{1., 20., -2., {}}}, 10., Phase::FixedWing);
            proof.observe(99, 99, original.incarnation, source[0], source[1], source[2], progresses);
            EXPECT_TRUE(proof.retired());
            EXPECT_FALSE(proof.ready());
            EXPECT_EQ(lease.current(10.2, Phase::FixedWing, proof.ready(), true, false), nullptr);
            EXPECT_FALSE(lease.identity());
            proof.observe(99, 99, original.incarnation, 10, 1, 1, true);
            EXPECT_FALSE(proof.ready());
        }
    }
}

TEST(OwnedModeContract, UnconfirmedForeignReplacementOrInvalidPacketCannotEstablishProof) {
    RegistrationProof proof;
    proof.observe(99, 100, {7, 8}, 11, 2, 3, true);
    proof.observe(0, 99, {7, 8}, 11, 2, 3, true);
    proof.observe(99, 99, {}, 11, 2, 3, true);
    proof.observe(99, 99, {7, 8}, 11, 2, 3, false);
    EXPECT_FALSE(proof.ready());
    EXPECT_FALSE(proof.retired());
    proof.observe(99, 99, {7, 8}, 10, 1, 1, true);
    EXPECT_TRUE(proof.ready());
    proof.observe(99, 100, {}, 11, 2, 3, true);
    EXPECT_TRUE(proof.ready());
}

TEST(OwnedModeContract, RetirementRevokesRetainedPursuitWithoutChangingOriginalReceiptValidity) {
    RegistrationProof proof;
    const auto original = context();
    proof.observe(99, 99, original.incarnation, 10, 1, 1, true);
    CommandLease lease;
    lease.acquire(original.identity, 10., 11.);
    lease.submit({original.identity, 1, 10., 11., FixedWingObjective{1., 20., -2., {}}}, 10., Phase::FixedWing);
    ASSERT_NE(lease.current(10.1, Phase::FixedWing, proof.ready(), true, false), nullptr);
    proof.observe(99, 100, original.incarnation, 10, 1, 1, true);
    EXPECT_EQ(lease.current(10.2, Phase::FixedWing, proof.ready(), true, false), nullptr);
    EXPECT_FALSE(lease.identity());
    EXPECT_TRUE(original.matches(original.token, original.incarnation, original.source_revision,
        original.source_epoch, original.source_mode, original.mode, original.registration_id));
}

TEST(OwnedModeContract, EqualSessionIdentityCannotAuthorizeAnOldAcquisitionToken) {
    auto original = context();
    auto replacement = original;
    replacement.token = {9, 10};
    ASSERT_TRUE(original.identity == replacement.identity);
    EXPECT_NO_THROW(replacement.requireToken(replacement.token));
    EXPECT_THROW(replacement.requireToken(original.token), std::invalid_argument);
}

TEST(OwnedModeContract, VerifiedRestartRetiresOwnerBeforeResetClockPublicationFiltering) {
    auto source = context();
    const auto original = source.incarnation;
    const OwnershipToken replacement{0, 3};
    EXPECT_FALSE(source.observePublication(1000, original, 2000000, 10, replacement, 10));
    EXPECT_TRUE(source.retired);
    // The rejected payload did not become a fresh status; even a later old-incarnation
    // publication cannot restore the immutable acquisition.
    EXPECT_TRUE(source.observePublication(1000, original, 2000000, 1001, original, 2000001));
    EXPECT_TRUE(source.retired);
    EXPECT_FALSE(source.matches(source.token, original, source.source_revision, source.source_epoch,
                                source.source_mode, source.mode, source.registration_id));
}
