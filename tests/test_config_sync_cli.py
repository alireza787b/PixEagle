"""Config sync setup/reporting contract tests."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


pytestmark = [pytest.mark.unit]
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup" / "config-sync-status.py"


def _windows_powershell() -> str:
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    assert shell is not None, "Windows ACL tests require PowerShell"
    return shell


def _config_defaults_with_stream_fps(value: int) -> dict:
    defaults = yaml.safe_load(
        (REPO_ROOT / "configs" / "config_default.yaml").read_text(encoding="utf-8")
    )
    defaults["Streaming"]["STREAM_FPS"] = value
    return defaults


def _write_staged_defaults(path: Path, value: int) -> None:
    path.write_text(
        yaml.safe_dump(_config_defaults_with_stream_fps(value), sort_keys=False),
        encoding="utf-8",
    )


def _write_minimal_config_project(root: Path, default_value: int = 2) -> None:
    configs = root / "configs"
    configs.mkdir(parents=True)
    (configs / "config_default.yaml").write_text(
        yaml.safe_dump(
            _config_defaults_with_stream_fps(default_value), sort_keys=False
        ),
        encoding="utf-8",
    )
    schema = yaml.safe_load(
        (REPO_ROOT / "configs" / "config_schema.yaml").read_text(encoding="utf-8")
    )
    schema["sections"]["Streaming"]["parameters"]["STREAM_FPS"][
        "default"
    ] = default_value
    (configs / "config_schema.yaml").write_text(
        yaml.safe_dump(schema, sort_keys=False),
        encoding="utf-8",
    )
    (configs / "config_retirements.yaml").write_text(
        (REPO_ROOT / "configs" / "config_retirements.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )


def _run_cli(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(project_root), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _make_owner_only(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
        return
    script = r"""
$ErrorActionPreference = 'Stop'
$path = $env:PIXEAGLE_TEST_STAGED_DEFAULTS_PATH
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = [System.Security.AccessControl.FileSecurity]::new()
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
$rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
    $sid,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.SetAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
"""
    powershell_env = os.environ.copy()
    powershell_env["PIXEAGLE_TEST_STAGED_DEFAULTS_PATH"] = str(path)
    result = subprocess.run(
        [_windows_powershell(), "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        env=powershell_env,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_config_sync_status_json_is_redacted_and_machine_readable():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert "registered_retirements" in report
    assert "unknown_extensions" in report
    assert report["contract_version"] == 2
    assert "removed_parameters" not in report
    assert "current_value" not in result.stdout
    assert "user_value" not in result.stdout


def test_bootstrap_and_update_only_snapshot_or_report_config_migrations():
    init_sh = (REPO_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    init_bat = (REPO_ROOT / "scripts" / "init.bat").read_text(encoding="utf-8")
    sync_sh = (REPO_ROOT / "scripts" / "lib" / "sync.sh").read_text(encoding="utf-8")
    update_sh = (REPO_ROOT / "scripts" / "update.sh").read_text(encoding="utf-8")

    for script in (init_sh, init_bat):
        assert "config-sync-status.py" in script
        assert "--initialize-baseline" in script
        assert "--apply" not in script
    assert "config-sync-status.py" in sync_sh
    assert "--validate-staged-baseline" in sync_sh
    assert "--apply" not in sync_sh

    install_sh = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "bash scripts/update.sh" in install_sh
    assert ".config_default_preupdate.yaml" not in install_sh
    for lifecycle_source in (sync_sh, install_ps1):
        assert ".config_default_preupdate.yaml" in lifecycle_source
        assert "Pre-update config defaults preserved" in lifecycle_source

    assert "--initialize-baseline-from" in init_sh
    assert "--initialize-baseline-from" in init_bat
    assert "do_sync" in update_sh


def test_update_lifecycle_is_fail_closed_and_uses_shared_venv_resolution():
    init_sh = (REPO_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    init_bat = (REPO_ROOT / "scripts" / "init.bat").read_text(encoding="utf-8")
    sync_sh = (REPO_ROOT / "scripts" / "lib" / "sync.sh").read_text(encoding="utf-8")
    update_sh = (REPO_ROOT / "scripts" / "update.sh").read_text(encoding="utf-8")
    install_sh = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "resolve_pixeagle_venv_python" in sync_sh
    assert "$project_root/venv/bin/python" not in sync_sh
    sync_update = sync_sh[sync_sh.index("do_sync()") :]
    install_update = install_sh[install_sh.index("clone_or_reconcile()") :]
    ps_update = install_ps1[install_ps1.index("function Install-OrUpdate") :]
    assert sync_update.index('_stage_preupdate_defaults "$project_root"') < sync_update.index(
        "git merge --ff-only"
    )
    assert "stage_preupdate_defaults" not in install_update
    assert "bash scripts/update.sh" in install_update
    assert ps_update.index("Stage-PreUpdateDefaults") < ps_update.index("git fetch --prune")
    assert "pixeagle_run_with_resource_locks" in update_sh
    assert '"$LIFECYCLE_RESOURCE" "$PROJECT_ROOT" "$VENV_DIR"' in update_sh

    assert "SetAccessRuleProtection($true, $false)" in install_ps1
    assert "Set-OwnerOnlyFileAcl" in install_ps1
    assert "CONFIG_DEFAULTS_STATE=\"degraded\"" in init_sh
    assert "CONFIG_DEFAULTS_READY=false" in init_bat
    assert 'exit /b 1' in init_bat


def test_setup_cli_exposes_non_destructive_and_explicit_baseline_modes():
    config_service_source = (
        REPO_ROOT / "src" / "classes" / "config_service.py"
    ).read_text(encoding="utf-8")

    assert "def initialize_defaults_snapshot" in config_service_source
    assert "if isinstance(snapshot, dict) and bool(snapshot):" in config_service_source
    assert "--replace-baseline" in SCRIPT.read_text(encoding="utf-8")


def test_staged_baseline_initializes_once_and_is_not_deleted_by_cli(tmp_path):
    _write_minimal_config_project(tmp_path)
    staged = tmp_path / "configs" / ".config_default_preupdate.yaml"
    _write_staged_defaults(staged, 1)
    _make_owner_only(staged)

    first = _run_cli(tmp_path, "--initialize-baseline-from", str(staged), "--json")

    assert first.returncode == 0, first.stderr
    metadata_path = tmp_path / "configs" / "config_sync_meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["defaults_snapshot"]["Streaming"]["STREAM_FPS"] == 1
    assert metadata["defaults_snapshot_provenance"] == "pre_update_staged_defaults"
    original_metadata_bytes = metadata_path.read_bytes()
    assert staged.exists(), "only the installer/init caller may delete the staged file"
    if os.name != "nt":
        assert stat.S_IMODE(metadata_path.stat().st_mode) == 0o600

    _write_staged_defaults(staged, 3)
    _make_owner_only(staged)
    second = _run_cli(tmp_path, "--initialize-baseline-from", str(staged), "--json")

    assert second.returncode == 0, second.stderr
    preserved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert preserved["defaults_snapshot"]["Streaming"]["STREAM_FPS"] == 1
    assert metadata_path.read_bytes() == original_metadata_bytes


@pytest.mark.parametrize(
    ("contents", "expected_error"),
    [
        ("Runtime: [\n", "Could not parse staged defaults baseline"),
        ("- not\n- a\n- mapping\n", "must contain a non-empty YAML mapping"),
    ],
)
def test_staged_baseline_rejects_malformed_content(
    tmp_path,
    contents,
    expected_error,
):
    _write_minimal_config_project(tmp_path)
    staged = tmp_path / "configs" / ".config_default_preupdate.yaml"
    staged.write_text(contents, encoding="utf-8")
    _make_owner_only(staged)

    result = _run_cli(tmp_path, "--initialize-baseline-from", str(staged))

    assert result.returncode == 2
    assert expected_error in result.stderr
    assert not (tmp_path / "configs" / "config_sync_meta.json").exists()


def test_validation_only_rejects_malformed_stage_without_mutating_state(tmp_path):
    _write_minimal_config_project(tmp_path)
    staged = tmp_path / "configs" / ".config_default_preupdate.yaml"
    staged.write_text("Runtime: [\n", encoding="utf-8")
    _make_owner_only(staged)

    result = _run_cli(tmp_path, "--validate-staged-baseline", str(staged))

    assert result.returncode == 2
    assert "Could not parse staged defaults baseline" in result.stderr
    assert not (tmp_path / "configs" / "config_sync_meta.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL contract")
def test_windows_stage_rejects_additional_acl_principal(tmp_path):
    _write_minimal_config_project(tmp_path)
    staged = tmp_path / "configs" / ".config_default_preupdate.yaml"
    _write_staged_defaults(staged, 1)
    _make_owner_only(staged)
    script = r"""
$ErrorActionPreference = 'Stop'
$path = $env:PIXEAGLE_TEST_STAGED_DEFAULTS_PATH
$everyone = [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0')
$acl = Get-Acl -LiteralPath $path
$acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new(
    $everyone,
    [System.Security.AccessControl.FileSystemRights]::Read,
    [System.Security.AccessControl.AccessControlType]::Allow
))
Set-Acl -LiteralPath $path -AclObject $acl
"""
    powershell_env = os.environ.copy()
    powershell_env["PIXEAGLE_TEST_STAGED_DEFAULTS_PATH"] = str(staged)
    acl_result = subprocess.run(
        [_windows_powershell(), "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        env=powershell_env,
    )
    assert acl_result.returncode == 0, acl_result.stderr or acl_result.stdout

    result = _run_cli(tmp_path, "--validate-staged-baseline", str(staged))

    assert result.returncode == 2
    assert "failed Windows ACL validation" in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission contract")
def test_staged_baseline_rejects_group_or_world_permissions(tmp_path):
    _write_minimal_config_project(tmp_path)
    staged = tmp_path / "configs" / ".config_default_preupdate.yaml"
    _write_staged_defaults(staged, 1)
    staged.chmod(0o644)

    result = _run_cli(tmp_path, "--initialize-baseline-from", str(staged))

    assert result.returncode == 2
    assert "permissions must be owner-only" in result.stderr
    assert not (tmp_path / "configs" / "config_sync_meta.json").exists()
