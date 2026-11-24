"""Both application Start paths resolve the same declared tracker input contract."""

import asyncio
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from classes.app_controller import AppController
from classes.command_preview import CommandPreviewController
from classes.follower import FollowerFactory
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.aircraft_state import AircraftKind
from tests.fixtures.following_observation import bind_controller_source, bind_image_source
from tests.unit.core_app.test_native_follow_application import app  # noqa: F401


def angles(ctrl):
    sample = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True,
                           angular=(1., 2., 3.), raw_data={'usable_for_following': True})
    ctrl.tracker = SimpleNamespace(normalized_center=None)
    ctrl.get_tracker_output = lambda: sample
    bind_controller_source(ctrl, sample)
    return sample


@pytest.mark.parametrize('mode', ['gm_velocity_vector', 'gm_velocity_chase'])
@pytest.mark.parametrize('target_mode', ['initial', 'center'])
async def test_live_start_passes_no_image_aim_for_angle_only_input(app, monkeypatch, mode, target_mode):
    ctrl = app.ctrl
    sample = angles(ctrl)
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', mode)
    monkeypatch.setattr(Parameters, 'TARGET_POSITION_MODE', target_mode)
    monkeypatch.setattr(Parameters, 'DESIRE_AIM', None)
    app.follower_factory.get_mode_info.return_value = FollowerFactory.get_follower_info(mode)
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    ctrl.px4_interface.start_offboard_mode.return_value = {'executed': True, 'errors': []}
    result = await ctrl._connect_px4_on_flight_loop()
    assert not result['errors']
    assert ctrl.following_active
    assert app.follower_factory.call_args.args[1] is None
    assert sample.position_2d is None
    ctrl.px4_interface.start_offboard_mode.assert_awaited_once()


@pytest.mark.parametrize('target_mode', ['initial', 'center'])
async def test_live_image_start_uses_typed_output_not_legacy_center(app, monkeypatch, target_mode):
    ctrl = app.ctrl
    sample = bind_image_source(ctrl)
    sample.position_2d = (.3, -.4)
    ctrl.tracker.normalized_center = None
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', 'mc_velocity_position')
    monkeypatch.setattr(Parameters, 'TARGET_POSITION_MODE', target_mode)
    monkeypatch.setattr(Parameters, 'DESIRE_AIM', [.1, .2])
    app.follower_factory.get_mode_info.return_value = FollowerFactory.get_follower_info('mc_velocity_position')
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    ctrl.px4_interface.start_offboard_mode.return_value = {'executed': True, 'errors': []}
    result = await ctrl._connect_px4_on_flight_loop()
    assert not result['errors']
    assert app.follower_factory.call_args.args[1] == ((.3, -.4) if target_mode == 'initial' else (.1, .2))


@pytest.mark.parametrize('target_mode', ['initial', 'center'])
@pytest.mark.parametrize('invalid', [None, (float('nan'), 0.), (float('inf'), 0.), (True, 0.)])
@pytest.mark.parametrize('preview', [False, True])
async def test_invalid_image_start_cannot_construct_or_acquire(app, monkeypatch, target_mode, invalid, preview):
    ctrl = app.ctrl
    sample = bind_image_source(ctrl)
    sample.position_2d = invalid if target_mode == 'initial' else (.1, .2)
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', 'mc_velocity_position')
    monkeypatch.setattr(Parameters, 'TARGET_POSITION_MODE', target_mode)
    monkeypatch.setattr(Parameters, 'DESIRE_AIM', invalid if target_mode == 'center' else (0., 0.))
    app.follower_factory.get_mode_info.return_value = FollowerFactory.get_follower_info('mc_velocity_position')
    ctrl.px4_interface.get_aircraft_kind.return_value = AircraftKind.MULTICOPTER
    ctrl._get_command_preview_readiness = Mock(return_value={'ready': True})
    result = await (ctrl._connect_command_preview_on_flight_loop() if preview
                    else ctrl._connect_px4_on_flight_loop())
    assert any('initial_target_coords' in error for error in result['errors'])
    assert not ctrl.following_active
    app.follower_factory.assert_not_called()
    ctrl.px4_interface.start_offboard_mode.assert_not_called()
    app.f.client.engage.assert_not_called()


@pytest.mark.parametrize('mode', ['gm_velocity_vector', 'gm_velocity_chase', 'mc_velocity_position'])
@pytest.mark.parametrize('target_mode', ['initial', 'center'])
async def test_preview_start_constructs_real_follower_with_only_its_declared_aim(monkeypatch, mode, target_mode):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    Parameters.publish_config_mapping(defaults)
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', mode)
    monkeypatch.setattr(Parameters, 'TARGET_POSITION_MODE', target_mode)
    image_consumer = mode == 'mc_velocity_position'
    monkeypatch.setattr(Parameters, 'DESIRE_AIM', [.1, .2] if image_consumer else None)
    ctrl = AppController.__new__(AppController)
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl.following_active = False
    ctrl.follower = ctrl.offboard_commander = ctrl.setpoint_sender = None
    ctrl.px4_interface = SimpleNamespace(setpoint_handler=None)
    ctrl._active_following_controller = ctrl.px4_interface
    ctrl.telemetry_handler = SimpleNamespace(follower=None)
    ctrl._apply_pending_follower_config = AsyncMock(return_value={'applied_count': 0})
    ctrl._get_command_preview_readiness = Mock(return_value={'ready': True})
    ctrl._ensure_continuity_watchdog = Mock()
    if image_consumer:
        ctrl.tracker = SimpleNamespace(normalized_center=None)
        sample = bind_image_source(ctrl)
        sample.position_2d = (.3, -.4)
    else:
        sample = angles(ctrl)
    try:
        result = await ctrl._connect_command_preview_on_flight_loop()
        assert not result['errors']
        assert ctrl.following_active and result['commands_sent_to_px4'] is False
        assert isinstance(ctrl._active_following_controller, CommandPreviewController)
        expected = ((.3, -.4) if target_mode == 'initial' else (.1, .2)) if image_consumer else None
        assert ctrl.follower.initial_target_coords == expected
        assert ctrl.follower.follower.initial_target_coords == expected
        if not image_consumer:
            assert sample.position_2d is None
    finally:
        if ctrl.offboard_commander is not None:
            await ctrl.offboard_commander.stop()
        if ctrl.follower is not None:
            ctrl.follower.follower.release_session_controls()
        Parameters.publish_config_mapping(previous)
