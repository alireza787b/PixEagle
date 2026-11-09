"""Body/provider and already aligned world rays share one native FW objective."""

from dataclasses import fields, replace
import math

import pytest

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion, Vector3
from classes.fixed_wing_vector_guidance import FixedWingCommand, FixedWingVectorGuidance
from classes.gimbal_geometry import body_line_of_sight
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.safety_types import AltitudeLimits
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


def _planner(state, *, altitude=True):
    planner = FixedWingVectorGuidance(enable_altitude_control=altitude, geometry_policy=GimbalGuidancePolicy())
    identity = GuidanceSessionIdentity('follow', state.binding, 1)
    planner.begin_phase(identity, state, now=100.0, timeout_s=0.5)
    return planner, dict(identity=identity, requested_eas_m_s=20.0,
                         altitude_limits=AltitudeLimits(5.0, 120.0, 2.0), now=100.0, timeout_s=0.5)


def _assert_same_result(actual, expected):
    for field in fields(FixedWingCommand):
        assert getattr(actual.command, field.name) == pytest.approx(getattr(expected.command, field.name))
    assert actual.geometry_state == expected.geometry_state
    assert actual.limiting_reason == expected.limiting_reason
    assert actual.speed_source == expected.speed_source
    assert actual.observed_eas_m_s == expected.observed_eas_m_s


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('attitude', [
    Quaternion(1.0, 0.0, 0.0, 0.0),
    Quaternion.from_euler(0.35, -0.45, 1.1),
    Quaternion.from_euler(0.2, -1.1, -2.9),
])
@pytest.mark.parametrize('target', [(25.0, 4.0, -3.0), (-25.0, -0.001, 5.0),
                                   (0.0, 0.0, 20.0), (0.0, 0.0, -20.0)])
@pytest.mark.parametrize('altitude', [False, True])
def test_both_mounts_and_full_attitudes_match_independent_ned_target(mount, attitude, target, altitude):
    state = aircraft_state(attitude_body_to_ned=attitude, is_vtol=True, is_tailsitter=True)
    angles = camera_angles_for_world_target((0.0, 0.0, 0.0), target,
                                            (attitude.w, attitude.x, attitude.y, attitude.z), mount)
    body_ray = Vector3(*body_line_of_sight(angles, mount))
    body_planner, arguments = _planner(state, altitude=altitude)
    world_planner, _ = _planner(state, altitude=altitude)
    body = body_planner.calculate(body_ray, state, **arguments)
    world = world_planner.calculate_ned(Vector3(*target).normalized(), state, frame='ned', **arguments)
    _assert_same_result(body, world)


def test_ned_entry_does_not_rotate_using_current_aircraft_attitude(monkeypatch):
    state = aircraft_state(attitude_body_to_ned=Quaternion.from_euler(0.3, -0.4, 1.2))
    planner, arguments = _planner(state)

    def unexpected_rotation(*args):
        raise AssertionError('NED ray must not be rotated again')

    monkeypatch.setattr(Quaternion, 'rotate', unexpected_rotation)
    result = planner.calculate_ned(Vector3(1.0, 0.2, 0.1).normalized(), state, frame='ned', **arguments)
    assert result.command.course_rad == pytest.approx(math.atan2(0.2, 1.0))
    assert result.command.height_rate_m_s == pytest.approx(-20.0 * 0.1 / math.hypot(1.0, 0.2))


def test_body_entry_normalizes_and_rotates_exactly_once(monkeypatch):
    state = aircraft_state(attitude_body_to_ned=Quaternion.from_euler(0.3, -0.4, 1.2))
    planner, arguments = _planner(state)
    original = Quaternion.rotate
    calls = []

    def counted(attitude, ray):
        calls.append(ray)
        return original(attitude, ray)

    monkeypatch.setattr(Quaternion, 'rotate', counted)
    planner.calculate(Vector3(10.0, 2.0, 1.0), state, **arguments)
    assert len(calls) == 1
    assert calls[0].magnitude == pytest.approx(1.0)


@pytest.mark.parametrize('altitude', [False, True])
def test_shared_entry_preserves_rearward_latch_vertical_hysteresis_and_hold_history(altitude):
    state = aircraft_state(attitude_body_to_ned=Quaternion.from_euler(0.3, -0.4, 1.2))
    body_planner, arguments = _planner(state, altitude=altitude)
    world_planner, _ = _planner(state, altitude=altitude)
    attitude = state.attitude_body_to_ned
    inverse = Quaternion(attitude.w, -attitude.x, -attitude.y, -attitude.z)
    changed = replace(state, altitude_amsl_m=555.0)
    for direction in ((-1.0, 0.01, 0.0), (-1.0, -0.01, 0.0),
                      (0.1, 0.0, 1.0), (0.25, 0.0, 1.0), (1.0, 0.1, -0.2)):
        world_ray = Vector3(*direction).normalized()
        body = body_planner.calculate(inverse.rotate(world_ray), changed, **arguments)
        world = world_planner.calculate_ned(world_ray, changed, frame='ned', **arguments)
        _assert_same_result(body, world)
        assert body_planner._rearward_turn_sign == world_planner._rearward_turn_sign
        assert body_planner._vertical == world_planner._vertical
        if not altitude:
            assert body.command.altitude_amsl_m == 550.0


@pytest.mark.parametrize('frame', ['physical_body_frd', 'heading_body', 'enu', '', None])
def test_ned_entry_rejects_other_frames_before_mutating_guidance_history(frame):
    state = aircraft_state()
    planner, arguments = _planner(state)
    with pytest.raises(ValueError, match='guidance_ray_frame_invalid'):
        planner.calculate_ned(Vector3(1.0, 0.0, 0.0), state, frame=frame, **arguments)
    assert planner._last_course is None and planner._rearward_turn_sign is None


@pytest.mark.parametrize('ray', [Vector3(0.0, 0.0, 0.0), Vector3(2.0, 0.0, 0.0),
                                Vector3(1e308, 1e308, 1e308), (1.0, 0.0, 0.0), math.nan, math.inf])
def test_ned_entry_requires_a_finite_unit_bearing_without_normalizing_invalid_input(ray):
    state = aircraft_state()
    planner, arguments = _planner(state)
    with pytest.raises(ValueError, match='guidance_ray_not_unit'):
        planner.calculate_ned(ray, state, frame='ned', **arguments)
    assert planner._last_course is None and planner._rearward_turn_sign is None


@pytest.mark.parametrize('relative,down,speed,expected,reason', [
    (6.0, 0.2, 20.0, 20.0, 'altitude_lower_warning_band'),
    (118.0, -0.2, 20.0, 20.0, 'altitude_upper_warning_band'),
    (50.0, 0.0, 8.0, 12.0, 'native_minimum_speed'),
    (50.0, 0.0, 40.0, 30.0, 'native_maximum_speed'),
])
def test_ned_entry_uses_existing_relative_altitude_and_native_speed_envelope(relative, down, speed, expected, reason):
    state = aircraft_state(relative_altitude_m=relative)
    planner, arguments = _planner(state)
    result = planner.calculate_ned(Vector3(1.0, 0.0, down).normalized(), state, frame='ned',
                                   **{**arguments, 'requested_eas_m_s': speed})
    assert result.command.height_rate_m_s == 0.0
    assert result.command.equivalent_airspeed_m_s == expected
    assert result.limiting_reason == reason


@pytest.mark.parametrize('changes,reason', [
    ({'relative_altitude_m': 4.0}, 'altitude_hard_limit'),
    ({'observed_at_monotonic_s': 98.0}, 'aircraft_state_stale'),
    ({'phase': AirframePhase.UNKNOWN}, 'fixed_wing_phase_required'),
    ({'altitude_reference_generation': 1}, 'altitude_reference_changed'),
])
def test_ned_entry_keeps_existing_state_and_reference_guards(changes, reason):
    state = aircraft_state()
    planner, arguments = _planner(state)
    with pytest.raises(ValueError, match=reason):
        planner.calculate_ned(Vector3(1.0, 0.0, 0.0), replace(state, **changes), frame='ned', **arguments)
