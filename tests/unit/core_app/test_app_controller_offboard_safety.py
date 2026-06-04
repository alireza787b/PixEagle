"""AppController Offboard safety regression tests."""

import asyncio
import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.app_controller import AppController
from classes.command_intent import CommandIntent
from classes.offboard_commander import OffboardCommander
from classes.fastapi_handler import FastAPIHandler
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
        connect_px4=AsyncMock(return_value={
            "steps": ["initial setpoint sent"],
            "errors": ["OffboardCommander configuration validation failed"],
        }),
    )

    result = await handler.start_offboard_mode()

    assert result["status"] == "failure"
    assert "OffboardCommander configuration validation failed" in result["error"]
    assert result["details"]["final_state"] == "inactive"


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
