from dataclasses import replace
import math

import pytest

from classes.aircraft_state import AircraftBinding, AirframePhase, GuidanceSessionIdentity
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.target_continuity import (
    ContinuityAuthorityState, ContinuityContext, ContinuityPolicy, IdentityVerdict,
    TargetContinuitySupervisor, TargetEvidenceSnapshot, TargetEvidenceState,
)


def identity(generation=1):
    return GuidanceSessionIdentity("follow", AircraftBinding("aircraft", "connection", 1), generation)


def intent(*, course=0., rate=-2., altitude=None, generation=1):
    return FixedWingCommand(course, 18., rate, altitude).intent(identity(generation), source="fixture")


def evidence(confirmed=True, epoch=1):
    return TargetEvidenceSnapshot(
        TargetEvidenceState.CONFIRMED if confirmed else TargetEvidenceState.ABSENT,
        0., epoch, "target", IdentityVerdict.CONFIRMED if confirmed else IdentityVerdict.UNCONFIRMED,
        "fixture",
    )


def context(**updates):
    return replace(ContinuityContext("COMMAND_PREVIEW", AirframePhase.FIXED_WING,
                                    "fixed_wing_external", True, True, True, guidance_identity=identity()), **updates)


def supervisor():
    result = TargetContinuitySupervisor(ContinuityPolicy.from_mapping({
        "MODE": "bounded_flight", "MAX_COAST_TIME_S": 8., "MAX_COAST_DISTANCE_M": 0.,
        "MAX_RETARGET_TIME_S": 8., "REACQUIRE_CONFIRMATION_S": .5,
        "AUTHORITY_RESTORE_TIME_S": .5,
    }), clock=lambda: 1.)
    result.reset_session(session_epoch=1, reason="start")
    result.evaluate(evidence(), context(), intent(), now_monotonic_s=0.)
    return result


def test_recovery_keeps_forward_speed_course_and_requests_level_flight():
    owner = supervisor()
    for now in (1., 2., 4., 8.99):
        decision = owner.evaluate(evidence(False), context(), now_monotonic_s=now)
        command = FixedWingCommand.from_intent(decision.authorized_intent)
        assert command.equivalent_airspeed_m_s == 18.
        assert command.course_rad == 0.
        assert command.height_rate_m_s == 0.
        assert decision.coast_distance_m == 0.
    decision = owner.evaluate(evidence(False), context(), now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == "maximum_coast_time_reached"
    assert decision.authorized_intent is None


def test_retarget_and_tracking_flaps_do_not_renew_existing_loss_deadline():
    owner = supervisor()
    decision = owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    assert owner.begin_target_transition(session_epoch=2, previous_intent=decision.authorized_intent)
    for now, good in ((2., True), (2.1, False), (8.8, True), (8.9, False)):
        decision = owner.evaluate(evidence(good, epoch=2), context(), intent(), now_monotonic_s=now)
        assert decision.authorized_intent is not None
    decision = owner.evaluate(evidence(False, epoch=2), context(), now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == "maximum_retarget_time_reached"


def test_unconfirmed_angles_do_not_scale_airspeed_or_absolute_course():
    owner = supervisor()
    assert owner.begin_target_transition(session_epoch=2, previous_intent=intent(course=2.))
    decision = owner.evaluate(evidence(False, epoch=2), context(), provisional_intent=intent(course=-2.),
                              now_monotonic_s=1.1)
    assert decision.authorized_intent.fields["equivalent_airspeed_m_s"] == 18.
    assert decision.authorized_intent.fields["course_rad"] == 2.


def test_confirmed_restoration_blends_course_across_wrap_without_reversing():
    owner = supervisor()
    assert owner.begin_target_transition(session_epoch=2, previous_intent=intent(course=math.radians(179)))
    next_intent = intent(course=math.radians(-179))
    for now in (1.1, 1.6, 1.85):
        decision = owner.evaluate(evidence(epoch=2), context(), next_intent, now_monotonic_s=now)
    assert abs(decision.authorized_intent.fields["course_rad"]) == pytest.approx(math.pi)
    assert decision.authorized_intent.fields["equivalent_airspeed_m_s"] == 18.
    decision = owner.evaluate(evidence(epoch=2), context(), next_intent, now_monotonic_s=2.11)
    assert decision.authority_state is ContinuityAuthorityState.ACTIVE


@pytest.mark.parametrize("updates,reason", [
    ({"operator_abort": True}, "operator_abort"),
    ({"vehicle_state_fresh": False}, "vehicle_state_stale"),
    ({"publisher_healthy": False}, "command_publisher_unhealthy"),
    ({"execution_mode": "PX4_NATIVE", "offboard_active": False}, "offboard_not_confirmed"),
])
def test_immediate_guards_precede_recovery(updates, reason):
    owner = supervisor()
    decision = owner.evaluate(evidence(False), context(**updates), now_monotonic_s=1.)
    assert decision.handoff_request.reason_code == reason
    assert decision.authorized_intent is None


def test_does_not_restore_commands_from_a_previous_phase_generation():
    owner = supervisor()
    owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    decision = owner.evaluate(evidence(), context(guidance_identity=identity(2)), intent(generation=2), now_monotonic_s=1.1)
    assert decision.authorized_intent is None
    assert decision.handoff_request.reason_code == "guidance_context_changed"


def test_phase_rebind_never_restarts_an_existing_loss_deadline():
    owner = supervisor()
    owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    next_context = context(guidance_identity=identity(2))
    decision = owner.rebind_strategy(owner.policy, intent(generation=2), next_context, now_monotonic_s=4.)
    assert decision.authorized_intent is None
    decision = owner.evaluate(evidence(False), next_context, now_monotonic_s=8.9)
    assert decision.authorized_intent.guidance_identity == identity(2)
    decision = owner.evaluate(evidence(False), next_context, now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == "maximum_coast_time_reached"


def test_expired_recovery_cannot_be_revived_by_phase_rebind():
    owner = supervisor()
    owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    decision = owner.rebind_strategy(owner.policy, intent(generation=2), context(guidance_identity=identity(2)),
                                     now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == "maximum_coast_time_reached"


@pytest.mark.parametrize("execution_mode", ["PX4", "UNKNOWN"])
def test_fw_recovery_requires_native_execution_owner(execution_mode):
    owner = supervisor()
    decision = owner.evaluate(evidence(False), context(execution_mode=execution_mode), now_monotonic_s=1.)
    assert decision.handoff_request.reason_code == f"fixed_wing_course_recovery_coasting_unsupported_for_{execution_mode.lower()}"


def test_native_fw_loss_reacquisition_and_expiry_keep_one_original_deadline():
    owner = supervisor()
    live = context(execution_mode="PX4_NATIVE")
    for now, confirmed in [(1., False), (3., False), (3.1, True), (3.4, False), (8.8, True)]:
        decision = owner.evaluate(evidence(confirmed), live, intent() if confirmed else None,
                                  now_monotonic_s=now)
        command = FixedWingCommand.from_intent(decision.authorized_intent)
        assert command.height_rate_m_s == 0.
        assert command.equivalent_airspeed_m_s == 18.
        assert decision.handoff_request is None
        assert decision.coast_distance_m == 0.
    decision = owner.evaluate(evidence(), live, intent(), now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == "maximum_coast_time_reached"


def test_altitude_hold_is_retained_without_converting_absolute_altitude_to_a_rate():
    owner = supervisor()
    owner.evaluate(evidence(), context(), intent(rate=None, altitude=500.), now_monotonic_s=.1)
    decision = owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    assert FixedWingCommand.from_intent(decision.authorized_intent).altitude_amsl_m == 500.
