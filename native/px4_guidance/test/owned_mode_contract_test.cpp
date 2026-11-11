#include <pixeagle/owned_mode_contract.hpp>
#include <gtest/gtest.h>
#include <fstream>
#include <limits>

using namespace pixeagle;

static OwnershipContext context() {
    return {Identity{"follow-a", "aircraft-a", "1", 1, 1}, {0, 1}, {0, 2}, 7, 1000000, 2000000,
            1500000, 4, 23, 99};
}

TEST(OwnedModeContract, GoldenAcquisitionAndReceiptUseTheOriginalIdentity) {
    std::ifstream file(PIXEAGLE_OWNERSHIP_PROTOCOL_FIXTURE);
    ASSERT_TRUE(file.good());
    const auto fixture = Json::parse(file);
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
