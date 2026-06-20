"""Tests for explicit PixEagle setup profiles."""

from __future__ import annotations

import subprocess
import sys
import json
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
    assert config["Streaming"]["API_CORS_ALLOWED_ORIGINS"] == [
        "http://127.0.0.1:3040",
        "http://localhost:3040",
        "http://127.0.0.1:5077",
        "http://localhost:5077",
    ]
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


def test_unsafe_demo_lan_media_only_fails_closed_without_writing_config(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "unsafe_demo_lan_media_only",
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "does not currently provide" in result.stderr
    assert not config_path.exists()


def test_demo_lan_browser_profile_generates_hashed_session_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "192.168.10.42",
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_EXPOSURE_MODE"] == "trusted_lan_legacy"
    assert streaming["HTTP_STREAM_HOST"] == "0.0.0.0"
    assert streaming["HTTP_STREAM_PORT"] == 5077
    assert streaming["API_AUTH_MODE"] == "browser_session"
    assert streaming["API_SESSION_USER_FILE"] == str(user_file)
    assert streaming["API_SESSION_COOKIE_SECURE"] is False
    assert streaming["API_ALLOWED_HOSTS"] == ["192.168.10.42"]
    assert "http://192.168.10.42:3040" in streaming["API_CORS_ALLOWED_ORIGINS"]
    assert "http://192.168.10.42:5077" in streaming["API_CORS_ALLOWED_ORIGINS"]
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False

    payload = json.loads(user_file.read_text(encoding="utf-8"))
    user_record = payload["users"][0]
    assert user_record["username"] == "pixeagle-demo"
    assert user_record["role"] == "operator"
    assert user_record["enabled"] is True
    assert user_record["password_pbkdf2_sha256"].startswith("pbkdf2_sha256$")
    assert "password" not in user_record
    assert "plaintext_password" not in user_record
    assert user_file.stat().st_mode & 0o777 == 0o600
    assert "Demo password:" in result.stdout
    assert "LAB ONLY" in result.stdout
    assert "backend/API media port 5077" in result.stdout


def test_production_remote_profile_generates_loopback_reverse_proxy_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_EXPOSURE_MODE"] == "trusted_lan_legacy"
    assert streaming["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert streaming["HTTP_STREAM_PORT"] == 5077
    assert streaming["API_AUTH_MODE"] == "browser_session"
    assert streaming["API_SESSION_USER_FILE"] == str(user_file)
    assert streaming["API_SESSION_COOKIE_SECURE"] is True
    assert streaming["API_SECURITY_AUDIT_ENABLED"] is True
    assert streaming["API_ALLOWED_HOSTS"] == ["pixeagle.example:443"]
    assert streaming["API_CORS_ALLOWED_ORIGINS"] == ["https://pixeagle.example"]
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False

    payload = json.loads(user_file.read_text(encoding="utf-8"))
    user_record = payload["users"][0]
    assert user_record["username"] == "pixeagle-operator"
    assert user_record["role"] == "operator"
    assert user_record["enabled"] is True
    assert user_record["password_pbkdf2_sha256"].startswith("pbkdf2_sha256$")
    assert "password" not in user_record
    assert "plaintext_password" not in user_record
    assert user_file.stat().st_mode & 0o777 == 0o600
    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert handoff["username"] == "pixeagle-operator"
    assert handoff["role"] == "operator"
    assert handoff["password"]
    assert handoff["one_time_handoff"] is True
    assert handoff_file.stat().st_mode & 0o777 == 0o600
    assert "Production password:" not in result.stdout
    assert "credential handoff file" in result.stdout
    assert "PRODUCTION REMOTE" in result.stdout
    assert "/pixeagle-api" in result.stdout


def test_production_remote_profile_accepts_custom_https_origin_port(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--public-origin",
        "https://pixeagle.example:8443",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_ALLOWED_HOSTS"] == ["pixeagle.example:8443"]
    assert streaming["API_CORS_ALLOWED_ORIGINS"] == [
        "https://pixeagle.example:8443"
    ]


def test_production_remote_profile_canonicalizes_explicit_default_https_port(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--public-origin",
        "https://pixeagle.example:443",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    streaming = _read_yaml(config_path)["Streaming"]
    assert streaming["API_ALLOWED_HOSTS"] == ["pixeagle.example:443"]
    assert streaming["API_CORS_ALLOWED_ORIGINS"] == ["https://pixeagle.example"]


def test_production_remote_profile_requires_public_host_and_explicit_user_file(tmp_path):
    config_path = tmp_path / "config.yaml"

    missing_host = _run_profile(
        "--profile",
        "production_remote",
        "--session-user-file",
        str(tmp_path / "production-users.json"),
        config_path=config_path,
    )
    assert missing_host.returncode == 2
    assert "requires --public-host" in missing_host.stderr
    assert not config_path.exists()

    missing_user_file = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        config_path=config_path,
    )
    assert missing_user_file.returncode == 2
    assert "requires --session-user-file" in missing_user_file.stderr
    assert not config_path.exists()


@pytest.mark.parametrize(
    "bad_host",
    [
        "0.0.0.0",
        "0.0.0.1",
        "127.0.0.1",
        "localhost",
        "192.0.0.1",
        "192.0.2.1",
        "198.18.0.1",
        "198.51.100.4",
        "203.0.113.9",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "2001:db8::1",
        "ff02::1",
        "fe80::42",
        "[fe80::42]",
        "https://pixeagle.example",
        "user:secret@pixeagle.example",
        "pixeagle.example?token=x",
        "pixeagle.example#frag",
        "pixeagle.example:8443",
        "[fc00::42]:8443",
        "fe80::42%eth0",
        "*",
    ],
)
def test_production_remote_profile_rejects_unsafe_public_hosts(tmp_path, bad_host):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        bad_host,
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert not config_path.exists()
    assert not user_file.exists()


@pytest.mark.parametrize(
    "bad_origin",
    [
        "http://pixeagle.example",
        "https://other.example",
        "https://pixeagle.example/api",
        "https://user:secret@pixeagle.example",
        "https://pixeagle.example?token=x",
        "https://pixeagle.example#frag",
        "https://pixeagle.example:notaport",
    ],
)
def test_production_remote_profile_rejects_unsafe_public_origins(tmp_path, bad_origin):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--public-origin",
        bad_origin,
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert not config_path.exists()
    assert not user_file.exists()


def test_production_remote_profile_dry_run_does_not_write_config_or_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--dry-run",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert "Would generate production browser-session user file" in result.stdout
    assert "PRODUCTION REMOTE" in result.stdout
    assert "Production password:" not in result.stdout
    assert not config_path.exists()
    assert not user_file.exists()


def test_production_remote_profile_refuses_existing_credentials_without_rotation(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"
    user_file.write_text('{"users": []}\n', encoding="utf-8")

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "already exists" in result.stderr
    assert not config_path.exists()


def test_production_remote_profile_requires_safe_noninteractive_password_handoff(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "requires --credential-handoff-file" in result.stderr
    assert not config_path.exists()
    assert not user_file.exists()


def test_production_remote_profile_explicit_stdout_password_opt_in(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--show-generated-password",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Production password:" in result.stdout
    assert config_path.exists()
    assert user_file.exists()


@pytest.mark.parametrize("collision_target", ["config", "defaults", "handoff"])
def test_production_remote_profile_rejects_output_path_collisions(
    tmp_path, collision_target
):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"
    defaults_path = DEFAULT_CONFIG

    if collision_target == "config":
        user_file = config_path
    elif collision_target == "defaults":
        user_file = defaults_path
    else:
        handoff_file = user_file

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "must not resolve to the same path" in result.stderr
    assert not config_path.exists()
    assert not handoff_file.exists()


def test_production_remote_profile_rejects_hardlink_and_symlink_aliases(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(DEFAULT_CONFIG.read_bytes())
    hardlink_user_file = tmp_path / "hardlink-users.json"
    hardlink_user_file.hardlink_to(config_path)
    handoff_file = tmp_path / "initial-credentials.json"

    hardlink_result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(hardlink_user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert hardlink_result.returncode == 2
    assert "must not reference the same file" in hardlink_result.stderr
    assert config_path.read_bytes() == DEFAULT_CONFIG.read_bytes()

    target = tmp_path / "real-users.json"
    symlink_user_file = tmp_path / "symlink-users.json"
    symlink_user_file.symlink_to(target)
    symlink_result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(symlink_user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=tmp_path / "other-config.yaml",
    )

    assert symlink_result.returncode == 2
    assert "must not be a symbolic link" in symlink_result.stderr
    assert not target.exists()


def test_production_remote_rotation_creates_backups_and_new_handoff(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"
    args = (
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
    )

    first = _run_profile(*args, config_path=config_path)
    assert first.returncode == 0, first.stderr
    first_handoff = json.loads(handoff_file.read_text(encoding="utf-8"))

    second = _run_profile(
        *args,
        "--rotate-session-credentials",
        config_path=config_path,
    )
    assert second.returncode == 0, second.stderr
    second_handoff = json.loads(handoff_file.read_text(encoding="utf-8"))

    assert second_handoff["password"] != first_handoff["password"]
    assert list(tmp_path.glob("production-users.json.backup.*"))
    assert not list(tmp_path.glob("initial-credentials.json.backup.*"))
    assert list(tmp_path.glob("config.yaml.backup.*"))


def test_profile_artifact_failure_does_not_write_runtime_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    user_file = blocked_parent / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "failed to write" in result.stderr
    assert "Traceback" not in result.stderr
    assert not config_path.exists()
    assert not handoff_file.exists()


def test_config_write_failure_rolls_back_generated_credentials(tmp_path):
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    config_path = blocked_parent / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = _run_profile(
        "--profile",
        "production_remote",
        "--public-host",
        "pixeagle.example",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "failed to write" in result.stderr
    assert "Traceback" not in result.stderr
    assert not user_file.exists()
    assert not handoff_file.exists()


@pytest.mark.parametrize(
    ("lan_host", "allowed_host", "origin_host"),
    [
        ("10.0.0.2", "10.0.0.2", "10.0.0.2"),
        ("172.16.0.2", "172.16.0.2", "172.16.0.2"),
        ("172.31.255.254", "172.31.255.254", "172.31.255.254"),
        ("192.168.10.42", "192.168.10.42", "192.168.10.42"),
        ("100.64.0.42", "100.64.0.42", "100.64.0.42"),
        ("169.254.10.20", "169.254.10.20", "169.254.10.20"),
        ("fc00::42", "fc00::42", "[fc00::42]"),
        ("[fc00::42]", "fc00::42", "[fc00::42]"),
        ("fe80::42", "fe80::42", "[fe80::42]"),
    ],
)
def test_demo_lan_browser_profile_accepts_lan_and_private_overlay_addresses(
    tmp_path, lan_host, allowed_host, origin_host
):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        lan_host,
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_ALLOWED_HOSTS"] == [allowed_host]
    assert f"http://{origin_host}:3040" in streaming["API_CORS_ALLOWED_ORIGINS"]
    assert f"http://{origin_host}:5077" in streaming["API_CORS_ALLOWED_ORIGINS"]


def test_demo_lan_browser_profile_requires_lan_host(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile("--profile", "demo_lan_browser", config_path=config_path)

    assert result.returncode == 2
    assert "requires --lan-host" in result.stderr
    assert not config_path.exists()


@pytest.mark.parametrize(
    "bad_host",
    [
        "0.0.0.0",
        "127.0.0.1",
        "localhost",
        "8.8.8.8",
        "172.15.255.255",
        "172.32.0.1",
        "192.0.2.1",
        "198.51.100.4",
        "203.0.113.9",
        "224.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "2001:4860:4860::8888",
        "2001:db8::1",
        "ff02::1",
        "example.com",
        "https://192.168.10.42",
        "user:secret@192.168.10.42",
        "192.168.10.42?token=x",
        "pixeagle.local#frag",
        "192.168.10.42:5077",
        "pixeagle.local:notaport",
        "[fc00::42]:5077",
        "[fc00::42]?x=1",
        "[fc00::42]x",
        "[fc00::42]]",
        "[]",
        "fe80::42%eth0",
        "[fe80::42%25eth0]",
        "*",
    ],
)
def test_demo_lan_browser_profile_rejects_unsafe_lan_hosts(tmp_path, bad_host):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        bad_host,
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert not config_path.exists()
    assert not user_file.exists()


def test_demo_lan_browser_profile_dry_run_does_not_write_config_or_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "192.168.10.42",
        "--session-user-file",
        str(user_file),
        "--dry-run",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert "Would generate browser-session user file" in result.stdout
    assert "LAN/private overlay" in result.stdout
    assert "Demo password:" not in result.stdout
    assert not config_path.exists()
    assert not user_file.exists()


def test_demo_lan_browser_profile_refuses_existing_credentials_without_rotation(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"
    user_file.write_text('{"users": []}\n', encoding="utf-8")

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "192.168.10.42",
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "already exists" in result.stderr
    assert not config_path.exists()


def test_demo_lan_browser_profile_rejects_empty_demo_username(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "192.168.10.42",
        "--session-user-file",
        str(user_file),
        "--demo-username",
        "",
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "--demo-username must not be empty" in result.stderr
    assert not config_path.exists()
    assert not user_file.exists()


def test_make_demo_lan_browser_profile_wrapper_passes_lan_host(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = subprocess.run(
        [
            "make",
            "demo-lan-browser-profile",
            f"PYTHON={sys.executable}",
            "LAN_HOST=192.168.10.42",
            (
                "SETUP_PROFILE_ARGS=--defaults "
                f"{DEFAULT_CONFIG} --config {config_path} "
                f"--session-user-file {user_file}"
            ),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    assert config["Streaming"]["API_AUTH_MODE"] == "browser_session"
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == ["192.168.10.42"]
    assert user_file.exists()


def test_make_production_remote_profile_wrapper_passes_public_host_and_user_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "production-users.json"
    handoff_file = tmp_path / "initial-credentials.json"

    result = subprocess.run(
        [
            "make",
            "production-remote-profile",
            f"PYTHON={sys.executable}",
            "PUBLIC_HOST=pixeagle.example",
            f"SESSION_USER_FILE={user_file}",
            f"CREDENTIAL_HANDOFF_FILE={handoff_file}",
            (
                "SETUP_PROFILE_ARGS=--defaults "
                f"{DEFAULT_CONFIG} --config {config_path}"
            ),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    assert config["Streaming"]["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert config["Streaming"]["API_AUTH_MODE"] == "browser_session"
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == ["pixeagle.example:443"]
    assert config["Streaming"]["API_SESSION_COOKIE_SECURE"] is True
    assert user_file.exists()
    assert handoff_file.exists()


def test_run_script_binds_dashboard_to_lan_for_browser_session_profile():
    script_text = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")

    assert 'API_AUTH_MODE=$(get_config_value "Streaming" "API_AUTH_MODE"' in script_text
    assert '"$API_EXPOSURE_MODE" == "trusted_lan_legacy"' in script_text
    assert '"$API_AUTH_MODE" == "browser_session"' in script_text
    assert '! is_loopback_host "$BACKEND_HOST"' in script_text
    assert 'DASHBOARD_HOST="0.0.0.0"' in script_text
    assert "Dashboard remains loopback for reverse-proxy/tunnel browser-session profiles" in script_text
    assert "PIXEAGLE_DASHBOARD_EXPOSURE_MODE=$dashboard_exposure_arg" in script_text


def test_windows_run_script_binds_dashboard_to_lan_for_browser_session_profile():
    script_text = (PROJECT_ROOT / "scripts" / "run.bat").read_text(encoding="utf-8")

    assert "API_EXPOSURE_MODE=local_only" in script_text
    assert "API_AUTH_MODE=local_compat" in script_text
    assert "BACKEND_HOST=127.0.0.1" in script_text
    assert "API_EXPOSURE_MODE" in script_text
    assert "API_AUTH_MODE" in script_text
    assert "HTTP_STREAM_HOST" in script_text
    assert "BACKEND_HOST_IS_LOOPBACK" in script_text
    assert 'if /I "!API_EXPOSURE_MODE!"=="trusted_lan_legacy"' in script_text
    assert 'if /I "!API_AUTH_MODE!"=="browser_session"' in script_text
    assert 'if "!BACKEND_HOST_IS_LOOPBACK!"=="0"' in script_text
    assert "PIXEAGLE_DASHBOARD_HOST=0.0.0.0" in script_text
    assert "PIXEAGLE_DASHBOARD_EXPOSURE_MODE=trusted_lan_legacy" in script_text


def test_dashboard_production_build_and_navigation_support_pixeagle_subpath():
    package = json.loads(
        (PROJECT_ROOT / "dashboard" / "package.json").read_text(encoding="utf-8")
    )
    follower_card = (
        PROJECT_ROOT / "dashboard" / "src" / "components" / "FollowerStatusCard.js"
    ).read_text(encoding="utf-8")
    safety_card = (
        PROJECT_ROOT / "dashboard" / "src" / "components" / "SafetyConfigCard.js"
    ).read_text(encoding="utf-8")

    assert package["homepage"] == "."
    assert "component={RouterLink}" in follower_card
    assert 'to="/follower"' in follower_card
    assert "window.location.href = '/follower'" not in follower_card
    assert "component={RouterLink}" in safety_card
    assert "pathname: '/settings'" in safety_card
    assert "window.location.href = '/settings#Safety'" not in safety_card


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


def test_production_remote_documents_posix_credential_mode_boundary():
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert 'if os.name == "nt" and not args.dry_run' in script_text
    assert "requires POSIX" in script_text
    assert "Windows ACL automation is not yet evidence-backed" in script_text


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
