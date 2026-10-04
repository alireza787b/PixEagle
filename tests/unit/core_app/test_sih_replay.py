"""Recorded input must never authorize a hardware or unowned publisher."""

import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from classes import sih_replay
from classes.following_readiness import evaluate_following_start_readiness
from classes.frame_publisher import CaptureStamp
from classes.parameters import Parameters

pytestmark = pytest.mark.unit


@pytest.fixture
def bench(monkeypatch, tmp_path):
    monkeypatch.setattr(Parameters, "SIH_RECORDED_VIDEO_FOLLOWING", True, raising=False)
    monkeypatch.setattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4")
    monkeypatch.setattr(Parameters, "VIDEO_SOURCE_TYPE", "VIDEO_FILE")
    config = yaml.safe_load(Path("configs/config_default.yaml").read_text())
    config["PX4"].update(SYSTEM_ADDRESS="udpin://127.0.0.1:14540", EXTERNAL_MAVSDK_SERVER=True,
        MAVSDK_SERVER_ADDRESS="127.0.0.1", MAVSDK_SERVER_PORT=50051)
    config["MAVLink"].update(MAVLINK_ENABLED=True, MAVLINK_HOST="127.0.0.1", MAVLINK_PORT=8088)
    monkeypatch.setattr(Parameters, "_raw_config", config)
    path = tmp_path / "logs/sih-replay-binding.json"
    path.parent.mkdir()
    binding = {"kind": "owned-isolated-sih-v1", "instance_id": "bench-instance",
        "simulated_autopilot_uid": "123", "network_namespace": os.readlink("/proc/self/ns/net")}
    path.write_text(json.dumps(binding))
    path.chmod(0o600)
    monkeypatch.setenv("PIXEAGLE_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PIXEAGLE_SIH_REPLAY_BINDING", str(path))
    monkeypatch.setenv("PIXEAGLE_INSTANCE_ID", "bench-instance")
    monkeypatch.setattr(sih_replay, "supervisor_available", lambda: True)
    command = {"connected": True, "autopilot_uid": "123", "connection_generation": "2:1"}
    telemetry = {"connected": True, "fresh": True, "autopilot_uid": "123", "connection_generation": "3"}
    flight = {"fresh": True, "autopilot_uid": "123", "connection_generation": "3"}
    raw = {"source": "fresh", "replay_source": True, "connection_open": True,
        "usable_for_following": False, "reason": "video_file_replay_frame"}
    app = SimpleNamespace(
        following_active=False,
        px4_interface=SimpleNamespace(get_aircraft_identity=lambda: command),
        mavlink_data_manager=SimpleNamespace(get_aircraft_identity=lambda: telemetry, get_flight_state=lambda: flight),
        video_handler=SimpleNamespace(get_frame_status=lambda: raw,
            get_capture_stamp=lambda: CaptureStamp("source", "1", time.monotonic(), "fresh")),
        _tracker_requires_video_for_following=lambda: True,
    )
    return SimpleNamespace(app=app, raw=raw, command=command, telemetry=telemetry,
        flight=flight, path=path, binding=binding, config=config)


def test_authorized_replay_preserves_truthful_provenance_and_requires_fresh_measurement(bench):
    result = sih_replay.following_video_frame_status(bench.app, bench.raw)
    assert result["sih_replay_authorized"] is True
    assert result["usable_for_following"] is True
    assert result["replay_source"] is True
    assert bench.raw["usable_for_following"] is False
    readiness = evaluate_following_start_readiness(bench.app, runtime_status={"usable_for_following": True})
    assert readiness["usable_for_following"] is True
    stale_target = evaluate_following_start_readiness(bench.app, runtime_status={"usable_for_following": False})
    assert stale_target["usable_for_following"] is False


@pytest.mark.parametrize("attribute,value", [
    ("SIH_RECORDED_VIDEO_FOLLOWING", False), ("SIH_RECORDED_VIDEO_FOLLOWING", "true"),
    ("FOLLOWER_EXECUTION_MODE", "COMMAND_PREVIEW"), ("VIDEO_SOURCE_TYPE", "RTSP_OPENCV"),
])
def test_config_cannot_authorize_other_execution_boundaries(bench, monkeypatch, attribute, value):
    monkeypatch.setattr(Parameters, attribute, value)
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


def test_unmanaged_backend_is_refused(bench, monkeypatch):
    monkeypatch.setattr(sih_replay, "supervisor_available", lambda: False)
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


@pytest.mark.parametrize("key,value", [
    ("kind", "other"), ("instance_id", "other"), ("network_namespace", "other"),
    ("simulated_autopilot_uid", "0"), ("simulated_autopilot_uid", "456"),
])
def test_wrong_launcher_binding_is_refused(bench, key, value):
    bench.binding[key] = value
    bench.path.write_text(json.dumps(bench.binding))
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


@pytest.mark.parametrize("owner,key,value", [
    ("command", "connected", False), ("command", "autopilot_uid", "456"),
    ("command", "connection_generation", None), ("telemetry", "fresh", False),
    ("telemetry", "autopilot_uid", "456"), ("flight", "fresh", False),
    ("flight", "connection_generation", "4"),
])
def test_identity_or_generation_change_revokes_authorization(bench, owner, key, value):
    getattr(bench, owner)[key] = value
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


def test_active_session_cannot_redirect_to_another_uid(bench):
    bench.app.following_active = True
    bench.app._following_session_aircraft_uid = "456"
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


def test_saved_external_command_route_is_refused(bench):
    bench.config["PX4"]["MAVSDK_SERVER_ADDRESS"] = "192.0.2.108"
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


@pytest.mark.parametrize("source,age", [("cached", 0), ("fresh", 2), ("fresh", -1)])
def test_cached_frozen_and_invalid_capture_times_remain_unusable(bench, source, age):
    bench.app.video_handler.get_capture_stamp = lambda: CaptureStamp("source", "1", time.monotonic() - age, source)
    result = sih_replay.following_video_frame_status(bench.app, bench.raw)
    assert result["sih_replay_authorized"] is False
    assert result["usable_for_following"] is False


def test_missing_or_public_binding_is_refused(bench):
    bench.path.chmod(0o644)
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)
    bench.path.unlink()
    assert not sih_replay.isolated_sih_replay_authorized(bench.app)


def test_status_payload_cannot_grant_its_own_authorization(bench, monkeypatch):
    monkeypatch.setattr(Parameters, "SIH_RECORDED_VIDEO_FOLLOWING", False)
    bench.raw["sih_replay_authorized"] = True
    result = sih_replay.following_video_frame_status(bench.app, bench.raw)
    assert not result.get("sih_replay_authorized")
    assert result["usable_for_following"] is False


@pytest.mark.asyncio
async def test_authorization_loss_requests_immediate_existing_handoff(bench):
    from unittest.mock import AsyncMock
    from classes.app_controller import AppController
    app = object.__new__(AppController)
    app.following_active = True
    app.follower = object()
    app._tracking_session_generation = 1
    app._is_command_preview_session = lambda: False
    app._tracker_requires_video_for_following = lambda: True
    app._get_video_frame_status_for_following = lambda: bench.raw
    app._stop_following_after_continuity_failure = AsyncMock()
    output = MagicMock()
    assert not await app._dispatch_tracker_output_on_flight_loop(output)
    app._stop_following_after_continuity_failure.assert_awaited_once_with("sih_replay_authorization_lost")


@pytest.mark.asyncio
async def test_optional_replay_display_does_not_interrupt_nonvideo_guidance(bench, monkeypatch):
    from unittest.mock import AsyncMock
    from classes.app_controller import AppController, TargetEvidenceSnapshot
    app = object.__new__(AppController)
    app.following_active = True
    app.follower = object()
    app._tracking_session_generation = 1
    app._is_command_preview_session = lambda: False
    app._tracker_requires_video_for_following = lambda: False
    app._get_video_frame_status_for_following = lambda: bench.raw
    app._stop_following_after_continuity_failure = AsyncMock()
    # Stop at the existing evidence boundary, after replay enforcement.
    marker = RuntimeError("nonvideo evidence reached")
    monkeypatch.setattr(TargetEvidenceSnapshot, "from_tracker_output", MagicMock(side_effect=marker))
    with pytest.raises(RuntimeError, match="nonvideo evidence reached"):
        await app._dispatch_tracker_output_on_flight_loop(MagicMock())
    app._stop_following_after_continuity_failure.assert_not_awaited()


@pytest.mark.parametrize("authorized,expected", [
    (True, "tracker_not_usable"), (False, "video_replay_not_authorized"),
])
def test_prediction_only_target_is_not_mislabelled_as_replay_refusal(authorized, expected):
    from classes.following_readiness import following_readiness_failure_code
    readiness = {"tracker_requires_video": True, "reason": "prediction_only",
        "video_frame_status": {"replay_source": True, "sih_replay_authorized": authorized,
            "usable_for_following": authorized}}
    assert following_readiness_failure_code(readiness) == expected
