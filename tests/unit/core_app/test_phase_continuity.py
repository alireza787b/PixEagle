"""One loss episode survives both phase directions; no synthetic PX4 claims."""

from dataclasses import replace

import pytest

from classes.aircraft_state import AirframePhase
from classes.command_intent import CommandIntent
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.core_app.test_fixed_wing_continuity import context, evidence, identity, intent, supervisor


def mc_policy():
    return ContinuityPolicy.from_mapping(dict(MODE="bounded_decay", MAX_COAST_TIME_S=8.,
                                             MAX_COAST_DISTANCE_M=4., MAX_RETARGET_TIME_S=8.,
                                             REACQUIRE_CONFIRMATION_S=.5, AUTHORITY_RESTORE_TIME_S=.5))


def mc_intent(generation=1, speed=0.):
    return CommandIntent("gm_velocity_vector", "velocity_body_offboard",
                         dict(vel_body_fwd=speed, vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.),
                         "fixture", guidance_identity=identity(generation))


def mc_context(generation=1, paused=False):
    return ContinuityContext("COMMAND_PREVIEW", AirframePhase.MULTICOPTER, "velocity_body_offboard",
                             True, True, True, vehicle_yaw_deg=0., guidance_identity=identity(generation),
                             pursuit_paused=paused)


def transition(generation):
    baseline = CommandIntent("gm_velocity_vector", "vtol_transition_external",
                             dict(course_rad=.4, equivalent_airspeed_m_s=18.), "fixture",
                             guidance_identity=identity(generation))
    paused = replace(context(guidance_identity=identity(generation)),
                      control_type=baseline.control_type, airframe_phase=AirframePhase.VTOL_TRANSITION,
                      pursuit_paused=True)
    return baseline, paused


def test_target_loss_deadline_keeps_running_during_transition_and_confirmation():
    owner = supervisor()
    owner.evaluate(evidence(False), context(), now_monotonic_s=1.)
    policy = owner.policy
    baseline, paused = transition(2)
    owner.rebind_strategy(policy, baseline, paused, now_monotonic_s=4.)
    for now in (4., 6., 8.):
        decision = owner.evaluate(evidence(False), paused, baseline, now_monotonic_s=now)
        assert decision.authorized_intent is baseline
        assert decision.authority_fraction == 0.
        assert decision.loss_elapsed_s == now - 1.
        assert not owner.get_status()['distance_budget_applies']
    fw = context(guidance_identity=identity(3), pursuit_paused=True)
    owner.rebind_strategy(policy, intent(generation=3, rate=0.), fw, now_monotonic_s=8.5)
    # Fresh target during phase confirmation cannot clear an existing loss budget.
    owner.evaluate(evidence(), fw, intent(generation=3, rate=0.), now_monotonic_s=8.9)
    decision = owner.evaluate(evidence(), fw, intent(generation=3, rate=0.), now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == 'maximum_coast_time_reached'


def test_mc_travel_is_retained_but_not_accumulated_in_fw_or_transition():
    owner = TargetContinuitySupervisor(mc_policy())
    owner.reset_session(session_epoch=1, reason="start")
    owner.evaluate(evidence(), mc_context(), mc_intent(speed=2.), now_monotonic_s=0.)
    owner.evaluate(evidence(False), mc_context(), now_monotonic_s=1.)
    owner.evaluate(evidence(False), mc_context(), now_monotonic_s=1.5)
    distance = owner.get_status()['coast_distance_m']
    assert distance == pytest.approx(1.)
    baseline, paused = transition(2)
    owner.rebind_strategy(mc_policy(), baseline, paused, now_monotonic_s=1.5)
    owner.evaluate(evidence(False), paused, baseline, now_monotonic_s=3.)
    fw_policy = supervisor().policy
    fw = context(guidance_identity=identity(3))
    owner.rebind_strategy(fw_policy, intent(generation=3), fw, now_monotonic_s=4.)
    owner.evaluate(evidence(False), fw, now_monotonic_s=7.)
    assert owner.get_status()['coast_distance_m'] == distance
    mc = mc_context(4, paused=True)
    owner.rebind_strategy(mc_policy(), mc_intent(4), mc, now_monotonic_s=7.5)
    decision = owner.evaluate(evidence(False), mc, mc_intent(4), now_monotonic_s=8.)
    assert decision.authorized_intent.guidance_identity == identity(4)
    assert decision.coast_distance_m == distance
    decision = owner.evaluate(evidence(False), mc, mc_intent(4), now_monotonic_s=9.)
    assert decision.handoff_request.reason_code == 'maximum_coast_time_reached'


def test_loss_begins_during_transition_and_repeated_retargets_cannot_renew_it():
    owner = supervisor()
    baseline, paused = transition(2)
    owner.rebind_strategy(owner.policy, baseline, paused, now_monotonic_s=1.)
    owner.evaluate(evidence(False), paused, baseline, now_monotonic_s=2.)
    assert owner.begin_target_transition(session_epoch=2, previous_intent=baseline)
    assert owner.begin_target_transition(session_epoch=3, previous_intent=baseline)
    decision = owner.evaluate(evidence(False, epoch=3), paused, baseline, now_monotonic_s=9.9)
    assert decision.loss_elapsed_s == pytest.approx(7.9)
    decision = owner.evaluate(evidence(False, epoch=3), paused, baseline, now_monotonic_s=10.)
    assert decision.handoff_request.reason_code == 'maximum_retarget_time_reached'


@pytest.mark.parametrize("updates,reason", [
    ({"vehicle_state_fresh": False}, "vehicle_state_stale"),
    ({"publisher_healthy": False}, "command_publisher_unhealthy"),
    ({"operator_abort": True}, "operator_abort"),
    ({"execution_mode": "PX4_NATIVE", "offboard_active": False}, "offboard_not_confirmed"),
])
def test_phase_pause_cannot_bypass_immediate_guards(updates, reason):
    owner = supervisor()
    baseline, paused = transition(2)
    owner.rebind_strategy(owner.policy, baseline, paused, now_monotonic_s=1.)
    decision = owner.evaluate(evidence(), replace(paused, **updates), baseline, now_monotonic_s=2.)
    assert decision.authorized_intent is None
    assert decision.handoff_request.reason_code == reason


def test_paused_contract_cannot_authorize_mc_motion_or_fw_descent():
    for baseline, paused in ((mc_intent(speed=2.), mc_context(paused=True)),
                             (intent(), context(pursuit_paused=True))):
        owner = TargetContinuitySupervisor(mc_policy() if paused.airframe_phase is AirframePhase.MULTICOPTER
                                           else supervisor().policy)
        owner.reset_session(session_epoch=1, reason="start")
        decision = owner.evaluate(evidence(), paused, baseline, now_monotonic_s=1.)
        assert decision.authorized_intent is None
        assert decision.handoff_request.reason_code == 'phase_baseline_invalid'
