from dataclasses import replace
import math

import pytest

from classes.aircraft_state import AirframePhase, AirspeedObservation, GuidanceSessionIdentity, Quaternion, Vector3
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy
from classes.fixed_wing_mavlink_control import FixedWingMavlinkTuning, FixedWingMavlinkVectorControl
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.safety_types import AltitudeLimits
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


def tuning(**changes):
    return FixedWingMavlinkTuning(**(dict(
        lookahead_m=50., speed_gain_per_m_s=.05, throttle_min=.1, throttle_trim=.6,
        throttle_max=1., pitch_min_rad=math.radians(-30), pitch_max_rad=math.radians(30),
        altitude_time_constant_s=5.,
    ) | changes))


def setup(*, state=None, altitude=True, unbounded=False, dive_throttle=None):
    state = state or aircraft_state(relative_altitude_m=1000., altitude_amsl_m=1500.)
    identity = GuidanceSessionIdentity("follow-a", state.binding, 1)
    controller = FixedWingMavlinkVectorControl(
        tuning=tuning(), geometry=GimbalGuidancePolicy().geometry,
        policy=FixedWingGuidancePolicy(UpperSpeedPolicy.NO_UPPER_SPEED_BOUND if unbounded
                                      else UpperSpeedPolicy.PX4_CONFIGURED_MAX, dive_throttle),
        enable_altitude_control=altitude,
    )
    controller.begin(identity, state, now=100., timeout_s=.5)
    return controller, identity, state


def calculate(controller, identity, state, ray=Vector3(1, 0, 0), speed=20., limits=AltitudeLimits(3, None, 2)):
    return controller.calculate(ray, state, identity=identity, requested_speed_m_s=speed,
                                altitude_limits=limits, now=100., timeout_s=.5)


def test_normal_speed_ceiling_and_unconstrained_request_are_separate_from_observed_speed():
    for unbounded, expected in [(False, 30.), (True, 60.)]:
        controller, identity, state = setup(unbounded=unbounded)
        result = calculate(controller, identity, state, speed=60.)
        assert result.requested_speed_m_s == 60.
        assert result.effective_speed_m_s == expected
        assert result.observed_speed_m_s == 20.
        assert result.thrust == 1.


def test_expert_dive_removes_pitch_and_sink_soft_limits_with_the_same_target_ray():
    ray = Vector3(1, 0, math.sqrt(3))
    normal, identity, state = setup()
    expert, _, _ = setup(unbounded=True)
    assert abs(calculate(normal, identity, state, ray).pitch_deg) < 30.
    assert calculate(expert, identity, state, ray).pitch_deg == pytest.approx(-60.)


def test_expert_near_vertical_ray_does_not_reintroduce_the_normal_sink_limit():
    ray = Vector3(.1, 0., math.sqrt(.99))
    normal, identity, state = setup()
    expert, _, _ = setup(unbounded=True)
    assert calculate(normal, identity, state, ray).pitch_deg > -30.
    result = calculate(expert, identity, state, ray)
    assert result.pitch_deg == pytest.approx(-math.degrees(math.acos(.1)))
    assert abs(result.roll_deg) < 1e-10  # Keep the last course; never FW stationary yaw.


@pytest.mark.parametrize("unbounded", [False, True])
def test_altitude_disabled_holds_engagement_altitude_independently_of_ray(unbounded):
    controller, identity, state = setup(altitude=False, unbounded=unbounded)
    state = replace(state, altitude_amsl_m=1510., relative_altitude_m=1010.)
    down = calculate(controller, identity, state, Vector3(1, 0, 1))
    up = calculate(controller, identity, state, Vector3(1, 0, -1))
    assert down.pitch_deg == up.pitch_deg < 0.


def test_unconstrained_dive_retains_the_same_minimum_altitude_guard():
    controller, identity, _ = setup(unbounded=True)
    low = aircraft_state(relative_altitude_m=4., altitude_amsl_m=504.)
    result = calculate(controller, identity, low, Vector3(1, 0, 1))
    assert result.pitch_deg == 0.
    assert result.limiting_reason == "altitude_lower_warning_band"


@pytest.mark.parametrize("unbounded", [False, True])
def test_speed_deficit_suppresses_climb_and_requests_available_throttle(unbounded):
    state = aircraft_state(airspeed=AirspeedObservation("sensor", 10., 10., 100., True))
    controller, identity, _ = setup(state=state, unbounded=unbounded)
    result = calculate(controller, identity, state, Vector3(1, 0, -1))
    assert result.pitch_deg == 0.
    assert result.thrust == 1.
    assert result.effective_speed_m_s >= state.fixed_wing_envelope.minimum_eas_m_s
    assert result.limiting_reason == "underspeed_recovery"


def test_climb_returns_continuously_between_native_minimum_and_trim():
    controller, identity, state = setup(unbounded=True)
    pitch = []
    for speed in [12., 13., 15., 18.]:
        observation = AirspeedObservation("sensor", speed, speed, 100., True)
        pitch.append(calculate(controller, identity, replace(state, airspeed=observation), Vector3(1, 0, -1)).pitch_deg)
    assert pitch[0] == 0.
    assert pitch == sorted(pitch)
    assert pitch[-1] == pytest.approx(45.)


def test_sensorless_feedback_is_a_named_proxy_and_never_an_airspeed_measurement():
    state = aircraft_state(airspeed=AirspeedObservation("unavailable", None, None, 100., False),
                           velocity_ned_m_s=Vector3(12., 0., 5.))
    controller, identity, _ = setup(state=state)
    result = calculate(controller, identity, state)
    assert result.speed_basis == "ground_speed_proxy"
    assert result.observed_speed_m_s == 13.


def test_dive_throttle_floor_is_respected_without_exceeding_actuator_limits():
    controller, identity, state = setup(unbounded=True, dive_throttle=.8)
    result = calculate(controller, identity, state, Vector3(1, 0, 1), speed=12.)
    assert result.thrust == .8


def test_tailsitter_and_native_fw_have_identical_navigation_requests():
    forward = Quaternion.from_euler(.1, .15, .3)
    state = aircraft_state(attitude_body_to_ned=forward, navigation_heading_rad=.3)
    tail = replace(state, is_vtol=True, is_tailsitter=True,
                   attitude_body_to_ned=forward.compose(Quaternion.from_euler(0., -math.pi / 2, 0.)))
    first, identity, _ = setup(state=state)
    second, _, _ = setup(state=tail)
    a = calculate(first, identity, state, Vector3(1, .3, .2))
    b = calculate(second, identity, tail, Vector3(1, .3, .2))
    assert a.roll_deg == pytest.approx(b.roll_deg)
    assert a.pitch_deg == pytest.approx(b.pitch_deg)
    assert a.yaw_deg == pytest.approx(b.yaw_deg)


def test_aligned_ground_course_preserves_crab_heading():
    state = aircraft_state(navigation_heading_rad=.25)
    controller, identity, _ = setup(state=state)
    result = calculate(controller, identity, state)
    assert result.roll_deg == pytest.approx(0.)
    assert result.yaw_deg == pytest.approx(math.degrees(.25))


def test_rearward_noise_keeps_turn_direction():
    controller, identity, state = setup()
    requests = [calculate(controller, identity, state, Vector3(-1, y, 0)) for y in [.01, -.01, .02, -.02]]
    assert all(r.roll_deg > 0 and r.geometry_state == "coordinated_turn" for r in requests)


@pytest.mark.parametrize("value", [0, -1., True, math.inf, math.nan])
def test_invalid_requested_speed_never_produces_commands(value):
    controller, identity, state = setup()
    with pytest.raises(ValueError):
        calculate(controller, identity, state, speed=value)


def test_very_large_finite_request_has_no_invented_upper_speed_ceiling():
    controller, identity, state = setup(unbounded=True)
    result = calculate(controller, identity, state, speed=1e100)
    assert result.effective_speed_m_s == 1e100
    assert result.thrust == 1.


@pytest.mark.parametrize("change", [
    {"phase": AirframePhase.VTOL_TRANSITION, "is_vtol": True},
    {"phase": AirframePhase.MULTICOPTER}, {"rescue_active": True},
    {"observed_at_monotonic_s": 98.},
])
def test_unknown_authority_or_stale_flight_state_cannot_produce_commands(change):
    controller, identity, state = setup()
    with pytest.raises(ValueError):
        calculate(controller, identity, replace(state, **change))


def test_reset_prevents_old_session_reuse():
    controller, identity, state = setup()
    controller.reset()
    with pytest.raises(ValueError, match="binding_changed"):
        calculate(controller, identity, state)


@pytest.mark.parametrize("changes", [{"lookahead_m": 0.}, {"throttle_max": 2.},
                                     {"pitch_min_rad": math.nan}, {"altitude_time_constant_s": -1.}])
def test_invalid_controller_values_are_rejected(changes):
    with pytest.raises(ValueError):
        tuning(**changes)
