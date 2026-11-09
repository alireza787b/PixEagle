"""Registered MC strategies resolve real defaults before generating command intent."""

from copy import deepcopy
import math
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
import yaml

from classes.follower import FollowerFactory
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.telemetry_observation import AltitudeObservation
from classes.command_safety import CommandValidationError


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
VELOCITY_MODES = (
    "mc_velocity_position", "mc_velocity_chase", "mc_velocity_ground", "mc_velocity_distance",
)


@pytest.fixture
def factory():
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((ROOT / "configs/config_default.yaml").read_text())

    def build(mode, *, altitude=False, configure=None, aim=(0., 0.)):
        config = deepcopy(defaults)
        config["Follower"]["General"]["ENABLE_ALTITUDE_CONTROL"] = altitude
        if configure is not None:
            configure(config)
        Parameters.publish_config_mapping(config)
        controller = SimpleNamespace(
            is_command_preview=False, current_altitude=30., current_pitch=0.,
            current_roll=0., current_ground_speed=0.,
            get_orientation=lambda: (0., 0., 0.),
            is_command_connection_ready=lambda **kwargs: True,
        )
        controller.get_altitude_observation = lambda: height_sample(controller.current_altitude)
        return FollowerFactory.create_follower(mode, controller, aim)

    try:
        yield build
    finally:
        Parameters.publish_config_mapping(previous)


def observe(follower, x, y):
    sample = TrackerOutput(
        TrackerDataType.POSITION_2D, timestamp=time.time(), tracking_active=True,
        position_2d=(x, y), confidence=.99, tracker_id="image_contract_test",
    )
    follower.calculate_control_commands(sample)
    intent = follower.get_last_command_intent()
    assert intent is not None
    assert all(math.isfinite(value) for value in intent.fields.values())
    return intent.fields


def height_sample(height=30., *, up=0., time_s=1., reference=1):
    return AltitudeObservation(
        height_relative_m=height, vertical_speed_up_m_s=up,
        source_marker=int(time_s * 1000), sample_time_s=time_s,
        received_at_monotonic_s=time.monotonic(), sample_time_basis="unit_fixture",
        source="test_paired_height", altitude_reference_generation=reference,
        connection_generation=1, telemetry_generation=1,
    )


@pytest.mark.parametrize("mode", VELOCITY_MODES)
@pytest.mark.parametrize("target", [(.3, .4), (-.3, -.4)])
def test_factory_altitude_off_never_requests_vertical_motion(factory, mode, target):
    follower = factory(mode)
    fields = observe(follower, *target)
    assert fields["vel_body_down"] == 0.
    if mode in {"mc_velocity_position", "mc_velocity_distance"}:
        assert fields["vel_body_fwd"] == 0.
    if mode == "mc_velocity_position":
        assert fields["vel_body_right"] == 0.


@pytest.mark.parametrize("y", [-.4, .4])
def test_centering_altitude_on_preserves_image_vertical_direction(factory, y):
    follower = factory("mc_velocity_distance", altitude=True)
    assert observe(follower, .2, y)["vel_body_down"] * y > 0.


def test_centering_altitude_off_cannot_replay_vertical_smoothing_history(factory):
    follower = factory("mc_velocity_distance")
    follower._last_vel_down = .5
    assert observe(follower, .2, -.4)["vel_body_down"] == 0.
    assert follower._last_vel_down == 0.


def test_position_yaw_disable_clears_previous_guidance(factory):
    def configure(config):
        config["MC_VELOCITY_POSITION"]["ENABLE_YAW_CONTROL"] = False

    follower = factory("mc_velocity_position", configure=configure)
    follower.yaw_smoother.last_yaw_rate = 10.
    follower.yaw_smoother.filtered_yaw_rate = 10.
    assert observe(follower, .5, .2)["yawspeed_deg_s"] == 0.
    assert follower.yaw_smoother.last_yaw_rate == 0.
    assert follower.yaw_smoother.filtered_yaw_rate == 0.


def test_chase_adaptation_cannot_enable_disabled_altitude_guidance(factory):
    def configure(config):
        config["MC_VELOCITY_CHASE"]["ENABLE_ADAPTIVE_DIVE_CLIMB"] = True

    follower = factory("mc_velocity_chase", configure=configure)
    follower.adaptive_active = True
    follower._calculate_target_vertical_rate = lambda *args: (20., 0., 20.)
    follower._check_adaptive_oscillation = lambda: False
    follower._check_adaptive_divergence = lambda: False
    assert observe(follower, .1, .4)["vel_body_down"] == 0.
    assert follower.adaptive_correction_down == 0.


def test_ground_pid_tuning_matches_command_axis(factory):
    def configure(config):
        config["PID"]["PID_GAINS"]["mc_vel_forward"]["p"] = .7
        config["PID"]["PID_GAINS"]["mc_vel_lateral"]["p"] = .2

    follower = factory("mc_velocity_ground", configure=configure)
    assert follower.pid_x.Kp == .2  # Image X commands body-right.
    assert follower.pid_y.Kp == .7  # Image Y commands body-forward.
    follower._update_pid_gains()
    assert follower.pid_x.Kp == .2
    assert follower.pid_y.Kp == .7


@pytest.mark.parametrize("altitude,expected", [(False, 30.), (True, 33.)])
def test_mc_rates_respect_altitude_guidance_permission_for_saved_offset(factory, altitude, expected):
    def configure(config):
        config["MC_ATTITUDE_RATE"]["TARGET_ALTITUDE_OFFSET"] = 3.

    follower = factory("mc_attitude_rate", altitude=altitude, configure=configure)
    follower._calculate_thrust_command(0.)
    assert follower.pid_altitude.setpoint == expected


@pytest.mark.parametrize("refresh", [False, True])
def test_mc_rate_image_gains_use_declared_degrees_per_second(factory, refresh):
    follower = factory("mc_attitude_rate")
    # Isolate P units from elapsed-time I/D, using the actual factory controllers.
    for axis in ("mc_pitchspeed_deg_s", "mc_att_yawspeed_deg_s"):
        Parameters.PID_GAINS[axis]["i"] = 0.
        Parameters.PID_GAINS[axis]["d"] = 0.
    follower._update_pid_gains()
    if refresh:
        Parameters.PID_GAINS["mc_pitchspeed_deg_s"]["p"] = 20.
        Parameters.PID_GAINS["mc_att_yawspeed_deg_s"]["p"] = 10.
        follower._update_pid_gains()
    pitch, yaw = follower._calculate_direct_rates((.01, -.01))
    expected_pitch, expected_yaw = (.2, .1) if refresh else (.18, .12)
    assert math.degrees(pitch) == pytest.approx(expected_pitch)
    assert math.degrees(yaw) == pytest.approx(expected_yaw)
    # Bank error is angular, unlike the normalized image input: preserve its gain.
    follower.pid_roll_rate.tunings = (1.5, 0., 0.)
    roll = follower._calculate_coordinated_roll_rate(0., 0., 10.)
    assert math.degrees(roll) == pytest.approx(-15.)


def test_mc_rate_image_gain_conversion_includes_integral_and_derivative(factory):
    follower = factory("mc_attitude_rate")
    for pid, axis in ((follower.pid_pitch_rate, "mc_pitchspeed_deg_s"),
                      (follower.pid_yaw_rate, "mc_att_yawspeed_deg_s")):
        gains = Parameters.PID_GAINS[axis]
        assert pid.tunings == pytest.approx(tuple(math.radians(gains[key]) for key in ("p", "i", "d")))


def test_mc_rate_height_integrates_once_per_source_sample_and_damps_vertical_speed(factory):
    def configure(config):
        config["PID"]["PID_GAINS"]["mc_att_altitude"] = dict(p=0., i=.1, d=.2)

    follower = factory("mc_attitude_rate", configure=configure)
    sample = height_sample()
    follower.px4_controller.get_altitude_observation = lambda: sample
    assert follower._calculate_altitude_correction() == 0.
    sample = height_sample(29., time_s=2.)
    assert follower._calculate_altitude_correction() == pytest.approx(.1)
    for _ in range(100):
        assert follower._calculate_altitude_correction() == pytest.approx(.1)
    sample = height_sample(29., up=.5, time_s=3.)
    assert follower._calculate_altitude_correction() == pytest.approx(.1)


@pytest.mark.parametrize("up", [-.5, .5])
def test_mc_rate_height_damping_uses_paired_measured_speed(factory, up):
    def configure(config):
        config["PID"]["PID_GAINS"]["mc_att_altitude"] = dict(p=0., i=0., d=.2)

    follower = factory("mc_attitude_rate", configure=configure)
    follower.px4_controller.get_altitude_observation = lambda: height_sample(up=up)
    assert follower._calculate_altitude_correction() == pytest.approx(-.2 * up)


@pytest.mark.parametrize("replacement,reason", [
    (None, "altitude_sample_unavailable"),
    (height_sample(time_s=.5), "altitude_source_time_reversed"),
    (height_sample(time_s=2., reference=2), "altitude_reference_changed"),
])
def test_mc_rate_invalid_height_cannot_reuse_a_hover_guess(factory, replacement, reason):
    follower = factory("mc_attitude_rate")
    follower._calculate_altitude_correction()
    follower.px4_controller.get_altitude_observation = lambda: replacement
    with pytest.raises(CommandValidationError, match=reason):
        follower._calculate_thrust_command(0.)


def test_mc_rate_yaw_gating_keeps_altitude_stabilization(factory):
    follower = factory("mc_attitude_rate")
    assert follower._apply_yaw_error_gating(1., .2, .61) == (0., .61)


def test_mc_rate_thrust_compensation_includes_roll_as_well_as_pitch(factory):
    follower = factory("mc_attitude_rate")
    baseline = follower._calculate_thrust_command(0., 0.)
    tilted = follower._calculate_thrust_command(20., 25.)
    expected = follower.hover_thrust * follower.pitch_compensation_gain * (
        1. / (math.cos(math.radians(20.)) * math.cos(math.radians(25.))) - 1.
    )
    assert tilted - baseline == pytest.approx(expected)


@pytest.mark.parametrize("legacy_enabled", [False, True])
def test_ground_cannot_reactivate_uncalibrated_corrections_from_saved_legacy_values(factory, legacy_enabled):
    def configure(config):
        config["MC_VELOCITY_GROUND"].update(
            COORDINATE_CORRECTIONS_ENABLED=legacy_enabled, IS_CAMERA_GIMBALED=False,
            BASE_ADJUSTMENT_FACTOR_X=100., BASE_ADJUSTMENT_FACTOR_Y=100., ALTITUDE_FACTOR=100.,
        )

    follower = factory("mc_velocity_ground", configure=configure)
    def no_uncalibrated_pose_correction():
        raise AssertionError("Image centering cannot infer a calibrated pose correction")
    follower.px4_controller.get_orientation = no_uncalibrated_pose_correction
    fields = observe(follower, 0., 0.)
    assert fields["vel_body_fwd"] == 0.
    assert fields["vel_body_right"] == 0.


@pytest.mark.parametrize("altitude", [False, True])
def test_ground_descent_requires_shared_altitude_guidance_permission(factory, altitude):
    def configure(config):
        config["MC_VELOCITY_GROUND"]["ENABLE_DESCEND_TO_TARGET"] = True

    follower = factory("mc_velocity_ground", altitude=altitude, configure=configure)
    down = observe(follower, .1, .1)["vel_body_down"]
    assert down > 0. if altitude else down == 0.


@pytest.mark.parametrize("mode", ["mc_velocity_position", "mc_velocity_distance"])
def test_clock_discontinuity_cannot_bypass_yaw_acceleration(factory, monkeypatch, mode):
    def configure(config):
        config[mode.upper()]["ENABLE_YAW_CONTROL"] = True

    follower = factory(mode, configure=configure)
    follower._last_update_time = 100.
    follower.yaw_smoother.last_yaw_rate = 4.
    follower.yaw_smoother.filtered_yaw_rate = 3.
    monkeypatch.setattr("classes.followers.base_follower.time.monotonic", lambda: 99.)
    assert observe(follower, -.8, 0.)["yawspeed_deg_s"] == 3.


@pytest.mark.parametrize("mode", ["mc_velocity_position", "mc_velocity_distance", "mc_velocity_ground"])
def test_retarget_does_not_reuse_previous_target_command_history(factory, mode):
    follower = factory(mode, altitude=True)
    previous = observe(follower, .4, .4)
    assert any(abs(value) > 0. for value in previous.values())
    assert follower.prepare_for_target_transition("test_retarget")
    for _ in range(3):
        centered = observe(follower, 0., 0.)
        assert all(abs(value) < 1e-9 for value in centered.values())
