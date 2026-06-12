"""Static guardrails for local-first process exposure defaults."""

import os
from pathlib import Path
import subprocess

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_defaults_are_local_only():
    defaults = yaml.safe_load(_text("configs/config_default.yaml"))
    streaming = defaults["Streaming"]

    assert streaming["API_EXPOSURE_MODE"] == "local_only"
    assert streaming["HTTP_STREAM_HOST"] == "127.0.0.1"
    assert "*" not in streaming["API_CORS_ALLOWED_ORIGINS"]


def test_websocket_handlers_check_origin_before_accept():
    fastapi_handler = _text("src/classes/fastapi_handler.py")
    webrtc_manager = _text("src/classes/webrtc_manager.py")

    video_handler = fastapi_handler[fastapi_handler.index("async def video_feed_websocket_optimized") :]
    signaling_handler = webrtc_manager[webrtc_manager.index("async def signaling_handler") :]

    assert video_handler.index("is_websocket_request_allowed") < video_handler.index("websocket.accept()")
    assert signaling_handler.index("is_websocket_request_allowed") < signaling_handler.index("websocket.accept()")


def test_dashboard_launchers_bind_loopback_by_default():
    shell_launcher = _text("scripts/components/dashboard.sh")
    windows_launcher = _text("scripts/components/dashboard.bat")
    dashboard_defaults = yaml.safe_load(_text("dashboard/env_default.yaml"))

    assert dashboard_defaults["HOST"] == "127.0.0.1"
    assert 'DASHBOARD_HOST="${PIXEAGLE_DASHBOARD_HOST:-127.0.0.1}"' in shell_launcher
    assert 'HOST="$DASHBOARD_HOST" npm start' in shell_launcher
    assert '-l "tcp://$DASHBOARD_HOST:$PORT"' in shell_launcher
    assert "Network:" not in shell_launcher

    assert 'PIXEAGLE_DASHBOARD_HOST=127.0.0.1' in windows_launcher
    assert 'set "HOST=%PIXEAGLE_DASHBOARD_HOST%"' in windows_launcher
    assert "-l tcp://%PIXEAGLE_DASHBOARD_HOST%:%DASHBOARD_PORT%" in windows_launcher


def test_mavlink2rest_launchers_are_process_local_by_default():
    windows_launcher = _text("scripts/components/mavlink2rest.bat")
    shell_launcher = _text("scripts/components/mavlink2rest.sh")
    legacy_helper = _text("src/tools/mavlink2rest/build_mavlink2rest.sh")

    assert 'MAVLINK_CONNECTION=udpin:127.0.0.1:14569' in windows_launcher
    assert 'MAVLINK2REST_HOST=127.0.0.1' in windows_launcher
    assert "--server 0.0.0.0:" not in windows_launcher
    assert "PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy" in windows_launcher

    assert 'DEFAULT_SERVER_BIND="127.0.0.1:8088"' in shell_launcher
    assert "PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy" in shell_launcher
    assert 'DEFAULT_SERVER_IP_PORT="127.0.0.1:8088"' in legacy_helper
    assert '"0.0.0.0:8088"' not in legacy_helper
    assert "PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy" in legacy_helper


def test_legacy_mavlink2rest_helper_rejects_remote_bind_without_legacy_mode():
    env = os.environ.copy()
    env["PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE"] = "local_only"

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "src/tools/mavlink2rest/build_mavlink2rest.sh"),
            "udpin:127.0.0.1:14569",
            "0.0.0.0:8088",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "trusted_lan_legacy" in result.stdout


def test_primary_launcher_does_not_advertise_lan_urls_by_default():
    launcher = _text("scripts/run.sh")
    windows_launcher = _text("scripts/run.bat")
    service_launcher = _text("scripts/service/run.sh")
    service_utils = _text("scripts/service/utils.sh")

    assert "Service URLs (Network Access)" not in launcher
    assert "http://${LAN_IP}" not in launcher
    assert "http://${lan_ip}" not in launcher
    assert "http://localhost:%DASHBOARD_PORT%" in windows_launcher
    assert "http://%LAN_IP%" not in windows_launcher
    assert "Network Access" not in windows_launcher
    assert "hostname -I" not in service_launcher
    assert "http://$ip" not in service_launcher
    assert "http://127.0.0.1:$dashboard_port" in service_launcher
    assert "http://%s:%s/docs" not in service_utils
    assert "hostname -I" not in service_utils
    assert "ssh -L %s:127.0.0.1:%s" in service_utils


def test_port_configuration_docs_match_local_first_defaults():
    port_config = _text("docs/drone-interface/04-infrastructure/port-configuration.md")
    mavlink2rest_api = _text("docs/drone-interface/03-protocols/mavlink2rest-api.md")

    assert "binds for LAN by launcher" not in port_config
    assert "`0.0.0.0` current default" not in port_config
    assert "`127.0.0.1` current default" in port_config
    assert "PixEagle dashboard 0.0.0.0:3040" not in port_config
    assert "PixEagle dashboard 127.0.0.1:3040" in port_config
    assert "PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy" in mavlink2rest_api
