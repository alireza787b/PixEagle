import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from classes.app_version import PIXEAGLE_VERSION
import classes.api_v1_snapshots as api_v1_snapshots
from classes.api_v1_read_routes import get_system_about


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class _VideoHandler:
    def get_connection_health(self):
        return {"status": "active"}

    def is_available(self):
        return True


def test_system_about_snapshot_reports_typed_process_local_metadata(monkeypatch):
    git_values = {
        ("rev-parse", "HEAD"): "abcdef1234567890",
        ("rev-parse", "--short", "HEAD"): "abcdef1",
        ("rev-parse", "--abbrev-ref", "HEAD"): "main",
        ("log", "-1", "--format=%cI"): "2026-07-05T12:34:56+00:00",
        ("describe", "--tags", "--always", "--dirty"): "v7.0.0-beta.1-1-gabcdef1",
        ("status", "--porcelain"): " M dashboard/src/components/NavigationDrawer.js",
    }

    monkeypatch.setattr(
        api_v1_snapshots,
        "_git_output",
        lambda args, cwd=api_v1_snapshots.PROJECT_ROOT: git_values.get(tuple(args)),
    )

    owner = SimpleNamespace(
        video_handler=_VideoHandler(),
        _restart_pending=False,
    )

    payload = api_v1_snapshots.get_system_about_snapshot(owner)

    assert payload["schema_version"] == 1
    assert payload["source"] == "pixeagle_system_about"
    assert payload["version"] == PIXEAGLE_VERSION
    assert payload["repository"]["url"] == "https://github.com/alireza787b/PixEagle"
    assert payload["git"] == {
        "available": True,
        "commit": "abcdef1",
        "full_commit": "abcdef1234567890",
        "branch": "main",
        "date": "2026-07-05T12:34:56+00:00",
        "dirty": True,
        "describe": "v7.0.0-beta.1-1-gabcdef1",
    }
    assert payload["backend"]["status"] == "running"
    assert payload["backend"]["video_available"] is True
    assert payload["runtime"]["python_version"]
    assert "cwd" not in payload["runtime"]
    assert payload["update"]["supported"] is False
    assert payload["update"]["available"] is None
    assert "does not fetch" in payload["update"]["reason"]
    assert payload["update"]["safe_workflow"] == "Stopped-runtime host workflow: make update"
    assert "process-local version" in payload["claim_boundary"]


def test_system_about_snapshot_degrades_when_git_is_unavailable(monkeypatch):
    monkeypatch.setattr(api_v1_snapshots, "_git_output", lambda args, cwd=None: None)
    owner = SimpleNamespace(video_handler=None, _restart_pending=True)

    payload = api_v1_snapshots.get_system_about_snapshot(owner)

    assert payload["git"]["available"] is False
    assert payload["git"]["commit"] == "unknown"
    assert payload["git"]["branch"] == "unknown"
    assert payload["git"]["dirty"] is None
    assert payload["backend"]["restart_pending"] is True


def test_runtime_status_reports_degraded_startup_capability():
    startup = {
        "status": "degraded",
        "degraded_components": ["video_input"],
        "initializing_components": [],
        "components": {
            "video_input": {
                "status": "degraded",
                "detail": "camera offline",
            }
        },
    }
    owner = SimpleNamespace(
        logger=None,
        video_handler=SimpleNamespace(
            get_connection_health=lambda: {"status": "unavailable"}
        ),
        app_controller=SimpleNamespace(
            get_startup_status=lambda: startup,
            smart_mode_active=False,
            tracking_started=False,
            segmentation_active=False,
            following_active=False,
            smart_tracker=None,
            offboard_commander=None,
            last_offboard_commander_failure=None,
            px4_interface=None,
            mavlink_data_manager=None,
        ),
    )

    payload = api_v1_snapshots.get_runtime_status_snapshot(owner)

    assert payload["status"] == "degraded"
    assert payload["consumer_guidance"] == "operator_attention"
    assert payload["reason"] == "startup_degraded:video_input"
    assert payload["subsystems"]["startup"] == startup


def test_runtime_status_survives_broken_capability_status_providers():
    def fail():
        raise RuntimeError("provider failed")

    owner = SimpleNamespace(
        logger=None,
        video_handler=SimpleNamespace(get_connection_health=fail),
        app_controller=SimpleNamespace(
            smart_mode_active=False,
            tracking_started=False,
            segmentation_active=False,
            following_active=False,
            smart_tracker=None,
            offboard_commander=SimpleNamespace(get_status=fail),
            last_offboard_commander_failure=None,
            px4_interface=SimpleNamespace(get_connection_status=fail),
            mavlink_data_manager=SimpleNamespace(get_connection_status=fail),
        ),
    )

    payload = api_v1_snapshots.get_runtime_status_snapshot(owner)

    assert payload["status"] == "degraded"
    assert payload["reason"] == "video_input_unavailable"
    assert payload["subsystems"]["video_status"] == "error"
    assert payload["subsystems"]["mavlink_telemetry"]["status"] == "error"
    assert payload["subsystems"]["px4_connection"]["status"] == "error"


@pytest.mark.asyncio
async def test_system_about_read_route_uses_structured_error_boundary():
    owner = SimpleNamespace(
        _get_system_about_snapshot=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        _api_v1_error_response=lambda **kwargs: kwargs,
        logger=None,
    )

    response = await get_system_about(owner)

    assert response["code"] == "system_about_error"
    assert response["path"] == "/api/v1/system/about"
    assert response["status_code"] == 500


def test_project_version_matches_dashboard_package_metadata():
    package = json.loads((PROJECT_ROOT / "dashboard" / "package.json").read_text())
    package_lock = json.loads(
        (PROJECT_ROOT / "dashboard" / "package-lock.json").read_text()
    )

    assert package["version"] == PIXEAGLE_VERSION
    assert package_lock["version"] == PIXEAGLE_VERSION
    assert package_lock["packages"][""]["version"] == PIXEAGLE_VERSION
    installer = (PROJECT_ROOT / "scripts" / "init.sh").read_text()
    assert f'get_version_info "{PIXEAGLE_VERSION}"' in installer
