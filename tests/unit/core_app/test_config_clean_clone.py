"""Clean-clone configuration behavior tests."""

import os
from pathlib import Path

import pytest

from classes.config_service import ConfigService
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit, pytest.mark.core_app]


def _new_config_service_for_project(project_root: Path) -> ConfigService:
    service = object.__new__(ConfigService)
    service._schema = {}
    service._config = {}
    service._config_raw = None
    service._default = {}
    service._audit_log = []
    service._project_root = project_root
    service._load_all()
    service._load_audit_log()
    return service


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
    (configs_dir / "config_schema.yaml").write_text(
        "schema_version: test\nsections: {}\ncategories: {}\n",
        encoding="utf-8",
    )
    (configs_dir / "config_default.yaml").write_text(
        "VideoSource:\n  DEFAULT_FPS: 31\n",
        encoding="utf-8",
    )

    service = _new_config_service_for_project(tmp_path)

    assert service.get_config("VideoSource")["DEFAULT_FPS"] == 31
    assert service.get_default("VideoSource")["DEFAULT_FPS"] == 31
    assert not (configs_dir / "config.yaml").exists()
