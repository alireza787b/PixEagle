"""Production fixed-wing math with explicit telemetry; no aircraft publication."""

import math
import time
from types import SimpleNamespace

import pytest
from classes.follower import FollowerFactory
from classes.tracker_output import TrackerDataType, TrackerOutput


@pytest.mark.parametrize(
    ("position", "field", "sign"),
    [
        ((0.15, 0.0), "yawspeed_deg_s", 1),
        ((-0.15, 0.0), "yawspeed_deg_s", -1),
        ((0.0, -0.12), "pitchspeed_deg_s", 1),
        ((0.0, 0.12), "pitchspeed_deg_s", -1),
    ],
)
def test_actual_pid_guidance_has_independent_image_axis_signs(position, field, sign):
    telemetry = fresh_airspeed_controller()
    follower = FollowerFactory.create_follower("fw_attitude_rate", telemetry, (0.0, 0.0))
    observation = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=position,
        confidence=0.99,
    )
    assert follower.follow_target(observation)
    command = follower.get_last_command_intent().fields
    assert command[field] * sign > 0.0
    assert all(math.isfinite(value) for value in command.values())
    for field, bound in (
        ("rollspeed_deg_s", follower.rate_limits.roll),
        ("pitchspeed_deg_s", follower.rate_limits.pitch),
        ("yawspeed_deg_s", follower.rate_limits.yaw),
    ):
        assert abs(command[field]) <= math.degrees(bound)
    assert 0.0 <= command["thrust"] <= 1.0
    assert follower.setpoint_handler.get_airframe_phase() == "fixed_wing"


def fresh_airspeed_controller(value=18.0, **observation_changes):
    observation = dict(available=True, fresh=True, airspeed_m_s=value,
                       observed_at_monotonic_s=time.monotonic(), source="mavsdk.fixedwing_metrics",
                       connection_generation=3, telemetry_generation=4)
    observation.update(observation_changes)
    controller = SimpleNamespace(
        current_airspeed=value, current_ground_speed=40.0, current_altitude=50.0,
        current_roll=0.0, current_pitch=0.0, current_yaw=0.0,
        get_airspeed_observation=lambda: observation,
        get_telemetry_readiness=lambda: dict(ready=True, owner_current=True, stale_timeout_s=0.5,
                                           connection_generation=3, telemetry_generation=4),
        is_command_connection_ready=lambda **_: True,
    )
    observation.setdefault("owner_instance", str(id(controller)))
    return controller


@pytest.mark.parametrize("change", [
    {"airspeed_m_s": None}, {"airspeed_m_s": float("nan")},
    {"airspeed_m_s": float("inf")}, {"airspeed_m_s": -1}, {"airspeed_m_s": True},
    {"connection_generation": 2}, {"telemetry_generation": 3}, {"fresh": False},
    {"source": "ground_speed"}, {"observed_at_monotonic_s": 0},
    {"owner_instance": "previous-controller"},
])
def test_fixed_wing_unavailable_airspeed_is_hard_safety_rejection(change):
    follower = FollowerFactory.create_follower("fw_attitude_rate", fresh_airspeed_controller(**change), (0, 0))
    observation = TrackerOutput(data_type=TrackerDataType.POSITION_2D, timestamp=time.time(),
                                tracking_active=True, position_2d=(0.1, 0.1), confidence=0.99)
    assert not follower.follow_target(observation)
    assert follower._safety_rejection in {"following_airspeed_unavailable", "following_airspeed_stale"}
    assert follower.get_last_command_intent() is None


def test_fresh_ground_speed_and_configured_cruise_cannot_replace_airspeed():
    follower = FollowerFactory.create_follower("fw_attitude_rate",
        SimpleNamespace(current_ground_speed=40.0, current_airspeed=18.0), (0, 0))
    with pytest.raises(ValueError, match="following_airspeed_unavailable"):
        follower._get_current_airspeed()


def test_command_preview_airspeed_is_explicit_synthetic_math_only():
    from classes.command_preview import CommandPreviewController
    from classes.airspeed_readiness import get_follower_airspeed, evaluate_following_start_airspeed
    preview = CommandPreviewController(airspeed_m_s=18.0)
    assert get_follower_airspeed(preview) == 18.0
    assert not evaluate_following_start_airspeed(SimpleNamespace(px4_interface=preview), mode="fw_attitude_rate")["ready"]


@pytest.mark.parametrize("mode", ["mc_velocity_chase", "mc_attitude_rate", "gm_velocity_chase", "gm_velocity_vector"])
def test_non_fixed_wing_readiness_does_not_add_airspeed_requirement(mode):
    from classes.airspeed_readiness import evaluate_following_start_airspeed
    assert evaluate_following_start_airspeed(SimpleNamespace(), mode=mode) == {"ready": True}


@pytest.mark.parametrize("value", [0.0, 11.0, 14.99])
def test_fixed_wing_start_rejects_stationary_or_below_margin_observation(value):
    from classes.airspeed_readiness import evaluate_following_start_airspeed
    result = evaluate_following_start_airspeed(SimpleNamespace(px4_interface=fresh_airspeed_controller(value)), mode="fw_attitude_rate")
    assert result["code"] == "following_airspeed_below_start_margin"


def test_under_speed_refuses_without_installing_unqualified_recovery_intent():
    follower = FollowerFactory.create_follower("fw_attitude_rate", fresh_airspeed_controller(1.0), (0, 0))
    observation = TrackerOutput(data_type=TrackerDataType.POSITION_2D, timestamp=time.time(),
                                tracking_active=True, position_2d=(0.1, 0.1), confidence=0.99)
    assert not follower.follow_target(observation)
    assert follower._safety_rejection == "following_airspeed_below_minimum"
    assert follower.get_last_command_intent() is None
    assert not follower.stall_recovery_active


def test_unexpected_observation_failure_is_sanitized_and_fail_closed():
    from classes.airspeed_readiness import get_follower_airspeed
    controller = fresh_airspeed_controller()
    controller.get_airspeed_observation = lambda: (_ for _ in ()).throw(OSError("private transport detail"))
    with pytest.raises(ValueError, match="^following_airspeed_unavailable$"):
        get_follower_airspeed(controller)


def fresh_ground_speed_controller(value=18.0, source="mavsdk", **health_changes):
    health = dict(ready=True, owner_current=True, source=source, stale_timeout_s=0.5,
                  last_complete_sample_age_s=0.02, connection_generation=3,
                  telemetry_connection_generation=3, telemetry_generation=4,
                  ground_speed_observation=dict(speed_m_s=value, source_progress_age_s=0.02,
                                                connection_generation=3, telemetry_generation=4))
    health.update(health_changes)
    return SimpleNamespace(current_ground_speed=value, current_altitude=50.0,
                           current_roll=0.0, current_pitch=0.0, current_yaw=0.0,
                           get_ground_speed=lambda: value, get_telemetry_readiness=lambda: health,
                           is_command_connection_ready=lambda **_: True)


@pytest.fixture
def ground_speed_fallback(monkeypatch):
    from classes.parameters import Parameters
    monkeypatch.setattr(Parameters, "FW_ATTITUDE_RATE", {
        **Parameters.FW_ATTITUDE_RATE, "ALLOW_GROUND_SPEED_FALLBACK": True})


@pytest.mark.parametrize("source", ["mavsdk", "mavlink2rest"])
def test_opted_in_fresh_ground_speed_is_distinct_control_proxy(ground_speed_fallback, source):
    from classes.airspeed_readiness import get_follower_speed_observation, evaluate_following_start_airspeed
    controller = fresh_ground_speed_controller(source=source)
    speed = get_follower_speed_observation(controller)
    assert speed == {"speed_m_s": 18.0, "source": "mavsdk.velocity_body" if source == "mavsdk" else "mavlink2rest.LOCAL_POSITION_NED", "fallback_active": True}
    assert evaluate_following_start_airspeed(SimpleNamespace(px4_interface=controller), mode="fw_attitude_rate")["speed_observation"] == speed
    follower = FollowerFactory.create_follower("fw_attitude_rate", controller, (0, 0))
    observation = TrackerOutput(data_type=TrackerDataType.POSITION_2D, timestamp=time.time(),
                                tracking_active=True, position_2d=(0.1, 0.1), confidence=0.99)
    assert follower.follow_target(observation)
    status = follower.get_fixed_wing_status()
    assert status["current_airspeed"] is None
    assert status["guidance_speed"] == speed
    assert "Ground-speed proxy: 18.0 m/s" in follower.get_status_report()


@pytest.mark.parametrize("value", [0.0, 11.0, 14.99, 18.0])
def test_valid_airspeed_always_wins_over_enabled_fallback(ground_speed_fallback, value):
    from classes.airspeed_readiness import get_follower_speed_observation, evaluate_following_start_airspeed
    controller = fresh_airspeed_controller(value)
    assert get_follower_speed_observation(controller) == {"speed_m_s": value, "source": "airspeed", "fallback_active": False}
    result = evaluate_following_start_airspeed(SimpleNamespace(px4_interface=controller), mode="fw_attitude_rate")
    assert result["ready"] is (value >= 15.0)
    if value < 15.0:
        assert result["code"] == "following_airspeed_below_start_margin"


@pytest.mark.parametrize("change", [{"ready": False}, {"owner_current": False},
    {"last_complete_sample_age_s": 0.6}, {"telemetry_connection_generation": 2},
    {"connection_generation": None}, {"source": "unqualified"},
    {"ground_speed_observation": None},
    {"ground_speed_observation": {"speed_m_s": 18.0, "source_progress_age_s": 0.6, "connection_generation": 3, "telemetry_generation": 4}},
    {"ground_speed_observation": {"speed_m_s": 18.0, "source_progress_age_s": 0.0, "connection_generation": 2, "telemetry_generation": 4}},
])
def test_fallback_rejects_stale_or_wrong_owner_ground_speed(ground_speed_fallback, change):
    from classes.airspeed_readiness import get_follower_speed_observation
    with pytest.raises(ValueError, match="following_ground_speed_(stale|unavailable)"):
        get_follower_speed_observation(fresh_ground_speed_controller(**change))


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf")])
def test_fallback_rejects_invalid_ground_speed(ground_speed_fallback, value):
    from classes.airspeed_readiness import get_follower_speed_observation
    with pytest.raises(ValueError, match="following_ground_speed_unavailable"):
        get_follower_speed_observation(fresh_ground_speed_controller(value))


def test_disabled_flag_does_not_admit_fresh_ground_speed(monkeypatch):
    from classes.parameters import Parameters
    from classes.airspeed_readiness import get_follower_speed_observation
    monkeypatch.setattr(Parameters, "FW_ATTITUDE_RATE", {**Parameters.FW_ATTITUDE_RATE, "ALLOW_GROUND_SPEED_FALLBACK": False})
    with pytest.raises(ValueError, match="following_airspeed_unavailable"):
        get_follower_speed_observation(fresh_ground_speed_controller())


def test_enabled_fallback_does_not_admit_synthetic_preview_to_live_start(ground_speed_fallback):
    from classes.command_preview import CommandPreviewController
    from classes.airspeed_readiness import evaluate_following_start_airspeed
    result = evaluate_following_start_airspeed(SimpleNamespace(px4_interface=CommandPreviewController(airspeed_m_s=18.0)), mode="fw_attitude_rate")
    assert result["code"] == "following_airspeed_unavailable"


def test_ground_proxy_under_configured_margin_is_not_called_airspeed(ground_speed_fallback):
    from classes.airspeed_readiness import evaluate_following_start_airspeed
    result = evaluate_following_start_airspeed(SimpleNamespace(px4_interface=fresh_ground_speed_controller(1.0)), mode="fw_attitude_rate")
    assert result["code"] == "following_ground_speed_below_start_margin"
    assert "ground-speed proxy" in result["message"]
