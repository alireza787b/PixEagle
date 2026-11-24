"""Visual Centering retains its zero-forward contract after continuity rotation."""

from dataclasses import replace
import math

import pytest

from classes.offboard_commander import OffboardCommander
from classes.target_continuity import (
    AirframePhase,
    ContinuityContext,
    ContinuityPolicy,
    IdentityVerdict,
    TargetContinuitySupervisor,
    TargetEvidenceSnapshot,
    TargetEvidenceState,
)
from tests.unit.followers.test_mc_factory_behavior import factory as factory


def _evidence(state, epoch):
    return TargetEvidenceSnapshot(
        state, 0.0, epoch, "target", IdentityVerdict.CONFIRMED
        if state is TargetEvidenceState.CONFIRMED else IdentityVerdict.UNCONFIRMED, "fixture",
    )


@pytest.mark.parametrize("retarget", [False, True])
@pytest.mark.parametrize("yaw", [-90.0, -45.0, 45.0, 90.0])
def test_heading_rotation_cannot_submit_forward_motion_during_centering_recovery(factory, retarget, yaw):
    follower = factory("mc_velocity_distance")
    assert follower.set_command_fields(
        dict(vel_body_fwd=0.0, vel_body_right=0.4, vel_body_down=0.0, yawspeed_deg_s=0.0),
        reason="confirmed_lateral_centering",
    )
    prior = follower.get_last_command_intent()
    now = [0.0]
    owner = TargetContinuitySupervisor(ContinuityPolicy.from_mapping({
        "MODE": "immediate_handoff" if retarget else "bounded_decay", "MAX_COAST_TIME_S": 8.0,
        "MAX_COAST_DISTANCE_M": 4.0, "MAX_RETARGET_TIME_S": 8.0,
    }), clock=lambda: now[0])
    owner.reset_session(session_epoch=1, reason="start")
    context = ContinuityContext("PX4", AirframePhase.MULTICOPTER, "velocity_body_offboard",
                                True, True, True, vehicle_yaw_deg=0.0)
    owner.evaluate(_evidence(TargetEvidenceState.CONFIRMED, 1), context, prior, now_monotonic_s=0.0)
    now[0] = 0.1
    epoch = 2 if retarget else 1
    if retarget:
        assert owner.begin_target_transition(session_epoch=epoch, previous_intent=prior)
    else:
        owner.evaluate(_evidence(TargetEvidenceState.ABSENT, epoch), context, now_monotonic_s=now[0])
    rotated = replace(context, vehicle_yaw_deg=yaw)
    decision = owner.evaluate(_evidence(TargetEvidenceState.ABSENT, epoch), rotated, now_monotonic_s=0.2)
    original_fields = dict(decision.authorized_intent.fields)
    assert abs(original_fields["vel_body_fwd"]) > 0.1

    fields = follower.prepare_authorized_command(original_fields, loss_decay=not retarget)
    submitted = replace(decision.authorized_intent, fields=fields)
    commander = OffboardCommander(follower.px4_controller, follower.setpoint_handler)
    assert commander.submit_intent(submitted)
    owner.record_authorized_intent(submitted)

    accepted = follower.setpoint_handler.get_fields()
    assert accepted["vel_body_fwd"] == 0.0
    assert abs(original_fields["vel_body_fwd"]) > 0.1
    assert accepted["vel_body_right"] == pytest.approx(original_fields["vel_body_right"])
    assert accepted["vel_body_down"] == original_fields["vel_body_down"] == 0.0
    assert accepted["yawspeed_deg_s"] == original_fields["yawspeed_deg_s"] == 0.0
    assert math.hypot(accepted["vel_body_fwd"], accepted["vel_body_right"]) <= math.hypot(
        original_fields["vel_body_fwd"], original_fields["vel_body_right"],
    )
    assert owner.last_authorized_intent().fields == accepted

    following = owner.evaluate(_evidence(TargetEvidenceState.ABSENT, epoch), rotated, now_monotonic_s=0.3)
    assert following.coast_distance_m == pytest.approx(
        decision.coast_distance_m + abs(accepted["vel_body_right"]) * 0.1,
    )
    assert following.episode_id == decision.episode_id
    expired = owner.evaluate(_evidence(TargetEvidenceState.ABSENT, epoch), rotated, now_monotonic_s=8.101)
    assert expired.authorized_intent is None
    assert expired.reason_code == ("maximum_retarget_time_reached" if retarget else "maximum_coast_time_reached")
