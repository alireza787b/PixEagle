"""Deterministic tracker-in-loop validation tests."""

import json
import math
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from classes.app_controller import AppController
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
from classes.followers.yaw_rate_smoother import YawRateSmoother
from classes.setpoint_handler import SetpointHandler
from classes.tracker_trace import write_trace_jsonl
from tests.fixtures.synthetic_tracker_scene import (
    ColorBlobTrackerProbe,
    GimbalReplaySample,
    SyntheticTargetScene,
    synthetic_video_handler,
)


class _CapturingCommander:
    def __init__(self):
        self.intents = []

    def submit_intent(self, intent):
        self.intents.append(intent)
        return True

    def get_status(self):
        return {
            "exists": True,
            "running": True,
            "health_state": "healthy",
            "successful_publishes": 0,
            "rejected_intents": 0,
            "command_publication_source": "offboard_commander",
        }


CLIP_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "tracker_clips"
    / "linear_green_target.json"
)


def _build_position_follower_stub() -> MCVelocityPositionFollower:
    follower = MCVelocityPositionFollower.__new__(MCVelocityPositionFollower)
    follower.setpoint_handler = SetpointHandler("mc_velocity_position")
    follower._telemetry_metadata = {}
    follower.update_telemetry_metadata = MagicMock(
        side_effect=lambda key, value: follower._telemetry_metadata.__setitem__(key, value)
    )

    pid_yaw = MagicMock()
    pid_yaw.setpoint = 0.0
    pid_yaw.side_effect = lambda measurement: -measurement
    follower.pid_yaw_rate = pid_yaw

    pid_z = MagicMock()
    pid_z.setpoint = 0.0
    pid_z.side_effect = lambda measurement: -measurement
    follower.pid_z = pid_z

    follower.yaw_control_enabled = True
    follower.altitude_control_enabled = True
    follower.yaw_control_threshold = 0.0
    follower.command_smoothing_enabled = False
    follower.smoothing_factor = 0.0
    follower._last_yaw_command = 0.0
    follower._last_vertical_velocity_up_m_s = 0.0
    follower._last_update_time = time.time() - 0.05
    follower.yaw_smoother = YawRateSmoother(enabled=False)
    follower.max_vertical_velocity = 3.0
    follower.min_descent_height = 5.0
    follower.max_climb_height = 120.0
    follower._control_statistics = {
        "pid_updates": 0,
        "last_update_time": None,
        "commands_sent": 0,
        "initialization_time": None,
    }
    follower._update_pid_gains = MagicMock(return_value=True)
    follower.px4_controller = SimpleNamespace(current_altitude=50.0)
    return follower


def _build_gimbal_vector_follower_stub(*, active_path: bool = False) -> GMVelocityVectorFollower:
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.setpoint_handler = SetpointHandler("gm_velocity_vector")
    follower.current_velocity_magnitude = 1.25
    follower.last_velocity_vector = object()
    follower.following_active = True
    follower.failed_updates = 0
    follower.successful_updates = 0
    follower.total_follow_calls = 0
    follower.last_valid_time = time.time()
    follower.log_follower_event = MagicMock()
    follower._perform_safety_checks = MagicMock(
        return_value={"safe_to_proceed": True, "reason": "unit_test"}
    )
    if active_path:
        follower.filtered_angles = None
        follower.angle_deadzone = 0.0
        follower.angle_smoothing_alpha = 1.0
        follower.mount_yaw_offset = 0.0
        follower.mount_pitch_offset = 0.0
        follower.mount_roll_offset = 0.0
        follower.invert_yaw = False
        follower.invert_pitch = False
        follower.invert_roll = False
        follower.mount_type = "HORIZONTAL"
        follower.max_velocity = 1.25
        follower.ramp_acceleration = 1000.0
        follower.enable_altitude_control = False
        follower.min_velocity = 0.0
        follower.enable_auto_mode_switching = False
        follower.active_lateral_mode = "sideslip"
        follower.command_smoothing_enabled = False
        follower.last_command_vector = None
        follower.last_update_time = time.time() - 0.05
        follower.emergency_stop_active = False
        follower.safety_violations_count = 0
    return follower


def _build_app_controller_stub(follower, *, external_tracker: bool = False):
    controller = AppController.__new__(AppController)
    commander = _CapturingCommander()
    controller.follower = follower
    controller.offboard_commander = commander
    if external_tracker:
        controller.tracker = SimpleNamespace(
            is_external_tracker=True,
            get_capabilities=lambda: {"requires_video": False},
        )
    else:
        controller.tracker = SimpleNamespace(is_external_tracker=False)
    controller.following_active = True
    controller.video_handler = SimpleNamespace(
        get_frame_status=lambda: {
            "source": "synthetic_test",
            "status": "fresh",
            "usable_for_following": True,
            "timestamp": time.time(),
        }
    )
    return controller, commander


def test_synthetic_color_blob_trace_is_deterministic_and_command_usable():
    scene = SyntheticTargetScene.from_clip_manifest(CLIP_FIXTURE)
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)

    trace = []
    for sample in scene.samples[:3]:
        success, bbox = tracker.update(sample.frame)
        output = tracker.get_output()
        trace.append((bbox, output.position_2d))

        assert success is True
        assert bbox == sample.bbox
        assert output.raw_data["has_output"] is True
        assert output.raw_data["usable_for_following"] is True
        assert output.raw_data["freshness_reason"] == "measurement"
        assert output.metadata["has_output"] is True
        assert output.position_2d == pytest.approx(sample.expected_position_2d)

    assert trace == [
        ((80, 100, 40, 30), pytest.approx((-0.6875, -0.5208333333))),
        ((120, 110, 40, 30), pytest.approx((-0.5625, -0.4791666667))),
        ((160, 120, 40, 30), pytest.approx((-0.4375, -0.4375))),
    ]


def test_synthetic_tracker_output_drives_position_follower_command_intent():
    scene = SyntheticTargetScene([(390, 210, 40, 30)])
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)
    success, _ = tracker.update(scene[0].frame)
    output = tracker.get_output()

    follower = _build_position_follower_stub()
    assert follower.follow_target(output) is True
    intent = follower.get_last_command_intent()

    assert success is True
    assert output.position_2d[0] > 0.0
    assert intent is not None
    assert intent.reason == "mc_velocity_position_normal_tracking"
    assert intent.fields["yawspeed_deg_s"] < 0.0
    assert math.isfinite(intent.fields["vel_body_down"])
    assert follower._control_statistics["commands_sent"] == 1
    assert follower._telemetry_metadata["control_active"] is True
    assert follower._telemetry_metadata["last_command_intent"]["fields"] == intent.fields


@pytest.mark.asyncio
async def test_synthetic_occlusion_keeps_output_visible_but_not_usable_for_following():
    scene = SyntheticTargetScene.from_clip_manifest(CLIP_FIXTURE)
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)
    tracker.update(scene[2].frame)

    success, bbox = tracker.update(scene[3].frame)
    output = tracker.get_output()

    assert success is False
    assert bbox == scene[2].bbox
    assert output.tracking_active is True
    assert output.raw_data["has_output"] is True
    assert output.raw_data["usable_for_following"] is False
    assert output.raw_data["data_is_stale"] is True
    assert output.raw_data["freshness_reason"] == "prediction_only"
    assert output.metadata["has_output"] is True
    assert output.metadata["usable_for_following"] is False

    follower = _build_position_follower_stub()
    controller, commander = _build_app_controller_stub(follower)
    assert await controller._follow_tracker_output(output) is True

    assert len(commander.intents) == 1
    intent = commander.intents[0]
    assert intent.reason == "mc_velocity_position_inactive_hold"
    assert intent.fields == {
        "vel_body_fwd": 0.0,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 0.0,
    }
    assert follower._telemetry_metadata["target_valid"] is False
    assert follower._telemetry_metadata["target_lost"] is True
    assert follower._telemetry_metadata["control_active"] is False


@pytest.mark.asyncio
async def test_sitl_validation_injection_uses_existing_target_loss_path():
    scene = SyntheticTargetScene.from_clip_manifest(CLIP_FIXTURE)
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)
    tracker.update(scene[2].frame)
    tracker.update(scene[3].frame)
    stale_output = tracker.get_output()

    follower = _build_position_follower_stub()
    controller, commander = _build_app_controller_stub(follower)

    result = await controller.inject_tracker_output_for_validation(
        stale_output,
        source="unit_test.sitl_target_loss",
    )

    assert result["status"] == "accepted"
    assert result["accepted"] is True
    assert result["injection"]["source"] == "unit_test.sitl_target_loss"
    assert result["injection"]["input_tracking_active"] is True
    assert result["injection"]["processed_tracking_active"] is False
    assert result["injection"]["processed_usable_for_following"] is False
    assert result["command_intent"]["reason"] == "mc_velocity_position_inactive_hold"
    assert result["offboard_commander"]["exists"] is True
    assert result["offboard_commander"]["running"] is True
    assert result["offboard_commander"]["command_publication_source"] == "offboard_commander"
    assert len(commander.intents) == 1


@pytest.mark.asyncio
async def test_sitl_validation_injection_refuses_when_following_is_inactive():
    scene = SyntheticTargetScene([(390, 210, 40, 30)])
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)
    tracker.update(scene[0].frame)
    output = tracker.get_output()

    follower = _build_position_follower_stub()
    controller, commander = _build_app_controller_stub(follower)
    controller.following_active = False

    result = await controller.inject_tracker_output_for_validation(
        output,
        source="unit_test.inactive_following",
    )

    assert result["status"] == "rejected"
    assert result["accepted"] is False
    assert result["reason"] == "following_not_active"
    assert len(commander.intents) == 0


def test_active_gimbal_replay_drives_vector_follower_command_intent():
    output = GimbalReplaySample(
        yaw_deg=20.0,
        pitch_deg=0.0,
        tracking_active=True,
        fresh=True,
    ).to_tracker_output()
    follower = _build_gimbal_vector_follower_stub(active_path=True)

    assert follower.follow_target(output) is True

    intent = follower.get_last_command_intent()
    assert intent is not None
    assert intent.reason == "gm_velocity_vector_normal_tracking"
    assert intent.fields["vel_body_fwd"] > 0.0
    assert intent.fields["vel_body_right"] > 0.0
    assert intent.fields["vel_body_down"] == 0.0
    assert intent.fields["yawspeed_deg_s"] == 0.0
    assert follower.following_active is True
    assert follower.successful_updates == 1
    assert follower.failed_updates == 0


@pytest.mark.asyncio
async def test_gimbal_replay_unusable_output_zeroes_vector_follower_command():
    stale_output = GimbalReplaySample(
        yaw_deg=12.0,
        pitch_deg=-8.0,
        tracking_active=False,
        fresh=False,
        reason="stale_gimbal_status",
    ).to_tracker_output()
    follower = _build_gimbal_vector_follower_stub()
    controller, commander = _build_app_controller_stub(follower, external_tracker=True)

    assert follower.should_process_inactive_tracker_output(stale_output) is True
    assert await controller._follow_tracker_output(stale_output) is True

    assert len(commander.intents) == 1
    intent = commander.intents[0]
    assert intent is not None
    assert intent.reason == "gm_velocity_vector_unusable_external_input"
    assert intent.fields == {
        "vel_body_fwd": 0.0,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 0.0,
    }
    assert follower.current_velocity_magnitude == 0.0
    assert follower.following_active is False
    assert follower.total_follow_calls == 1
    follower.log_follower_event.assert_called_once()


@pytest.mark.asyncio
async def test_synthetic_tracker_app_controller_smoke_writes_normalized_trace_artifacts(tmp_path):
    scene = SyntheticTargetScene.from_clip_manifest(CLIP_FIXTURE)
    tracker = ColorBlobTrackerProbe(video_handler=synthetic_video_handler())
    tracker.start_tracking(scene[0].frame, scene[0].bbox)
    follower = _build_position_follower_stub()
    controller, commander = _build_app_controller_stub(follower)
    tracker_trace = tmp_path / "trace" / "tracker_command_trace.jsonl"
    offboard_trace = tmp_path / "trace" / "offboard_publish_trace.jsonl"
    trace_status = controller.configure_tracker_trace_artifacts(
        tracker_command_trace_path=tracker_trace,
        offboard_publish_trace_path=offboard_trace,
        source="unit_test.synthetic_color_blob",
    )

    assert trace_status["enabled"] is True
    assert "does not prove PX4" in trace_status["claim_boundary"]

    for index, sample in enumerate(scene.samples[:3]):
        success, bbox = tracker.update(sample.frame)
        output = tracker.get_output()
        accepted = await controller._follow_tracker_output(output)

        assert success is True
        assert bbox == sample.bbox
        assert accepted is True
        if index == 0:
            assert not offboard_trace.exists()
        controller._record_offboard_publish_result(
            {
                "command_intent": commander.intents[-1],
                "publish_status": {
                    "last_publish_success": True,
                    "command_publication_source": "offboard_commander",
                },
            }
        )

    tracker_lines = [
        json.loads(line)
        for line in tracker_trace.read_text(encoding="utf-8").splitlines()
    ]
    offboard_lines = [
        json.loads(line)
        for line in offboard_trace.read_text(encoding="utf-8").splitlines()
    ]

    assert [line["frame_index"] for line in tracker_lines] == [0, 1, 2]
    assert all(line["schema_version"] == 1 for line in tracker_lines)
    assert all(line["record_type"] == "tracker_command" for line in tracker_lines)
    assert all(line["dispatch_accepted"] is True for line in tracker_lines)
    assert all(line["source"] == "unit_test.synthetic_color_blob" for line in tracker_lines)
    assert all(
        line["tracker_output"]["tracker_id"].startswith("synthetic_color_blob_")
        for line in tracker_lines
    )
    assert all(
        line["tracker_output"]["usable_for_following"] is True
        for line in tracker_lines
    )
    assert tracker_lines[0]["tracker_output"]["bbox"] == [80, 100, 40, 30]
    assert tracker_lines[0]["command_intent"]["reason"] == (
        "mc_velocity_position_normal_tracking"
    )
    assert set(tracker_lines[0]["command_intent"]["fields"]) == {
        "vel_body_fwd",
        "vel_body_right",
        "vel_body_down",
        "yawspeed_deg_s",
    }
    assert tracker_lines[0]["offboard_commander"]["command_publication_source"] == (
        "offboard_commander"
    )
    assert tracker_lines[0]["frame_status"]["status"] == "fresh"
    assert "does not prove PX4" in tracker_lines[0]["claim_boundary"]

    assert [line["sequence"] for line in offboard_lines] == [0, 1, 2]
    assert all(line["record_type"] == "offboard_publish" for line in offboard_lines)
    assert all(line["publish_success"] is True for line in offboard_lines)
    assert all(line["source"] == "unit_test.synthetic_color_blob" for line in offboard_lines)
    assert offboard_lines[0]["command_intent"]["reason"] == (
        "mc_velocity_position_normal_tracking"
    )
    assert "does not prove PX4" in offboard_lines[0]["claim_boundary"]


def test_trace_jsonl_writer_rejects_non_finite_values(tmp_path):
    trace_path = tmp_path / "trace" / "tracker_command_trace.jsonl"

    with pytest.raises(ValueError):
        write_trace_jsonl(
            trace_path,
            [
                {
                    "schema_version": 1,
                    "record_type": "tracker_command",
                    "timestamp": float("nan"),
                }
            ],
        )
