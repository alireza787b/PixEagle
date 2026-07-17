"""Clean-clone configuration behavior tests."""

import os
from pathlib import Path
import shutil

import yaml

import pytest

from classes.config_service import ConfigService
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit, pytest.mark.core_app]
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _new_config_service_for_project(project_root: Path) -> ConfigService:
    return ConfigService(project_root=project_root)


def test_missing_default_runtime_config_falls_back_to_checked_in_defaults(tmp_path):
    """Default runtime config path should read defaults when config.yaml is absent."""
    configs_dir = tmp_path / "configs"
    runtime_config = configs_dir / "config.yaml"
    default_config = configs_dir / "config_default.yaml"
    configs_dir.mkdir()
    default_config.write_text(
        "VideoSource:\n  DEFAULT_FPS: 27\nSafety:\n  GlobalLimits: {}\n",
        encoding="utf-8",
    )

    original_default = Parameters._DEFAULT_CONFIG_FILE
    original_fallback = Parameters._FALLBACK_CONFIG_FILE
    try:
        Parameters._DEFAULT_CONFIG_FILE = os.path.normpath(str(runtime_config))
        Parameters._FALLBACK_CONFIG_FILE = os.path.normpath(str(default_config))

        Parameters.load_config(str(runtime_config))

        assert Parameters._loaded_config_file == os.path.normpath(str(default_config))
        assert Parameters.DEFAULT_FPS == 27
        assert not runtime_config.exists()
    finally:
        Parameters._DEFAULT_CONFIG_FILE = original_default
        Parameters._FALLBACK_CONFIG_FILE = original_fallback
        Parameters.reload_config()


def test_missing_custom_config_path_still_fails(tmp_path):
    """Only the default runtime config path should use the clean-clone fallback."""
    missing_custom_config = tmp_path / "custom.yaml"

    with pytest.raises(FileNotFoundError):
        Parameters.load_config(str(missing_custom_config))


def test_config_service_uses_defaults_read_only_when_runtime_config_is_absent(tmp_path):
    """ConfigService should not create config.yaml just to read default values."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    for filename in (
        "config_default.yaml",
        "config_schema.yaml",
        "config_retirements.yaml",
    ):
        shutil.copy2(PROJECT_ROOT / "configs" / filename, configs_dir / filename)
    expected_defaults = yaml.safe_load(
        (configs_dir / "config_default.yaml").read_text(encoding="utf-8")
    )

    service = _new_config_service_for_project(tmp_path)

    expected_fps = expected_defaults["VideoSource"]["DEFAULT_FPS"]
    assert service.get_config("VideoSource")["DEFAULT_FPS"] == expected_fps
    assert service.get_default("VideoSource")["DEFAULT_FPS"] == expected_fps
    assert not (configs_dir / "config.yaml").exists()


def test_config_service_keeps_the_normalized_runtime_candidate_in_memory(tmp_path):
    """A validated legacy alias cannot poison later unrelated config writes."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    for filename in (
        "config_default.yaml",
        "config_schema.yaml",
        "config_retirements.yaml",
    ):
        shutil.copy2(PROJECT_ROOT / "configs" / filename, configs_dir / filename)

    runtime_config = yaml.safe_load(
        (configs_dir / "config_default.yaml").read_text(encoding="utf-8")
    )
    runtime_config["SmartTracker"]["TRACKER_TYPE"] = "botsort_reid"
    (configs_dir / "config.yaml").write_text(
        yaml.safe_dump(runtime_config, sort_keys=False),
        encoding="utf-8",
    )

    service = _new_config_service_for_project(tmp_path)

    assert service.get_parameter("SmartTracker", "TRACKER_TYPE") == "botsort"
    result = service.set_parameter("VideoSource", "CAPTURE_WIDTH", 800)
    assert result.valid is True
