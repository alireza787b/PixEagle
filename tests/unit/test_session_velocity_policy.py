"""One explicit permission controls existing session velocity overrides."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity
from classes.airframe_session_controls import AirframeSessionControls
from classes.config_validator import normalize_safety_config
from classes.followers.base_follower import BaseFollower
from classes.safety_manager import SafetyManager
from classes.setpoint_handler import SetpointHandler
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


@pytest.fixture
def config():
    from pathlib import Path
    return yaml.safe_load((Path(__file__).resolve().parents[2] / 'configs/config_default.yaml').read_text())


def test_public_factory_keeps_position_altitude_hold_and_conservative_authority(config):
    assert config['Follower']['FOLLOWER_MODE'] == 'mc_velocity_position'
    assert config['Follower']['General']['ENABLE_ALTITUDE_CONTROL'] is False
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert config['Safety']['ALLOW_SESSION_VELOCITY_OVERRIDE'] is False
    limits = config['Safety']['GlobalLimits']
    assert (limits['MIN_ALTITUDE'], limits['MAX_ALTITUDE']) == (5., 100.)
    assert limits['ALTITUDE_SAFETY_ENABLED'] is True
    assert (limits['MAX_VELOCITY'], limits['MAX_VELOCITY_FORWARD']) == (4., 4.)
    assert (limits['MAX_VELOCITY_LATERAL'], limits['MAX_VELOCITY_VERTICAL']) == (.5, .5)
    assert config['MC_VELOCITY_CHASE']['REQUESTED_SPEED'] == .5
    assert config['FixedWingGuidance']['UPPER_SPEED_POLICY'] == 'px4_configured_max'
    assert all(not values.get('ENABLE_ALTITUDE_CONTROL', False)
        for values in config['Follower']['FollowerOverrides'].values())


@pytest.mark.parametrize('allowed', [False, True])
def test_factory_and_expert_controls_use_one_policy_including_phase_binding(config, allowed):
    config['Safety']['ALLOW_SESSION_VELOCITY_OVERRIDE'] = allowed
    manager = SafetyManager()
    manager.load_from_config(config)
    follower = SimpleNamespace(safety_manager=manager, setpoint_handler=SetpointHandler('gm_velocity_vector'))
    control = BaseFollower._create_translation_speed_controls(follower, 6., startup=6.)['requested_speed']
    state = aircraft_state(phase=AirframePhase.MULTICOPTER)
    identity = GuidanceSessionIdentity('session-a', state.binding, 0)
    owner = AirframeSessionControls.from_multicopter_control(identity, control)
    owner.enter_phase(identity, state, now=state.observed_at_monotonic_s, timeout_s=.5)
    current = owner.current_control
    assert current.maximum == (None if allowed else 6.)
    assert not current.override_active
    if allowed:
        owner.update(10., identity=identity, expected_revision=current.revision)
        assert owner.current_control.value == 10. and owner.current_control.override_active
        owner.update(None, identity=identity, expected_revision=owner.current_control.revision)
        assert owner.current_control.value == 6. and not owner.current_control.override_active
    else:
        with pytest.raises(ValueError, match='out_of_range'):
            owner.update(10., identity=identity, expected_revision=current.revision)
        assert owner.current_control.value == 6.
        with pytest.raises(ValueError, match='override_disabled'):
            manager.bind_session_velocity('GM_VELOCITY_VECTOR', follower, lambda: 10.)


def test_missing_legacy_permission_remains_visible_and_does_not_rewrite_saved_values(config):
    del config['Safety']['ALLOW_SESSION_VELOCITY_OVERRIDE']
    before = deepcopy(config)
    normalized = normalize_safety_config(config, require_safety=True)
    assert 'ALLOW_SESSION_VELOCITY_OVERRIDE' not in normalized['Safety']
    manager = SafetyManager()
    manager.load_from_config(normalized)
    assert manager.allows_session_velocity_override()
    assert config == before


@pytest.mark.parametrize('invalid', [None, 'true', 1, [], {}])
def test_malformed_permission_cannot_change_a_published_policy(config, invalid):
    manager = SafetyManager()
    manager.load_from_config(config)
    assert not manager.allows_session_velocity_override()
    config['Safety']['ALLOW_SESSION_VELOCITY_OVERRIDE'] = invalid
    with pytest.raises(ValueError):
        normalize_safety_config(config, require_safety=True)
    with pytest.raises(ValueError):
        manager.load_from_config(config)
    assert not manager.allows_session_velocity_override()
