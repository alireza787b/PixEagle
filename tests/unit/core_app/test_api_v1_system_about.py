from types import SimpleNamespace

import pytest

from classes.app_version import PIXEAGLE_VERSION
import classes.api_v1_snapshots as api_v1_snapshots
from classes.api_v1_read_routes import get_system_about


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
        ("describe", "--tags", "--always", "--dirty"): "v3.2.1-1-gabcdef1",
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
        "describe": "v3.2.1-1-gabcdef1",
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
