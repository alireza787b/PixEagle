"""An SIH profile must remain inert until an isolated PX4 run is verified."""

import json

import pytest
import yaml

from tools.prepare_sitl_gimbal_profile import prepare, validate


def test_prepared_gimbal_sih_profile_blocks_commands_and_uses_one_mount_setting(tmp_path):
    directory = tmp_path / "sih"
    prepare(
        directory, camera_host="192.0.2.108", rtsp_url="rtsp://192.0.2.108/stream=0",
        mount_type="VERTICAL", follower_mode="gm_velocity_vector", backend_port=18096,
    )
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    manifest = json.loads((directory / "profile-manifest.json").read_text())

    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert config["Follower"]["FOLLOWER_EXECUTION_MODE"] == "PX4"
    assert config["Follower"]["FOLLOWER_MODE"] == "gm_velocity_vector"
    assert config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] == "Gimbal"
    assert config["GimbalTracker"]["MOUNT_TYPE"] == "VERTICAL"
    assert config["GimbalTracker"]["CONTROL_ENABLED"] is True
    assert config["PX4"]["SYSTEM_ADDRESS"] == "udpin://127.0.0.1:14540"
    assert config["MAVLink"]["MAVLINK_ENABLED"] is True
    assert config["Streaming"]["HTTP_STREAM_HOST"] == "0.0.0.0"
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == ["127.0.0.1"]
    assert manifest["services_started"] is False
    assert manifest["flight_commands_blocked"] is True
    assert (directory / "configs/segmentation_models.yaml").is_file()
    assert not any(path.is_symlink() for path in directory.rglob("*"))
    assert validate(directory)["mount_type"] == "VERTICAL"
    with pytest.raises(ValueError, match="never overwritten"):
        prepare(directory, camera_host="192.0.2.108",
                rtsp_url="rtsp://192.0.2.108/stream=0", mount_type="VERTICAL")


def test_profile_validation_rejects_changed_circuit_breaker(tmp_path):
    directory = tmp_path / "sih"
    prepare(directory, camera_host="192.0.2.108",
            rtsp_url="rtsp://192.0.2.108/stream=0", mount_type="VERTICAL")
    config_path = directory / "configs/config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["FOLLOWER_CIRCUIT_BREAKER"] = False
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="snapshot changed"):
        validate(directory)


def test_bounded_continuity_is_explicit_in_private_sih_profile(tmp_path):
    directory = tmp_path / "bounded-sih"
    prepare(directory, camera_host="192.0.2.108",
            rtsp_url="rtsp://192.0.2.108/stream=0", mount_type="VERTICAL",
            continuity_mode="bounded_decay")
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert config["TargetContinuity"] == {
        "MODE": "bounded_decay", "MAX_COAST_TIME_S": 8.0,
        "MAX_COAST_DISTANCE_M": 4.0, "REACQUIRE_CONFIRMATION_S": 0.5,
        "MAX_RETARGET_TIME_S": 8.0,
        "AUTHORITY_RESTORE_TIME_S": 0.5, "TERMINAL_ACTION": "hold",
        "RETARGET_ANGLE_BLEND_FRACTION": 0.7,
        "RETARGET_PROVISIONAL_AUTHORITY_FRACTION": 0.5,
        "RETARGET_RESTORE_TIME_S": 0.5,
    }
    assert config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["LATERAL_GUIDANCE_MODE"] == "coordinated_turn"
    assert validate(directory)["continuity_mode"] == "bounded_decay"


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("192.0.2.108", "rtsp://192.0.2.109/stream=0"),
        ("192.0.2.108", "rtsp://user:password@192.0.2.108/stream=0"),
        ("192.0.2.108", "rtsp://:password@192.0.2.108/stream=0"),
        ("http://192.0.2.108", "rtsp://192.0.2.108/stream=0"),
    ],
)
def test_profile_refuses_ambiguous_or_embedded_camera_credentials(tmp_path, host, url):
    with pytest.raises(ValueError):
        prepare(tmp_path / "sih", camera_host=host, rtsp_url=url, mount_type="VERTICAL")
    assert not (tmp_path / "sih").exists()


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_local_camera_profile_keeps_image_tracking_and_controls_independent(tmp_path, mount):
    directory = tmp_path / "local"
    prepare(directory, camera_host="192.0.2.108", rtsp_url="rtsp://192.0.2.108/stream=0",
        mount_type=mount, tracking_engine="local", follower_mode="mc_velocity_position")
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    assert config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] == "CSRT"
    assert config["GimbalTracker"]["ENABLED"]
    assert config["GimbalTracker"]["CONTROL_ENABLED"]
    assert config["GimbalTracker"]["MOUNT_TYPE"] == mount
    assert config["VideoSource"]["VIDEO_SOURCE_TYPE"] == "RTSP_OPENCV"
    assert config["Follower"]["FOLLOWER_MODE"] == "mc_velocity_position"
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert config["Safety"]["GlobalLimits"]["ALTITUDE_SAFETY_ENABLED"] is True
    assert config["Streaming"]["API_SYSTEM_RESTART_POLICY"] == "lab_admin_browser"
    assert validate(directory)["tracking_engine"] == "local"


def test_local_camera_profile_rejects_angle_follower(tmp_path):
    with pytest.raises(ValueError, match="Follower must match"):
        prepare(tmp_path / "invalid", camera_host="192.0.2.108",
            rtsp_url="rtsp://192.0.2.108/stream=0", mount_type="VERTICAL",
            tracking_engine="local", follower_mode="gm_velocity_chase")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("video", ["test4.mp4", "test9.mp4", "test11.mp4"])
def test_recorded_profile_has_no_camera_owner(tmp_path, video):
    directory = tmp_path / "recorded"
    prepare(directory, recorded_video=video, tracking_engine="local", follower_mode="mc_velocity_position")
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    assert config["VideoSource"]["VIDEO_FILE_PATH"] == f"resources/{video}"
    assert (directory / f"resources/{video}").is_file()
    assert not config["GimbalTracker"]["ENABLED"]
    assert not config["GimbalTracker"]["CONTROL_ENABLED"]
    assert config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] == "CSRT"
    assert config["FOLLOWER_CIRCUIT_BREAKER"]
    assert validate(directory)["camera_host"] is None


def test_recorded_profile_refuses_camera_tracking(tmp_path):
    with pytest.raises(ValueError, match="Recorded-video SIH requires local"):
        prepare(tmp_path / "wrong", recorded_video="test9.mp4")
    assert not (tmp_path / "wrong").exists()


def test_recorded_follower_test_reuses_command_preview_and_keeps_commands_blocked(tmp_path):
    directory = tmp_path / "follower-test"
    prepare(directory, recorded_video="test11.mp4", tracking_engine="local",
        follower_mode="mc_velocity_chase", follower_execution_mode="COMMAND_PREVIEW")
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    assert config["Follower"]["FOLLOWER_EXECUTION_MODE"] == "COMMAND_PREVIEW"
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert validate(directory)["follower_execution_mode"] == "COMMAND_PREVIEW"


def test_follower_test_profile_refuses_a_live_camera(tmp_path):
    with pytest.raises(ValueError, match="requires recorded video"):
        prepare(tmp_path / "wrong", camera_host="192.0.2.108",
            rtsp_url="rtsp://192.0.2.108/stream=0", follower_execution_mode="COMMAND_PREVIEW")
    assert not (tmp_path / "wrong").exists()


def test_recorded_sih_opt_in_is_private_and_keeps_aircraft_commands_blocked(tmp_path):
    directory = tmp_path / "recorded-sih"
    prepare(directory, recorded_video="test11.mp4", tracking_engine="local",
        follower_mode="mc_velocity_position", allow_recorded_sih_following=True)
    config = yaml.safe_load((directory / "configs/config.yaml").read_text())
    assert config["Follower"]["SIH_RECORDED_VIDEO_FOLLOWING"] is True
    assert config["Follower"]["FOLLOWER_EXECUTION_MODE"] == "PX4"
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert validate(directory)["allow_recorded_sih_following"] is True
