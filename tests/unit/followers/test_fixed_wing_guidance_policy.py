from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from classes.aircraft_state import AircraftLayout, AirframePhase
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.guidance_phase_session import GuidancePhaseSession
from tests.unit.followers.test_guidance_phase_session import session
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def test_missing_saved_policy_preserves_native_defaults():
    assert FixedWingGuidancePolicy.from_mapping(None) == FixedWingGuidancePolicy()
    assert FixedWingGuidancePolicy.from_mapping({}) == FixedWingGuidancePolicy()
    assert FixedWingGuidancePolicy().min_dive_throttle is None
    assert FixedWingGuidancePolicy().resolve_native(False) == FixedWingGuidancePolicy()


@pytest.mark.parametrize("floor", [None, 0., .1, 1.])
def test_finite_dive_floor_is_shared_configuration_not_a_second_thrust_controller(floor):
    policy = FixedWingGuidancePolicy.from_mapping({"UPPER_SPEED_POLICY": "no_upper_speed_bound",
                                                 "MIN_DIVE_THROTTLE": floor})
    assert policy.min_dive_throttle == floor
    assert policy.resolve_native(False) == FixedWingGuidancePolicy()
    assert policy.resolve_native(True) is policy


@pytest.mark.parametrize("raw", [
    [], True, {"UNKNOWN": 1}, {"UPPER_SPEED_POLICY": "uncontrolled"},
    {"UPPER_SPEED_POLICY": True}, {"MIN_DIVE_THROTTLE": True}, {"MIN_DIVE_THROTTLE": "0.2"},
    {"MIN_DIVE_THROTTLE": float('nan')}, {"MIN_DIVE_THROTTLE": float('inf')},
    {"MIN_DIVE_THROTTLE": -.01}, {"MIN_DIVE_THROTTLE": 1.01},
])
def test_invalid_policy_cannot_reach_the_flight_owner(raw):
    with pytest.raises(ValueError):
        FixedWingGuidancePolicy.from_mapping(raw)


def test_public_defaults_preserve_beginner_mc_workflow_and_native_fw_envelope():
    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((root / 'configs/config_default.yaml').read_text())
    policy = FixedWingGuidancePolicy.from_mapping(config['FixedWingGuidance'])
    assert policy.upper_speed_policy is UpperSpeedPolicy.PX4_CONFIGURED_MAX
    assert policy.min_dive_throttle is None
    assert config['Follower']['AIRFRAME_LAYOUT'] == 'AUTO'
    assert config['Follower']['FOLLOWER_MODE'] == 'mc_velocity_position'
    assert config['Follower']['General']['ENABLE_ALTITUDE_CONTROL'] is False
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert config['VideoSource']['VIDEO_SOURCE_TYPE'] == 'VIDEO_FILE'
    assert config['Tracking']['DEFAULT_TRACKING_ALGORITHM'] == 'CSRT'


@pytest.mark.parametrize("phase,vtol,tail,expected", [
    (AirframePhase.MULTICOPTER, False, False, AircraftLayout.MULTICOPTER),
    (AirframePhase.FIXED_WING, False, False, AircraftLayout.FIXED_WING),
    (AirframePhase.MULTICOPTER, True, False, AircraftLayout.VTOL),
    (AirframePhase.FIXED_WING, True, False, AircraftLayout.VTOL),
    (AirframePhase.VTOL_TRANSITION, True, False, AircraftLayout.VTOL),
    (AirframePhase.MULTICOPTER, True, True, AircraftLayout.VTOL_TAILSITTER),
    (AirframePhase.FIXED_WING, True, True, AircraftLayout.VTOL_TAILSITTER),
    (AirframePhase.VTOL_TRANSITION, True, True, AircraftLayout.VTOL_TAILSITTER),
])
def test_layout_verifies_installation_without_forcing_a_phase(phase, vtol, tail, expected):
    state = aircraft_state(phase=phase, is_vtol=vtol, is_tailsitter=tail)
    for layout in AircraftLayout:
        assert layout.matches(state) is (layout in {AircraftLayout.AUTO, expected})
    owner = session()
    owner.expected_layout = expected
    result = owner.observe(state, now=100., owner_confirmed=True, target_confirmed=True)
    if phase is AirframePhase.VTOL_TRANSITION:
        assert result.phase is AirframePhase.UNKNOWN
        assert result.reason == "aircraft_transition_observed"
    else:
        assert result.phase is phase
    assert not result.pursuit_allowed


def test_incorrect_explicit_layout_cannot_override_observed_tailsitter_state():
    owner = session()
    owner.expected_layout = AircraftLayout.FIXED_WING
    state = aircraft_state(is_vtol=True, is_tailsitter=True)
    result = owner.observe(state, now=100., owner_confirmed=True, target_confirmed=True)
    assert result.reason == 'aircraft_layout_mismatch'
    result = owner.observe(replace(state, sequence=2, is_vtol=False, is_tailsitter=False),
                           now=100.1, owner_confirmed=True, target_confirmed=True)
    assert not result.pursuit_allowed
    assert result.reason == 'aircraft_layout_mismatch'


def test_layout_configuration_requires_an_explicit_known_enum():
    previous = session()
    with pytest.raises(ValueError, match='aircraft_layout_invalid'):
        GuidancePhaseSession(previous.identity, previous.capabilities, confirmation_s=.5,
                             observation_timeout_s=.75, expected_layout='FIXED_WING')
