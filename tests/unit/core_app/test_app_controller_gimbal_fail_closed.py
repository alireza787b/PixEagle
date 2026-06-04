"""AppController regression tests for external gimbal fail-closed dispatch."""

import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.app_controller import AppController
from classes.command_intent import CommandIntent
from classes.follower import Follower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower, Vector3D
from classes.tracker_output import TrackerDataType, TrackerOutput


def _build_follower_stub() -> GMVelocityVectorFollower:
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.total_follow_calls = 0
    follower.successful_updates = 0
    follower.failed_updates = 0
    follower.following_active = True
    follower.last_valid_time = time.time()
    follower.current_velocity_magnitude = 4.0
    follower.last_velocity_vector = Vector3D(4.0, 0.0, 0.0)
    follower._perform_safety_checks = MagicMock(
        return_value={'safe_to_proceed': True, 'reason': 'test'}
    )
    follower.log_follower_event = MagicMock()
    fields = {
        'vel_body_fwd': 4.0,
        'vel_body_right': 1.0,
        'vel_body_down': -1.0,
        'yawspeed_deg_s': 2.0,
    }

    def set_fields(field_values, *, source, reason=None, require_all=True):
        fields.update(field_values)
        return CommandIntent(
            profile_name='gm_velocity_vector',
            control_type='velocity_body_offboard',
            fields=fields.copy(),
            source=source,
            reason=reason,
        )

    follower.setpoint_handler = SimpleNamespace(
        get_control_type=MagicMock(return_value='velocity_body_offboard'),
        get_fields=MagicMock(side_effect=lambda: fields.copy()),
        set_fields=MagicMock(side_effect=set_fields),
    )
    return follower


def _build_follower_manager_stub(concrete_follower: GMVelocityVectorFollower) -> Follower:
    manager = Follower.__new__(Follower)
    manager.follower = concrete_follower
    manager.mode = 'gm_velocity_vector'
    return manager


def _stale_gimbal_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='gimbal_tracker',
        angular=(10.0, -5.0, 0.0),
        raw_data={
            'data_is_stale': True,
            'usable_for_following': False,
            'tracking_status': 'TRACKING_ACTIVE',
        },
        metadata={'usable_for_following': False},
    )


@pytest.mark.asyncio
async def test_app_controller_dispatches_zero_command_for_unusable_gimbal_output():
    """Inactive external gimbal output must reach the follower and PX4 sender."""
    tracker_output = _stale_gimbal_output()
    follower = _build_follower_stub()
    follower_manager = _build_follower_manager_stub(follower)

    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=True)
    ctrl.tracking_started = False
    ctrl.following_active = True
    ctrl.follower = follower_manager
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(),
        send_attitude_rate_commands=AsyncMock(),
        send_velocity_body_offboard_commands=AsyncMock(),
    )
    ctrl.offboard_commander = SimpleNamespace(
        submit_intent=MagicMock(return_value=True),
    )

    result = await ctrl.follow_target()

    assert result is True
    ctrl.offboard_commander.submit_intent.assert_called_once()
    ctrl.px4_interface.send_velocity_body_offboard_commands.assert_not_awaited()
    ctrl.px4_interface.send_body_velocity_commands.assert_not_awaited()
    ctrl.px4_interface.send_attitude_rate_commands.assert_not_awaited()

    follower.setpoint_handler.set_fields.assert_called_once_with(
        {
            "vel_body_fwd": 0.0,
            "vel_body_right": 0.0,
            "vel_body_down": 0.0,
            "yawspeed_deg_s": 0.0,
        },
        source='GMVelocityVectorFollower',
        reason='gm_velocity_vector_unusable_external_input',
        require_all=True,
    )
