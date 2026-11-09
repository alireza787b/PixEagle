"""Retarget admission must preserve an unsupported active command and target."""

import asyncio
from dataclasses import replace
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from classes.aircraft_state import AircraftBinding, AirframePhase, GuidanceSessionIdentity
from classes.app_controller import AppController
from classes.command_intent import CommandIntent
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.target_continuity import (
    ContinuityContext,
    ContinuityPolicy,
    IdentityVerdict,
    TargetContinuitySupervisor,
    TargetEvidenceSnapshot,
    TargetEvidenceState,
)


def _velocity_intent():
    return CommandIntent(
        "mc_velocity_chase", "velocity_body_offboard",
        {"vel_body_fwd": 2.0, "vel_body_right": 0.5, "vel_body_down": -0.4, "yawspeed_deg_s": 7.0},
        "fixture",
    )


def _controller(intent):
    native = intent.control_type == "fixed_wing_external"
    owner = TargetContinuitySupervisor(
        ContinuityPolicy.from_mapping({"MODE": "bounded_flight" if native else "immediate_handoff"}),
        clock=lambda: 1.0,
    )
    owner.reset_session(session_epoch=7, reason="start")
    owner.evaluate(
        TargetEvidenceSnapshot(TargetEvidenceState.CONFIRMED, 0.0, 7, "old-target",
                               IdentityVerdict.CONFIRMED, "fixture"),
        ContinuityContext("PX4_NATIVE" if native else "PX4",
                          AirframePhase.FIXED_WING if native else AirframePhase.MULTICOPTER,
                          intent.control_type, True, True, True, vehicle_yaw_deg=12.0,
                          guidance_identity=intent.guidance_identity),
        intent, now_monotonic_s=0.0,
    )
    controller = object.__new__(AppController)
    controller._follower_state_lock = asyncio.Lock()
    controller._tracker_model_state_lock = threading.RLock()
    controller._tracking_session_generation = 7
    controller.following_active = True
    controller.following_execution_mode = "PX4"
    controller.smart_mode_active = False
    controller.tracking_started = True
    controller.selected_bbox = (10, 10, 20, 20)
    controller.current_frame = np.zeros((80, 160, 3), dtype=np.uint8)
    controller.tracker = SimpleNamespace(
        is_external_tracker=False, bbox=controller.selected_bbox,
        reset=Mock(), start_tracking=Mock(), stop_tracking=Mock(),
    )
    controller.follower = SimpleNamespace(
        prepare_for_target_transition=Mock(return_value=True),
        get_last_command_intent=lambda: intent,
    )
    controller.offboard_commander = SimpleNamespace(
        submit_intent=Mock(return_value=True),
        get_status=lambda: {"failsafe_defaults_active": False},
    )
    controller.target_continuity = owner
    controller._activate_offboard_commander_failsafe_defaults = Mock()
    return controller


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["mc_attitude_rate", "fw_attitude_rate"])
async def test_rate_retarget_requires_stop_before_follower_or_old_target_changes(profile):
    prior = CommandIntent(
        profile, "attitude_rate",
        {"rollspeed_deg_s": 1.0, "pitchspeed_deg_s": -2.0, "yawspeed_deg_s": 3.0, "thrust": 0.6},
        "fixture",
    )
    controller = _controller(prior)
    status = controller.target_continuity.get_status()

    result = await controller.start_tracking({"x": 50, "y": 30, "width": 30, "height": 20})

    assert not result["started"]
    assert result["reason"] == "retarget_requires_stop"
    assert "Stop following" in result["target_transition"]["message"]
    controller.follower.prepare_for_target_transition.assert_not_called()
    controller.offboard_commander.submit_intent.assert_not_called()
    controller._activate_offboard_commander_failsafe_defaults.assert_not_called()
    controller.tracker.reset.assert_not_called()
    controller.tracker.start_tracking.assert_not_called()
    assert controller.tracker.bbox == controller.selected_bbox == (10, 10, 20, 20)
    assert controller.tracking_started and controller.following_active
    assert controller._tracking_session_generation == 7
    assert controller._get_current_command_intent() is prior
    assert controller.target_continuity.last_authorized_intent() is prior
    assert controller.target_continuity.get_status() == status
    assert not controller.target_continuity.begin_target_transition(session_epoch=8, previous_intent=prior)
    assert controller.target_continuity.get_status() == status


@pytest.mark.parametrize("fields", [
    {"vel_body_fwd": 1.0, "vel_body_right": 0.0, "yawspeed_deg_s": 0.0},
    {**_velocity_intent().fields, "thrust": 0.6},
    {**_velocity_intent().fields, "vel_body_fwd": float("nan")},
    {**_velocity_intent().fields, "vel_body_fwd": float("inf")},
    {**_velocity_intent().fields, "vel_body_fwd": "2.0"},
    {**_velocity_intent().fields, "vel_body_fwd": True},
    {**_velocity_intent().fields, "vel_body_fwd": None},
])
def test_invalid_velocity_snapshot_is_rejected_before_retarget_reset(fields):
    controller = _controller(replace(_velocity_intent(), fields=fields))

    result = controller._prepare_following_target_transition("operator_target_retarget")

    assert not result["prepared"] and result["reason"] == "retarget_requires_stop"
    controller.follower.prepare_for_target_transition.assert_not_called()
    controller.offboard_commander.submit_intent.assert_not_called()
    assert controller._tracking_session_generation == 7


def test_velocity_retarget_preserves_horizontal_motion_and_native_identity():
    identity = GuidanceSessionIdentity("follow", AircraftBinding("aircraft", "connection", 1), 2)
    prior = replace(_velocity_intent(), guidance_identity=identity)
    controller = _controller(prior)

    result = controller._prepare_following_target_transition("operator_target_retarget")

    assert result["prepared"] and result["bounded_transition_applied"]
    carryover = controller.offboard_commander.submit_intent.call_args.args[0]
    assert carryover.fields == {**prior.fields, "vel_body_down": 0.0, "yawspeed_deg_s": 0.0}
    assert carryover.guidance_identity == identity
    assert controller.target_continuity.supports_target_transition_intent(carryover)
    assert controller.target_continuity.begin_target_transition(session_epoch=8, previous_intent=prior)


@pytest.mark.parametrize("altitude", [None, 500.0])
def test_native_fw_retarget_keeps_native_fields_identity_and_level_recovery(altitude):
    identity = GuidanceSessionIdentity("follow", AircraftBinding("aircraft", "connection", 1), 2)
    prior = FixedWingCommand(0.7, 18.0, -2.0 if altitude is None else None, altitude).intent(
        identity, profile_name="gm_velocity_vector", source="fixture",
    )
    controller = _controller(prior)

    result = controller._prepare_following_target_transition("operator_target_retarget")

    assert result["prepared"] and result["bounded_transition_applied"]
    carryover = controller.offboard_commander.submit_intent.call_args.args[0]
    command = FixedWingCommand.from_intent(carryover)
    assert command.course_rad == 0.7 and command.equivalent_airspeed_m_s == 18.0
    assert command.altitude_amsl_m == altitude
    assert command.height_rate_m_s == (0.0 if altitude is None else None)
    assert carryover.guidance_identity == identity
    assert set(carryover.fields) == set(prior.fields)
    assert controller.target_continuity.begin_target_transition(session_epoch=8, previous_intent=prior)
