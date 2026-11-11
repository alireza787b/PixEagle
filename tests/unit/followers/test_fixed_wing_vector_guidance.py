from dataclasses import replace
import math

import pytest

from classes.aircraft_state import AirframePhase, AirspeedObservation, GuidanceSessionIdentity, Quaternion, Vector3
from classes.fixed_wing_vector_guidance import FixedWingVectorGuidance, FixedWingCommand, UpperSpeedPolicy
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.safety_types import AltitudeLimits
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def calculate(ray, *, planner=None, state=None, **kwargs):
    planner = planner or FixedWingVectorGuidance(enable_altitude_control=True,
                                                geometry_policy=GimbalGuidancePolicy())
    state = state or aircraft_state()
    identity = kwargs.pop("identity", GuidanceSessionIdentity("follow-a", state.binding, 1))
    if planner._identity is None and state.phase is AirframePhase.FIXED_WING:
        planner.begin_phase(identity, state, now=100, timeout_s=.5)
    return planner.calculate(ray, state, identity=identity, requested_eas_m_s=kwargs.pop("speed", 20),
                             altitude_limits=kwargs.pop("limits", AltitudeLimits(5, 120, 2)),
                             now=100.0, timeout_s=.5, **kwargs)


def test_los_controls_course_and_world_path_not_euler_pitch_or_thrust():
    result = calculate(Vector3(10, 10, 1))
    assert result.command.course_rad == pytest.approx(math.pi / 4)
    assert result.command.height_rate_m_s == pytest.approx(-math.sqrt(2))
    assert result.command.equivalent_airspeed_m_s == 20
    assert result.command.altitude_amsl_m is None
    assert "thrust" not in result.command.wire_payload()


def test_disabled_altitude_holds_engagement_amsl_not_zero_pitch():
    planner = FixedWingVectorGuidance(enable_altitude_control=False, geometry_policy=GimbalGuidancePolicy())
    first = calculate(Vector3(1, 0, 1), planner=planner)
    second = calculate(Vector3(1, 0, -1), planner=planner, state=aircraft_state(altitude_amsl_m=555))
    assert first.command.altitude_amsl_m == second.command.altitude_amsl_m == 550
    assert first.command.height_rate_m_s is None


@pytest.mark.parametrize("down,expected", [(1, -5), (-1, 4)])
def test_vertical_ray_keeps_course_and_viable_forward_airspeed(down, expected):
    command = calculate(Vector3(0, 0, down)).command
    assert command.course_rad == 0
    assert command.equivalent_airspeed_m_s == 20
    assert command.height_rate_m_s == expected


def test_rearward_noise_does_not_reverse_turn_direction():
    planner = FixedWingVectorGuidance(enable_altitude_control=True, geometry_policy=GimbalGuidancePolicy())
    commands = [calculate(Vector3(-1, y, 0), planner=planner).command for y in [.001, -.001, .002, -.002]]
    assert all(0 < command.course_rad < math.pi for command in commands)
    assert all(command.equivalent_airspeed_m_s == 20 for command in commands)


def test_startup_uses_valid_low_airspeed_not_a_high_groundspeed_proxy():
    state = aircraft_state(airspeed=AirspeedObservation("sensor", 8, 9, 100, True))
    assert FixedWingVectorGuidance.startup_speed(state, now=100, timeout_s=.5) == (12, "sensor")
    result = calculate(Vector3(1, 0, 0), state=state)
    assert result.observed_eas_m_s == 8
    assert result.speed_source == "sensor"


def test_sensorless_startup_uses_trim_reference_without_inventing_observation():
    state = aircraft_state(airspeed=AirspeedObservation("unavailable", None, None, 100, False))
    assert FixedWingVectorGuidance.startup_speed(state, now=100, timeout_s=.5) == (18, "px4_trim_reference")
    result = calculate(Vector3(1, 0, 0), state=state)
    assert result.observed_eas_m_s is None
    assert result.speed_source == "native_airspeedless"


def test_wind_based_estimate_is_used_without_relabelling_it_a_sensor():
    state = aircraft_state(airspeed=AirspeedObservation("ground_minus_wind", 22, 23, 100, True))
    assert FixedWingVectorGuidance.startup_speed(state, now=100, timeout_s=.5) == (22, "ground_minus_wind")


def test_unrestricted_requests_require_verified_native_capability_and_are_finite():
    limited = calculate(Vector3(1, 0, 0), speed=40)
    assert limited.command.equivalent_airspeed_m_s == 30
    assert limited.limiting_reason == "native_maximum_speed"
    unsupported = FixedWingVectorGuidance(enable_altitude_control=True, geometry_policy=GimbalGuidancePolicy(),
                                         policy=FixedWingGuidancePolicy(UpperSpeedPolicy.NO_UPPER_SPEED_BOUND, .15))
    assert unsupported.policy == FixedWingGuidancePolicy()
    assert unsupported.policy_reason == "unrestricted_speed_not_supported"
    assert calculate(Vector3(1, 0, 0), speed=20., planner=unsupported).limiting_reason == "unrestricted_speed_not_supported"
    planner = FixedWingVectorGuidance(enable_altitude_control=True, geometry_policy=GimbalGuidancePolicy(),
                                     policy=FixedWingGuidancePolicy(UpperSpeedPolicy.NO_UPPER_SPEED_BOUND),
                                     unrestricted_capability=True)
    result = calculate(Vector3(1, 0, 0), speed=40, planner=planner)
    assert result.command.equivalent_airspeed_m_s == 40
    with pytest.raises(ValueError):
        calculate(Vector3(1, 0, 0), speed=math.inf, planner=planner)


@pytest.mark.parametrize("speed", [0, -1])
def test_mc_zero_never_becomes_fw_speed(speed):
    with pytest.raises(ValueError, match="not_positive"):
        calculate(Vector3(1, 0, 0), speed=speed)


def test_native_load_dependent_minimum_limits_command_without_rewriting_request():
    state = aircraft_state()
    loaded = replace(state, fixed_wing_envelope=replace(state.fixed_wing_envelope, minimum_eas_m_s=24))
    limited = calculate(Vector3(1, 0, 0), state=loaded, speed=20)
    assert limited.command.equivalent_airspeed_m_s == 24
    assert limited.limiting_reason == "native_minimum_speed"
    assert calculate(Vector3(1, 0, 0), state=state, speed=20).command.equivalent_airspeed_m_s == 20


def test_altitude_floor_suppresses_descent_without_increasing_speed():
    result = calculate(Vector3(1, 0, 1), state=aircraft_state(relative_altitude_m=6))
    assert result.command.height_rate_m_s == 0
    assert result.command.equivalent_airspeed_m_s == 20
    assert result.limiting_reason == "altitude_lower_warning_band"
    with pytest.raises(ValueError, match="altitude_hard_limit"):
        calculate(Vector3(1, 0, 0), state=aircraft_state(relative_altitude_m=4))


def test_physical_frame_rotation_controls_the_world_path():
    state = aircraft_state(attitude_body_to_ned=Quaternion(math.sqrt(.5), 0, math.sqrt(.5), 0))
    result = calculate(Vector3(1, 0, 0), state=state)
    assert result.command.height_rate_m_s == 4
    assert result.geometry_state == "vertical_path_limited"


@pytest.mark.parametrize("changes,error", [
    ({"observed_at_monotonic_s": 98}, "stale"),
    ({"rescue_active": True}, "rescue"),
    ({"phase": AirframePhase.UNKNOWN}, "phase_required"),
    ({"fixed_wing_envelope": None}, "envelope_unavailable"),
])
def test_invalid_aircraft_state_refuses_guidance(changes, error):
    with pytest.raises(ValueError, match=error):
        calculate(Vector3(1, 0, 0), state=aircraft_state(**changes))


def test_command_contract_rejects_ambiguous_vertical_and_nonfinite_fields():
    with pytest.raises(ValueError, match="vertical_contract"):
        FixedWingCommand(0, 20, 1, 550)
    with pytest.raises(ValueError, match="vertical_contract"):
        FixedWingCommand(0, 20, None, None)
    with pytest.raises(ValueError, match="course_invalid"):
        FixedWingCommand(math.nan, 20, 1, None)


@pytest.mark.parametrize('height_rate,altitude,variant', [(1, None, 'height_rate'), (None, 550, 'altitude')])
def test_command_field_variants_match_complete_native_intents(height_rate, altitude, variant):
    identity = GuidanceSessionIdentity('follow-a', aircraft_state().binding, 1)
    command = FixedWingCommand(.5, 20, height_rate, altitude)
    intent = command.intent(identity, profile_name='fixture_native_fw', source='test')
    assert set(intent.fields) == FixedWingCommand.field_variants()[variant]
    assert FixedWingCommand.from_intent(intent) == command


def test_new_fw_phase_recaptures_altitude_and_drops_old_turn_history():
    planner = FixedWingVectorGuidance(enable_altitude_control=False, geometry_policy=GimbalGuidancePolicy())
    calculate(Vector3(-1, 0.1, 0), planner=planner)
    next_state = aircraft_state(altitude_amsl_m=575)
    next_identity = GuidanceSessionIdentity("follow-a", next_state.binding, 3)
    planner.begin_phase(next_identity, next_state, now=100, timeout_s=.5)
    assert planner._rearward_turn_sign is None
    result = calculate(Vector3(1, 0, 1), planner=planner, state=next_state, identity=next_identity)
    assert result.command.altitude_amsl_m == 575
    with pytest.raises(ValueError, match="phase_binding_changed"):
        calculate(Vector3(1, 0, 0), planner=planner)


def test_altitude_reference_reset_invalidates_a_retained_hold_target():
    planner = FixedWingVectorGuidance(enable_altitude_control=False, geometry_policy=GimbalGuidancePolicy())
    calculate(Vector3(1, 0, 0), planner=planner)
    with pytest.raises(ValueError, match="altitude_reference_changed"):
        calculate(Vector3(1, 0, 0), planner=planner, state=aircraft_state(altitude_reference_generation=1))
    with pytest.raises(ValueError, match="hold_target_outside_limits"):
        calculate(Vector3(1, 0, 0), planner=planner, state=aircraft_state(altitude_amsl_m=620))


def test_native_vertical_response_begins_leveling_before_reaching_warning_band():
    state = aircraft_state(relative_altitude_m=20., velocity_ned_m_s=Vector3(20., 0., 5.))
    result = calculate(Vector3(1, 0, .25), state=state)
    assert result.command.height_rate_m_s == 0.
    assert result.limiting_reason == "altitude_descent_response_limited"
    assert result.command.equivalent_airspeed_m_s == 20.
    state = replace(state, relative_altitude_m=110., velocity_ned_m_s=Vector3(20., 0., -4.))
    result = calculate(Vector3(1, 0, -.25), state=state)
    assert result.command.height_rate_m_s == 0.
    assert result.limiting_reason == "altitude_climb_response_limited"
