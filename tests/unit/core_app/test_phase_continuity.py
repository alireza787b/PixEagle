"""Startup uses the existing continuity owner; phase changes never rebind it."""

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


def mc_intent(speed=0.):
    return CommandIntent("gm_velocity_vector", "velocity_body_offboard",
                         dict(vel_body_fwd=speed, vel_body_right=0., vel_body_down=0., yawspeed_deg_s=0.),
                         "fixture", guidance_identity=identity())


def mc_context(paused=False):
    return ContinuityContext("COMMAND_PREVIEW", AirframePhase.MULTICOPTER, "velocity_body_offboard",
                             True, True, True, vehicle_yaw_deg=0., guidance_identity=identity(),
                             pursuit_paused=paused)


@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_initial_strategy_binds_once_with_original_identity_and_startup_baseline(phase):
    policy = mc_policy() if phase is AirframePhase.MULTICOPTER else supervisor().policy
    baseline = mc_intent() if phase is AirframePhase.MULTICOPTER else intent(rate=0.)
    paused = mc_context(True) if phase is AirframePhase.MULTICOPTER else context(pursuit_paused=True)
    owner = TargetContinuitySupervisor(mc_policy())
    owner.reset_session(session_epoch=1, reason="start")
    result = owner.bind_initial_strategy(policy, baseline, paused, now_monotonic_s=1.)
    assert result.authorized_intent is None
    assert owner.policy is policy
    with pytest.raises(ValueError, match="initial_strategy_already_bound"):
        owner.bind_initial_strategy(policy, baseline, paused, now_monotonic_s=1.)
    result = owner.evaluate(evidence(), paused, baseline, now_monotonic_s=1.1)
    assert result.authorized_intent is baseline
    assert result.authorized_intent.guidance_identity == identity()
    assert result.authority_fraction == 0.
    result = owner.evaluate(evidence(), replace(paused, pursuit_paused=False), baseline, now_monotonic_s=1.5)
    assert result.authority_fraction == 1.


def test_startup_loss_and_repeated_retargets_keep_the_original_budget():
    owner = TargetContinuitySupervisor(supervisor().policy, clock=lambda: 2.)
    owner.reset_session(session_epoch=1, reason="start")
    paused, baseline = context(pursuit_paused=True), intent(rate=0.)
    owner.bind_initial_strategy(owner.policy, baseline, paused, now_monotonic_s=1.)
    owner.evaluate(evidence(False), paused, baseline, now_monotonic_s=2.)
    assert owner.begin_target_transition(session_epoch=2, previous_intent=baseline)
    assert owner.begin_target_transition(session_epoch=3, previous_intent=baseline)
    decision = owner.evaluate(evidence(False, epoch=3), paused, baseline, now_monotonic_s=9.9)
    assert decision.loss_elapsed_s == pytest.approx(7.9)
    assert not owner.get_status()['distance_budget_applies']
    decision = owner.evaluate(evidence(False, epoch=3), paused, baseline, now_monotonic_s=10.)
    assert decision.handoff_request.reason_code == 'maximum_retarget_time_reached'


@pytest.mark.parametrize("updates,reason", [
    ({"vehicle_state_fresh": False}, "vehicle_state_stale"),
    ({"publisher_healthy": False}, "command_publisher_unhealthy"),
    ({"operator_abort": True}, "operator_abort"),
    ({"execution_mode": "PX4_NATIVE", "offboard_active": False}, "offboard_not_confirmed"),
])
def test_startup_pause_cannot_bypass_immediate_guards(updates, reason):
    owner = TargetContinuitySupervisor(supervisor().policy)
    owner.reset_session(session_epoch=1, reason="start")
    paused, baseline = context(pursuit_paused=True), intent(rate=0.)
    owner.bind_initial_strategy(owner.policy, baseline, paused, now_monotonic_s=1.)
    decision = owner.evaluate(evidence(), replace(paused, **updates), baseline, now_monotonic_s=2.)
    assert decision.authorized_intent is None
    assert decision.handoff_request.reason_code == reason


def test_startup_contract_cannot_authorize_mc_motion_or_fw_descent():
    for baseline, paused in ((mc_intent(speed=2.), mc_context(True)),
                             (intent(), context(pursuit_paused=True))):
        owner = TargetContinuitySupervisor(mc_policy() if paused.airframe_phase is AirframePhase.MULTICOPTER
                                           else supervisor().policy)
        owner.reset_session(session_epoch=1, reason="start")
        decision = owner.evaluate(evidence(), paused, baseline, now_monotonic_s=1.)
        assert decision.authorized_intent is None
        assert decision.handoff_request.reason_code == 'phase_baseline_invalid'


def test_transition_is_not_a_pursuit_or_retarget_contract():
    baseline = CommandIntent("gm_velocity_vector", "vtol_transition_external",
        dict(course_rad=.4, equivalent_airspeed_m_s=18.), "fixture", guidance_identity=identity())
    owner = TargetContinuitySupervisor(supervisor().policy)
    owner.reset_session(session_epoch=1, reason="start")
    assert not owner.begin_target_transition(session_epoch=2, previous_intent=baseline)
    with pytest.raises(ValueError, match="phase_contract_not_qualified"):
        owner.bind_initial_strategy(owner.policy, baseline, context(), now_monotonic_s=1.)
