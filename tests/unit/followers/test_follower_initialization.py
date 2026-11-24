"""Initialization uses declared input requirements, never a synthetic image aim."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes import follower as module
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerDataType, TrackerOutput


@pytest.fixture
def configuration():
    previous = Parameters.get_runtime_config_snapshot()
    root = Path(__file__).resolve().parents[3]
    Parameters.publish_config_mapping(yaml.safe_load((root / 'configs/config_default.yaml').read_text()))
    yield
    Parameters.publish_config_mapping(previous)


IMAGE_MODES = (
    'mc_velocity_chase', 'mc_velocity_ground', 'mc_velocity_distance', 'mc_velocity_position',
    'mc_attitude_rate', 'fw_attitude_rate', 'fw_navigation_chase',
)
ANGLE_MODES = ('gm_velocity_vector', 'gm_velocity_chase')
INVALID = (None, (), (0.,), (0., 0., 0.), ('0', 0.), (True, 0.),
           (float('nan'), 0.), (0., float('inf')), (float('-inf'), 0.))


def output(position=(.25, -.4)):
    return TrackerOutput(TrackerDataType.POSITION_2D, 1., True, position_2d=position)


@pytest.mark.parametrize('mode', IMAGE_MODES)
@pytest.mark.parametrize('target_mode', ['initial', 'center'])
def test_image_aim_uses_typed_measurement_or_declared_center(mode, target_mode):
    aim = module.resolve_initial_target_coords(mode, output(), target_position_mode=target_mode,
                                               desired_aim=[.1, .2])
    assert aim == ((.25, -.4) if target_mode == 'initial' else (.1, .2))


@pytest.mark.parametrize('mode', IMAGE_MODES)
@pytest.mark.parametrize('target_mode', ['initial', 'center'])
@pytest.mark.parametrize('invalid', INVALID)
def test_invalid_image_aim_never_falls_back(mode, target_mode, invalid):
    sample = output()
    sample.position_2d = invalid
    with pytest.raises(ValueError, match='initial_target_coords'):
        module.resolve_initial_target_coords(mode, sample, target_position_mode=target_mode,
                                             desired_aim=invalid if target_mode == 'center' else (0., 0.))


@pytest.mark.parametrize('sample', [None, SimpleNamespace(position_2d=(.1, .2))])
def test_initial_image_aim_requires_typed_output(sample):
    with pytest.raises(ValueError, match='initial_target_coords'):
        module.resolve_initial_target_coords('mc_velocity_chase', sample,
                                             target_position_mode='initial', desired_aim=(0., 0.))


@pytest.mark.parametrize('mode', ANGLE_MODES)
@pytest.mark.parametrize('target_mode', ['initial', 'center'])
def test_angle_only_followers_construct_without_image_aim(mode, target_mode, monkeypatch, configuration):
    sample = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 1., True, angular=(1., 2., 3.))
    aim = module.resolve_initial_target_coords(mode, sample, target_position_mode=target_mode,
                                               desired_aim=None)
    assert aim is None and sample.position_2d is None
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', mode)
    wrapper = module.Follower(SimpleNamespace(current_altitude=50., setpoint_handler=None), aim)
    assert wrapper.initial_target_coords is None
    assert wrapper.follower.initial_target_coords is None
    wrapper.follower.release_session_controls()


@pytest.mark.parametrize('mode', ANGLE_MODES)
def test_legacy_unused_image_pair_is_not_stored_as_angle_evidence(mode, monkeypatch):
    module.FollowerFactory._initialize_registry()
    constructor = Mock()
    constructor.__name__ = 'AngleFollower'
    monkeypatch.setitem(module.FollowerFactory._follower_registry, mode, constructor)
    module.FollowerFactory.create_follower(mode, None, (.2, .3))
    constructor.assert_called_once_with(None, None)


@pytest.mark.parametrize('mode', IMAGE_MODES)
@pytest.mark.parametrize('invalid', INVALID)
@pytest.mark.parametrize('entry', ['wrapper', 'factory'])
def test_all_image_constructor_entries_reject_invalid_aim_before_construction(mode, invalid, entry, monkeypatch):
    monkeypatch.setattr(Parameters, 'FOLLOWER_MODE', mode)
    module.FollowerFactory._initialize_registry()
    constructor = Mock(side_effect=AssertionError('invalid aim reached concrete constructor'))
    monkeypatch.setitem(module.FollowerFactory._follower_registry, mode, constructor)
    with pytest.raises(ValueError, match='initial_target_coords'):
        if entry == 'wrapper':
            module.Follower(None, invalid)
        else:
            module.FollowerFactory.create_follower(mode, None, invalid)
    constructor.assert_not_called()


def test_declared_requirements_drive_resolution_under_an_unrelated_profile_name(monkeypatch):
    info = Mock(return_value={'required_tracker_data': ['GIMBAL_ANGLES']})
    monkeypatch.setattr(SetpointHandler, 'get_profile_info', info)
    assert module.resolve_initial_target_coords('custom_profile', None,
        target_position_mode='initial', desired_aim=None) is None
    info.return_value = {'required_tracker_data': ['POSITION_2D']}
    assert module.resolve_initial_target_coords('custom_profile', output(),
        target_position_mode='initial', desired_aim=None) == (.25, -.4)


def test_image_target_mode_must_be_known():
    with pytest.raises(ValueError, match='target_position_mode'):
        module.resolve_initial_target_coords('mc_velocity_chase', output(),
            target_position_mode='unexpected', desired_aim=(0., 0.))
