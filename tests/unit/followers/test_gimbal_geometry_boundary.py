"""Invalid camera-body angles must not leave pursuit intent active."""

import math
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.gimbal_geometry import (
    InvalidGimbalGeometry,
    body_line_of_sight,
    migrate_legacy_geometry,
    require_canonical_geometry_settings,
    require_finite_body_angles,
    resolve_angle_geometry,
    resolve_mount_type,
)
from classes.tracker_output import TrackerDataType, TrackerOutput


def test_chase_accepts_fresh_consecutive_observations_without_false_safety_handoff():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower._safety_checks_bypassed_for_testing = lambda: False
    follower.emergency_stop_active = False
    follower.rtl_triggered = False
    follower._check_altitude_safety = lambda: {"safe": True}
    follower.min_altitude_safety = 3.0
    follower.max_altitude_safety = 120.0
    follower.safety_violations_count = 0
    follower._follower_config_name = "GM_VELOCITY_CHASE"
    follower.safety_manager = SimpleNamespace(
        get_safety_behavior=lambda _: SimpleNamespace(max_safety_violations=3)
    )
    assert follower._perform_safety_checks()["safe_to_proceed"]
    assert follower._perform_safety_checks()["safe_to_proceed"]
    follower._check_altitude_safety = lambda: {"safe": False, "violation_type": "too_low"}
    assert follower._perform_safety_checks()["reason"] == "altitude_violation_too_low"


@pytest.mark.parametrize("follower_type", [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_camera_vertical_guard_stops_at_warning_bounds_and_rejects_stale_telemetry(follower_type):
    follower = follower_type.__new__(follower_type)
    aircraft = SimpleNamespace(current_altitude=10.0, is_command_connection_ready=lambda **_: True)
    follower.px4_controller = aircraft
    follower._follower_config_name = follower_type.__name__
    follower.safety_manager = SimpleNamespace(get_altitude_limits=lambda _: SimpleNamespace(
        min_altitude=3.0, max_altitude=120.0, warning_buffer=2.0,
    ))
    assert follower.guard_gimbal_vertical_velocity(0.3) == 0.3
    aircraft.current_altitude = 5.0
    assert follower.guard_gimbal_vertical_velocity(0.3) == 0.0
    assert follower._vertical_limit_status == "descent_limited"
    aircraft.current_altitude = 118.0
    assert follower.guard_gimbal_vertical_velocity(-0.3) == 0.0
    assert follower._vertical_limit_status == "climb_limited"
    aircraft.is_command_connection_ready = lambda **_: False
    with pytest.raises(ValueError, match="Fresh aircraft altitude"):
        follower.guard_gimbal_vertical_velocity(0.3)


@pytest.mark.parametrize("angles", [None, 0, (1.0,), (math.nan, 0, 0), (0, math.inf, 0), ("0", 0, 0)])
def test_nonfinite_or_malformed_body_angles_are_rejected(angles):
    with pytest.raises(InvalidGimbalGeometry):
        require_finite_body_angles(angles)


def test_valid_body_angles_preserve_raw_order_and_sign():
    assert require_finite_body_angles((-12, 100.5, 3)) == (-12.0, 100.5, 3.0)


@pytest.mark.parametrize(
    ("angles", "expected"),
    [
        ((0, 90, 0), (1, 0, 0)),
        ((0, 90, 30), (math.sqrt(3) / 2, -0.5, 0)),
        ((0, 60, 0), (math.sqrt(3) / 2, 0, -0.5)),
        ((0, 120, 0), (math.sqrt(3) / 2, 0, 0.5)),
        ((-20, 60, 30), (0.75, -math.sqrt(3) / 4, -0.5)),
    ],
)
def test_measured_vertical_convention_produces_independent_body_directions(angles, expected):
    assert body_line_of_sight(angles, "VERTICAL") == pytest.approx(expected)


def test_vertical_optical_roll_does_not_move_line_of_sight():
    assert body_line_of_sight((-30, 90, 0), "VERTICAL") == pytest.approx(
        body_line_of_sight((30, 90, 0), "VERTICAL")
    )


def test_horizontal_convention_preserves_synthetic_forward_right_down():
    assert body_line_of_sight((30, 30, 0), "HORIZONTAL") == pytest.approx(
        (0.75, math.sqrt(3) / 4, 0.5)
    )


def test_expert_mapping_overrides_one_axis_without_changing_mount_preset():
    mapping = resolve_angle_geometry(
        {
            "PROVIDER": "topotek_sip_udp",
            "GEOMETRY_OVERRIDE": {
                "AZIMUTH_SIGN": "POSITIVE",
                "DEPRESSION_ZERO_ADJUST_DEG": -10.0,
            },
        },
        "VERTICAL",
    )
    assert body_line_of_sight((0, 80, 30), "VERTICAL", mapping) == pytest.approx(
        (math.sqrt(3) / 2, 0.5, 0)
    )


@pytest.mark.parametrize(
    "override",
    [
        {"AZIMUTH_AXIS": "PITCH"},
        {"AZIMUTH_SIGN": "SIDEWAYS"},
        {"DEPRESSION_ZERO_ADJUST_DEG": math.nan},
    ],
)
def test_invalid_expert_mapping_fails_before_following(override):
    with pytest.raises(InvalidGimbalGeometry):
        resolve_angle_geometry({"GEOMETRY_OVERRIDE": override}, "VERTICAL")


def test_unknown_provider_does_not_inherit_topotek_geometry():
    with pytest.raises(InvalidGimbalGeometry, match="provider"):
        resolve_angle_geometry({"PROVIDER": "different_camera"}, "VERTICAL")


def test_unknown_mount_rejects_direction():
    with pytest.raises(InvalidGimbalGeometry):
        body_line_of_sight((0, 90, 0), "SIDEWAYS")


def test_camera_mount_setting_is_shared_by_both_legacy_follower_profiles():
    assert resolve_mount_type(
        {"MOUNT_TYPE": "VERTICAL"},
        {"MOUNT_TYPE": "HORIZONTAL"},
        {"MOUNT_TYPE": "HORIZONTAL"},
        allowed=("HORIZONTAL", "VERTICAL"),
    ) == "VERTICAL"


def test_conflicting_nondefault_legacy_mount_requires_correction():
    with pytest.raises(InvalidGimbalGeometry, match="conflicts"):
        resolve_mount_type(
            {"MOUNT_TYPE": "HORIZONTAL"},
            {"MOUNT_TYPE": "VERTICAL"},
            {"MOUNT_TYPE": "HORIZONTAL"},
            allowed=("HORIZONTAL", "VERTICAL"),
        )
    with pytest.raises(InvalidGimbalGeometry, match="Conflicting legacy"):
        resolve_mount_type(
            {},
            {"MOUNT_TYPE": "VERTICAL"},
            {"MOUNT_TYPE": "HORIZONTAL"},
            allowed=("HORIZONTAL", "VERTICAL"),
        )


def test_consistent_old_mount_remains_readable_without_camera_mount_setting():
    assert resolve_mount_type(
        {},
        {"MOUNT_TYPE": "VERTICAL"},
        {"MOUNT_TYPE": "VERTICAL"},
        allowed=("HORIZONTAL", "VERTICAL"),
    ) == "VERTICAL"


def test_unambiguous_old_mount_is_promoted_before_retirement():
    old = {
        "GM_VELOCITY_CHASE": {"MOUNT_TYPE": "VERTICAL"},
        "GM_VELOCITY_VECTOR": {"MOUNT_TYPE": "VERTICAL"},
        "GimbalTracker": {"PROVIDER": "topotek_sip_udp"},
    }
    migrated = migrate_legacy_geometry(old)
    assert migrated["GimbalTracker"]["MOUNT_TYPE"] == "VERTICAL"
    assert "MOUNT_TYPE" not in old["GimbalTracker"]


def test_conflicting_old_mount_and_non_neutral_direction_cannot_be_discarded():
    with pytest.raises(InvalidGimbalGeometry, match="Conflicting legacy"):
        migrate_legacy_geometry({
            "GM_VELOCITY_CHASE": {"MOUNT_TYPE": "VERTICAL"},
            "GM_VELOCITY_VECTOR": {"MOUNT_TYPE": "HORIZONTAL"},
        })
    with pytest.raises(InvalidGimbalGeometry, match="GEOMETRY_OVERRIDE"):
        migrate_legacy_geometry({
            "GM_VELOCITY_VECTOR": {"INVERT_GIMBAL_ROLL": True},
        })
    with pytest.raises(InvalidGimbalGeometry, match="Unsupported gimbal MOUNT_TYPE"):
        migrate_legacy_geometry({"GM_VELOCITY_VECTOR": {"MOUNT_TYPE": "TILTED_45"}})


def test_historical_inversion_default_does_not_block_unrelated_local_profile():
    old = {
        "Tracking": {"DEFAULT_TRACKING_ALGORITHM": "CSRT"},
        "Follower": {"FOLLOWER_MODE": "mc_velocity_position"},
        "GM_VELOCITY_CHASE": {"INVERT_VERTICAL_CONTROL": True},
    }
    assert migrate_legacy_geometry(old)["GM_VELOCITY_CHASE"]["INVERT_VERTICAL_CONTROL"] is True
    old["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] = "Gimbal"
    with pytest.raises(InvalidGimbalGeometry, match="GEOMETRY_OVERRIDE"):
        migrate_legacy_geometry(old)


@pytest.mark.parametrize(
    ("follower_name", "override"),
    [
        ("GM_VELOCITY_CHASE", {"INVERT_VERTICAL_CONTROL": True}),
        ("GM_VELOCITY_CHASE", {"ROLL_RIGHT_SIGN": "POSITIVE"}),
        ("GM_VELOCITY_CHASE", {"NEUTRAL_PITCH_ANGLE": 15.0}),
        ("GM_VELOCITY_VECTOR", {"MOUNT_YAW_OFFSET_DEG": 12.0}),
        ("GM_VELOCITY_VECTOR", {"INVERT_GIMBAL_ROLL": True}),
    ],
)
def test_follower_specific_geometry_overrides_require_migration(follower_name, override):
    with pytest.raises(InvalidGimbalGeometry, match="GimbalTracker.GEOMETRY_OVERRIDE"):
        require_canonical_geometry_settings(follower_name, override)


def test_chase_guidance_errors_use_the_same_body_direction():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.mount_type = "VERTICAL"
    follower.max_roll_angle = 90.0
    follower.max_pitch_angle = 90.0
    follower.lateral_invert = False
    follower.vertical_invert = False

    left, level = follower._transform_gimbal_to_control_frame(20, 90, 30)
    center, up = follower._transform_gimbal_to_control_frame(0, 60, 0)

    assert (left, level) == pytest.approx((-1 / 3, 0))
    assert (center, up) == pytest.approx((0, -1 / 3))


def test_pitch_based_forward_speed_uses_camera_mount_neutral_and_override():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.angle_geometry = resolve_angle_geometry(
        {"GEOMETRY_OVERRIDE": {"DEPRESSION_ZERO_ADJUST_DEG": -10}}, "VERTICAL"
    )
    assert follower._get_forward_pitch_error(70) == pytest.approx(-10)
    follower.angle_geometry = resolve_angle_geometry({}, "HORIZONTAL")
    assert follower._get_forward_pitch_error(10) == pytest.approx(10)


def test_both_followers_reject_rearward_target_direction():
    chase = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    chase.mount_type = "VERTICAL"
    vector = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    vector.mount_type = "VERTICAL"

    with pytest.raises(InvalidGimbalGeometry, match="forward hemisphere"):
        chase._transform_gimbal_to_control_frame(0, 90, 180)
    with pytest.raises(InvalidGimbalGeometry, match="forward hemisphere"):
        vector._gimbal_to_body_vector(0, 90, 180)


def _invalid_output():
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(), tracking_active=True,
        angular=(math.nan, 100.0, 0.0),
    )


def test_chase_invalid_geometry_requests_hold_before_pursuit():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.debug_logging_enabled = False
    follower.last_ramp_update_time = time.monotonic()
    follower.update_rate = 20
    follower._apply_gimbal_emergency_hold = Mock()
    follower.set_command_fields = Mock()

    with pytest.raises(RuntimeError, match="finite"):
        follower.calculate_control_commands(_invalid_output())
    assert follower._process_normal_tracking(_invalid_output(), time.time()) is False
    follower._apply_gimbal_emergency_hold.assert_called_once_with("invalid_gimbal_command")
    follower.set_command_fields.assert_not_called()


def test_vector_invalid_geometry_requests_emergency_stop():
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.total_follow_calls = 0
    follower._perform_safety_checks = Mock(return_value={"safe_to_proceed": True})
    follower.validate_tracker_compatibility = Mock(return_value=True)
    follower.last_update_time = time.time()
    follower.update_rate = 20
    follower.emergency_stop = Mock()
    follower.log_follower_event = Mock()
    follower.set_command_fields = Mock()

    with pytest.raises(RuntimeError, match="finite"):
        follower.calculate_control_commands(_invalid_output())
    assert follower.follow_target(_invalid_output()) is False
    follower.emergency_stop.assert_called_once_with()
    follower.set_command_fields.assert_not_called()


def test_chase_hold_clears_forward_pursuit():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.current_forward_velocity = 3.0
    follower.following_active = True
    follower.yaw_smoother = Mock()
    follower.set_command_fields = Mock(return_value=True)
    follower.log_follower_event = Mock()

    follower._apply_gimbal_emergency_hold("invalid_gimbal_command")

    assert follower.set_command_fields.call_args.args[0] == {
        "vel_body_fwd": 0.0, "vel_body_right": 0.0,
        "vel_body_down": 0.0, "yawspeed_deg_s": 0.0,
    }
    assert follower.current_forward_velocity == 0.0
    assert follower.following_active is False


def test_vector_stop_clears_smoothing_history():
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.following_active = True
    follower.emergency_stop_active = False
    follower.current_velocity_magnitude = 3.0
    follower.last_command_vector = object()
    follower.last_velocity_vector = object()
    follower.yaw_smoother = Mock()
    follower.set_command_fields = Mock(return_value=True)
    follower.log_follower_event = Mock()

    follower.emergency_stop()

    assert follower.set_command_fields.call_args.args[0] == {
        "vel_body_fwd": 0.0, "vel_body_right": 0.0,
        "vel_body_down": 0.0, "yawspeed_deg_s": 0.0,
    }
    assert follower.emergency_stop_active is True
    assert follower.following_active is False
    assert follower.current_velocity_magnitude == 0.0
    assert follower.last_command_vector is None
    assert follower.last_velocity_vector is None
    follower.yaw_smoother.reset.assert_called_once_with()
