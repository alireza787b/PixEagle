"""An SIH profile must remain inert until an isolated PX4 run is verified."""

import json

import pytest
import yaml

from tools.prepare_simulation_profile import prepare, validate


def test_fixed_wing_image_profile_can_be_preselected_without_fabricating_aircraft_phase(tmp_path):
    directory = tmp_path / 'fw'
    prepare(directory, recorded_video='test4.mp4', tracking_engine='local',
            follower_mode='fw_navigation_chase', enable_altitude_control=True)
    config = yaml.safe_load((directory / 'configs/config.yaml').read_text())
    assert config['Follower']['FOLLOWER_MODE'] == 'fw_navigation_chase'
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert validate(directory)['follower_mode'] == 'fw_navigation_chase'


def test_stamped_gazebo_profile_is_explicit_and_keeps_commands_blocked(tmp_path):
    settings = dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id='test-world',
        world='training', image_topic='/camera/image', max_attitude_skew_s=.05)
    directory = tmp_path / 'gazebo'
    prepare(directory, gazebo_camera=settings, tracking_engine='local', follower_mode='mc_velocity_chase',
            enable_altitude_control=True)
    config = yaml.safe_load((directory / 'configs/config.yaml').read_text())
    assert config['VideoSource']['VIDEO_SOURCE_TYPE'] == 'GAZEBO_CAMERA'
    assert config['VideoSource']['GAZEBO_CAMERA'] == settings
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert config['Follower']['General']['ENABLE_ALTITUDE_CONTROL'] is True
    assert config['Follower']['FollowerOverrides']['MC_VELOCITY_CHASE']['ENABLE_ALTITUDE_CONTROL'] is True
    assert not config['GimbalTracker']['ENABLED']
    assert not config['GimbalTracker']['CONTROL_ENABLED']
    assert validate(directory)['video_source'] == 'gazebo'


def test_stamped_gazebo_and_udp_sources_cannot_be_combined(tmp_path):
    settings = dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id='test-world',
        world='training', image_topic='/camera/image', max_attitude_skew_s=.05)
    with pytest.raises(ValueError, match='one simulation video source'):
        prepare(tmp_path / 'mixed', gazebo_camera=settings, udp_url='udp://127.0.0.1:5600',
            tracking_engine='local', follower_mode='mc_velocity_chase')
    assert not (tmp_path / 'mixed').exists()


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
    assert config["GimbalTracker"]["GUIDANCE"]["POLICY"] == "reverse_then_yaw"
    assert config["GimbalTracker"]["GUIDANCE"]["TRANSITION_DWELL_MS"] == 300.0
    assert config["GimbalTracker"]["GUIDANCE"]["REARWARD_GRACE_MS"] == 500.0
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
        "PhaseOverrides": {"fixed_wing": {
            "MODE": "bounded_flight", "MAX_COAST_TIME_S": 8.0,
            "MAX_RETARGET_TIME_S": 8.0, "AUTHORITY_RESTORE_TIME_S": 0.5,
        }},
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


def test_gazebo_camera_profile_uses_normal_udp_capture_without_replay_or_gimbal(tmp_path):
    directory = tmp_path / 'gazebo'
    prepare(directory, udp_url='udp://127.0.0.1:5600', tracking_engine='local',
            follower_mode='mc_velocity_chase', enable_altitude_control=True,
            username='admin', password='admin')
    config = yaml.safe_load((directory / 'configs/config.yaml').read_text())
    manifest = validate(directory)
    assert manifest['video_source'] == 'udp'
    assert config['VideoSource']['VIDEO_SOURCE_TYPE'] == 'UDP_STREAM'
    assert config['VideoSource']['USE_GSTREAMER'] is True
    assert config['VideoSource']['UDP_URL'] == 'udp://127.0.0.1:5600'
    assert not config['GimbalTracker']['ENABLED'] and not config['GimbalTracker']['CONTROL_ENABLED']
    assert not config['Follower']['SIH_RECORDED_VIDEO_FOLLOWING']
    assert config['Follower']['FollowerOverrides']['MC_VELOCITY_CHASE']['ENABLE_ALTITUDE_CONTROL'] is True
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True
    assert config['Safety']['GlobalLimits']['ALTITUDE_SAFETY_ENABLED'] is True
    credentials = json.loads((directory / 'credentials.json').read_text())
    assert credentials['username'] == 'admin' and credentials['password'] == 'admin'


@pytest.mark.parametrize('url', ['http://127.0.0.1:5600', 'udp://192.0.2.1:5600',
                                 'udp://127.0.0.1:0', 'udp://user@127.0.0.1:5600',
                                 'udp://127.0.0.1:5600/path', 'udp://127.0.0.1:5600?x=1'])
def test_udp_training_profile_rejects_nonlocal_or_ambiguous_source_before_copy(tmp_path, url):
    with pytest.raises(ValueError):
        prepare(tmp_path / 'bad', udp_url=url, tracking_engine='local', follower_mode='mc_velocity_chase')
    assert not (tmp_path / 'bad').exists()


def test_profile_uses_catalog_compatible_mc_followers(tmp_path):
    directory = tmp_path / 'ground'
    prepare(directory, udp_url='udp://127.0.0.1:5600', tracking_engine='local',
            follower_mode='mc_velocity_ground')
    assert validate(directory)['follower_mode'] == 'mc_velocity_ground'


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_rendered_gimbal_keeps_video_and_external_observation_contracts_separate(tmp_path, mount):
    camera = dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id='test-clock',
        world='training', image_topic='/camera/image', max_attitude_skew_s=.05)
    gimbal = dict(socket_path='/run/pixeagle-gimbal/gimbal.sock', source_clock_id='test-clock',
        world='training', max_attitude_skew_s=.05)
    directory = tmp_path / 'rendered'
    prepare(directory, gazebo_camera=camera, gazebo_gimbal=gimbal, mount_type=mount,
        tracking_engine='camera', follower_mode='gm_velocity_vector', enable_altitude_control=True,
        username='admin', password='admin')
    config = yaml.safe_load((directory / 'configs/config.yaml').read_text())
    assert validate(directory)['gazebo_gimbal'] == gimbal
    assert config['VideoSource']['GAZEBO_CAMERA'] == camera
    assert config['VideoSource']['FIXED_CAMERA_CALIBRATION'] is None
    assert config['GimbalTracker']['GAZEBO_INPUT'] == gimbal
    assert config['GimbalTracker']['MOUNT_TYPE'] == mount
    assert config['GimbalTracker']['ENABLED'] and not config['GimbalTracker']['CONTROL_ENABLED']
    assert config['Tracking']['DEFAULT_TRACKING_ALGORITHM'] == 'Gimbal'
    assert config['FOLLOWER_CIRCUIT_BREAKER'] is True


@pytest.mark.parametrize('field', ['world', 'source_clock_id'])
def test_rendered_gimbal_refuses_another_world_or_clock_before_snapshot(tmp_path, field):
    camera = dict(socket_path='/run/camera.sock', source_clock_id='test-clock', world='training',
        image_topic='/camera/image', max_attitude_skew_s=.05)
    gimbal = dict(socket_path='/run/gimbal.sock', source_clock_id='test-clock', world='training', max_attitude_skew_s=.05)
    gimbal[field] = 'another'
    with pytest.raises(ValueError, match='same simulator clock/world'):
        prepare(tmp_path / 'bad', gazebo_camera=camera, gazebo_gimbal=gimbal,
            tracking_engine='camera', follower_mode='gm_velocity_vector')
    assert not (tmp_path / 'bad').exists()
