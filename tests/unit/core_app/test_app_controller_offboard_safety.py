"""AppController Offboard safety regression tests."""

import asyncio
import json
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, Response
import numpy as np
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.app_controller import AppController
from classes.command_intent import CommandIntent
from classes.offboard_commander import OffboardCommander
from classes.fastapi_handler import (
    APIActionRequest,
    APITrackingCatalogResponse,
    APITrackingSmartClickRequest,
    APITrackingStartRequest,
    APITrackerSwitchRequest,
    FastAPIHandler,
)
from classes.parameters import Parameters
from classes.follower import Follower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower, Vector3D
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
from classes.tracker_output import TrackerDataType, TrackerOutput


def _active_gimbal_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='gimbal_tracker',
        angular=(0.0, 0.0, 0.0),
        raw_data={'usable_for_following': True},
    )


def _inactive_gimbal_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='gimbal_tracker',
        angular=(0.0, 0.0, 0.0),
        raw_data={'usable_for_following': True},
    )


def _stale_gimbal_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='gimbal_tracker',
        angular=(0.0, 0.0, 0.0),
        raw_data={'usable_for_following': False, 'data_is_stale': True},
    )


def _inactive_position_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='vision_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.2,
    )


def _active_position_output(**raw_overrides) -> TrackerOutput:
    raw_data = {'usable_for_following': True, 'measurement_source': 'measurement'}
    raw_data.update(raw_overrides)
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='vision_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.8,
        raw_data=raw_data,
        metadata={'usable_for_following': raw_data.get('usable_for_following', True)},
    )


def _active_position_output_without_usability_metadata() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='custom_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.8,
        raw_data={'measurement_source': 'measurement'},
        metadata={},
    )


def _stale_multi_target_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.MULTI_TARGET,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='smart_tracker',
        position_2d=(0.2, -0.1),
        targets=[
            {
                'target_id': 7,
                'bbox': (100, 100, 50, 50),
                'center': (125, 125),
                'confidence': 0.8,
                'is_selected': True,
            }
        ],
        confidence=0.8,
        raw_data={
            'usable_for_following': False,
            'data_is_stale': True,
            'prediction_only': True,
            'freshness_reason': 'prediction_only',
        },
        metadata={'usable_for_following': False},
    )


def _visible_multi_target_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.MULTI_TARGET,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='smart_tracker',
        targets=[
            {
                'target_id': 7,
                'bbox': (100, 100, 50, 50),
                'center': (125, 125),
                'confidence': 0.8,
                'is_selected': False,
            }
        ],
        confidence=0.8,
        raw_data={
            'usable_for_following': False,
            'data_is_stale': False,
        },
        metadata={'usable_for_following': False},
    )


def _follower_manager_stub(control_type='velocity_body_offboard'):
    follower = MagicMock()
    follower.validate_tracker_compatibility.return_value = True
    follower.should_process_inactive_tracker_output.return_value = False
    follower.follow_target.return_value = True
    follower.get_control_type.return_value = control_type
    follower.get_last_command_intent.return_value = _command_intent(control_type=control_type)
    follower.get_display_name.return_value = 'GM Velocity Vector'
    follower.get_available_fields.return_value = [
        'vel_body_fwd',
        'vel_body_right',
        'vel_body_down',
        'yawspeed_deg_s',
    ]
    follower.validate_current_mode.return_value = True
    return follower


def _command_intent(control_type='velocity_body_offboard', fields=None):
    if fields is None:
        if control_type == 'attitude_rate':
            fields = {
                'rollspeed_deg_s': 0.0,
                'pitchspeed_deg_s': 0.0,
                'yawspeed_deg_s': 0.0,
                'thrust': 0.5,
            }
        else:
            fields = {
                'vel_body_fwd': 0.0,
                'vel_body_right': 0.0,
                'vel_body_down': 0.0,
                'yawspeed_deg_s': 0.0,
            }

    return CommandIntent(
        profile_name='unit_test',
        control_type=control_type,
        fields=fields,
        source='unit_test',
        reason='unit_test',
    )


def _commander_stub(accepted=True):
    return SimpleNamespace(
        submit_intent=MagicMock(return_value=accepted),
        get_status=MagicMock(return_value={
            'exists': True,
            'running': True,
            'health_state': 'running',
            'sends_mavsdk_commands': True,
            'command_publication_source': 'offboard_commander',
        }),
    )


def _assert_no_frame_loop_px4_send(ctrl):
    ctrl.px4_interface.send_body_velocity_commands.assert_not_awaited()
    ctrl.px4_interface.send_attitude_rate_commands.assert_not_awaited()
    ctrl.px4_interface.send_velocity_body_offboard_commands.assert_not_awaited()


def _manager_for_concrete_follower(concrete_follower):
    manager = Follower.__new__(Follower)
    manager.follower = concrete_follower
    manager.mode = 'test'
    return manager


def _external_non_video_tracker():
    """External tracker fixture with an explicit non-video contract."""
    return SimpleNamespace(
        is_external_tracker=True,
        get_capabilities=MagicMock(return_value={'requires_video': False}),
    )


def _set_following_inactive(ctrl):
    async def _disconnect():
        ctrl.following_active = False
        return {"steps": ["Offboard mode stopped"], "errors": []}

    return _disconnect


def _minimal_update_loop_controller(frame):
    ctrl = object.__new__(AppController)
    ctrl.last_system_status_time = time.time()
    ctrl.system_status_interval = 9999.0
    ctrl.preprocessor = None
    ctrl.segmentation_active = False
    ctrl.segmentor = None
    ctrl.smart_tracker = None
    ctrl.smart_mode_active = False
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.tracking_failure_start_time = None
    ctrl.frame_counter = 0
    ctrl.detector = SimpleNamespace(update_template=MagicMock())
    ctrl.telemetry_handler = SimpleNamespace(
        should_send_telemetry=MagicMock(return_value=False),
        send_telemetry=MagicMock(),
    )
    ctrl.video_handler = SimpleNamespace(
        current_raw_frame=frame,
        current_resized_raw_frame=None,
        current_osd_frame=None,
        current_resized_osd_frame=None,
        update_resized_frames=MagicMock(),
        resize_frame=MagicMock(return_value=frame),
    )
    ctrl.osd_pipeline = SimpleNamespace(compose=MagicMock(return_value=frame))
    ctrl.frame_publisher = SimpleNamespace(publish=MagicMock())
    ctrl.recording_manager = None
    ctrl._pipeline_metrics = {}
    ctrl.px4_interface = SimpleNamespace(
        failsafe_active=False,
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()
    ctrl._is_always_reporting_tracker = MagicMock(return_value=False)
    ctrl.is_smart_override_active = MagicMock(return_value=False)
    ctrl.follower = _follower_manager_stub(control_type='attitude_rate')
    ctrl.follower.validate_tracker_compatibility.side_effect = lambda output: output.tracking_active
    ctrl.follower.should_process_inactive_tracker_output.side_effect = lambda output: not output.tracking_active
    return ctrl


@pytest.mark.asyncio
async def test_update_loop_first_classic_tracker_failure_dispatches_unusable_output():
    """First failed classic tracker update must not leave the last PX4 command alive."""
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    ctrl = _minimal_update_loop_controller(frame)
    ctrl.tracker = SimpleNamespace(
        is_external_tracker=False,
        update=MagicMock(return_value=(False, None)),
        get_output=MagicMock(return_value=_active_position_output()),
        position_estimator=None,
    )

    with patch('classes.app_controller.Parameters.ENABLE_PREPROCESSING', False), \
            patch('classes.app_controller.Parameters.ENABLE_DEBUGGING', False), \
            patch('classes.app_controller.Parameters.STREAM_PROCESSED_OSD', False), \
            patch('classes.app_controller.Parameters.ENABLE_GSTREAMER_STREAM', False):
        await ctrl.update_loop(frame)

    ctrl.tracker.update.assert_called_once_with(frame)
    assert ctrl.tracking_failure_start_time is not None
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['usable_for_following'] is False
    assert passed_output.raw_data['freshness_reason'] == 'classic_tracker_update_failed'
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_update_loop_dispatches_failed_always_reporting_tracker_output():
    """Failed always-reporting updates with inactive output must still publish safe commands."""
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    ctrl = _minimal_update_loop_controller(frame)
    tracker_output = _stale_gimbal_output()
    ctrl.tracking_started = False
    ctrl._is_always_reporting_tracker.return_value = True
    ctrl.tracker = SimpleNamespace(
        is_external_tracker=True,
        get_capabilities=MagicMock(return_value={'requires_video': False}),
        update=MagicMock(return_value=(False, tracker_output)),
        draw_tracking=MagicMock(return_value=frame),
    )

    with patch('classes.app_controller.Parameters.ENABLE_PREPROCESSING', False), \
            patch('classes.app_controller.Parameters.STREAM_PROCESSED_OSD', False), \
            patch('classes.app_controller.Parameters.ENABLE_GSTREAMER_STREAM', False):
        await ctrl.update_loop(frame)

    ctrl.tracker.update.assert_called_once_with(frame)
    assert ctrl.tracker.draw_tracking.call_args.kwargs['tracking_successful'] is False
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['command_freshness_blocked'] is True
    assert passed_output.raw_data['freshness_reason'] == 'tracker_unusable_for_following'
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_follow_target_returns_false_when_commander_rejects_intent():
    """A rejected command intent must not look like a successful follow cycle."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = _external_non_video_tracker()
    ctrl.tracking_started = False
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub()
    ctrl.get_tracker_output = MagicMock(return_value=_active_gimbal_output())
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub(accepted=False)

    result = await ctrl.follow_target()

    assert result is False
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_follow_target_dispatches_when_follower_accepts_inactive_output():
    """Inactive target-loss output must still publish when the follower opts in."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = _external_non_video_tracker()
    ctrl.tracking_started = False
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub()
    ctrl.follower.validate_tracker_compatibility.return_value = False
    ctrl.follower.should_process_inactive_tracker_output.return_value = True
    tracker_output = _inactive_gimbal_output()
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    ctrl.follower.follow_target.assert_called_once_with(tracker_output)
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_follow_target_rejects_inactive_output_without_explicit_opt_in():
    """Inactive output must not bypass opt-in through a permissive validator."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=False)
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub(control_type='attitude_rate')
    ctrl.follower.validate_tracker_compatibility.return_value = True
    ctrl.follower.should_process_inactive_tracker_output.return_value = False
    tracker_output = _inactive_position_output()
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)
    ctrl.video_handler = SimpleNamespace(
        get_frame_status=MagicMock(return_value={
            'source': 'fresh',
            'status': 'fresh',
            'usable_for_following': True,
            'reason': 'capture_success',
        })
    )
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is False
    ctrl.follower.follow_target.assert_not_called()
    _assert_no_frame_loop_px4_send(ctrl)


def test_external_tracker_without_capabilities_requires_video_by_default():
    """Only explicit non-video external trackers may bypass video freshness."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=True)

    assert ctrl._tracker_requires_video_for_following() is True


@pytest.mark.asyncio
async def test_follow_target_routes_real_manager_inactive_gimbal_stop_to_offboard_send():
    """Real Follower manager forwarding must preserve inactive-output zero dispatch."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = _external_non_video_tracker()
    ctrl.tracking_started = False
    ctrl.following_active = True
    tracker_output = _stale_gimbal_output()
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)

    concrete = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    concrete.total_follow_calls = 0
    concrete.successful_updates = 0
    concrete.current_velocity_magnitude = 4.0
    concrete.last_velocity_vector = Vector3D(4.0, 0.0, 0.0)
    concrete.following_active = True
    concrete._perform_safety_checks = MagicMock(
        return_value={'safe_to_proceed': True, 'reason': 'test'}
    )
    concrete.set_command_fields = MagicMock(return_value=True)
    concrete.log_follower_event = MagicMock()
    concrete.get_control_type = MagicMock(return_value='velocity_body_offboard')
    concrete.get_last_command_intent = MagicMock(
        return_value=_command_intent(control_type='velocity_body_offboard')
    )
    ctrl.follower = _manager_for_concrete_follower(concrete)
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)
    commands = concrete.set_command_fields.call_args.args[0]
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0


@pytest.mark.asyncio
async def test_follow_target_routes_real_manager_inactive_position_hover_to_attitude_send():
    """Inactive attitude-rate follower output must dispatch through manager forwarding."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=True)
    ctrl.tracking_started = False
    ctrl.following_active = True
    tracker_output = _inactive_position_output()
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)

    concrete = MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)
    concrete.emergency_stop_active = False
    concrete.target_lost = False
    concrete.target_loss_start_time = None
    concrete.target_loss_events = 0
    concrete.hover_thrust = 0.5
    concrete.validate_tracker_compatibility = MagicMock(return_value=False)
    concrete._check_altitude_safety = MagicMock(return_value=True)
    concrete.set_command_fields = MagicMock(return_value=True)
    concrete.update_telemetry_metadata = MagicMock()
    concrete.get_control_type = MagicMock(return_value='attitude_rate')
    concrete.get_last_command_intent = MagicMock(
        return_value=_command_intent(control_type='attitude_rate')
    )
    ctrl.follower = _manager_for_concrete_follower(concrete)
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)
    commands = concrete.set_command_fields.call_args.args[0]
    assert commands["rollspeed_deg_s"] == 0.0
    assert commands["pitchspeed_deg_s"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert commands["thrust"] == 0.5


@pytest.mark.asyncio
async def test_follow_target_converts_cached_video_frame_to_inactive_fail_closed_output():
    """Cached video frames must not be treated as active command-fresh targets."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=False)
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.video_handler = SimpleNamespace(
        get_frame_status=MagicMock(return_value={
            'source': 'cached',
            'status': 'cached',
            'usable_for_following': False,
            'reason': 'using_cached_frame',
        })
    )
    tracker_output = _active_position_output()
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)
    ctrl.follower = _follower_manager_stub(control_type='attitude_rate')
    ctrl.follower.validate_tracker_compatibility.side_effect = lambda output: output.tracking_active
    ctrl.follower.should_process_inactive_tracker_output.side_effect = lambda output: not output.tracking_active
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['usable_for_following'] is False
    assert passed_output.raw_data['command_freshness_blocked'] is True
    assert passed_output.raw_data['freshness_reason'] == 'video_frame_cached'
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_follow_target_converts_prediction_only_output_to_fail_closed_output():
    """Estimator-only tracker output should be visible but unusable for commands."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=False)
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.video_handler = SimpleNamespace(
        get_frame_status=MagicMock(return_value={
            'source': 'fresh',
            'status': 'fresh',
            'usable_for_following': True,
            'reason': 'capture_success',
        })
    )
    tracker_output = _active_position_output(
        usable_for_following=False,
        data_is_stale=True,
        prediction_only=True,
        freshness_reason='prediction_only',
    )
    ctrl.get_tracker_output = MagicMock(return_value=tracker_output)
    ctrl.follower = _follower_manager_stub(control_type='velocity_body_offboard')
    ctrl.follower.validate_tracker_compatibility.side_effect = lambda output: output.tracking_active
    ctrl.follower.should_process_inactive_tracker_output.side_effect = lambda output: not output.tracking_active
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['freshness_reason'] == 'prediction_only'
    assert passed_output.raw_data['command_freshness_blocked'] is True
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_follow_target_routes_inactive_smart_tracker_multi_target_to_safe_hold():
    """Stale SmartTracker MULTI_TARGET output must not skip safe publication."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=False)
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.video_handler = SimpleNamespace(
        get_frame_status=MagicMock(return_value={
            'source': 'fresh',
            'status': 'fresh',
            'usable_for_following': True,
            'reason': 'capture_success',
        })
    )
    ctrl.get_tracker_output = MagicMock(return_value=_stale_multi_target_output())

    concrete = MCVelocityPositionFollower.__new__(MCVelocityPositionFollower)
    concrete._last_yaw_command = 0.8
    concrete._last_vel_z_command = -0.3
    concrete._last_update_time = 0.0
    concrete.validate_tracker_compatibility = MagicMock(return_value=False)
    concrete.extract_target_coordinates = MagicMock()
    concrete.calculate_control_commands = MagicMock()
    concrete.set_command_fields = MagicMock(return_value=True)
    concrete.update_telemetry_metadata = MagicMock()
    concrete.get_control_type = MagicMock(return_value='velocity_body_offboard')
    concrete.get_last_command_intent = MagicMock(
        return_value=_command_intent(control_type='velocity_body_offboard')
    )
    ctrl.follower = _manager_for_concrete_follower(concrete)
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.follow_target()

    assert result is True
    concrete.extract_target_coordinates.assert_not_called()
    concrete.calculate_control_commands.assert_not_called()
    passed_output = concrete.validate_tracker_compatibility.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.data_type == TrackerDataType.MULTI_TARGET
    commands = concrete.set_command_fields.call_args.args[0]
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_video_frame_unavailable_dispatches_synthetic_inactive_output():
    """A hard video stall must still give the follower a fail-closed input."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(
        is_external_tracker=False,
        get_output=MagicMock(return_value=_active_position_output()),
    )
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub(control_type='attitude_rate')
    ctrl.follower.validate_tracker_compatibility.side_effect = lambda output: output.tracking_active
    ctrl.follower.should_process_inactive_tracker_output.side_effect = lambda output: not output.tracking_active
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.handle_video_frame_unavailable({
        'source': 'none',
        'status': 'unavailable',
        'usable_for_following': False,
        'reason': 'frame_read_failed_no_cache',
    })

    assert result is True
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['freshness_reason'] == 'video_frame_unavailable'
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_sitl_video_stall_injection_uses_frame_unavailable_path():
    """The validation injector must reuse the video-frame unavailable path."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(
        is_external_tracker=False,
        get_output=MagicMock(return_value=_active_position_output()),
    )
    ctrl.tracking_started = True
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub(control_type='attitude_rate')
    ctrl.follower.validate_tracker_compatibility.side_effect = lambda output: output.tracking_active
    ctrl.follower.should_process_inactive_tracker_output.side_effect = lambda output: not output.tracking_active
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = _commander_stub()

    result = await ctrl.inject_video_stall_for_validation(
        {
            'source': 'sitl_test',
            'status': 'unavailable',
            'usable_for_following': False,
            'reason': 'sitl_video_stall',
        },
        source='unit.video_stall',
    )

    assert result['status'] == 'accepted'
    assert result['accepted'] is True
    assert result['injection']['source'] == 'unit.video_stall'
    assert result['injection']['tracker_requires_video'] is True
    assert result['injection']['frame_status']['reason'] == 'sitl_video_stall'
    assert result['command_intent']['reason'] == 'unit_test'
    assert result['offboard_commander']['running'] is True
    passed_output = ctrl.follower.follow_target.call_args.args[0]
    assert passed_output.tracking_active is False
    assert passed_output.raw_data['freshness_reason'] == 'video_frame_unavailable'
    ctrl.offboard_commander.submit_intent.assert_called_once()
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_sitl_video_stall_injection_refuses_inactive_following():
    ctrl = object.__new__(AppController)
    ctrl.tracker = SimpleNamespace(is_external_tracker=False)
    ctrl.following_active = False

    result = await ctrl.inject_video_stall_for_validation(
        {'reason': 'sitl_video_stall'},
        source='unit.video_stall',
    )

    assert result['status'] == 'rejected'
    assert result['accepted'] is False
    assert result['reason'] == 'following_not_active'
    assert result['offboard_commander'] is None


@pytest.mark.asyncio
async def test_connect_px4_does_not_mark_following_active_when_offboard_start_fails(monkeypatch):
    """Offboard start errors returned by PX4InterfaceManager must fail closed."""
    monkeypatch.setattr(
        'classes.app_controller.Parameters.TARGET_POSITION_MODE',
        'initial',
        raising=False,
    )

    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = False
    ctrl.follower = None
    ctrl.setpoint_sender = None
    ctrl.tracker = SimpleNamespace(normalized_center=(0.5, 0.5))
    ctrl.telemetry_handler = SimpleNamespace(follower=None)
    ctrl.px4_interface = SimpleNamespace(
        connect=AsyncMock(),
        set_hover_throttle=AsyncMock(),
        send_initial_setpoint=AsyncMock(return_value=True),
        start_offboard_mode=AsyncMock(
            return_value={
                "steps": [],
                "errors": ["PX4 rejected Offboard mode"],
            }
        ),
        stop_offboard_mode=AsyncMock(),
    )

    with patch('classes.app_controller.Follower', return_value=_follower_manager_stub()):
        result = await ctrl.connect_px4()

    assert ctrl.following_active is False
    assert result["errors"]
    assert any("PX4 rejected Offboard mode" in error for error in result["errors"])
    ctrl.px4_interface.stop_offboard_mode.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_px4_starts_offboard_commander_instead_of_setpoint_sender(monkeypatch):
    """Successful follow activation starts the commander heartbeat owner."""
    monkeypatch.setattr(
        'classes.app_controller.Parameters.TARGET_POSITION_MODE',
        'initial',
        raising=False,
    )

    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = False
    ctrl.follower = None
    ctrl.setpoint_sender = None
    ctrl.offboard_commander = None
    ctrl.tracker = SimpleNamespace(normalized_center=(0.5, 0.5))
    ctrl.telemetry_handler = SimpleNamespace(follower=None)
    ctrl.px4_interface = SimpleNamespace(
        connect=AsyncMock(),
        set_hover_throttle=AsyncMock(),
        send_initial_setpoint=AsyncMock(return_value=True),
        start_offboard_mode=AsyncMock(return_value={"steps": [], "errors": []}),
        stop_offboard_mode=AsyncMock(),
    )
    commander = SimpleNamespace(
        start=AsyncMock(return_value=True),
        stop=AsyncMock(),
        get_status=MagicMock(return_value={"running": True}),
    )

    with patch('classes.app_controller.Follower', return_value=_follower_manager_stub()), \
            patch('classes.app_controller.OffboardCommander', return_value=commander) as commander_ctor:
        result = await ctrl.connect_px4()

    assert result["errors"] == []
    assert ctrl.following_active is True
    assert ctrl.offboard_commander is commander
    assert ctrl.setpoint_sender is None
    commander.start.assert_awaited_once()
    commander_ctor.assert_called_once()
    assert commander_ctor.call_args.kwargs["on_failure_threshold"] == ctrl._schedule_offboard_commander_failure


@pytest.mark.asyncio
async def test_follow_target_fails_closed_without_offboard_commander():
    """Frame-loop code must not fall back to direct PX4 sends if commander is absent."""
    ctrl = object.__new__(AppController)
    ctrl.tracker = _external_non_video_tracker()
    ctrl.tracking_started = False
    ctrl.following_active = True
    ctrl.follower = _follower_manager_stub()
    ctrl.get_tracker_output = MagicMock(return_value=_active_gimbal_output())
    ctrl.px4_interface = SimpleNamespace(
        send_body_velocity_commands=AsyncMock(return_value=True),
        send_attitude_rate_commands=AsyncMock(return_value=True),
        send_velocity_body_offboard_commands=AsyncMock(return_value=True),
    )
    ctrl.offboard_commander = None

    result = await ctrl.follow_target()

    assert result is False
    _assert_no_frame_loop_px4_send(ctrl)


@pytest.mark.asyncio
async def test_disconnect_stops_offboard_commander_before_offboard_stop():
    """Disconnect must stop the heartbeat owner before leaving Offboard."""
    ctrl = object.__new__(AppController)
    ctrl.following_active = True
    ctrl.follower = SimpleNamespace(get_status_report=MagicMock(return_value="status"))
    ctrl.setpoint_sender = None
    events = []

    async def stop_commander(*, publish_final):
        events.append(("commander", publish_final))

    async def stop_offboard():
        events.append(("offboard", None))

    ctrl.offboard_commander = SimpleNamespace(
        get_status=MagicMock(return_value={"running": True}),
        stop=AsyncMock(side_effect=stop_commander),
    )
    ctrl.px4_interface = SimpleNamespace(stop_offboard_mode=AsyncMock(side_effect=stop_offboard))

    result = await ctrl._disconnect_px4_internal()

    assert result["errors"] == []
    assert ctrl.offboard_commander is None
    assert ctrl.following_active is False
    assert events == [("commander", True), ("offboard", None)]


@pytest.mark.asyncio
async def test_offboard_commander_failure_handler_stops_following_without_final_publish():
    """Sustained commander publish failures must stop local follow mode fail-closed."""
    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = True
    ctrl.follower = SimpleNamespace(get_status_report=MagicMock(return_value="status"))
    ctrl.setpoint_sender = None
    events = []

    async def stop_commander(*, publish_final):
        events.append(("commander", publish_final))

    async def stop_offboard():
        events.append(("offboard", None))

    ctrl.offboard_commander = SimpleNamespace(
        get_status=MagicMock(return_value={"running": False, "health_state": "failed"}),
        stop=AsyncMock(side_effect=stop_commander),
    )
    ctrl.px4_interface = SimpleNamespace(stop_offboard_mode=AsyncMock(side_effect=stop_offboard))
    failure_status = {
        "failure_policy_triggered": True,
        "failure_policy_reason": "3 consecutive publish failures",
        "consecutive_failures": 3,
    }

    await ctrl._handle_offboard_commander_failure(failure_status)

    assert ctrl.following_active is False
    assert ctrl.offboard_commander is None
    assert ctrl.last_offboard_commander_failure["failure_policy_triggered"] is True
    assert ctrl.last_offboard_commander_failure["disconnect_result"]["errors"] == []
    assert events == [("commander", False), ("offboard", None)]


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_awaits_cleanup_without_mavsdk_send():
    """Validation-only publish failures should trip cleanup without sending to PX4."""
    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = True
    ctrl.last_offboard_commander_failure = None
    ctrl.follower = SimpleNamespace(get_status_report=MagicMock(return_value="status"))
    ctrl.setpoint_sender = None
    ctrl.px4_interface = SimpleNamespace(stop_offboard_mode=AsyncMock())
    px4_publish_interface = SimpleNamespace(
        send_commands_unified=AsyncMock(return_value=True)
    )
    commander = OffboardCommander(
        px4_publish_interface,
        setpoint_handler=object(),
        command_failure_threshold=3,
    )
    commander.running = True
    ctrl.offboard_commander = commander

    result = await ctrl.inject_commander_publish_failure_for_validation(
        source="unit.commander_failure",
        reason="sitl_commander_publish_failure",
        metadata={"scenario": "commander_publish_failure"},
    )

    px4_publish_interface.send_commands_unified.assert_not_awaited()
    ctrl.px4_interface.stop_offboard_mode.assert_awaited_once()
    assert result["accepted"] is True
    assert result["following_active"] is False
    assert result["injection"]["applied_failure_count"] == 3
    assert result["offboard_commander_before"]["running"] is True
    assert result["offboard_commander_after"]["running"] is False
    assert result["offboard_commander_after"]["health_state"] == "failed"
    assert result["offboard_commander_after"]["consecutive_failures"] == 3
    assert result["offboard_commander_after"]["failure_policy_triggered"] is True
    assert result["offboard_commander_failure"]["failure_policy_triggered"] is True
    assert result["disconnect_result"]["errors"] == []
    assert ctrl.offboard_commander is None
    assert ctrl.following_active is False


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_marks_px4_and_records_stop_error():
    """MAVSDK disconnect injection should prove the local command path failed closed."""
    ctrl = object.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = True
    ctrl.last_offboard_commander_failure = None
    ctrl.follower = SimpleNamespace(get_status_report=MagicMock(return_value="status"))
    ctrl.setpoint_sender = None

    class PX4Probe:
        def __init__(self):
            self.validation_disconnect_active = False
            self.reason = None
            self.source = None
            self.disconnect_count = 0
            self.stop_offboard_calls = 0
            self.send_commands_unified = AsyncMock(return_value=True)

        def get_connection_status(self):
            if self.validation_disconnect_active:
                return {
                    "status": "validation_disconnected",
                    "connected": False,
                    "active_mode": False,
                    "validation_disconnect_active": True,
                    "disconnect_reason": self.reason,
                    "disconnect_source": self.source,
                    "disconnect_count": self.disconnect_count,
                    "last_error": f"MAVSDK disconnected - {self.reason}",
                    "system_address": "udp://127.0.0.1:14540",
                    "uses_mavlink2rest": True,
                }
            return {
                "status": "connected",
                "connected": True,
                "active_mode": True,
                "validation_disconnect_active": False,
                "disconnect_count": self.disconnect_count,
                "last_error": None,
                "system_address": "udp://127.0.0.1:14540",
                "uses_mavlink2rest": True,
            }

        async def inject_mavsdk_disconnect_for_validation(self, *, reason, source):
            self.validation_disconnect_active = True
            self.reason = reason
            self.source = source
            self.disconnect_count += 1
            return self.get_connection_status()

        async def stop_offboard_mode(self):
            self.stop_offboard_calls += 1
            raise RuntimeError(f"MAVSDK disconnected - {self.reason}")

    px4_probe = PX4Probe()
    commander = OffboardCommander(
        px4_probe,
        setpoint_handler=object(),
        command_failure_threshold=3,
    )
    commander.running = True
    ctrl.offboard_commander = commander
    ctrl.px4_interface = px4_probe

    result = await ctrl.inject_mavsdk_disconnect_for_validation(
        source="unit.mavsdk_disconnect",
        reason="sitl_mavsdk_disconnect",
        failure_count=1,
        metadata={"scenario": "mavsdk_disconnect"},
    )

    px4_probe.send_commands_unified.assert_not_awaited()
    assert px4_probe.stop_offboard_calls == 1
    assert result["accepted"] is True
    assert result["following_active"] is False
    assert result["injection"]["failure_mode"] == "local_mavsdk_command_disconnect"
    assert result["injection"]["requested_failure_count"] == 1
    assert result["injection"]["applied_failure_count"] == 3
    assert result["px4_connection_before"]["connected"] is True
    assert result["px4_connection_after"]["status"] == "validation_disconnected"
    assert result["px4_connection_after"]["validation_disconnect_active"] is True
    assert result["px4_connection_after"]["disconnect_reason"] == "sitl_mavsdk_disconnect"
    assert result["offboard_commander_before"]["running"] is True
    assert result["offboard_commander_after"]["running"] is False
    assert result["offboard_commander_after"]["health_state"] == "failed"
    assert result["offboard_commander_after"]["last_publish_reason"] == "sitl_mavsdk_disconnect"
    assert result["offboard_commander_failure"]["failure_policy_triggered"] is True
    assert result["disconnect_result"]["errors"] == [
        "Failed to stop offboard mode: MAVSDK disconnected - sitl_mavsdk_disconnect"
    ]
    assert ctrl.offboard_commander is None
    assert ctrl.following_active is False


@pytest.mark.asyncio
async def test_offboard_commander_failure_scheduler_uses_running_loop():
    """Commander failure callbacks must schedule cleanup on the app event loop."""
    ctrl = object.__new__(AppController)
    ctrl._app_event_loop = asyncio.get_running_loop()
    ctrl.following_active = True
    ctrl._handle_offboard_commander_failure = AsyncMock()

    status = {"failure_policy_triggered": True, "consecutive_failures": 3}
    ctrl._schedule_offboard_commander_failure(status)
    await asyncio.sleep(0.05)

    ctrl._handle_offboard_commander_failure.assert_awaited_once_with(status)


@pytest.mark.asyncio
async def test_offboard_exit_callback_from_worker_thread_uses_app_loop():
    """MAVLink polling thread callbacks must schedule cleanup on the app loop."""
    ctrl = object.__new__(AppController)
    ctrl._app_event_loop = asyncio.get_running_loop()
    ctrl.following_active = True
    ctrl._handle_offboard_mode_exit = AsyncMock()

    worker = threading.Thread(
        target=ctrl._schedule_offboard_mode_exit,
        args=(393216, 196608),
    )
    worker.start()
    worker.join(timeout=2.0)
    await asyncio.sleep(0.05)

    assert not worker.is_alive()
    ctrl._handle_offboard_mode_exit.assert_awaited_once_with(393216, 196608)


def test_offboard_exit_callback_without_loop_fails_closed_locally():
    """If no loop is available, local following state is cleared synchronously."""
    ctrl = object.__new__(AppController)
    ctrl._app_event_loop = None
    ctrl.following_active = True
    ctrl._handle_offboard_mode_exit = AsyncMock()

    ctrl._schedule_offboard_mode_exit(393216, 196608)

    assert ctrl.following_active is False
    ctrl._handle_offboard_mode_exit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_activities_async_disconnects_before_clearing_tracking():
    """Operator cancel must stop PX4 following before clearing tracker state."""
    ctrl = object.__new__(AppController)
    ctrl.following_active = True
    ctrl.tracking_started = True
    ctrl.segmentation_active = True
    ctrl.selected_bbox = (1, 2, 3, 4)
    ctrl.setpoint_sender = None
    ctrl.smart_tracker = None
    ctrl.tracker = MagicMock()
    ctrl.tracker.is_external_tracker = False
    ctrl.disconnect_px4 = AsyncMock(side_effect=_set_following_inactive(ctrl))

    result = await ctrl.cancel_activities_async()

    ctrl.disconnect_px4.assert_awaited_once()
    ctrl.tracker.stop_tracking.assert_called_once()
    ctrl.tracker.clear_external_override.assert_called_once()
    assert ctrl.tracking_started is False
    assert ctrl.segmentation_active is False
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_keyboard_smart_mode_stops_following_before_sync_toggle():
    """Keyboard smart-mode toggle must stop following before clearing tracker state."""
    ctrl = object.__new__(AppController)
    ctrl.following_active = True
    events = []

    async def cancel_activities_async():
        events.append("cancel")
        ctrl.following_active = False
        return {"steps": ["stopped"], "errors": []}

    def toggle_smart_mode():
        events.append("toggle")

    ctrl.cancel_activities_async = AsyncMock(side_effect=cancel_activities_async)
    ctrl.toggle_smart_mode = MagicMock(side_effect=toggle_smart_mode)

    await ctrl.handle_key_input_async(ord('s'), None)

    assert events == ["cancel", "toggle"]
    ctrl.cancel_activities_async.assert_awaited_once()
    ctrl.toggle_smart_mode.assert_called_once()


@pytest.mark.asyncio
async def test_start_offboard_mode_api_reports_failure_when_controller_returns_errors():
    """The start-Offboard API must not return success for failed controller activation."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        px4_interface=object(),
        tracker=object(),
        video_handler=object(),
        get_tracker_output=MagicMock(return_value=_active_position_output()),
        connect_px4=AsyncMock(return_value={
            "steps": ["initial setpoint sent"],
            "errors": ["OffboardCommander configuration validation failed"],
        }),
    )

    result = await handler._execute_offboard_start_action()

    assert result["status"] == "failure"
    assert "OffboardCommander configuration validation failed" in result["error"]
    assert result["details"]["final_state"] == "inactive"
    assert result["action_audit"]["action_type"] == "offboard_start"
    assert result["action_audit"]["status"] == "failure"
    assert result["action_audit"]["canonical_route"] == "/api/v1/actions/offboard-start"


@pytest.mark.asyncio
async def test_start_offboard_mode_api_blocks_unusable_tracker_output():
    """Direct API starts must fail closed when tracker output is stale/unusable."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        px4_interface=object(),
        tracker=object(),
        video_handler=object(),
        get_tracker_output=MagicMock(return_value=_stale_gimbal_output()),
        connect_px4=AsyncMock(),
    )

    result = await handler._execute_offboard_start_action()

    assert result["status"] == "failure"
    assert "Tracker output is stale" in result["error"]
    assert result["details"]["tracker_runtime"]["usable_for_following"] is False
    assert result["action_audit"]["status"] == "failure"
    handler.app_controller.connect_px4.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_is_idempotent_when_inactive():
    """Internal stop-Offboard executor must be safe when already inactive."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        disconnect_px4=AsyncMock(),
    )

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "success"
    assert result["details"]["was_active"] is False
    assert result["details"]["final_state"] == "inactive"
    assert result["details"]["errors"] == []
    assert result["action_audit"]["action_type"] == "offboard_stop"
    assert result["action_audit"]["canonical_route"] == "/api/v1/actions/offboard-stop"
    assert action["source"] == "internal_compatibility"
    assert action["following_active_before"] is False
    assert action["following_active_after"] is False
    handler.app_controller.disconnect_px4.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_disconnects_when_active():
    """Legacy stop-Offboard API should delegate active cleanup to AppController."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)

    async def disconnect():
        controller.following_active = False
        return {"steps": ["stopped"], "errors": []}

    controller.disconnect_px4 = AsyncMock(side_effect=disconnect)
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "success"
    assert result["details"]["initial_state"] == "active"
    assert result["details"]["final_state"] == "inactive"
    assert result["details"]["was_active"] is True
    assert result["details"]["errors"] == []
    assert result["action_audit"]["action_type"] == "offboard_stop"
    assert result["action_audit"]["status"] == "success"
    assert result["action_audit"]["canonical_route"] == "/api/v1/actions/offboard-stop"
    assert action["following_active_before"] is True
    assert action["following_active_after"] is False
    controller.disconnect_px4.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_reports_disconnect_warnings_as_failure():
    """Legacy stop-Offboard API must not hide cleanup warnings as success."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)

    async def disconnect():
        controller.following_active = False
        return {"steps": ["stopped"], "errors": ["Failed to stop offboard mode: link down"]}

    controller.disconnect_px4 = AsyncMock(side_effect=disconnect)
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "failure"
    assert result["error"] == "Failed to stop offboard mode: link down"
    assert result["details"]["final_state"] == "inactive"
    assert result["action_audit"]["status"] == "failure"
    assert action["status"] == "failure"
    assert action["following_active_after"] is False
    controller.disconnect_px4.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_fails_if_following_remains_active():
    """Legacy stop-Offboard API must fail closed when local following stays active."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=True,
        disconnect_px4=AsyncMock(return_value={"steps": ["stopped"], "errors": []}),
    )
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "failure"
    assert result["details"]["final_state"] == "active"
    assert result["error"] == "Offboard stop command returned with following still active."
    assert result["action_audit"]["status"] == "failure"
    assert action["following_active_after"] is True
    controller.disconnect_px4.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_emergency_cleanup_on_disconnect_exception():
    """Legacy stop-Offboard API keeps its emergency cleanup fallback."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    offboard_commander = SimpleNamespace(stop=AsyncMock())
    setpoint_sender = SimpleNamespace(stop=MagicMock())
    controller = SimpleNamespace(
        following_active=True,
        disconnect_px4=AsyncMock(side_effect=RuntimeError("disconnect failed")),
        offboard_commander=offboard_commander,
        setpoint_sender=setpoint_sender,
        follower=object(),
    )
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "failure"
    assert result["error"] == "disconnect failed"
    assert result["details"]["initial_state"] == "active"
    assert result["details"]["final_state"] == "inactive"
    assert result["details"]["was_active"] is True
    assert result["details"]["exception_type"] == "RuntimeError"
    assert controller.following_active is False
    assert controller.offboard_commander is None
    assert controller.setpoint_sender is None
    assert controller.follower is None
    assert result["action_audit"]["action_type"] == "offboard_stop"
    assert result["action_audit"]["status"] == "failure"
    assert action["error"] == "disconnect failed"
    offboard_commander.stop.assert_awaited_once_with(publish_final=True)
    setpoint_sender.stop.assert_called_once()


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_reports_cleanup_failure():
    """Emergency cleanup failures should remain visible in the stop result."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    offboard_commander = SimpleNamespace(
        stop=AsyncMock(side_effect=RuntimeError("cleanup failed"))
    )
    controller = SimpleNamespace(
        following_active=True,
        disconnect_px4=AsyncMock(side_effect=RuntimeError("disconnect failed")),
        offboard_commander=offboard_commander,
        setpoint_sender=SimpleNamespace(stop=MagicMock()),
        follower=object(),
    )
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "failure"
    assert result["error"] == (
        "disconnect failed; Emergency cleanup failed: cleanup failed"
    )
    assert result["details"]["final_state"] == "active"
    assert result["details"]["was_active"] is True
    assert result["details"]["errors"] == [
        "disconnect failed",
        "Emergency cleanup failed: cleanup failed",
    ]
    assert result["details"]["cleanup_errors"] == [
        "Emergency cleanup failed: cleanup failed",
    ]
    assert action["error"] == result["error"]
    assert controller.following_active is True
    offboard_commander.stop.assert_awaited_once_with(publish_final=True)
    handler.logger.error.assert_any_call("❌ Emergency cleanup failed: cleanup failed")


@pytest.mark.asyncio
async def test_stop_offboard_mode_api_handles_unreadable_final_state():
    """The legacy final-state fallback should survive unreadable state access."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()

    class UnreadableFinalStateController:
        def __init__(self):
            self._following_active = True
            self._reads = 0
            self.disconnect_px4 = AsyncMock(side_effect=RuntimeError("disconnect failed"))
            self.offboard_commander = None
            self.setpoint_sender = None
            self.follower = None

        @property
        def following_active(self):
            self._reads += 1
            if self._reads >= 4:
                raise BaseException("state unavailable")
            return self._following_active

        @following_active.setter
        def following_active(self, value):
            self._following_active = value

    controller = UnreadableFinalStateController()
    handler.app_controller = controller

    result = await handler._execute_offboard_stop_action()

    assert result["status"] == "failure"
    assert result["error"] == "disconnect failed"
    assert result["details"]["initial_state"] == "active"
    assert result["details"]["final_state"] == "unknown"
    assert result["details"]["was_active"] is True
    assert controller._following_active is False


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_dry_run_does_not_execute_legacy_route():
    """Dry-run stop requests must validate without stopping Offboard."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_offboard_stop_action = AsyncMock()
    response = Response()

    result = await handler.stop_offboard_action(
        APIActionRequest(dry_run=True, source="operator_test"),
        response,
    )

    assert response.status_code == 200
    assert result["action_type"] == "offboard_stop"
    assert result["status"] == "validated"
    assert result["accepted"] is True
    assert result["executed"] is False
    assert result["following_active_before"] is True
    assert result["following_active_after"] is True
    assert result["result"]["would_execute"] == "api_legacy_control_routes.stop_offboard_mode"
    handler._execute_offboard_stop_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_requires_confirmation_before_mutation():
    """Typed Offboard stop requires explicit confirmation unless dry-run."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_offboard_stop_action = AsyncMock()
    response = Response()

    result = await handler.stop_offboard_action(APIActionRequest(), response)
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert payload["detail"]["action_type"] == "offboard_stop"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["accepted"] is False
    assert action["executed"] is False
    assert action["status"] == "failure"
    handler._execute_offboard_stop_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_requires_idempotency_key():
    """Confirmed Offboard stop mutations must be idempotent before execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_offboard_stop_action = AsyncMock()

    result = await handler.stop_offboard_action(
        APIActionRequest(confirm=True, source="operator_test"),
        Response(),
    )
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_IDEMPOTENCY_KEY_REQUIRED"
    assert payload["detail"]["action_type"] == "offboard_stop"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["accepted"] is False
    assert action["executed"] is False
    assert action["status"] == "failure"
    handler._execute_offboard_stop_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate Offboard-stop execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller

    async def stop_offboard():
        controller.following_active = False
        return {"status": "success", "details": {"errors": [], "final_state": "inactive"}}

    handler._execute_offboard_stop_action = AsyncMock(side_effect=stop_offboard)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="operator-stop",
        source="operator_test",
    )

    first_response = Response()
    first = await handler.stop_offboard_action(request, first_response)
    second_response = Response()
    second = await handler.stop_offboard_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "offboard_stop"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["following_active_before"] is True
    assert first["following_active_after"] is False
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_offboard_stop_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_serializes_concurrent_idempotent_requests():
    """Concurrent duplicate Offboard-stop requests must not both execute cleanup."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller
    entered = asyncio.Event()
    release = asyncio.Event()

    async def stop_offboard():
        entered.set()
        await release.wait()
        controller.following_active = False
        return {"status": "success", "details": {"errors": [], "final_state": "inactive"}}

    handler._execute_offboard_stop_action = AsyncMock(side_effect=stop_offboard)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="concurrent-stop",
        source="operator_test",
    )
    response_one = Response()
    response_two = Response()

    task_one = asyncio.create_task(handler.stop_offboard_action(request, response_one))
    await entered.wait()
    task_two = asyncio.create_task(handler.stop_offboard_action(request, response_two))
    await asyncio.sleep(0)
    assert handler._execute_offboard_stop_action.await_count == 1
    release.set()

    first, second = await asyncio.gather(task_one, task_two)

    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["following_active_before"] is True
    assert first["following_active_after"] is False
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert response_one.status_code == 202
    assert response_two.status_code == 200
    assert handler._execute_offboard_stop_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_fails_on_legacy_warnings():
    """Typed stop should not report success when legacy cleanup reports errors."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller

    async def stop_offboard():
        controller.following_active = False
        return {"status": "success", "details": {"errors": ["cleanup warning"]}}

    handler._execute_offboard_stop_action = AsyncMock(side_effect=stop_offboard)

    result = await handler.stop_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="operator-stop-warning",
            source="operator_test",
        ),
        Response(),
    )

    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["following_active_after"] is False
    assert result["error"] == "cleanup warning"


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_fails_if_following_remains_active():
    """A successful legacy body is not enough if local following stays active."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_offboard_stop_action = AsyncMock(
        return_value={"status": "success", "details": {"errors": []}}
    )

    result = await handler.stop_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="operator-stop-remains-active",
            source="operator_test",
        ),
        Response(),
    )

    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["following_active_after"] is True
    assert "did not leave local following inactive" in result["error"]


@pytest.mark.asyncio
async def test_api_v1_offboard_stop_action_wraps_legacy_exception_as_action_record():
    """Typed Offboard stop must not leak legacy route exceptions."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_offboard_stop_action = AsyncMock(
        side_effect=HTTPException(status_code=500, detail="legacy stop failure")
    )
    response = Response()

    result = await handler.stop_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="operator-stop-exception",
            source="operator_test",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["action_type"] == "offboard_stop"
    assert "HTTPException" in result["error"]


@pytest.mark.asyncio
async def test_api_v1_offboard_action_blocks_unusable_tracker_output():
    """Typed action callers inherit the same tracker usability guard."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        px4_interface=object(),
        tracker=object(),
        video_handler=object(),
        get_tracker_output=MagicMock(return_value=_stale_gimbal_output()),
        connect_px4=AsyncMock(),
    )

    response = Response()
    result = await handler.start_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="stale-output-start",
            source="operator_test",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["status"] == "failure"
    assert "Tracker output is stale" in result["error"]
    handler.app_controller.connect_px4.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_v1_tracking_runtime_status_reports_visible_output_without_following():
    """The typed tracker runtime API separates visible output from live targets."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="SmartTracker",
        get_tracker_output=MagicMock(return_value=_visible_multi_target_output()),
    )

    payload = await handler.get_tracking_runtime_status()

    assert payload["schema_version"] == 1
    assert payload["status"] == "visible_output"
    assert payload["consumer_guidance"] == "diagnostic_only"
    assert payload["has_output"] is True
    assert payload["active_tracking"] is False
    assert payload["usable_for_following"] is False
    assert payload["target_count"] == 1
    assert payload["configured_tracker"] == "SmartTracker"
    assert payload["claim_boundary"].startswith("PixEagle local tracker runtime status")


@pytest.mark.asyncio
async def test_api_v1_tracking_catalog_reports_schema_and_builtin_types(monkeypatch):
    """Typed tracker catalog combines schema-manager UI entries and built-ins."""
    tracker_output = _active_position_output()

    class FakeTracker:
        pass

    class FakeSchemaManager:
        schemas = {
            "POSITION_2D": {
                "name": "2D Position Tracking",
                "required_fields": ["position_2d"],
            }
        }

        @staticmethod
        def get_available_classic_trackers():
            return {
                "CSRTTracker": {
                    "name": "CSRT Tracker",
                    "description": "OpenCV CSRT tracker",
                    "supported_schemas": ["POSITION_2D"],
                    "capabilities": ["manual_bbox"],
                    "performance": {"cpu": "medium"},
                    "ui_metadata": {
                        "display_name": "CSRT",
                        "short_description": "Stable single target tracker",
                        "suitable_for": ["stable targets"],
                        "icon": "target",
                        "performance_category": "balanced",
                        "factory_key": "CSRT",
                    },
                }
            }

    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: FakeSchemaManager(),
    )
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=FakeTracker(),
        smart_mode_active=False,
        tracking_started=True,
        tracking_active=True,
        following_active=False,
        current_tracker_type="CSRT",
        get_tracker_output=MagicMock(return_value=tracker_output),
    )

    payload = await handler.get_tracking_catalog()
    model = APITrackingCatalogResponse(**payload)

    assert payload["schema_version"] == 1
    assert payload["source"] == "tracking_catalog"
    assert model.source == "tracking_catalog"
    assert payload["status"] == "available"
    assert payload["consumer_guidance"] == "selectable"
    assert payload["configured_tracker"] == "CSRT"
    assert payload["active_tracker"] == "FakeTracker"
    assert payload["tracking_started"] is True
    assert payload["tracking_active"] is True
    assert payload["total_trackers"] == 1
    assert payload["ui_trackers"][0]["source"] == "schema_manager"
    assert payload["ui_trackers"][0]["name"] == "CSRTTracker"
    assert payload["ui_trackers"][0]["display_name"] == "CSRT"
    assert payload["ui_trackers"][0]["request_tracker_type"] == "CSRTTracker"
    assert payload["ui_trackers"][0]["factory_key"] == "CSRT"
    assert payload["ui_trackers"][0]["supported_schemas"] == ["POSITION_2D"]
    assert payload["data_type_schemas"]["POSITION_2D"]["required_fields"] == [
        "position_2d"
    ]
    assert payload["tracker_types"]["SmartTracker"]["source"] == "builtin_compatibility"
    assert payload["runtime_status"]["status"] == "active_usable"
    assert "legacy_compatibility" not in payload
    assert not hasattr(model, "legacy_compatibility")
    assert payload["claim_boundary"].startswith(
        "PixEagle process-local tracker catalog"
    )


@pytest.mark.asyncio
async def test_api_v1_tracking_catalog_ui_names_are_switch_action_valid():
    """Real catalog UI tracker names must be accepted by tracker-switch validation."""
    from classes.schema_manager import get_schema_manager

    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=None,
        smart_mode_active=False,
        tracking_started=False,
        tracking_active=False,
        following_active=False,
        current_tracker_type="CSRT",
        get_tracker_output=MagicMock(return_value=None),
    )

    payload = await handler.get_tracking_catalog()
    ui_tracker_names = [entry["name"] for entry in payload["ui_trackers"]]

    assert "CSRTTracker" in ui_tracker_names
    assert "GimbalTracker" in ui_tracker_names

    schema_manager = get_schema_manager()
    invalid = []
    for tracker_name in ui_tracker_names:
        is_valid, error_msg = schema_manager.validate_tracker_for_ui(tracker_name)
        if not is_valid:
            invalid.append((tracker_name, error_msg))

    assert invalid == []


@pytest.mark.asyncio
async def test_real_tracker_schema_accepts_ui_and_factory_identifiers():
    """Tracker switch validation accepts both catalog names and existing config keys."""
    from classes.schema_manager import get_schema_manager

    schema_manager = get_schema_manager()

    expectations = {
        "CSRTTracker": "CSRTTracker",
        "CSRT": "CSRTTracker",
        "KCFKalmanTracker": "KCFKalmanTracker",
        "KCF": "KCFKalmanTracker",
        "DlibTracker": "DlibTracker",
        "dlib": "DlibTracker",
        "GimbalTracker": "GimbalTracker",
        "Gimbal": "GimbalTracker",
    }

    for identifier, expected_canonical in expectations.items():
        canonical, tracker_info, error = schema_manager.resolve_tracker_for_ui(
            identifier
        )
        assert error == ""
        assert canonical == expected_canonical
        assert tracker_info is not None
        valid, message = schema_manager.validate_tracker_for_ui(identifier)
        assert valid is True
        assert message == ""


@pytest.mark.asyncio
async def test_schema_info_does_not_advertise_retired_tracker_fallbacks():
    """Legacy schema metadata must not imply retired tracker aliases still fallback."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=None,
        follower=None,
    )

    response = await handler.get_schema_info()
    payload = json.loads(response.body)

    compatibility = payload["backward_compatibility"]
    assert compatibility["enabled"] is True
    assert compatibility["legacy_endpoints_available"] is True
    assert compatibility["automatic_fallback"] is False
    assert compatibility["remaining_tracker_diagnostic_routes"] == []
    assert set(compatibility["retired_tracker_catalog_config_routes"]) == {
        "/api/tracker/available",
        "/api/tracker/current",
        "/api/tracker/available-types",
        "/api/tracker/current-config",
    }
    assert set(compatibility["retired_tracker_diagnostic_routes"]) == {
        "/api/tracker/current-status",
        "/api/tracker/output",
        "/api/tracker/schema",
        "/api/tracker/capabilities",
    }
    assert "not available" in compatibility["claim_boundary"]


@pytest.mark.asyncio
async def test_api_v1_tracking_catalog_degrades_when_schema_manager_fails(monkeypatch):
    """Schema-manager failure should not hide built-in compatibility types."""
    def fail_schema_manager():
        raise RuntimeError("schema unavailable")

    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        fail_schema_manager,
    )
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=None,
        smart_mode_active=True,
        tracking_started=False,
        tracking_active=False,
        following_active=False,
        current_tracker_type="SmartTracker",
        get_tracker_output=MagicMock(return_value=None),
    )

    payload = await handler.get_tracking_catalog()
    model = APITrackingCatalogResponse(**payload)

    assert payload["status"] == "degraded"
    assert model.status == "degraded"
    assert payload["consumer_guidance"] == "schema_manager_unavailable"
    assert payload["ui_trackers"] == []
    assert payload["total_trackers"] == 0
    assert "CSRT" in payload["tracker_types"]
    assert payload["tracker_types"]["CSRT"]["available"] is True
    assert payload["health_issues"] == [
        "schema_manager_unavailable: RuntimeError: schema unavailable"
    ]
    assert payload["runtime_status"]["status"] == "no_output"
    assert "legacy_compatibility" not in payload
    assert not hasattr(model, "legacy_compatibility")


@pytest.mark.asyncio
async def test_tracking_runtime_status_and_offboard_readiness_reject_stale_active_output():
    """Active tracking does not override stale/unusable tracker metadata."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="SmartTracker",
        get_tracker_output=MagicMock(return_value=_stale_multi_target_output()),
    )

    payload = await handler.get_tracking_runtime_status()
    readiness = handler._get_tracker_following_readiness()

    assert payload["active_tracking"] is True
    assert payload["has_output"] is True
    assert payload["usable_for_following"] is False
    assert payload["data_is_stale"] is True
    assert payload["status"] == "stale_output"
    assert payload["consumer_guidance"] == "stale"
    assert readiness["usable_for_following"] is False
    assert readiness["status"] == payload["status"]


@pytest.mark.asyncio
async def test_tracking_runtime_status_rejects_active_not_usable_output():
    """Active fresh output still fails closed when not marked follower-usable."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=False,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(
            return_value=_active_position_output(usable_for_following=False)
        ),
    )

    payload = await handler.get_tracking_runtime_status()

    assert payload["active_tracking"] is True
    assert payload["has_output"] is True
    assert payload["data_is_stale"] is False
    assert payload["usable_for_following"] is False
    assert payload["status"] == "not_usable"
    assert payload["consumer_guidance"] == "not_usable"


def test_following_readiness_rejects_video_file_replay_for_video_tracker():
    """A replay frame may drive tracking UI, but cannot start real Offboard."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=False,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(return_value=_active_position_output()),
        _tracker_requires_video_for_following=MagicMock(return_value=True),
        video_handler=SimpleNamespace(
            get_frame_status=MagicMock(return_value={
                "source": "fresh",
                "usable_for_following": False,
                "reason": "video_file_replay_frame",
                "replay_source": True,
                "video_file_playback_epoch": 0,
            })
        ),
    )

    readiness = handler._get_tracker_following_readiness()

    assert readiness["active_tracking"] is True
    assert readiness["usable_for_following"] is False
    assert readiness["status"] == "not_usable"
    assert "Video-file replay" in readiness["reason"]
    assert readiness["video_frame_status"]["replay_source"] is True


def test_following_readiness_allows_explicit_non_video_tracker_with_replay_loaded():
    """External providers with requires_video=false keep their independent contract."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=False,
        following_active=False,
        current_tracker_type="ExternalTracker",
        get_tracker_output=MagicMock(return_value=_active_position_output()),
        _tracker_requires_video_for_following=MagicMock(return_value=False),
        video_handler=SimpleNamespace(
            get_frame_status=MagicMock(return_value={"replay_source": True})
        ),
    )

    readiness = handler._get_tracker_following_readiness()

    assert readiness["usable_for_following"] is True


@pytest.mark.asyncio
async def test_tracking_runtime_status_requires_explicit_usability_metadata():
    """Custom trackers must opt in before active output can drive following."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=False,
        following_active=False,
        current_tracker_type="CustomTracker",
        get_tracker_output=MagicMock(
            return_value=_active_position_output_without_usability_metadata()
        ),
    )

    payload = await handler.get_tracking_runtime_status()
    readiness = handler._get_tracker_following_readiness()

    assert payload["active_tracking"] is True
    assert payload["has_output"] is True
    assert payload["data_is_stale"] is False
    assert payload["usable_for_following"] is False
    assert payload["status"] == "not_usable"
    assert "explicitly marked usable" in payload["reason"]
    assert readiness["usable_for_following"] is False


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_reports_live_tracker_geometry():
    """Typed tracker telemetry exposes geometry without using the legacy route."""
    tracker_output = _active_position_output()
    tracker_output.normalized_bbox = (0.1, 0.2, 0.3, 0.4)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(return_value=tracker_output),
    )
    handler.telemetry_handler = SimpleNamespace(
        get_tracker_data=MagicMock(return_value={
            "center": [9.0, 9.0],
            "bounding_box": [0.9, 0.9, 0.1, 0.1],
            "tracker_data": {
                "position_2d": [9.0, 9.0],
                "normalized_bbox": [0.9, 0.9, 0.1, 0.1],
            },
        })
    )

    payload = await handler.get_tracking_telemetry()

    assert payload["schema_version"] == 1
    assert payload["source"] == "tracking_telemetry"
    assert payload["status"] == "active_usable"
    assert payload["consumer_guidance"] == "usable"
    assert payload["has_output"] is True
    assert payload["active_tracking"] is True
    assert payload["tracking_active"] is True
    assert payload["tracker_started"] is True
    assert payload["usable_for_following"] is True
    assert payload["data_is_stale"] is False
    assert payload["center"] == [0.2, -0.1]
    assert payload["bounding_box"] == [0.1, 0.2, 0.3, 0.4]
    assert payload["fields"]["position_2d"] == [0.2, -0.1]
    assert payload["fields"]["normalized_bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert payload["field_source"] == "tracker_output"
    assert payload["runtime_status"]["usable_for_following"] is True
    assert payload["claim_boundary"].startswith(
        "PixEagle process-local tracker telemetry"
    )


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_keeps_pixel_bbox_out_of_top_level_bbox():
    """Top-level bounding_box must stay normalized-only for plot consumers."""
    tracker_output = _active_position_output()
    tracker_output.bbox = (100, 120, 30, 40)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(return_value=tracker_output),
    )
    handler.telemetry_handler = SimpleNamespace(get_tracker_data=MagicMock(return_value={}))

    payload = await handler.get_tracking_telemetry()

    assert payload["center"] == [0.2, -0.1]
    assert payload["bounding_box"] is None
    assert payload["fields"]["bbox"] == [100, 120, 30, 40]
    assert "normalized_bbox" not in payload["fields"]
    assert payload["field_source"] == "tracker_output"


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_live_output_does_not_depend_on_legacy_cache():
    """Live TrackerOutput telemetry must not fail because legacy cache retrieval fails."""
    tracker_output = _active_position_output()
    tracker_output.normalized_bbox = (0.1, 0.2, 0.3, 0.4)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(return_value=tracker_output),
    )
    handler.telemetry_handler = SimpleNamespace(
        get_tracker_data=MagicMock(side_effect=RuntimeError("legacy cache failed"))
    )

    payload = await handler.get_tracking_telemetry()

    assert payload["status"] == "active_usable"
    assert payload["center"] == [0.2, -0.1]
    assert payload["bounding_box"] == [0.1, 0.2, 0.3, 0.4]
    assert payload["field_source"] == "tracker_output"
    assert payload["legacy_payload_keys"] == []
    handler.telemetry_handler.get_tracker_data.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_rejects_malformed_top_level_geometry():
    """Malformed or non-finite geometry must not enter top-level plot fields."""
    tracker_output = _active_position_output()
    tracker_output.position_2d = (float("inf"), 0.1)
    tracker_output.normalized_bbox = (0.1, 0.2, 0.3)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=True,
        following_active=False,
        current_tracker_type="VisionTracker",
        get_tracker_output=MagicMock(return_value=tracker_output),
    )
    handler.telemetry_handler = SimpleNamespace(get_tracker_data=MagicMock(return_value={}))

    payload = await handler.get_tracking_telemetry()

    assert payload["center"] is None
    assert payload["bounding_box"] is None
    assert payload["fields"]["position_2d"] == [None, 0.1]
    assert payload["fields"]["normalized_bbox"] == [0.1, 0.2, 0.3]
    assert payload["field_source"] == "tracker_output"


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_uses_legacy_snapshot_as_compatibility_source():
    """The typed route can still report legacy tracker payloads for old internals."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        tracker=object(),
        smart_mode_active=False,
        following_active=False,
        current_tracker_type="LegacyTracker",
        get_tracker_output=MagicMock(return_value=None),
    )
    handler.telemetry_handler = SimpleNamespace(
        get_tracker_data=MagicMock(return_value={
            "timestamp": "2026-06-06T00:00:00.000Z",
            "center": [0.3, -0.2],
            "bounding_box": [0.2, 0.3, 0.4, 0.5],
            "tracker_started": True,
            "tracker_data": {
                "position_2d": [0.3, -0.2],
                "normalized_bbox": [0.2, 0.3, 0.4, 0.5],
            },
        })
    )

    payload = await handler.get_tracking_telemetry()

    assert payload["status"] == "no_output"
    assert payload["has_output"] is False
    assert payload["tracker_started"] is True
    assert payload["center"] == [0.3, -0.2]
    assert payload["bounding_box"] == [0.2, 0.3, 0.4, 0.5]
    assert payload["field_source"] == "legacy_telemetry"
    assert payload["legacy_payload_keys"] == [
        "bounding_box",
        "center",
        "timestamp",
        "tracker_data",
        "tracker_started",
    ]


@pytest.mark.asyncio
async def test_api_v1_tracking_telemetry_returns_structured_error_on_failure():
    """Typed tracker telemetry failures must use the shared error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler._get_tracking_telemetry_snapshot = MagicMock(
        side_effect=RuntimeError("tracker telemetry failed")
    )

    response = await handler.get_tracking_telemetry()
    payload = json.loads(response.body)

    assert response.status_code == 500
    assert payload["code"] == "tracking_telemetry_error"
    assert payload["path"] == "/api/v1/tracking/telemetry"
    assert "tracker telemetry failed" in payload["detail"]


@pytest.mark.asyncio
async def test_api_v1_tracking_catalog_returns_structured_error_on_failure():
    """Typed tracker catalog failures must use the shared error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler._get_tracking_catalog_snapshot = MagicMock(
        side_effect=RuntimeError("tracker catalog failed")
    )

    response = await handler.get_tracking_catalog()
    payload = json.loads(response.body)

    assert response.status_code == 500
    assert payload["code"] == "tracking_catalog_error"
    assert payload["path"] == "/api/v1/tracking/catalog"
    assert "tracker catalog failed" in payload["detail"]


@pytest.mark.asyncio
async def test_legacy_cancel_activities_route_records_action_audit():
    """Compatibility cancel route should leave a typed action audit record."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)

    async def cancel():
        controller.following_active = False
        return {"steps": ["stopped"], "errors": []}

    controller.cancel_activities_async = AsyncMock(side_effect=cancel)
    handler.app_controller = controller

    result = await handler._execute_operator_abort_action()
    action = await handler.get_action_resource(result["action_audit"]["action_id"])

    assert result["status"] == "success"
    assert result["action_audit"]["action_type"] == "operator_abort"
    assert result["action_audit"]["status"] == "success"
    assert result["action_audit"]["canonical_route"] == "/api/v1/actions/operator-abort"
    assert action["source"] == "internal_compatibility"
    assert action["following_active_before"] is True
    assert action["following_active_after"] is False


@pytest.mark.asyncio
async def test_api_v1_offboard_action_dry_run_does_not_execute_legacy_route():
    """Dry-run action requests must validate without starting Offboard."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=False)
    handler._execute_offboard_start_action = AsyncMock()
    response = Response()

    result = await handler.start_offboard_action(
        APIActionRequest(dry_run=True, source="sitl_validation"),
        response,
    )

    assert response.status_code == 200
    assert result["action_type"] == "offboard_start"
    assert result["status"] == "validated"
    assert result["accepted"] is True
    assert result["executed"] is False
    assert result["following_active_before"] is False
    assert result["following_active_after"] is False
    assert result["result"]["would_execute"] == "api_legacy_control_routes.start_offboard_mode"
    handler._execute_offboard_start_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_action_requires_confirmation_before_mutation():
    """Typed control actions require explicit confirmation unless dry-run."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=False)
    handler._execute_offboard_start_action = AsyncMock()
    response = Response()

    result = await handler.start_offboard_action(APIActionRequest(), response)
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert payload["detail"]["action_type"] == "offboard_start"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["accepted"] is False
    assert action["executed"] is False
    assert action["status"] == "failure"
    handler._execute_offboard_start_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_action_requires_idempotency_key_for_confirmed_mutation():
    """Confirmed dangerous actions must be idempotent before execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=False)
    handler._execute_offboard_start_action = AsyncMock()

    result = await handler.start_offboard_action(
        APIActionRequest(confirm=True, source="operator_test"),
        Response(),
    )
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_IDEMPOTENCY_KEY_REQUIRED"
    assert payload["detail"]["action_type"] == "offboard_start"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["accepted"] is False
    assert action["executed"] is False
    assert action["status"] == "failure"
    handler._execute_offboard_start_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_offboard_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate Offboard-start execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=False)
    handler.app_controller = controller

    async def start_offboard():
        controller.following_active = True
        return {"status": "success", "details": {"final_state": "active"}}

    handler._execute_offboard_start_action = AsyncMock(side_effect=start_offboard)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="phase2-offboard-entry",
        source="phase2_follower_validation",
    )

    first_response = Response()
    first = await handler.start_offboard_action(request, first_response)
    second_response = Response()
    second = await handler.start_offboard_action(request, second_response)

    assert first_response.status_code == 202
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["following_active_before"] is False
    assert first["following_active_after"] is True
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_offboard_start_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_offboard_action_serializes_concurrent_idempotent_requests():
    """Concurrent duplicate action requests must not both execute the mutation."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=False)
    handler.app_controller = controller
    entered = asyncio.Event()
    release = asyncio.Event()

    async def start_offboard():
        entered.set()
        await release.wait()
        controller.following_active = True
        return {"status": "success", "details": {"final_state": "active"}}

    handler._execute_offboard_start_action = AsyncMock(side_effect=start_offboard)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="concurrent-start",
        source="operator_test",
    )
    response_one = Response()
    response_two = Response()

    task_one = asyncio.create_task(handler.start_offboard_action(request, response_one))
    await entered.wait()
    task_two = asyncio.create_task(handler.start_offboard_action(request, response_two))
    await asyncio.sleep(0)
    assert handler._execute_offboard_start_action.await_count == 1
    release.set()

    first, second = await asyncio.gather(task_one, task_two)

    assert first["status"] == "success"
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert response_one.status_code == 202
    assert response_two.status_code == 200
    assert handler._execute_offboard_start_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_offboard_action_dry_run_does_not_consume_idempotency_key():
    """A dry-run preview must not block a later confirmed mutation retry key."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=False)
    handler.app_controller = controller

    async def start_offboard():
        controller.following_active = True
        return {"status": "success", "details": {"final_state": "active"}}

    handler._execute_offboard_start_action = AsyncMock(side_effect=start_offboard)

    preview = await handler.start_offboard_action(
        APIActionRequest(
            dry_run=True,
            idempotency_key="operator-start-preview",
            source="operator_test",
        ),
        Response(),
    )
    confirmed = await handler.start_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="operator-start-preview",
            source="operator_test",
        ),
        Response(),
    )

    assert preview["status"] == "validated"
    assert preview["executed"] is False
    assert confirmed["status"] == "success"
    assert confirmed["executed"] is True
    assert confirmed["action_id"] != preview["action_id"]
    handler._execute_offboard_start_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_v1_operator_abort_action_records_safe_cancel_result():
    """Operator abort action should call the safe cancel route and track state."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller

    async def cancel():
        controller.following_active = False
        return {"status": "success", "result": {"steps": ["stopped"], "errors": []}}

    handler._execute_operator_abort_action = AsyncMock(side_effect=cancel)
    response = Response()

    result = await handler.operator_abort_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="abort-safe-cancel",
            source="operator_test",
        ),
        response,
    )
    fetched = await handler.get_action_resource(result["action_id"])

    assert response.status_code == 202
    assert result["action_type"] == "operator_abort"
    assert result["status"] == "success"
    assert result["executed"] is True
    assert result["following_active_before"] is True
    assert result["following_active_after"] is False
    assert fetched["action_id"] == result["action_id"]
    handler._execute_operator_abort_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_api_v1_operator_abort_action_serializes_concurrent_idempotent_requests():
    """Concurrent duplicate abort requests must not both execute the mutation."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller
    entered = asyncio.Event()
    release = asyncio.Event()

    async def cancel():
        entered.set()
        await release.wait()
        controller.following_active = False
        return {"status": "success", "result": {"steps": ["stopped"], "errors": []}}

    handler._execute_operator_abort_action = AsyncMock(side_effect=cancel)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="concurrent-abort",
        source="operator_test",
    )
    response_one = Response()
    response_two = Response()

    task_one = asyncio.create_task(handler.operator_abort_action(request, response_one))
    await entered.wait()
    task_two = asyncio.create_task(handler.operator_abort_action(request, response_two))
    await asyncio.sleep(0)
    assert handler._execute_operator_abort_action.await_count == 1
    release.set()

    first, second = await asyncio.gather(task_one, task_two)

    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["following_active_before"] is True
    assert first["following_active_after"] is False
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert response_one.status_code == 202
    assert response_two.status_code == 200
    assert handler._execute_operator_abort_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_operator_abort_action_fails_if_following_remains_active():
    """A successful legacy body is not enough if local following stays active."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(following_active=True)
    handler.app_controller = controller
    handler._execute_operator_abort_action = AsyncMock(
        return_value={"status": "success", "result": {"steps": [], "errors": []}}
    )

    result = await handler.operator_abort_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="abort-remains-active",
            source="operator_test",
        ),
        Response(),
    )

    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["following_active_after"] is True
    assert "did not leave local following inactive" in result["error"]


@pytest.mark.asyncio
async def test_api_v1_operator_abort_action_wraps_legacy_exception_as_action_record():
    """Typed action routes must not leak legacy HTTPException bodies."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(following_active=True)
    handler._execute_operator_abort_action = AsyncMock(
        side_effect=HTTPException(status_code=500, detail="legacy failure")
    )
    response = Response()

    result = await handler.operator_abort_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="abort-exception",
            source="operator_test",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["action_type"] == "operator_abort"
    assert "HTTPException" in result["error"]
    assert result["idempotency_key"] == "abort-exception"


@pytest.mark.asyncio
async def test_api_v1_tracking_start_action_dry_run_does_not_execute_legacy_route():
    """Dry-run tracking-start requests must validate without starting tracking."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
    )
    handler._execute_tracking_start_action = AsyncMock()
    response = Response()

    result = await handler.tracking_start_action(
        APITrackingStartRequest(
            dry_run=True,
            source="operator_test",
            bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        ),
        response,
    )

    assert response.status_code == 200
    assert result["action_type"] == "tracking_start"
    assert result["status"] == "validated"
    assert result["accepted"] is True
    assert result["executed"] is False
    assert result["result"]["bbox"] == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.4,
    }
    assert result["result"]["tracking_active_before"] is False
    assert result["result"]["tracking_active_after"] is False
    handler._execute_tracking_start_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracking_start_action_requires_confirmation_and_idempotency():
    """Confirmed tracking-start mutations must be explicit and idempotent."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
    )
    handler._execute_tracking_start_action = AsyncMock()

    missing_confirmation = await handler.tracking_start_action(
        APITrackingStartRequest(
            source="operator_test",
            bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        ),
        Response(),
    )
    missing_confirmation_payload = json.loads(missing_confirmation.body)

    missing_key = await handler.tracking_start_action(
        APITrackingStartRequest(
            confirm=True,
            source="operator_test",
            bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        ),
        Response(),
    )
    missing_key_payload = json.loads(missing_key.body)

    assert missing_confirmation.status_code == 409
    assert missing_confirmation_payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert missing_confirmation_payload["detail"]["action_type"] == "tracking_start"
    assert missing_key.status_code == 409
    assert missing_key_payload["code"] == "ACTION_IDEMPOTENCY_KEY_REQUIRED"
    assert missing_key_payload["detail"]["action_type"] == "tracking_start"
    handler._execute_tracking_start_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracking_start_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate tracking-start execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
    )
    handler.app_controller = controller

    async def start_tracking(bbox):
        controller.tracking_started = True
        return {
            "status": "Tracking started",
            "bbox": {
                "x": bbox.x,
                "y": bbox.y,
                "width": bbox.width,
                "height": bbox.height,
            },
        }

    handler._execute_tracking_start_action = AsyncMock(side_effect=start_tracking)
    request = APITrackingStartRequest(
        confirm=True,
        idempotency_key="tracking-roi-start",
        source="operator_test",
        bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
    )

    first_response = Response()
    first = await handler.tracking_start_action(request, first_response)
    second_response = Response()
    second = await handler.tracking_start_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "tracking_start"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["tracking_active_before"] is False
    assert first["result"]["tracking_active_after"] is True
    assert first["result"]["bbox"] == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.4,
    }
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_tracking_start_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_tracking_stop_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate tracking-stop execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
    )
    handler.app_controller = controller

    async def stop_tracking():
        controller.tracking_started = False
        return {"status": "Tracking stopped", "result": {"errors": []}}

    handler._execute_tracking_stop_action = AsyncMock(side_effect=stop_tracking)
    request = APIActionRequest(
        confirm=True,
        idempotency_key="tracking-stop",
        source="operator_test",
    )

    first_response = Response()
    first = await handler.tracking_stop_action(request, first_response)
    second_response = Response()
    second = await handler.tracking_stop_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "tracking_stop"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["tracking_active_before"] is True
    assert first["result"]["tracking_active_after"] is False
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_tracking_stop_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_tracking_redetect_action_reports_no_target_as_failure():
    """Re-detection should be accepted but recorded failed when no target returns."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
        segmentation_active=False,
        smart_mode_active=False,
    )
    handler._execute_tracking_redetect_action = AsyncMock(return_value={
        "status": "success",
        "detection_result": {"success": False, "message": "no target"},
    })
    response = Response()

    result = await handler.tracking_redetect_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="redetect-no-target",
            source="operator_test",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["action_type"] == "tracking_redetect"
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["error"] == "no target"
    assert result["result"]["state_before"]["tracking_active"] is True
    assert handler._execute_tracking_redetect_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_segmentation_toggle_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate segmentation-toggle execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
        segmentation_active=False,
        smart_mode_active=False,
    )
    handler.app_controller = controller

    async def toggle_segmentation():
        controller.segmentation_active = True
        return {"status": "success", "segmentation_active": True}

    handler._execute_segmentation_toggle_action = AsyncMock(
        side_effect=toggle_segmentation
    )
    request = APIActionRequest(
        confirm=True,
        idempotency_key="segmentation-toggle",
        source="operator_test",
    )

    first_response = Response()
    first = await handler.segmentation_toggle_action(request, first_response)
    second_response = Response()
    second = await handler.segmentation_toggle_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "segmentation_toggle"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["state_before"]["segmentation_active"] is False
    assert first["result"]["state_after"]["segmentation_active"] is True
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_segmentation_toggle_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_smart_mode_toggle_action_fails_when_state_does_not_change():
    """Smart-mode toggle should fail closed if the controller cannot change state."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
    )
    handler._execute_smart_mode_toggle_action = AsyncMock(return_value={
        "status": "Smart mode disabled",
    })
    response = Response()

    result = await handler.smart_mode_toggle_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="smart-mode-unavailable",
            source="operator_test",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["action_type"] == "smart_mode_toggle"
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["error"] == "Smart mode state did not change."
    assert handler._execute_smart_mode_toggle_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_smart_click_action_executes_once_with_idempotency_key():
    """Idempotency keys prevent duplicate smart-click execution."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
        segmentation_active=False,
        smart_mode_active=True,
    )

    async def smart_click(click):
        return {
            "status": "Click processed",
            "applied": True,
            "success": True,
            "x": click.x,
            "y": click.y,
        }

    handler._execute_smart_click_action = AsyncMock(side_effect=smart_click)
    request = APITrackingSmartClickRequest(
        confirm=True,
        idempotency_key="smart-click",
        source="operator_test",
        click={"x": 0.25, "y": 0.4},
    )

    first_response = Response()
    first = await handler.smart_click_action(request, first_response)
    second_response = Response()
    second = await handler.smart_click_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "smart_click"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["click"] == {"x": 0.25, "y": 0.4}
    assert first["result"]["legacy_result"] == {
        "status": "Click processed",
        "applied": True,
        "success": True,
        "x": 0.25,
        "y": 0.4,
    }
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_smart_click_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_smart_click_action_records_no_target_as_failure():
    """Smart-click must not report success when no target override was applied."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
        segmentation_active=False,
        smart_mode_active=True,
    )
    handler._execute_smart_click_action = AsyncMock(return_value={
        "status": "Click not applied",
        "applied": False,
        "success": False,
        "message": "No AI detection selected. Override not applied.",
    })
    response = Response()

    result = await handler.smart_click_action(
        APITrackingSmartClickRequest(
            confirm=True,
            idempotency_key="smart-click-no-target",
            source="operator_test",
            click={"x": 0.25, "y": 0.4},
        ),
        response,
    )

    assert response.status_code == 202
    assert result["action_type"] == "smart_click"
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["error"] == "No AI detection selected. Override not applied."
    assert handler._execute_smart_click_action.await_count == 1


def _patch_tracker_switch_schema(monkeypatch, *, valid=True, message=None):
    class FakeSchemaManager:
        def validate_tracker_for_ui(self, tracker_type):
            if valid:
                return True, None
            return False, message or f"Invalid tracker {tracker_type}"

    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: FakeSchemaManager(),
    )


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_dry_run_validates_without_mutation(monkeypatch):
    """Dry-run tracker-restart requests validate the configured tracker only."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="Gimbal",
        tracker=None,
    )
    handler._execute_tracker_restart_action = AsyncMock()
    response = Response()

    result = await handler.tracker_restart_action(
        APIActionRequest(
            dry_run=True,
            source="operator_test",
            reason="apply_tracker_config",
        ),
        response,
    )

    assert response.status_code == 200
    assert result["action_type"] == "tracker_restart"
    assert result["status"] == "validated"
    assert result["accepted"] is True
    assert result["executed"] is False
    assert result["result"]["tracker_type"] == "Gimbal"
    assert result["result"]["state_before"]["configured_tracker"] == "Gimbal"
    handler._execute_tracker_restart_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_accepts_factory_key_default():
    """Existing config defaults such as CSRT must not fail typed restart validation."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler._execute_tracker_restart_action = AsyncMock()
    response = Response()

    result = await handler.tracker_restart_action(
        APIActionRequest(
            dry_run=True,
            source="operator_test",
            reason="apply_tracker_config",
        ),
        response,
    )

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["result"]["tracker_type"] == "CSRT"
    assert result["result"]["state_before"]["configured_tracker"] == "CSRT"
    handler._execute_tracker_restart_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_requires_confirmation_and_idempotency(monkeypatch):
    """Confirmed tracker-restart mutations must be explicit and idempotent."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="Gimbal",
        tracker=None,
    )
    handler._execute_tracker_restart_action = AsyncMock()

    missing_confirmation = await handler.tracker_restart_action(
        APIActionRequest(source="operator_test", reason="apply_tracker_config"),
        Response(),
    )
    missing_confirmation_payload = json.loads(missing_confirmation.body)

    missing_key = await handler.tracker_restart_action(
        APIActionRequest(
            confirm=True,
            source="operator_test",
            reason="apply_tracker_config",
        ),
        Response(),
    )
    missing_key_payload = json.loads(missing_key.body)

    assert missing_confirmation.status_code == 409
    assert missing_confirmation_payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert missing_confirmation_payload["detail"]["action_type"] == "tracker_restart"
    assert missing_key.status_code == 409
    assert missing_key_payload["code"] == "ACTION_IDEMPOTENCY_KEY_REQUIRED"
    assert missing_key_payload["detail"]["action_type"] == "tracker_restart"
    handler._execute_tracker_restart_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_executes_once_with_idempotency_key(monkeypatch):
    """Idempotency keys prevent duplicate tracker-restart execution."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="Gimbal",
        tracker=None,
    )
    handler.app_controller = controller
    handler._execute_tracker_restart_action = AsyncMock(
        return_value={
            "success": True,
            "action": "tracker_restarted",
            "tracker_type": "Gimbal",
            "config_reloaded": True,
        }
    )
    request = APIActionRequest(
        confirm=True,
        idempotency_key="tracker-restart-gimbal",
        source="operator_test",
        reason="apply_tracker_config",
    )

    first_response = Response()
    first = await handler.tracker_restart_action(request, first_response)
    second_response = Response()
    second = await handler.tracker_restart_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "tracker_restart"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["tracker_type"] == "Gimbal"
    assert first["result"]["state_before"]["configured_tracker"] == "Gimbal"
    assert first["result"]["state_after"]["configured_tracker"] == "Gimbal"
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_tracker_restart_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_rejects_invalid_configured_tracker(monkeypatch):
    """Invalid configured tracker types fail closed before restart execution."""
    _patch_tracker_switch_schema(monkeypatch, valid=False, message="bad tracker")
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="BadTracker",
        tracker=None,
    )
    handler._execute_tracker_restart_action = AsyncMock()

    result = await handler.tracker_restart_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="invalid-tracker-restart",
            source="operator_test",
            reason="apply_tracker_config",
        ),
        Response(),
    )
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_TRACKER_RESTART_INVALID"
    assert payload["detail"]["tracker_type"] == "BadTracker"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["status"] == "failure"
    assert action["accepted"] is False
    assert action["executed"] is False
    handler._execute_tracker_restart_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_restart_action_reports_legacy_failure(monkeypatch):
    """Legacy restart failures are captured as failed typed action resources."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="Gimbal",
        tracker=None,
    )
    handler._execute_tracker_restart_action = AsyncMock(
        return_value={
            "success": False,
            "action": "restart_failed",
            "tracker_type": "Gimbal",
            "error": "reload failed",
            "config_reloaded": True,
        }
    )

    result = await handler.tracker_restart_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="tracker-restart-failure",
            source="operator_test",
            reason="apply_tracker_config",
        ),
        Response(),
    )

    assert result["action_type"] == "tracker_restart"
    assert result["status"] == "failure"
    assert result["executed"] is True
    assert result["error"] == "reload failed"
    assert handler._execute_tracker_restart_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_tracker_switch_action_dry_run_validates_without_mutation(monkeypatch):
    """Dry-run tracker-switch requests validate the selected tracker only."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler._execute_tracker_switch_action = AsyncMock()
    response = Response()

    result = await handler.tracker_switch_action(
        APITrackerSwitchRequest(
            dry_run=True,
            source="operator_test",
            tracker_type="Gimbal",
        ),
        response,
    )

    assert response.status_code == 200
    assert result["action_type"] == "tracker_switch"
    assert result["status"] == "validated"
    assert result["accepted"] is True
    assert result["executed"] is False
    assert result["result"]["requested_tracker"] == "Gimbal"
    assert result["result"]["state_before"]["configured_tracker"] == "CSRT"
    handler._execute_tracker_switch_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_switch_action_requires_confirmation_and_idempotency(monkeypatch):
    """Confirmed tracker-switch mutations must be explicit and idempotent."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler._execute_tracker_switch_action = AsyncMock()

    missing_confirmation = await handler.tracker_switch_action(
        APITrackerSwitchRequest(source="operator_test", tracker_type="Gimbal"),
        Response(),
    )
    missing_confirmation_payload = json.loads(missing_confirmation.body)

    missing_key = await handler.tracker_switch_action(
        APITrackerSwitchRequest(
            confirm=True,
            source="operator_test",
            tracker_type="Gimbal",
        ),
        Response(),
    )
    missing_key_payload = json.loads(missing_key.body)

    assert missing_confirmation.status_code == 409
    assert missing_confirmation_payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert missing_confirmation_payload["detail"]["action_type"] == "tracker_switch"
    assert missing_key.status_code == 409
    assert missing_key_payload["code"] == "ACTION_IDEMPOTENCY_KEY_REQUIRED"
    assert missing_key_payload["detail"]["action_type"] == "tracker_switch"
    handler._execute_tracker_switch_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_switch_action_executes_once_with_idempotency_key(monkeypatch):
    """Idempotency keys prevent duplicate tracker-switch execution."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler.app_controller = controller

    async def switch_tracker(tracker_type):
        controller.current_tracker_type = tracker_type
        return {
            "status": "success",
            "action": "tracker_switched",
            "old_tracker": "CSRT",
            "new_tracker": tracker_type,
            "requires_restart": False,
        }

    handler._execute_tracker_switch_action = AsyncMock(side_effect=switch_tracker)
    request = APITrackerSwitchRequest(
        confirm=True,
        idempotency_key="tracker-switch-gimbal",
        source="operator_test",
        tracker_type="Gimbal",
    )

    first_response = Response()
    first = await handler.tracker_switch_action(request, first_response)
    second_response = Response()
    second = await handler.tracker_switch_action(request, second_response)

    assert first_response.status_code == 202
    assert first["action_type"] == "tracker_switch"
    assert first["status"] == "success"
    assert first["executed"] is True
    assert first["result"]["requested_tracker"] == "Gimbal"
    assert first["result"]["state_before"]["configured_tracker"] == "CSRT"
    assert first["result"]["state_after"]["configured_tracker"] == "Gimbal"
    assert second_response.status_code == 200
    assert second["action_id"] == first["action_id"]
    assert second["idempotent_replay"] is True
    assert handler._execute_tracker_switch_action.await_count == 1


@pytest.mark.asyncio
async def test_app_controller_tracker_switch_canonicalizes_factory_key(monkeypatch):
    """Switching with a factory key records the canonical schema tracker name."""
    monkeypatch.setattr(Parameters, "DEFAULT_TRACKING_ALGORITHM", "CSRT", raising=False)

    class FakeTracker:
        pass

    created = {}

    def fake_create_tracker(factory_key, video_handler, detector, controller):
        created["factory_key"] = factory_key
        created["video_handler"] = video_handler
        created["detector"] = detector
        created["controller"] = controller
        return FakeTracker()

    monkeypatch.setattr(
        "classes.app_controller.create_tracker",
        fake_create_tracker,
    )

    controller = object.__new__(AppController)
    controller.current_tracker_type = "CSRT"
    controller.following_active = False
    controller.tracking_started = False
    controller.tracker = None
    controller.video_handler = object()
    controller.detector = object()

    result = await controller.switch_tracker_type("KCF")

    assert result["success"] is True
    assert result["requested_tracker"] == "KCF"
    assert result["new_tracker"] == "KCFKalmanTracker"
    assert result["factory_key"] == "KCF"
    assert controller.current_tracker_type == "KCFKalmanTracker"
    assert Parameters.DEFAULT_TRACKING_ALGORITHM == "KCF"
    assert created["factory_key"] == "KCF"
    assert created["controller"] is controller


@pytest.mark.asyncio
async def test_api_v1_tracker_switch_action_rejects_invalid_tracker_before_mutation(monkeypatch):
    """Invalid tracker selections fail closed before route execution."""
    _patch_tracker_switch_schema(monkeypatch, valid=False, message="bad tracker")
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler._execute_tracker_switch_action = AsyncMock()

    result = await handler.tracker_switch_action(
        APITrackerSwitchRequest(
            confirm=True,
            idempotency_key="invalid-tracker-switch",
            source="operator_test",
            tracker_type="BadTracker",
        ),
        Response(),
    )
    payload = json.loads(result.body)

    assert result.status_code == 409
    assert payload["code"] == "ACTION_TRACKER_SWITCH_INVALID"
    assert payload["detail"]["requested_tracker"] == "BadTracker"
    action = await handler.get_action_resource(payload["detail"]["action_id"])
    assert action["status"] == "failure"
    assert action["accepted"] is False
    assert action["executed"] is False
    handler._execute_tracker_switch_action.assert_not_called()


@pytest.mark.asyncio
async def test_api_v1_tracker_switch_action_fails_when_configured_state_does_not_change(monkeypatch):
    """A legacy success payload is not enough if local configured state is unchanged."""
    _patch_tracker_switch_schema(monkeypatch)
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        tracking_started=False,
        segmentation_active=False,
        smart_mode_active=False,
        current_tracker_type="CSRT",
        tracker=None,
    )
    handler._execute_tracker_switch_action = AsyncMock(return_value={
        "status": "success",
        "action": "tracker_switched",
        "old_tracker": "CSRT",
        "new_tracker": "Gimbal",
    })

    result = await handler.tracker_switch_action(
        APITrackerSwitchRequest(
            confirm=True,
            idempotency_key="tracker-switch-mismatch",
            source="operator_test",
            tracker_type="Gimbal",
        ),
        Response(),
    )

    assert result["status"] == "failure"
    assert result["executed"] is True
    assert "configured tracker is 'CSRT'" in result["error"]
    assert handler._execute_tracker_switch_action.await_count == 1


@pytest.mark.asyncio
async def test_api_v1_runtime_action_replay_requires_confirmation():
    """A reused idempotency key must not bypass explicit confirmation."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    controller = SimpleNamespace(
        following_active=False,
        tracking_started=True,
        segmentation_active=False,
        smart_mode_active=False,
    )
    handler.app_controller = controller

    async def toggle_segmentation():
        controller.segmentation_active = True
        return {"status": "success", "segmentation_active": True}

    handler._execute_segmentation_toggle_action = AsyncMock(
        side_effect=toggle_segmentation
    )
    confirmed_request = APIActionRequest(
        confirm=True,
        idempotency_key="segmentation-confirmation-order",
        source="operator_test",
    )
    first = await handler.segmentation_toggle_action(confirmed_request, Response())

    replay_without_confirmation = await handler.segmentation_toggle_action(
        APIActionRequest(
            idempotency_key="segmentation-confirmation-order",
            source="operator_test",
        ),
        Response(),
    )
    payload = json.loads(replay_without_confirmation.body)

    assert first["status"] == "success"
    assert replay_without_confirmation.status_code == 409
    assert payload["code"] == "ACTION_CONFIRMATION_REQUIRED"
    assert payload["detail"]["action_type"] == "segmentation_toggle"
    assert handler._execute_segmentation_toggle_action.await_count == 1


@pytest.mark.asyncio
async def test_setpoints_status_uses_concrete_handler_and_commander_publication():
    """Setpoint status should unwrap the concrete follower and expose commander truth."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    setpoint_handler = SimpleNamespace(
        get_fields_with_status=MagicMock(return_value={
            "setpoints": {"vel_body_fwd": 1.0},
            "profile": "gm_velocity_vector",
            "control_type": "velocity_body_offboard",
            "circuit_breaker": {"active": False, "status": "LIVE_MODE"},
        })
    )
    commander = SimpleNamespace(
        get_status=MagicMock(return_value={
            "exists": True,
            "running": True,
            "successful_publishes": 3,
            "last_intent_fresh": True,
            "failsafe_defaults_active": False,
        })
    )
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=SimpleNamespace(follower=SimpleNamespace(setpoint_handler=setpoint_handler)),
        offboard_commander=commander,
    )

    response = await handler.get_follower_setpoints_with_status()
    data = response.body.decode()

    assert '"command_publication"' in data
    assert '"commands_sent_to_px4":true' in data.replace(" ", "")
    assert '"follower_type":"SimpleNamespace"' in data.replace(" ", "")


@pytest.mark.asyncio
async def test_status_exposes_mavlink_telemetry_freshness():
    """Top-level status should expose typed MAVLink telemetry freshness state."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = SimpleNamespace(
        get_connection_health=MagicMock(return_value={"status": "connected"})
    )
    handler.app_controller = SimpleNamespace(
        smart_mode_active=False,
        tracking_started=False,
        segmentation_active=False,
        following_active=False,
        smart_tracker=None,
        offboard_commander=None,
        last_offboard_commander_failure={"health_state": "failed"},
        mavlink_data_manager=SimpleNamespace(
            get_connection_status=MagicMock(return_value={
                "status": "stale",
                "fresh": False,
                "stale_timeout_s": 2.0,
            })
        ),
    )

    status = await handler.get_status()

    assert status["mavlink_telemetry"]["status"] == "stale"
    assert status["mavlink_telemetry"]["fresh"] is False
    assert status["offboard_commander_failure"]["health_state"] == "failed"


@pytest.mark.asyncio
async def test_typed_runtime_status_wraps_process_local_status_snapshot():
    """Typed runtime status should expose mode flags without making PX4 claims."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = SimpleNamespace(
        get_connection_health=MagicMock(return_value={"status": "connected"})
    )
    handler.app_controller = SimpleNamespace(
        smart_mode_active=True,
        tracking_started=True,
        segmentation_active=False,
        following_active=False,
        smart_tracker=SimpleNamespace(
            get_runtime_info=MagicMock(return_value={"mode": "hybrid"})
        ),
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={"health_state": "healthy"})
        ),
        last_offboard_commander_failure=None,
        px4_interface=SimpleNamespace(
            get_connection_status=MagicMock(return_value={"connected": True})
        ),
        mavlink_data_manager=SimpleNamespace(
            get_connection_status=MagicMock(return_value={"status": "healthy"})
        ),
    )

    result = await handler.get_runtime_status()

    assert result["schema_version"] == 1
    assert result["source"] == "pixeagle_runtime"
    assert result["status"] == "active"
    assert result["consumer_guidance"] == "vision_active"
    assert result["modes"] == {
        "smart_mode_active": True,
        "tracking_started": True,
        "segmentation_active": False,
        "following_active": False,
    }
    assert result["subsystems"]["video_status"] == "connected"
    assert result["subsystems"]["smart_tracker_runtime"]["mode"] == "hybrid"
    assert result["subsystems"]["mavlink_telemetry"]["status"] == "healthy"
    assert "not PX4, SITL, HIL" in result["claim_boundary"]


@pytest.mark.asyncio
async def test_typed_runtime_status_degrades_on_commander_failure():
    """Commander failures should be visible in the typed runtime contract."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = None
    handler.app_controller = SimpleNamespace(
        smart_mode_active=False,
        tracking_started=False,
        segmentation_active=False,
        following_active=True,
        smart_tracker=None,
        offboard_commander=None,
        last_offboard_commander_failure={"health_state": "failed"},
        px4_interface=None,
        mavlink_data_manager=None,
    )

    result = await handler.get_runtime_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_failure_present"
    assert result["modes"]["following_active"] is True
    assert result["subsystems"]["offboard_commander_failure"]["health_state"] == "failed"


@pytest.mark.asyncio
async def test_typed_runtime_status_degrades_when_following_without_running_commander():
    """Local following must not look healthy when command publication is stopped."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = None
    handler.app_controller = SimpleNamespace(
        smart_mode_active=False,
        tracking_started=False,
        segmentation_active=False,
        following_active=True,
        smart_tracker=None,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "running": False,
                "task_active": False,
                "health_state": "stopped",
                "last_intent_fresh": False,
                "failsafe_defaults_active": True,
            })
        ),
        last_offboard_commander_failure=None,
        px4_interface=None,
        mavlink_data_manager=None,
    )

    result = await handler.get_runtime_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_not_running"
    assert result["modes"]["following_active"] is True
    assert result["subsystems"]["offboard_commander"]["health_state"] == "stopped"


@pytest.mark.asyncio
async def test_typed_runtime_status_degrades_on_stale_commander_intent():
    """Following with a stale OffboardCommander intent should require attention."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = None
    handler.app_controller = SimpleNamespace(
        smart_mode_active=False,
        tracking_started=False,
        segmentation_active=False,
        following_active=True,
        smart_tracker=None,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "running": True,
                "task_active": True,
                "health_state": "running",
                "last_intent_fresh": False,
                "failsafe_defaults_active": False,
            })
        ),
        last_offboard_commander_failure=None,
        px4_interface=None,
        mavlink_data_manager=None,
    )

    result = await handler.get_runtime_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_intent_stale"


@pytest.mark.asyncio
async def test_typed_runtime_status_degrades_on_incomplete_commander_snapshot():
    """Following with unknown command-publication fields should fail closed."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = None
    handler.app_controller = SimpleNamespace(
        smart_mode_active=False,
        tracking_started=False,
        segmentation_active=False,
        following_active=True,
        smart_tracker=None,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={"health_state": "running"})
        ),
        last_offboard_commander_failure=None,
        px4_interface=None,
        mavlink_data_manager=None,
    )

    result = await handler.get_runtime_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_running_unknown"


@pytest.mark.asyncio
async def test_typed_runtime_status_returns_structured_error():
    """Typed runtime-status failures should use the /api/v1 error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.video_handler = SimpleNamespace(
        get_connection_health=MagicMock(side_effect=RuntimeError("video failed"))
    )
    handler.app_controller = SimpleNamespace()

    response = await handler.get_runtime_status()
    payload = json.loads(response.body.decode())

    assert response.status_code == 500
    assert payload["code"] == "runtime_status_error"
    assert payload["detail"] == "video failed"
    assert payload["path"] == "/api/v1/runtime/status"
    assert payload["request_id"].startswith("pixeagle-api-")


@pytest.mark.asyncio
async def test_typed_following_status_reports_inactive_without_commander():
    """Inactive local following should expose an explicit typed status."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        follower=None,
        offboard_commander=None,
        last_offboard_commander_failure=None,
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_status()

    assert result["schema_version"] == 1
    assert result["source"] == "following_runtime"
    assert result["status"] == "inactive"
    assert result["consumer_guidance"] == "inactive"
    assert result["following_active"] is False
    assert result["profile"]["configured_mode"] == "gm_velocity_vector"
    assert result["profile"]["profile_valid"] is True
    assert result["command_publication"]["exists"] is False
    assert "not PX4, SITL, HIL" in result["claim_boundary"]


@pytest.mark.asyncio
async def test_typed_following_status_reports_active_with_healthy_commander():
    """Active local following requires a healthy command-publication owner."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    follower = SimpleNamespace(
        mode="gm_velocity_vector",
        follower=SimpleNamespace(),
        get_display_name=MagicMock(return_value="Gimbal Velocity Vector"),
        get_control_type=MagicMock(return_value="velocity_body_offboard"),
        get_available_fields=MagicMock(return_value=[
            "vel_body_fwd",
            "vel_body_right",
            "vel_body_down",
            "yawspeed_deg_s",
        ]),
    )
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=follower,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "exists": True,
                "running": True,
                "task_active": True,
                "health_state": "running",
                "sends_mavsdk_commands": True,
                "command_publication_source": "offboard_commander",
                "last_intent_fresh": True,
                "failsafe_defaults_active": False,
                "successful_publishes": 3,
                "failed_publishes": 0,
                "consecutive_failures": 0,
            })
        ),
        last_offboard_commander_failure=None,
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_status()

    assert result["status"] == "active"
    assert result["consumer_guidance"] == "following_active"
    assert result["following_active"] is True
    assert result["profile"]["current_mode"] == "gm_velocity_vector"
    assert result["profile"]["control_type"] == "velocity_body_offboard"
    assert result["command_publication"]["running"] is True
    assert result["command_publication"]["last_intent_fresh"] is True
    assert result["command_publication"]["local_successful_publish_observed"] is True
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_typed_following_status_degrades_when_following_without_running_commander():
    """Following cannot look active when command publication is stopped."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=SimpleNamespace(
            mode="gm_velocity_vector",
            follower=SimpleNamespace(),
            get_display_name=MagicMock(return_value="Gimbal Velocity Vector"),
            get_control_type=MagicMock(return_value="velocity_body_offboard"),
            get_available_fields=MagicMock(return_value=[]),
        ),
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "exists": True,
                "running": False,
                "task_active": False,
                "health_state": "stopped",
                "last_intent_fresh": False,
                "failsafe_defaults_active": True,
                "successful_publishes": 0,
            })
        ),
        last_offboard_commander_failure=None,
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_not_running"
    assert result["following_active"] is True
    assert result["command_publication"]["local_successful_publish_observed"] is False


@pytest.mark.asyncio
async def test_typed_following_status_degrades_when_commander_runs_while_inactive():
    """Stopped local following should still flag a live command publication task."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        follower=None,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "exists": True,
                "running": True,
                "task_active": True,
                "health_state": "running",
                "successful_publishes": 1,
            })
        ),
        last_offboard_commander_failure=None,
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_status()

    assert result["status"] == "degraded"
    assert result["consumer_guidance"] == "operator_attention"
    assert result["reason"] == "offboard_commander_running_while_inactive"
    assert result["following_active"] is False


@pytest.mark.asyncio
async def test_typed_following_status_returns_structured_error():
    """Typed following-status failures should use the /api/v1 error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=None,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(side_effect=RuntimeError("commander failed"))
        ),
        last_offboard_commander_failure=None,
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        response = await handler.get_following_status()
    payload = json.loads(response.body.decode())

    assert response.status_code == 500
    assert payload["code"] == "following_status_error"
    assert payload["detail"] == "commander failed"
    assert payload["path"] == "/api/v1/following/status"
    assert payload["request_id"].startswith("pixeagle-api-")


@pytest.mark.asyncio
async def test_typed_following_telemetry_reports_active_fields_and_diagnostics():
    """Typed following telemetry should expose live fields without PX4 proof claims."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    setpoint_handler = SimpleNamespace(
        get_fields=MagicMock(return_value={
            "vel_body_fwd": 1.25,
            "vel_body_right": -0.5,
            "vel_body_down": 0.0,
            "yawspeed_deg_s": 3.0,
        })
    )
    follower = SimpleNamespace(
        mode="gm_velocity_vector",
        follower=SimpleNamespace(setpoint_handler=setpoint_handler),
        get_display_name=MagicMock(return_value="Gimbal Velocity Vector"),
        get_control_type=MagicMock(return_value="velocity_body_offboard"),
        get_available_fields=MagicMock(return_value=[
            "vel_body_fwd",
            "vel_body_right",
            "vel_body_down",
            "yawspeed_deg_s",
        ]),
        get_last_command_intent=MagicMock(return_value=_command_intent()),
    )
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=follower,
        offboard_commander=SimpleNamespace(
            get_status=MagicMock(return_value={
                "exists": True,
                "running": True,
                "task_active": True,
                "health_state": "running",
                "sends_mavsdk_commands": True,
                "command_publication_source": "offboard_commander",
                "last_intent_fresh": True,
                "failsafe_defaults_active": False,
                "successful_publishes": 4,
                "failed_publishes": 0,
                "consecutive_failures": 0,
            })
        ),
        last_offboard_commander_failure=None,
    )
    handler.telemetry_handler = SimpleNamespace(
        get_follower_data=MagicMock(return_value={
            "fields": {"legacy": 9.0},
            "target_loss_handler": {"state": "ACTIVE"},
            "safety_systems": {"safety_violations_count": 0},
            "performance": {"success_rate_percent": 100.0},
            "circuit_breaker": {"active": False, "status": "LIVE_MODE"},
            "flight_mode": 393216,
            "flight_mode_text": "Offboard",
            "is_offboard": True,
        })
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_telemetry()

    assert result["schema_version"] == 1
    assert result["source"] == "following_telemetry"
    assert result["status"] == "active"
    assert result["consumer_guidance"] == "following_active"
    assert result["following_active"] is True
    assert result["fields"]["vel_body_fwd"] == 1.25
    assert "legacy" not in result["fields"]
    assert result["field_source"] == "active_follower"
    assert result["target_loss_handler"]["state"] == "ACTIVE"
    assert result["safety_systems"]["safety_violations_count"] == 0
    assert result["performance"]["success_rate_percent"] == 100.0
    assert result["circuit_breaker_active"] is False
    assert result["flight_mode"] == 393216
    assert result["is_offboard"] is True
    assert result["command_publication"]["local_successful_publish_observed"] is True
    assert result["last_command_intent"]["source"] == "unit_test"
    assert "not PX4-observed Offboard" in result["claim_boundary"]


@pytest.mark.asyncio
async def test_typed_following_telemetry_falls_back_to_legacy_fields():
    """Typed telemetry can preserve legacy field values when no live handler exists."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        follower=None,
        offboard_commander=None,
        last_offboard_commander_failure=None,
    )
    handler.telemetry_handler = SimpleNamespace(
        get_follower_data=MagicMock(return_value={
            "fields": {"vel_body_fwd": 0.0},
            "profile_name": "Gimbal Velocity Vector",
        })
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        result = await handler.get_following_telemetry()

    assert result["status"] == "inactive"
    assert result["consumer_guidance"] == "inactive"
    assert result["fields"] == {"vel_body_fwd": 0.0}
    assert result["field_source"] == "legacy_telemetry"
    assert result["command_publication"]["exists"] is False


@pytest.mark.asyncio
async def test_typed_following_telemetry_returns_structured_error():
    """Typed following telemetry failures should use the /api/v1 error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(
        following_active=False,
        follower=None,
        offboard_commander=None,
        last_offboard_commander_failure=None,
    )
    handler.telemetry_handler = SimpleNamespace(
        get_follower_data=MagicMock(side_effect=RuntimeError("telemetry failed"))
    )

    with patch('classes.fastapi_handler.Parameters.FOLLOWER_MODE', 'gm_velocity_vector'):
        response = await handler.get_following_telemetry()
    payload = json.loads(response.body.decode())

    assert response.status_code == 500
    assert payload["code"] == "following_telemetry_error"
    assert payload["detail"] == "telemetry failed"
    assert payload["path"] == "/api/v1/following/telemetry"
    assert payload["request_id"].startswith("pixeagle-api-")


@pytest.mark.asyncio
async def test_typed_telemetry_health_endpoint_forwards_manager_snapshot():
    """Typed telemetry health should use the manager's structured contract."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    expected_health = {
        "schema_version": 1,
        "source": "mavlink2rest",
        "enabled": True,
        "status": "degraded",
        "consumer_guidance": "degraded_latest_request_failed",
        "transport": {
            "state": "error",
            "latest_request_ok": False,
            "latest_request_result": "failure",
            "latest_request_age_s": 0.1,
            "last_error": "Connection timeout - simulated",
            "error_count": 1,
            "validation_timeout_active": False,
            "request_timeout_s": 5.0,
            "request_retries": 0,
            "endpoint": "http://127.0.0.1:8088",
        },
        "request_freshness": {
            "fresh": True,
            "last_success_age_s": 0.2,
            "stale_timeout_s": 2.0,
            "last_success_monotonic_available": True,
        },
        "payload": {
            "has_payload": True,
            "sample_count": 2,
            "available_keys": ["arm_status", "flight_mode"],
            "flight_mode": 393216,
            "arm_status": "Armed",
            "fresh": True,
            "payload_age_s": 0.2,
        },
        "claim_boundary": "PixEagle local MAVLink2REST client health only; not PX4, SITL, HIL, field, or follower-response proof.",
        "timestamp": time.time(),
    }
    manager = SimpleNamespace(get_telemetry_health=MagicMock(return_value=expected_health))
    handler.app_controller = SimpleNamespace(mavlink_data_manager=manager)

    result = await handler.get_telemetry_health()

    assert result == expected_health
    manager.get_telemetry_health.assert_called_once_with()


@pytest.mark.asyncio
async def test_typed_telemetry_health_endpoint_reports_unavailable_without_manager():
    """Typed telemetry health should fail closed when no manager is configured."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = SimpleNamespace(mavlink_data_manager=None)

    result = await handler.get_telemetry_health()

    assert result["enabled"] is False
    assert result["status"] == "disconnected"
    assert result["consumer_guidance"] == "unavailable"
    assert result["transport"]["latest_request_result"] == "not_attempted"
    assert result["transport"]["last_error"] == "MAVLink data manager is not configured"
    assert result["request_freshness"]["fresh"] is False
    assert "not PX4, SITL, HIL" in result["claim_boundary"]


@pytest.mark.asyncio
async def test_typed_telemetry_health_endpoint_returns_structured_error():
    """Typed telemetry-health failures should use the /api/v1 error envelope."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    manager = SimpleNamespace(
        get_telemetry_health=MagicMock(side_effect=RuntimeError("health failed"))
    )
    handler.app_controller = SimpleNamespace(mavlink_data_manager=manager)

    response = await handler.get_telemetry_health()
    payload = json.loads(response.body.decode())

    assert response.status_code == 500
    assert payload["code"] == "telemetry_health_error"
    assert payload["detail"] == "health failed"
    assert payload["path"] == "/api/v1/telemetry/health"
    assert payload["request_id"].startswith("pixeagle-api-")


@pytest.mark.asyncio
async def test_follower_health_marks_running_degraded_commander_as_degraded():
    """Follower health should not treat transient commander failures as fully healthy."""
    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    commander = SimpleNamespace(
        get_status=MagicMock(return_value={
            "exists": True,
            "running": True,
            "health_state": "degraded",
            "consecutive_failures": 1,
        })
    )
    follower = SimpleNamespace(
        get_display_name=MagicMock(return_value="Unit follower"),
        get_control_type=MagicMock(return_value="velocity_body_offboard"),
        validate_current_mode=MagicMock(return_value=True),
    )
    handler.app_controller = SimpleNamespace(
        following_active=True,
        follower=follower,
        offboard_commander=commander,
        setpoint_sender=None,
        px4_interface=SimpleNamespace(),
        tracker=SimpleNamespace(),
        tracking_started=True,
        _follower_state_lock=asyncio.Lock(),
    )

    response = await handler.get_follower_health()
    data = response.body.decode()

    assert '"overall_status":"degraded"' in data.replace(" ", "")
    assert "transient publish failures" in data


@pytest.mark.asyncio
async def test_stop_tracking_external_tracker_disconnects_following_first():
    """External tracker stop requests must not leave PX4 following active."""
    ctrl = object.__new__(AppController)
    ctrl.following_active = True
    ctrl.tracking_started = True
    ctrl.tracker = SimpleNamespace(
        is_external_tracker=True,
        stop_tracking=MagicMock(),
        clear_external_override=MagicMock(),
    )
    ctrl.disconnect_px4 = AsyncMock(side_effect=_set_following_inactive(ctrl))

    result = await ctrl.stop_tracking()

    ctrl.disconnect_px4.assert_awaited_once()
    ctrl.tracker.stop_tracking.assert_not_called()
    assert result["external_tracker"] is True
    assert ctrl.following_active is False
