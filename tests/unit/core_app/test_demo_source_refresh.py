"""Stopped demo refresh preserves operator data and replaces stale code as a unit."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import refresh_native_demo_sources as refresh


@pytest.fixture
def fixture(tmp_path):
    repo = tmp_path / "repo"
    runtime = tmp_path / "runtime"
    repo.mkdir()
    runtime.mkdir(mode=0o700)
    for root in (repo, runtime):
        (root / "src/classes").mkdir(parents=True)
        (root / "configs").mkdir()
        (root / "src/classes/api_security_policy.py").write_text("fresh" if root == repo else "stale")
        for name in refresh.DEFINITIONS:
            (root / "configs" / name).write_text("new" if root == repo else "old")
    (runtime / "src/removed.py").write_text("stale retired code")
    for name in ("configs/config.yaml", "configs/secrets/users.json", "models/local.pt", "resources/test9.mp4"):
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private operator data")
    (runtime / "demo-manifest.json").write_text(json.dumps({"version": 1, "kind": "real-core-recorded-video",
        "source_files": {"src/removed.py": "oldhash", "models/local.pt": "modelhash"}}))
    return repo, runtime


def test_refresh_replaces_stale_code_preserves_data_and_records_backup(fixture, monkeypatch):
    repo, runtime = fixture
    monkeypatch.setattr(refresh, "source_paths", lambda root: ["src/classes/api_security_policy.py"])
    with patch.object(refresh.subprocess, "check_output", return_value=b"fixture-revision\n"):
        backup = refresh.refresh(runtime, repository=repo)
    assert (runtime / "src/classes/api_security_policy.py").read_text() == "fresh"
    assert not (runtime / "src/removed.py").exists()
    assert (backup / "src/removed.py").exists()
    for name in ("configs/config.yaml", "configs/secrets/users.json", "models/local.pt", "resources/test9.mp4"):
        assert (runtime / name).read_text() == "private operator data"
    for name in refresh.DEFINITIONS:
        assert (runtime / "configs" / name).read_text() == "new"
        assert (backup / name).read_text() == "old"
    manifest = json.loads((runtime / "demo-manifest.json").read_text())
    assert manifest["source_files"]["src/classes/api_security_policy.py"] == refresh.digest(runtime / "src/classes/api_security_policy.py")
    assert "src/removed.py" not in manifest["source_files"]
    assert manifest["source_files"]["models/local.pt"] == "modelhash"


def test_refresh_failure_restores_source_definitions_and_manifest(fixture, monkeypatch):
    repo, runtime = fixture
    before = (runtime / "demo-manifest.json").read_bytes()
    monkeypatch.setattr(refresh, "source_paths", lambda root: ["src/classes/api_security_policy.py"])
    with patch.object(refresh.subprocess, "check_output", side_effect=RuntimeError("revision unavailable")):
        with pytest.raises(RuntimeError):
            refresh.refresh(runtime, repository=repo)
    assert (runtime / "src/classes/api_security_policy.py").read_text() == "stale"
    assert (runtime / "src/removed.py").exists()
    assert (runtime / "configs/config_schema.yaml").read_text() == "old"
    assert (runtime / "demo-manifest.json").read_bytes() == before


def test_refresh_rejects_symlink_definitions(fixture):
    repo, runtime = fixture
    path = runtime / "configs/config_schema.yaml"
    path.unlink()
    path.symlink_to(repo / "configs/config_schema.yaml")
    with pytest.raises(ValueError, match="symlinked config"):
        refresh.refresh(runtime, repository=repo)
    assert (runtime / "src/removed.py").exists()
