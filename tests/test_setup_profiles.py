"""Tests for explicit PixEagle setup profiles."""

from __future__ import annotations

import subprocess
import sys
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from classes.api_auth_runtime import (
    API_AUTH_MODE_MACHINE_BEARER,
    hash_bearer_token,
    resolve_api_auth_runtime_from_parameters,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "apply-setup-profile.py"
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "config_default.yaml"
CONFIG_SCHEMA = PROJECT_ROOT / "configs" / "config_schema.yaml"
QGC_DOCS = [
    PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "remote-media-security.md",
    PROJECT_ROOT / "docs" / "video" / "04-streaming" / "qgc-http-websocket-source-plan.md",
    PROJECT_ROOT / "docs" / "video" / "03-gstreamer" / "output-pipeline.md",
    PROJECT_ROOT / "docs" / "video" / "06-configuration" / "streaming-config.md",
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
    assert "make check-gstreamer-runtime" in result.stdout
    assert "does not prove receiver playback" in result.stdout


def test_field_qgc_video_profile_requires_gcs_host(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile("--profile", "field_qgc_video", config_path=config_path)

    assert result.returncode == 2
    assert "requires --gcs-host" in result.stderr
    assert not config_path.exists()


def test_qgc_direct_media_profile_generates_media_only_bearer_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_EXPOSURE_MODE"] == "trusted_lan_legacy"
    assert streaming["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert streaming["API_AUTH_MODE"] == "machine_bearer"
    assert streaming["API_BEARER_TOKEN_FILE"] == str(token_file)
    assert streaming["API_ALLOWED_HOSTS"] == ["pixeagle.example:443"]
    assert streaming["API_CORS_ALLOWED_ORIGINS"] == ["https://pixeagle.example"]
    assert streaming["API_SECURITY_AUDIT_ENABLED"] is True
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False

    token_payload = json.loads(token_file.read_text(encoding="utf-8"))
    token_record = token_payload["tokens"][0]
    assert token_record["token_id"] == "qgc-media-viewer"
    assert token_record["subject"] == "qgroundcontrol"
    assert token_record["scopes"] == ["media:read"]
    assert len(token_record["token_sha256"]) == 64
    assert "bearer_token" not in token_record
    assert token_file.stat().st_mode & 0o777 == 0o600

    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert handoff["bearer_token"]
    assert handoff["scopes"] == ["media:read"]
    assert handoff["origin"] == "https://pixeagle.example"
    assert handoff["http_mjpeg_url"].endswith("/pixeagle-api/video_feed")
    assert handoff["websocket_jpeg_url"].endswith("/pixeagle-api/ws/video_feed")
    assert handoff_file.stat().st_mode & 0o777 == 0o600
    assert handoff["bearer_token"] not in result.stdout
    assert "delete the handoff file" in result.stdout
    assert "strict TLS remains required" in result.stdout

    runtime = resolve_api_auth_runtime_from_parameters(
        SimpleNamespace(
            API_AUTH_MODE=API_AUTH_MODE_MACHINE_BEARER,
            API_BEARER_TOKEN_FILE=str(token_file),
            _raw_config={},
        )
    )
    assert runtime.mode == API_AUTH_MODE_MACHINE_BEARER
    assert hash_bearer_token(handoff["bearer_token"]) in runtime.bearer_tokens_by_hash


@pytest.mark.parametrize(
    ("public_host", "public_origin", "allowed_host", "normalized_origin"),
    [
        (
            "pixeagle.example",
            "https://pixeagle.example:8443",
            "pixeagle.example:8443",
            "https://pixeagle.example:8443",
        ),
        (
            "2001:4860:4860::8888",
            "https://[2001:4860:4860::8888]:8443",
            "[2001:4860:4860::8888]:8443",
            "https://[2001:4860:4860::8888]:8443",
        ),
    ],
)
def test_qgc_direct_media_profile_preserves_tls_authority(
    tmp_path,
    public_host,
    public_origin,
    allowed_host,
    normalized_origin,
):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        public_host,
        "--public-origin",
        public_origin,
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        "--token-id",
        "a",
        "--token-subject",
        "q",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    streaming = _read_yaml(config_path)["Streaming"]
    assert streaming["API_ALLOWED_HOSTS"] == [allowed_host]
    assert streaming["API_CORS_ALLOWED_ORIGINS"] == [normalized_origin]
    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert handoff["origin"] == normalized_origin
    assert handoff["http_mjpeg_url"] == (
        f"{normalized_origin}/pixeagle-api/video_feed"
    )
    assert handoff["websocket_jpeg_url"] == (
        f"wss://{normalized_origin.removeprefix('https://')}/pixeagle-api/ws/video_feed"
    )


def test_qgc_direct_media_profile_requires_tls_host(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "requires --public-host" in result.stderr
    assert not config_path.exists()


def test_qgc_direct_media_profile_refuses_existing_credentials_without_rotation(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"
    token_file.write_text("existing", encoding="utf-8")

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "--rotate-qgc-token" in result.stderr
    assert token_file.read_text(encoding="utf-8") == "existing"
    assert not handoff_file.exists()
    assert not config_path.exists()


def test_qgc_direct_media_profile_dry_run_writes_nothing(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        "--dry-run",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Would generate owner-only QGC bearer token file" in result.stdout
    assert not config_path.exists()
    assert not token_file.exists()
    assert not handoff_file.exists()


def test_qgc_direct_media_rotation_backs_up_only_hashed_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"
    args = (
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
    )

    first = _run_profile(*args, config_path=config_path)
    assert first.returncode == 0, first.stderr
    original_token = token_file.read_text(encoding="utf-8")
    original_handoff = handoff_file.read_text(encoding="utf-8")
    token_file.chmod(0o644)
    handoff_file.chmod(0o644)

    second = _run_profile(
        *args,
        "--rotate-qgc-token",
        config_path=config_path,
    )

    assert second.returncode == 0, second.stderr
    token_backups = list(tmp_path.glob("qgc-tokens.json.backup.*"))
    handoff_backups = list(tmp_path.glob("qgc-handoff.json.backup.*"))
    assert len(token_backups) == 1
    assert not handoff_backups
    assert token_backups[0].read_text(encoding="utf-8") == original_token
    assert token_backups[0].stat().st_mode & 0o777 == 0o600
    assert token_file.read_text(encoding="utf-8") != original_token
    assert handoff_file.read_text(encoding="utf-8") != original_handoff
    assert token_file.stat().st_mode & 0o777 == 0o600
    assert handoff_file.stat().st_mode & 0o777 == 0o600


def test_qgc_direct_media_config_failure_rolls_back_credentials(tmp_path):
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    config_path = blocked_parent / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "failed to write" in result.stderr
    assert "Traceback" not in result.stderr
    assert not token_file.exists()
    assert not handoff_file.exists()


def test_qgc_direct_media_handoff_failure_rolls_back_token(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    handoff_file = blocked_parent / "qgc-handoff.json"

    result = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "failed to write" in result.stderr
    assert "Traceback" not in result.stderr
    assert not token_file.exists()
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


def test_unsafe_demo_lan_media_only_requires_lan_host(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "unsafe_demo_lan_media_only",
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "requires --lan-host" in result.stderr
    assert not config_path.exists()


def test_unsafe_demo_lan_media_only_enables_only_anonymous_media(tmp_path):
    config_path = tmp_path / "config.yaml"

    result = _run_profile(
        "--profile",
        "unsafe_demo_lan_media_only",
        "--lan-host",
        "192.168.10.42",
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    streaming = config["Streaming"]
    assert streaming["API_EXPOSURE_MODE"] == "trusted_lan_legacy"
    assert streaming["HTTP_STREAM_HOST"] == "0.0.0.0"
    assert streaming["HTTP_STREAM_PORT"] == 5077
    assert streaming["API_ALLOWED_HOSTS"] == ["192.168.10.42"]
    assert "http://192.168.10.42:3040" in streaming["API_CORS_ALLOWED_ORIGINS"]
    assert "http://192.168.10.42:5077" in streaming["API_CORS_ALLOWED_ORIGINS"]
    assert streaming["API_AUTH_MODE"] == "local_compat"
    assert streaming["API_BEARER_TOKEN_FILE"] == ""
    assert streaming["API_SESSION_USER_FILE"] == ""
    assert streaming["ALLOW_UNAUTHENTICATED_MEDIA_STREAMING"] is True
    assert streaming["API_SECURITY_AUDIT_ENABLED"] is True
    assert config["GStreamer"]["ENABLE_GSTREAMER_STREAM"] is False
    assert "anonymous access is enabled only for /video_feed and /ws/video_feed" in result.stdout
    assert "LAN_HOST is the PixEagle URL Host authority, not the GCS client/source IP" in result.stdout
    assert "Dashboard/control/config/log/API routes are not made anonymous" in result.stdout


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
    assert user_record["role"] == "admin"
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


def test_demo_lan_browser_profile_can_write_private_credential_handoff(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"
    handoff_file = tmp_path / "demo-handoff.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "192.168.10.42",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Demo password:" not in result.stdout
    assert "Generated one-time demo credential handoff file" in result.stdout
    payload = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert payload["username"] == "pixeagle-demo"
    assert payload["role"] == "admin"
    assert payload["password"]
    assert payload["dashboard_url"] == "http://192.168.10.42:3040"
    assert payload["backend_api_url"] == "http://192.168.10.42:5077"
    assert payload["authentication"] == "browser_session"
    assert payload["security_boundary"] == "isolated LAN/private-overlay HTTP demo"
    assert handoff_file.stat().st_mode & 0o777 == 0o600


def test_demo_lan_browser_profile_rejects_public_ip_without_explicit_override(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "204.168.181.45",
        "--session-user-file",
        str(user_file),
        config_path=config_path,
    )

    assert result.returncode == 2
    assert "RFC1918 private" in result.stderr
    assert not config_path.exists()
    assert not user_file.exists()


def test_demo_lan_browser_public_http_override_is_explicit_and_warned(tmp_path):
    config_path = tmp_path / "config.yaml"
    user_file = tmp_path / "demo-users.json"
    handoff_file = tmp_path / "demo-handoff.json"

    result = _run_profile(
        "--profile",
        "demo_lan_browser",
        "--lan-host",
        "204.168.181.45",
        "--allow-public-http-demo",
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )

    assert result.returncode == 0, result.stderr
    config = _read_yaml(config_path)
    assert config["Streaming"]["API_ALLOWED_HOSTS"] == ["204.168.181.45"]
    assert "http://204.168.181.45:3040" in config["Streaming"]["API_CORS_ALLOWED_ORIGINS"]
    assert "TEMPORARY PUBLIC HTTP" in result.stdout
    payload = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert payload["dashboard_url"] == "http://204.168.181.45:3040"
    assert payload["security_boundary"] == "temporary public HTTP demo"


def test_make_quick_browser_demo_wrapper_supports_dry_run_handoff():
    unique = f"pixeagle-dry-run-{os.getpid()}"
    user_file = Path("/tmp") / f"{unique}-demo-users.json"
    handoff_file = Path("/tmp") / f"{unique}-demo-handoff.json"
    user_file.unlink(missing_ok=True)
    handoff_file.unlink(missing_ok=True)

    result = subprocess.run(
        [
            "make",
            "quick-browser-demo",
            f"PYTHON={sys.executable}",
            "LAN_HOST=192.168.10.42",
            "DRY_RUN=1",
            "START_DEMO=0",
            "OPEN_FIREWALL=0",
            f"SESSION_USER_FILE={user_file}",
            f"CREDENTIAL_HANDOFF_FILE={handoff_file}",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PixEagle quick browser demo" in result.stdout
    assert "Mode: dry run (no files, firewall, or services will be changed)" in result.stdout
    assert "Dashboard URL: http://192.168.10.42:3040" in result.stdout
    assert "Role: admin" in result.stdout
    assert "SESSION_ROLE=operator" in result.stdout
    assert "Services: dashboard/backend only" in result.stdout
    assert "Video transport: browser Auto mode" in result.stdout
    assert "Cleanup restores local-only config by default" in result.stdout
    assert "Cleanup preview: DRY_RUN=1 make quick-browser-demo-cleanup" in result.stdout
    assert "Cleanup after test: CONFIRM=1 make quick-browser-demo-cleanup" in result.stdout
    assert f"SESSION_USER_FILE={user_file}" in result.stdout
    assert f"CREDENTIAL_HANDOFF_FILE={handoff_file}" in result.stdout
    assert "Would write one-time demo credential handoff file" in result.stdout
    assert not user_file.exists()
    assert not handoff_file.exists()


def test_make_quick_browser_demo_cleanup_wrapper_supports_dry_run(tmp_path):
    user_file = tmp_path / "demo-users.json"
    handoff_file = tmp_path / "demo-handoff.json"
    user_file.write_text('{"users": []}\n', encoding="utf-8")
    handoff_file.write_text('{"username": "demo"}\n', encoding="utf-8")

    result = subprocess.run(
        [
            "make",
            "quick-browser-demo-cleanup",
            "LAN_HOST=192.168.10.42",
            "DRY_RUN=1",
            "STOP_DEMO=0",
            "CLOSE_FIREWALL=0",
            f"SESSION_USER_FILE={user_file}",
            f"CREDENTIAL_HANDOFF_FILE={handoff_file}",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PixEagle quick browser demo cleanup" in result.stdout
    assert "Mode: dry run" in result.stdout
    assert f"Credential handoff: would remove {handoff_file}" in result.stdout
    assert f"Credential store: would remove {user_file}" in result.stdout
    assert "Configuration: would restore local-only profile" in result.stdout
    assert "Cleanup complete." in result.stdout
    assert user_file.exists()
    assert handoff_file.exists()


def test_make_quick_browser_demo_cleanup_public_firewall_uses_broad_rules():
    result = subprocess.run(
        [
            "make",
            "quick-browser-demo-cleanup",
            "LAN_HOST=204.168.181.45",
            "DRY_RUN=1",
            "STOP_DEMO=0",
            "REMOVE_DEMO_CREDENTIALS=0",
            "RESTORE_LOCAL_PROFILE=0",
            "CLOSE_FIREWALL=1",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Firewall: public demo cleanup" in result.stdout
    assert "Firewall: would delete allow rule for TCP 3040 from anywhere" in result.stdout
    assert "Firewall: would delete allow rule for TCP 5077 from anywhere" in result.stdout
    assert "from 204.168.181.45" not in result.stdout


def test_make_quick_browser_demo_cleanup_private_firewall_requires_cidr():
    result = subprocess.run(
        [
            "make",
            "quick-browser-demo-cleanup",
            "LAN_HOST=192.168.255.254",
            "DRY_RUN=1",
            "STOP_DEMO=0",
            "REMOVE_DEMO_CREDENTIALS=0",
            "RESTORE_LOCAL_PROFILE=0",
            "CLOSE_FIREWALL=1",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "cannot infer the trusted CIDR" in result.stderr


def test_update_paths_are_fast_forward_only_and_non_destructive():
    sync_text = (PROJECT_ROOT / "scripts" / "lib" / "sync.sh").read_text(
        encoding="utf-8"
    )
    install_text = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1_text = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
    service_cli_text = (
        PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    ).read_text(encoding="utf-8")

    combined_update_text = "\n".join([sync_text, install_text, install_ps1_text])
    assert "git stash push" not in combined_update_text
    assert "git reset --hard" not in combined_update_text
    assert "git merge --quiet --no-edit" not in sync_text
    assert "git merge --ff-only" in sync_text
    assert "git merge --ff-only" in install_text
    assert "git merge --ff-only" in install_ps1_text
    assert "Fetch failed for origin/$BRANCH" in install_text
    assert "Fetch failed for origin/$Branch" in install_ps1_text
    assert "clean worktree" in sync_text.lower()
    assert "auto-stash" not in service_cli_text


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_sync_script_refuses_dirty_worktree_before_fetch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "-c", "user.name=PixEagle Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial")
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "lib" / "sync.sh")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 2
    assert "sync requires a clean worktree" in combined
    assert "Fetching updates" not in combined


def test_sync_script_fails_when_fetch_fails_without_stale_update(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "tracked.txt").write_text("initial\n", encoding="utf-8")
    configs = repo / "configs"
    configs.mkdir()
    (configs / "config_default.yaml").write_text(
        "Runtime:\n  VALUE: 1\n",
        encoding="utf-8",
    )
    setup_dir = repo / "scripts" / "setup"
    setup_dir.mkdir(parents=True)
    (setup_dir / "config-sync-status.py").write_text(
        (PROJECT_ROOT / "scripts" / "setup" / "config-sync-status.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        "configs/.config_default_preupdate.yaml\n"
        "configs/.config_default_preupdate.yaml.tmp.*\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=PixEagle Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial")

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "lib" / "sync.sh")],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "Fetch failed from origin" in combined
    assert "Already up to date" not in combined


def test_make_qgc_direct_media_profile_wrapper_passes_secure_media_paths(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"

    result = subprocess.run(
        [
            "make",
            "qgc-direct-media-profile",
            f"PYTHON={sys.executable}",
            "PUBLIC_HOST=pixeagle.example",
            f"QGC_TOKEN_FILE={token_file}",
            f"QGC_HANDOFF_FILE={handoff_file}",
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
    assert config["Streaming"]["API_AUTH_MODE"] == "machine_bearer"
    assert config["Streaming"]["API_BEARER_TOKEN_FILE"] == str(token_file)
    assert token_file.exists()
    assert handoff_file.exists()
    assert "PUBLIC_HOST is the QGC URL/proxy Host authority, not the GCS client/source IP" in result.stdout


@pytest.mark.parametrize("false_value", ["0", "false", "no", "off"])
def test_make_qgc_direct_media_false_rotation_values_do_not_rotate(
    tmp_path,
    false_value,
):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"
    args = (
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
    )
    first = _run_profile(*args, config_path=config_path)
    assert first.returncode == 0, first.stderr
    original_token = token_file.read_bytes()
    original_handoff = handoff_file.read_bytes()

    result = subprocess.run(
        [
            "make",
            "qgc-direct-media-profile",
            f"PYTHON={sys.executable}",
            "PUBLIC_HOST=pixeagle.example",
            f"QGC_TOKEN_FILE={token_file}",
            f"QGC_HANDOFF_FILE={handoff_file}",
            f"ROTATE_QGC_TOKEN={false_value}",
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

    assert result.returncode == 2
    assert "--rotate-qgc-token" in result.stderr
    assert token_file.read_bytes() == original_token
    assert handoff_file.read_bytes() == original_handoff
    assert not list(tmp_path.glob("qgc-tokens.json.backup.*"))
    assert not list(tmp_path.glob("qgc-handoff.json.backup.*"))


def test_make_qgc_direct_media_explicit_true_rotates(tmp_path):
    config_path = tmp_path / "config.yaml"
    token_file = tmp_path / "qgc-tokens.json"
    handoff_file = tmp_path / "qgc-handoff.json"
    first = _run_profile(
        "--profile",
        "qgc_direct_media",
        "--public-host",
        "pixeagle.example",
        "--bearer-token-file",
        str(token_file),
        "--qgc-handoff-file",
        str(handoff_file),
        config_path=config_path,
    )
    assert first.returncode == 0, first.stderr
    original_token = token_file.read_bytes()
    original_handoff = handoff_file.read_bytes()

    result = subprocess.run(
        [
            "make",
            "qgc-direct-media-profile",
            f"PYTHON={sys.executable}",
            "PUBLIC_HOST=pixeagle.example",
            f"QGC_TOKEN_FILE={token_file}",
            f"QGC_HANDOFF_FILE={handoff_file}",
            "ROTATE_QGC_TOKEN=1",
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
    assert token_file.read_bytes() != original_token
    assert handoff_file.read_bytes() != original_handoff
    assert len(list(tmp_path.glob("qgc-tokens.json.backup.*"))) == 1
    assert not list(tmp_path.glob("qgc-handoff.json.backup.*"))


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


def test_makefile_uses_bootstrap_created_venv_before_system_python():
    makefile_text = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "$(CURDIR)/.venv/bin/python" in makefile_text
    assert "$(CURDIR)/venv/bin/python" in makefile_text
    assert "$(CURDIR)/venv/bin/python,python3" in makefile_text


def test_runtime_launchers_support_dotvenv_and_venv_fallbacks():
    run_text = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")
    main_text = (PROJECT_ROOT / "scripts" / "components" / "main.sh").read_text(
        encoding="utf-8"
    )

    assert 'resolve_venv_dir()' in run_text
    assert 'resolve_pixeagle_venv_dir "$PIXEAGLE_DIR"' in run_text
    assert '$PIXEAGLE_DIR/.venv/bin/python' in run_text
    assert '$PIXEAGLE_DIR/venv/bin/python' in run_text
    assert 'bash $MAIN_APP_SCRIPT $python_arg' in run_text

    assert 'resolve_python_interpreter()' in main_text
    assert 'source "$SCRIPTS_DIR/lib/common.sh"' in main_text
    assert 'resolve_pixeagle_venv_python "$PIXEAGLE_DIR"' in main_text
    assert '$PIXEAGLE_DIR/.venv/bin/python' in main_text
    assert '$PIXEAGLE_DIR/venv/bin/python' in main_text
    assert '"$PYTHON_INTERPRETER" "$MAIN_SCRIPT"' in main_text


def test_removed_legacy_opencv_builder_does_not_compete_with_setup_entrypoint():
    assert not (PROJECT_ROOT / "src" / "tools" / "install_opencv_gstreamer.sh").exists()
    assert (PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh").is_file()


def test_run_script_captures_tmux_panes_to_runtime_logs():
    run_text = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")

    assert "RUNTIME_LOG_PIPE_TOOL" in run_text
    assert "RUNTIME_LOG_EXEC_TOOL" in run_text
    assert "prepare_runtime_component_logs" in run_text
    assert "component_wrapped_command" in run_text
    assert "PIXEAGLE_RUNTIME_LOG_PIPE_PYTHON" in run_text
    assert "bash -lc" in run_text
    assert 'component_log_names["MainApp"]="main_app"' in run_text
    assert 'component_log_names["Dashboard"]="dashboard"' in run_text
    assert 'component_log_names["MAVLink2REST"]="mavlink2rest"' in run_text
    assert 'component_log_names["MAVSDKServer"]="mavsdk_server"' in run_text


def test_run_script_blocks_foreign_port_owners_and_has_no_netcat_dependency():
    script_text = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")

    assert "is_pixeagle_owned_pid" in script_text
    assert "non-PixEagle process" in script_text
    assert "Startup blocked by non-PixEagle process" in script_text
    assert "socket.create_connection" in script_text
    assert "nc -z localhost" in script_text
    assert "command -v nc" in script_text


def test_run_script_normalizes_service_ready_retry_overrides():
    script_text = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")

    assert "positive_integer_or_default()" in script_text
    assert '[[ "$value" =~ ^[1-9][0-9]*$ ]]' in script_text
    assert 'positive_integer_or_default "${PIXEAGLE_DASHBOARD_READY_RETRIES:-120}" 120' in script_text
    assert 'positive_integer_or_default "${PIXEAGLE_BACKEND_READY_RETRIES:-30}" 30' in script_text
    assert 'positive_integer_or_default "${PIXEAGLE_MAVLINK2REST_READY_RETRIES:-30}" 30' in script_text
    assert 'positive_integer_or_default "${PIXEAGLE_SERVICE_READY_RETRIES:-15}" 15' in script_text


def test_guided_install_docs_do_not_advertise_macos_bootstrap():
    readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    install_text = (PROJECT_ROOT / "docs" / "INSTALLATION.md").read_text(
        encoding="utf-8"
    )
    installer_text = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "**Linux/macOS:**" not in readme_text
    assert "**Linux/macOS:**" not in install_text
    assert "guided bootstrap currently supports Linux only" in installer_text
    assert "not a maintained macOS path" in readme_text
    assert "not a maintained guided-bootstrap target" in install_text


def test_manual_setup_docs_preserve_core_ai_split_and_dashboard_env_conversion():
    readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    install_text = (PROJECT_ROOT / "docs" / "INSTALLATION.md").read_text(
        encoding="utf-8"
    )
    setup_profile_text = (
        PROJECT_ROOT / "docs" / "setup" / "setup-profiles.md"
    ).read_text(encoding="utf-8")

    assert "cp dashboard/env_default.yaml dashboard/.env" not in install_text
    assert "yaml.safe_load" in install_text
    assert "pip install -r requirements-core.txt" in install_text
    assert "bash scripts/setup/install-ai-deps.sh" in install_text
    assert "pip install -r requirements-dev.txt" in install_text
    assert "pip install -r requirements.txt" not in install_text
    assert "component readiness summary" in readme_text
    assert "component readiness summary" in install_text
    assert "manual follow-up" in install_text
    assert "reports setup state separately from profile state" in setup_profile_text


def test_python_requirements_are_role_based_and_stale_paths_removed():
    aggregate = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    core = (PROJECT_ROOT / "requirements-core.txt").read_text(encoding="utf-8")
    ai = (PROJECT_ROOT / "requirements-ai.txt").read_text(encoding="utf-8")
    dev = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    init_text = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    assert "-r requirements-core.txt" in aggregate
    assert "-r requirements-ai.txt" in aggregate
    assert "-r requirements-dev.txt" in aggregate
    assert "scripts/setup/install-dlib.sh" in core
    assert "scripts/install_dlib.sh" not in core
    assert "scripts/install_dlib.sh" not in aggregate

    forbidden_core_terms = [
        "ultralytics",
        " ncnn",
        "\nncnn",
        "\nlap",
        "pnnx",
        "pytest",
        "httpx",
        "ipython",
    ]
    for term in forbidden_core_terms:
        assert term not in core

    assert "ultralytics" in ai
    assert "\nlap" in ai
    assert "\nncnn" in ai
    assert "pnnx remains best-effort" in ai
    assert "pytest" in dev
    assert "httpx" in dev
    assert "requirements-core.txt" in init_text
    assert "requirements-ai.txt" in init_text


def test_init_summary_uses_explicit_component_states():
    script_text = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    summary_text = script_text.split("show_summary() {", 1)[1].split(
        "# ============================================================================\n# Optional Service Setup",
        1,
    )[0]

    assert "summary_status_line" in summary_text
    assert "NODE_SETUP_STATE" in summary_text
    assert "DASHBOARD_DEPS_STATE" in summary_text
    assert "MAVSDK_BINARY_STATE" in summary_text
    assert "MAVLINK2REST_BINARY_STATE" in summary_text
    assert "node -v" not in summary_text
    assert "mavsdk_status" not in summary_text
    assert "mavlink2rest_status" not in summary_text
    assert '[[ -f "$PIXEAGLE_DIR/bin/mavsdk_server_bin" ]]' not in summary_text
    assert '[[ -f "$PIXEAGLE_DIR/bin/mavlink2rest" ]]' not in summary_text


def test_init_summary_tracks_dashboard_and_binary_followup_states():
    script_text = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    assert 'DASHBOARD_DEPS_STATE="skipped"' in script_text
    assert 'DASHBOARD_DEPS_STATE="manual_follow_up"' in script_text
    assert 'DASHBOARD_DEPS_STATE="degraded"' in script_text
    assert "npm unavailable; install Node.js/npm" in script_text
    assert "npm install failed; run cd dashboard && npm install manually" in script_text

    assert 'MAVSDK_BINARY_STATE="ready"' in script_text
    assert 'MAVSDK_BINARY_STATE="skipped"' in script_text
    assert 'MAVSDK_BINARY_STATE="degraded"' in script_text
    assert 'MAVSDK_BINARY_STATE="manual_follow_up"' in script_text
    assert "existing binary failed manifest verification" in script_text
    assert "operator skipped download; run download-binaries.sh --mavsdk" in script_text
    assert "MAVSDK Server downloaded and verified" in script_text

    assert 'MAVLINK2REST_BINARY_STATE="ready"' in script_text
    assert 'MAVLINK2REST_BINARY_STATE="skipped"' in script_text
    assert 'MAVLINK2REST_BINARY_STATE="degraded"' in script_text
    assert 'MAVLINK2REST_BINARY_STATE="manual_follow_up"' in script_text
    assert "operator skipped download; run download-binaries.sh --mavlink2rest" in script_text
    assert "MAVLink2REST Server downloaded and verified" in script_text


def test_one_line_installer_does_not_overstate_partial_init_success():
    installer_text = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "Installation Complete!" not in installer_text
    assert "Bootstrap Finished" in installer_text
    assert "Review the init summary above before starting services." in installer_text
    assert "Resolve any degraded or manual-follow-up items" in installer_text
    assert "only after the init summary is ready for your use case" in installer_text


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
        "qgc_direct_media",
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


def test_gstreamer_schema_ranges_accept_defaults_and_match_runtime_contract():
    config = _read_yaml(DEFAULT_CONFIG)["GStreamer"]
    schema = _read_yaml(CONFIG_SCHEMA)["sections"]["GStreamer"]["parameters"]

    for name in [
        "GSTREAMER_PORT",
        "GSTREAMER_BITRATE",
        "GSTREAMER_WIDTH",
        "GSTREAMER_HEIGHT",
        "GSTREAMER_FRAMERATE",
        "GSTREAMER_BUFFER_SIZE",
        "GSTREAMER_KEY_INT_MAX",
    ]:
        assert schema[name]["min"] <= config[name] <= schema[name]["max"]

    assert schema["GSTREAMER_PORT"]["max"] == 65535
    assert schema["GSTREAMER_INCLUDE_OSD"]["reload_tier"] == "immediate"
    assert [item["value"] for item in schema["GSTREAMER_SPEED_PRESET"]["options"]] == [
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
    ]
