"""Tests for explicit PixEagle setup profiles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "apply-setup-profile.py"
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "config_default.yaml"
CONFIG_SCHEMA = PROJECT_ROOT / "configs" / "config_schema.yaml"
QGC_DOCS = [
    PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "remote-media-security.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "qgc-http-websocket-source-plan.md",
    PROJECT_ROOT / "docs" / "video" / "03-gstreamer" / "output-pipeline.md",
]


pytestmark = [pytest.mark.unit]


def _run_profile(*args: str, config_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--defaults",
            str(DEFAULT_CONFIG),
            "--config",
            str(config_path),
            *args,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_local_dev_profile_keeps_backend_loopback_only(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile("--profile", "local_dev", config_path=config_path)

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    assert config["Streaming"]["API_EXPOSURE_MODE"] == "local_only"
    assert config["Streaming"]["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert config["Streaming"]["API_AUTH_MODE"] == "local_compat"
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == []
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False
    assert config["GStreamer"]["GSTREAMER_HOST"] == "127.0.0.1"
    assert config["GStreamer"]["GSTREAMER_PORT"] == 5600


def test_field_qgc_video_profile_enables_only_udp_video_output(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "field_qgc_video",
        "--gcs-host",
        "192.168.10.20",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    assert config["Streaming"]["API_EXPOSURE_MODE"] == "local_only"
    assert config["Streaming"]["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert config["Streaming"]["API_AUTH_MODE"] == "local_compat"
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == []
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is True
    assert config["GStreamer"]["GSTREAMER_HOST"] == "192.168.10.20"
    assert config["GStreamer"]["GSTREAMER_PORT"] == 5600


def test_field_qgc_video_profile_requires_gcs_host(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile("--profile", "field_qgc_video", config_path=config_path)

    assert result.returncode == 2
    assert "requires --gcs-host" in result.stderr
    assert not config_path.exists()


@pytest.mark.parametrize("bad_port", ["0", "65536"])
def test_field_qgc_video_profile_rejects_invalid_ports(tmp_path, bad_port):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "field_qgc_video",
        "--gcs-host",
        "192.168.10.20",
        "--gstreamer-port",
        bad_port,
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "--gstreamer-port must be in the range" in result.stderr
    assert not config_path.exists()


@pytest.mark.parametrize(
    "profile",
    ["demo_lan_browser", "production_remote", "unsafe_demo_lan_media_only"],
)
def test_deferred_or_unsafe_profiles_fail_closed_without_writing_config(tmp_path, profile):
    config_path = tmp_path / "config.yaml"

    result = _run_profile("--profile", profile, config_path=config_path)

    assert result.returncode == 2
    assert "not automated" in result.stderr or "does not currently provide" in result.stderr
    assert not config_path.exists()


def test_dry_run_does_not_create_runtime_config(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "field_qgc_video",
        "--gcs-host",
        "192.168.10.20",
        "--dry-run",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert "GStreamer.ENABLE_GSTREAMER_STREAM" in result.stdout
    assert not config_path.exists()


def test_list_profiles_reports_all_supported_defined_and_unsafe_profiles(tmp_path):
    result = _run_profile("--list-profiles", config_path=tmp_path / "config.yaml")

    assert result.returncode == 0, result.stderr
    for profile_name in [
        "local_dev",
        "field_qgc_video",
        "demo_lan_browser",
        "production_remote",
        "unsafe_demo_lan_media_only",
    ]:
        assert profile_name in result.stdout


def test_qgc_field_video_default_port_is_single_source_of_truth():
    config = _read_yaml(DEFAULT_CONFIG)
    schema = _read_yaml(CONFIG_SCHEMA)

    assert config["GStreamer"]["GSTREAMER_PORT"] == 5600
    assert (
        schema["sections"]["GStreamer"]["parameters"]["GSTREAMER_PORT"]["default"]
        == 5600
    )

    script_text = SCRIPT.read_text(encoding="utf-8")
    assert "QGC_DEFAULT_UDP_H264_PORT = 5600" in script_text
    assert "Default: 5600" in script_text

    for doc in QGC_DOCS:
        text = doc.read_text(encoding="utf-8")
        assert "5600" in text, f"{doc.relative_to(PROJECT_ROOT)} missing QGC port 5600"
        assert "GSTREAMER_PORT: 2000" not in text
        assert "port 2000" not in text
