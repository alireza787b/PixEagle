"""Fresh ordinary defaults must not instantiate external camera control."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.camera_runtime import CameraRuntime


def test_fresh_recorded_local_workflow_has_no_camera_provider(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load((root / "configs/config_default.yaml").read_text())
    factory = Mock()
    monkeypatch.setattr("classes.camera_runtime.create_gimbal_provider", factory)
    runtime = CameraRuntime(SimpleNamespace(), config["GimbalTracker"])
    with pytest.raises(ValueError, match="disabled"):
        runtime.start()
    factory.assert_not_called()
    assert config["VideoSource"]["VIDEO_SOURCE_TYPE"] == "VIDEO_FILE"
    assert (root / config["VideoSource"]["VIDEO_FILE_PATH"]).is_file()
    assert config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] == "CSRT"
    assert config["GimbalTracker"]["CONTROL_ENABLED"] is False
    assert config["FOLLOWER_CIRCUIT_BREAKER"] is True
    assert config["Safety"]["GlobalLimits"]["ALTITUDE_SAFETY_ENABLED"] is True
    assert config["Follower"]["FOLLOWER_MODE"] == "mc_velocity_position"
    assert config["MC_VELOCITY_POSITION"]["ENABLE_YAW_CONTROL"] is True
    assert config["Follower"]["General"]["ENABLE_ALTITUDE_CONTROL"] is False
