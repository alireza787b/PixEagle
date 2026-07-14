"""End-to-end tests for defaults preservation across source updates."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.name == "nt", reason="bash lifecycle"),
]
REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run("git", *args, cwd=repo)


def _write_config_contract(root: Path, default_value: int) -> None:
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / "config_default.yaml").write_text(
        f"Runtime:\n  VALUE: {default_value}\n",
        encoding="utf-8",
    )
    (configs / "config_schema.yaml").write_text(
        """\
schema_version: 1.0.0
sections:
  Runtime:
    type: object
    parameters:
      VALUE:
        type: integer
        default: %d
"""
        % default_value,
        encoding="utf-8",
    )
    (configs / "config_retirements.yaml").write_text(
        "registry_version: 1\nretirements: []\n",
        encoding="utf-8",
    )


def _write_lifecycle_checkout(root: Path, default_value: int = 1) -> None:
    _write_config_contract(root, default_value)
    (root / "requirements.txt").write_text("# lifecycle test marker\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        """\
.venv/
venv/
configs/config.lock
configs/config_sync_meta.json
configs/audit_log.json
configs/backups/
configs/.config_default_preupdate.yaml
""",
        encoding="utf-8",
    )

    for relative_path in (
        "scripts/lib/common.sh",
        "scripts/lib/sync.sh",
        "scripts/setup/config-sync-status.py",
        "src/classes/config_service.py",
        "src/classes/config_sync.py",
    ):
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative_path, destination)
    (root / "src" / "classes" / "__init__.py").touch()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=PixEagle Lifecycle Test",
        "-c",
        "user.email=lifecycle@example.invalid",
        "commit",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _prepare_remote_update(tmp_path: Path) -> tuple[Path, Path, str, str]:
    publisher = tmp_path / "publisher"
    publisher.mkdir()
    _git(publisher, "init", "-b", "main")
    _write_lifecycle_checkout(publisher, default_value=1)
    old_head = _commit(publisher, "old defaults")

    remote = tmp_path / "remote.git"
    _run("git", "clone", "--bare", str(publisher), str(remote), cwd=tmp_path)
    client = tmp_path / "client"
    _run("git", "clone", str(remote), str(client), cwd=tmp_path)

    _git(publisher, "remote", "add", "origin", str(remote))
    _write_config_contract(publisher, default_value=2)
    new_head = _commit(publisher, "new defaults")
    _git(publisher, "push", "origin", "main")
    return client, remote, old_head, new_head


def _add_test_venv_python(client: Path) -> None:
    python_path = client / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text(
        f"#!/bin/sh\nexec {shlex.quote(str(Path(sys.executable).absolute()))} \"$@\"\n",
        encoding="utf-8",
    )
    python_path.chmod(0o700)


def _run_sync(client: Path) -> subprocess.CompletedProcess[str]:
    return _run("bash", "scripts/lib/sync.sh", cwd=client, check=False)


def _load_sync_meta(client: Path) -> dict:
    return json.loads((client / "configs" / "config_sync_meta.json").read_text(encoding="utf-8"))


def _write_failing_status_git(bin_dir: Path) -> None:
    fake_git = bin_dir / "git"
    fake_git.write_text(
        """#!/bin/sh
case "$1" in
    --version)
        echo "git version 2.43.0"
        exit 0
        ;;
    rev-parse)
        echo "test-head"
        exit 0
        ;;
    branch)
        echo "main"
        exit 0
        ;;
    status)
        exit 42
        ;;
esac
exit 99
""",
        encoding="utf-8",
    )
    fake_git.chmod(0o700)


def test_old_defaults_survive_real_fast_forward(tmp_path):
    client, _remote, old_head, new_head = _prepare_remote_update(tmp_path)
    _add_test_venv_python(client)

    result = _run_sync(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == new_head
    assert old_head != new_head
    meta = _load_sync_meta(client)
    assert meta["defaults_snapshot"]["Runtime"]["VALUE"] == 1
    assert meta["defaults_snapshot_provenance"] == "pre_update_staged_defaults"
    assert not (client / "configs" / ".config_default_preupdate.yaml").exists()
    assert "Sync complete" in result.stdout


def test_no_helper_retains_old_defaults_until_recovery(tmp_path):
    client, _remote, _old_head, new_head = _prepare_remote_update(tmp_path)

    first = _run_sync(client)

    staged = client / "configs" / ".config_default_preupdate.yaml"
    assert first.returncode == 1
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == new_head
    assert staged.read_text(encoding="utf-8") == "Runtime:\n  VALUE: 1\n"
    assert stat.S_IMODE(staged.stat().st_mode) == 0o600
    assert "configuration readiness is degraded" in (first.stdout + first.stderr).lower()
    assert "Sync complete" not in first.stdout

    _add_test_venv_python(client)
    second = _run_sync(client)

    assert second.returncode == 0, second.stdout + second.stderr
    assert _load_sync_meta(client)["defaults_snapshot"]["Runtime"]["VALUE"] == 1
    assert not staged.exists()


def test_existing_defaults_baseline_is_never_overwritten(tmp_path):
    client, _remote, _old_head, _new_head = _prepare_remote_update(tmp_path)
    _add_test_venv_python(client)
    metadata_path = client / "configs" / "config_sync_meta.json"
    metadata_path.write_text(
        json.dumps(
            {
                "defaults_snapshot": {"Runtime": {"VALUE": -7}},
                "defaults_snapshot_saved_at": "existing",
                "defaults_snapshot_mode": "full",
            }
        ),
        encoding="utf-8",
    )
    metadata_path.chmod(0o600)

    result = _run_sync(client)

    assert result.returncode == 0, result.stdout + result.stderr
    meta = _load_sync_meta(client)
    assert meta["defaults_snapshot"]["Runtime"]["VALUE"] == -7
    assert meta["defaults_snapshot_saved_at"] == "existing"
    assert "defaults_snapshot_provenance" not in meta


def test_invalid_pending_stage_aborts_before_fetch(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    staged = client / "configs" / ".config_default_preupdate.yaml"
    staged.symlink_to(client / "configs" / "config_default.yaml")

    result = _run_sync(client)

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert "not an owner-controlled regular file" in combined
    assert "Fetching updates" not in combined


def test_malformed_pending_stage_aborts_before_fetch(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    staged = client / "configs" / ".config_default_preupdate.yaml"
    staged.write_text("Runtime: [\n", encoding="utf-8")
    staged.chmod(0o600)

    result = _run_sync(client)

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert "failed integrity validation" in combined
    assert "Fetching updates" not in combined


def test_linux_installer_fails_closed_when_worktree_status_is_unavailable(tmp_path):
    install_dir = tmp_path / "existing"
    (install_dir / ".git").mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_failing_status_git(fake_bin)
    env = os.environ.copy()
    env["PIXEAGLE_HOME"] = str(install_dir)
    env["PIXEAGLE_BRANCH"] = "main"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "Cannot inspect the existing checkout" in combined
    assert "Updating repository" not in combined
    assert "Running initialization script" not in combined


def test_windows_installer_checks_git_status_exit_before_filtering_output():
    source = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    capture = source.index(
        "$rawStatus = @(git status --porcelain --untracked-files=all 2>$null)"
    )
    exit_capture = source.index("$statusExitCode = $LASTEXITCODE", capture)
    fail_closed = source.index("if ($statusExitCode -ne 0)", exit_capture)
    filtering = source.index("$status = @(", fail_closed)

    assert capture < exit_capture < fail_closed < filtering
    assert "Cannot inspect the existing checkout; refusing automatic update" in source
