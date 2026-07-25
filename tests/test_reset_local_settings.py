"""Tests for the offline local-settings reset transaction."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESET_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "reset-local-settings.py"


def _load_reset_module():
    spec = importlib.util.spec_from_file_location(
        "pixeagle_reset_local_settings",
        RESET_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prepare_project(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    root = tmp_path / "PixEagle"
    configs = root / "configs"
    dashboard = root / "dashboard"
    configs.mkdir(parents=True)
    dashboard.mkdir()
    for filename in (
        "config_default.yaml",
        "config_schema.yaml",
        "config_retirements.yaml",
    ):
        shutil.copy2(PROJECT_ROOT / "configs" / filename, configs / filename)
    shutil.copy2(
        PROJECT_ROOT / "dashboard" / "env_default.yaml",
        dashboard / "env_default.yaml",
    )

    runtime = yaml.safe_load(
        (configs / "config_default.yaml").read_text(encoding="utf-8")
    )
    runtime["Streaming"]["STREAM_FPS"] = 7
    runtime["OperatorExtension"] = {"preserve_only_until_reset": True}
    old_config = yaml.safe_dump(runtime, sort_keys=False).encode("utf-8")
    old_env = b"REACT_APP_API_URL=http://old.invalid:9999\n"
    (configs / "config.yaml").write_bytes(old_config)
    (dashboard / ".env").write_bytes(old_env)
    (configs / "config_sync_meta.json").write_text(
        json.dumps(
            {
                "defaults_snapshot": {"Old": {"VALUE": 1}},
                "defaults_snapshot_provenance": "test_old",
            }
        ),
        encoding="utf-8",
    )
    (configs / "audit_log.json").write_text("[]", encoding="utf-8")
    return root, old_config, old_env


def test_reset_replaces_both_settings_and_refreshes_baseline(tmp_path):
    root, old_config, old_env = _prepare_project(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(RESET_SCRIPT),
            "--project-root",
            str(root),
            "--source",
            "test_reset",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Config file not found" not in result.stdout + result.stderr
    assert (root / "configs" / "config.yaml").read_bytes() == (
        root / "configs" / "config_default.yaml"
    ).read_bytes()
    env_defaults = yaml.safe_load(
        (root / "dashboard" / "env_default.yaml").read_text(encoding="utf-8")
    )
    expected_env = "".join(f"{key}={value}\n" for key, value in env_defaults.items())
    assert (root / "dashboard" / ".env").read_text(encoding="utf-8") == expected_env

    meta = json.loads(
        (root / "configs" / "config_sync_meta.json").read_text(encoding="utf-8")
    )
    assert meta["defaults_snapshot_provenance"] == "test_reset"
    assert meta["defaults_snapshot"] == yaml.safe_load(
        (root / "configs" / "config_default.yaml").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (root / "configs" / "audit_log.json").read_text(encoding="utf-8")
    )
    assert audit[-1]["action"] == "reset_defaults"
    assert audit[-1]["source"] == "test_reset"

    config_backups = list((root / "configs" / "backups").glob("config_*.yaml"))
    env_backups = list((root / "dashboard" / "backups").glob("env_*.env"))
    assert len(config_backups) == 1
    assert len(env_backups) == 1
    assert config_backups[0].read_bytes() == old_config
    assert env_backups[0].read_bytes() == old_env
    if os.name != "nt":
        assert stat.S_IMODE(config_backups[0].stat().st_mode) == 0o600
        assert stat.S_IMODE(env_backups[0].stat().st_mode) == 0o600


def test_reset_rolls_back_both_settings_when_baseline_refresh_fails(
    tmp_path,
    monkeypatch,
):
    root, old_config, old_env = _prepare_project(tmp_path)
    old_meta = (root / "configs" / "config_sync_meta.json").read_bytes()
    old_audit = (root / "configs" / "audit_log.json").read_bytes()
    staged_defaults = root / "configs" / ".config_default_preupdate.yaml"
    staged_defaults.write_bytes(b"old defaults snapshot\n")
    reset_module = _load_reset_module()
    monkeypatch.setattr(
        reset_module.ConfigService,
        "refresh_defaults_snapshot",
        lambda self, **kwargs: False,
    )

    try:
        reset_module.reset_local_settings(root, source="failing_test")
    except RuntimeError as exc:
        assert "refresh the config defaults baseline" in str(exc)
    else:
        raise AssertionError("reset unexpectedly succeeded")

    assert (root / "configs" / "config.yaml").read_bytes() == old_config
    assert (root / "dashboard" / ".env").read_bytes() == old_env
    assert (root / "configs" / "config_sync_meta.json").read_bytes() == old_meta
    assert (root / "configs" / "audit_log.json").read_bytes() == old_audit
    assert staged_defaults.read_bytes() == b"old defaults snapshot\n"
    assert not list((root / "configs" / "backups").glob("config_*.yaml"))
    assert not list((root / "dashboard" / "backups").glob("env_*.env"))


def test_initializer_uses_one_explicit_local_settings_action():
    source = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    assert "PIXEAGLE_LOCAL_SETTINGS_ACTION" in source
    assert "Allowed: preserve, reset" in source
    assert (
        "Reset local runtime and dashboard settings to this release? [y/N]: "
        in source
    )
    assert "Replace with latest default? [y/N]:" not in source
