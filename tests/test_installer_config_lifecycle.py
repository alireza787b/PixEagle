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
import yaml


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
    defaults = yaml.safe_load(
        (REPO_ROOT / "configs" / "config_default.yaml").read_text(encoding="utf-8")
    )
    schema = yaml.safe_load(
        (REPO_ROOT / "configs" / "config_schema.yaml").read_text(encoding="utf-8")
    )
    defaults["Streaming"]["STREAM_FPS"] = default_value
    schema["sections"]["Streaming"]["parameters"]["STREAM_FPS"][
        "default"
    ] = default_value
    (configs / "config_default.yaml").write_text(
        yaml.safe_dump(defaults, sort_keys=False),
        encoding="utf-8",
    )
    (configs / "config_schema.yaml").write_text(
        yaml.safe_dump(schema, sort_keys=False),
        encoding="utf-8",
    )
    shutil.copy2(
        REPO_ROOT / "configs" / "config_retirements.yaml",
        configs / "config_retirements.yaml",
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
configs/config.yaml
dashboard/.env
""",
        encoding="utf-8",
    )

    for relative_path in (
        "Makefile",
        "install.sh",
        "scripts/lib/common.sh",
        "scripts/lib/dashboard_dependencies.sh",
        "scripts/lib/ports.sh",
        "scripts/lib/runtime_ownership.sh",
        "scripts/lib/sync.sh",
        "scripts/lib/setup_lock.sh",
        "scripts/lib/setup_lock_supervisor.py",
        "scripts/lib/venv_transaction.sh",
        "scripts/run.sh",
        "scripts/stop.sh",
        "scripts/update.sh",
        "scripts/service/cli.sh",
        "scripts/service/install.sh",
        "scripts/service/run.sh",
        "scripts/service/utils.sh",
        "scripts/setup/config-sync-status.py",
        "src/classes/config_service.py",
        "src/classes/config_sync.py",
        "src/classes/config_validator.py",
        "src/classes/follower_types.py",
        "src/classes/safety_types.py",
    ):
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative_path, destination)
    (root / "src" / "classes" / "__init__.py").touch()
    init_script = root / "scripts" / "init.sh"
    init_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$root/scripts/lib/common.sh"
staged="$root/configs/.config_default_preupdate.yaml"
python="$(resolve_pixeagle_venv_python "$root")"
if [[ ! -x "$python" ]]; then
    printf '%s\n' 'Config lifecycle is pending: virtual-environment Python unavailable' >&2
    exit 1
fi
"$python" "$root/scripts/setup/config-sync-status.py" \
    --project-root "$root" --initialize-baseline-from "$staged"
rm -f -- "$staged"
""",
        encoding="utf-8",
    )
    init_script.chmod(0o700)


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


def _prepare_remote_update(
    tmp_path: Path, *, failing_initializer: bool = False
) -> tuple[Path, Path, str, str]:
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
    if failing_initializer:
        (publisher / "scripts" / "init.sh").write_text(
            "#!/usr/bin/env bash\nexit 42\n", encoding="utf-8"
        )
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


def _run_sync(
    client: Path, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = """
set -euo pipefail
source scripts/lib/common.sh
source scripts/lib/setup_lock.sh
venv_dir="$(resolve_pixeagle_venv_dir "$PWD")"
pixeagle_run_with_resource_locks exclusive lifecycle-test 3 \
    "$PWD" "$venv_dir" -- \
    bash -c 'set -euo pipefail
        source scripts/lib/common.sh
        source scripts/lib/sync.sh
        do_sync
        bash scripts/init.sh'
"""
    return subprocess.run(
        ["bash", "-c", command],
        cwd=client,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_sync_and_report_failure_state(
    client: Path, *, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    command = """
set -euo pipefail
source scripts/lib/common.sh
source scripts/lib/setup_lock.sh
venv_dir="$(resolve_pixeagle_venv_dir "$PWD")"
pixeagle_run_with_resource_locks exclusive lifecycle-test 3 \
    "$PWD" "$venv_dir" -- \
    bash -c 'set -euo pipefail
        source scripts/lib/common.sh
        source scripts/lib/sync.sh
        status=0
        do_sync || status=$?
        printf "SYNC_CHANGED=%s\\n" "$PIXEAGLE_SYNC_CHANGED"
        exit "$status"'
"""
    return subprocess.run(
        ["bash", "-c", command],
        cwd=client,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_update(client: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "update-bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "lsof").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    (fake_bin / "tmux").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    (fake_bin / "systemctl").write_text(
        """#!/usr/bin/env bash
printf '%s\n' 'LoadState=not-found' 'ActiveState=inactive'
""",
        encoding="utf-8",
    )
    for command in ("lsof", "tmux", "systemctl"):
        (fake_bin / command).chmod(0o700)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "PIXEAGLE_NONINTERACTIVE": "1",
            "PIXEAGLE_INSTALL_PROFILE": "core",
        }
    )
    return subprocess.run(
        ["bash", "scripts/update.sh"],
        cwd=client,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


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
    check-ref-format)
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
    assert meta["defaults_snapshot"]["Streaming"]["STREAM_FPS"] == 1
    assert meta["defaults_snapshot_provenance"] == "pre_update_staged_defaults"
    assert not (client / "configs" / ".config_default_preupdate.yaml").exists()
    assert "Exact source candidate published" in result.stdout


def test_no_helper_retains_old_defaults_until_recovery(tmp_path):
    client, _remote, _old_head, new_head = _prepare_remote_update(tmp_path)

    first = _run_sync(client)

    staged = client / "configs" / ".config_default_preupdate.yaml"
    assert first.returncode == 1
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == new_head
    staged_defaults = yaml.safe_load(staged.read_text(encoding="utf-8"))
    assert staged_defaults["Streaming"]["STREAM_FPS"] == 1
    assert stat.S_IMODE(staged.stat().st_mode) == 0o600
    assert "config lifecycle is pending" in (first.stdout + first.stderr).lower()
    assert "Config update baseline" not in first.stdout

    _add_test_venv_python(client)
    second = _run_sync(client)

    assert second.returncode == 0, second.stdout + second.stderr
    assert (
        _load_sync_meta(client)["defaults_snapshot"]["Streaming"]["STREAM_FPS"]
        == 1
    )
    assert not staged.exists()


def test_existing_defaults_baseline_is_never_overwritten(tmp_path):
    client, _remote, _old_head, _new_head = _prepare_remote_update(tmp_path)
    _add_test_venv_python(client)
    metadata_path = client / "configs" / "config_sync_meta.json"
    metadata_path.write_text(
        json.dumps(
            {
                "defaults_snapshot": {"Streaming": {"STREAM_FPS": -7}},
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
    assert meta["defaults_snapshot"]["Streaming"]["STREAM_FPS"] == -7
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
    assert "Exact source candidate published" not in combined


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
    assert "Exact source candidate published" not in combined


def test_insecure_pending_stage_is_rejected_without_permission_repair(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    _add_test_venv_python(client)
    staged = client / "configs" / ".config_default_preupdate.yaml"
    staged.write_bytes((client / "configs" / "config_default.yaml").read_bytes())
    staged.chmod(0o644)

    result = _run_sync(client)

    assert result.returncode == 1
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert stat.S_IMODE(staged.stat().st_mode) == 0o644
    assert "must already be an owner-only single-link file" in (
        result.stdout + result.stderr
    )


def test_untracked_inventory_failure_is_not_treated_as_clean(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    fake_bin = tmp_path / "git-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git.write_text(
        f"""#!/usr/bin/env bash
if [[ ${{1:-}} == ls-files ]]; then exit 42; fi
exec {shlex.quote(real_git)} "$@"
""",
        encoding="utf-8",
    )
    fake_git.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = _run_sync(client, env=env)

    assert result.returncode == 2
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert "Cannot inspect untracked files" in result.stdout + result.stderr


def test_candidate_tracking_ignored_operator_path_is_rejected_before_fast_forward(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    publisher = tmp_path / "publisher"
    operator_config = publisher / "configs" / "config.yaml"
    operator_config.write_text("candidate-owned: true\n", encoding="utf-8")
    _git(publisher, "add", "-f", "configs/config.yaml")
    _commit(publisher, "candidate tracks operator config")
    _git(publisher, "push", "origin", "main")
    _add_test_venv_python(client)
    local_config = client / "configs" / "config.yaml"
    local_config.write_text("operator-owned: true\n", encoding="utf-8")

    result = _run_update(client, tmp_path)

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert local_config.read_text(encoding="utf-8") == "operator-owned: true\n"
    assert "would overwrite untracked or ignored operator data" in combined


def test_candidate_missing_public_runtime_contract_is_rejected_before_fast_forward(tmp_path):
    client, _remote, old_head, _new_head = _prepare_remote_update(tmp_path)
    publisher = tmp_path / "publisher"
    (publisher / "scripts" / "run.sh").unlink()
    _commit(publisher, "break public runtime contract")
    _git(publisher, "push", "origin", "main")
    _add_test_venv_python(client)

    result = _run_update(client, tmp_path)

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert "unsafe or missing required path: scripts/run.sh" in combined


def test_partial_fast_forward_failure_records_changed_head(tmp_path):
    client, _remote, old_head, _candidate_head = _prepare_remote_update(tmp_path)
    (client / "requirements.txt").write_text(
        "# unexpected local publication\n", encoding="utf-8"
    )
    unexpected_head = _commit(client, "unexpected publication")
    _git(client, "reset", "--hard", old_head)

    fake_bin = tmp_path / "merge-failure-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git.write_text(
        f"""#!/usr/bin/env bash
if [[ ${{1:-}} == merge && ${{2:-}} == --ff-only ]]; then
    {shlex.quote(real_git)} reset --hard "$TEST_FAILURE_HEAD" >/dev/null
    exit 42
fi
exec {shlex.quote(real_git)} "$@"
""",
        encoding="utf-8",
    )
    fake_git.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["TEST_FAILURE_HEAD"] = unexpected_head

    result = _run_sync_and_report_failure_state(client, env=env)

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == unexpected_head
    assert "SYNC_CHANGED=true" in combined
    assert "state requiring manual inspection" in combined


def test_full_updater_fast_forwards_reconciles_and_preserves_operator_config(tmp_path):
    client, _remote, _old_head, new_head = _prepare_remote_update(tmp_path)
    _add_test_venv_python(client)
    operator_config = client / "configs" / "config.yaml"
    operator_config.write_bytes((client / "configs" / "config_default.yaml").read_bytes())
    dashboard_secret = client / "dashboard" / ".env"
    dashboard_secret.parent.mkdir()
    dashboard_secret.write_text("PIXEAGLE_DEMO_PASSWORD=keep-me\n", encoding="utf-8")
    expected_config = operator_config.read_bytes()

    result = _run_update(client, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == new_head
    assert operator_config.read_bytes() == expected_config
    assert dashboard_secret.read_text(encoding="utf-8") == "PIXEAGLE_DEMO_PASSWORD=keep-me\n"
    assert _load_sync_meta(client)["defaults_snapshot"]["Streaming"]["STREAM_FPS"] == 1
    assert not (client / "configs" / ".config_default_preupdate.yaml").exists()
    assert "Update reconciliation complete" in result.stdout


def test_full_updater_rolls_back_source_after_initializer_failure(tmp_path):
    client, _remote, old_head, new_head = _prepare_remote_update(
        tmp_path, failing_initializer=True
    )
    _add_test_venv_python(client)
    operator_config = client / "configs" / "config.yaml"
    operator_config.write_bytes((client / "configs" / "config_default.yaml").read_bytes())
    dashboard_secret = client / "dashboard" / ".env"
    dashboard_secret.parent.mkdir()
    dashboard_secret.write_text("PIXEAGLE_DEMO_PASSWORD=keep-me\n", encoding="utf-8")
    expected_config = operator_config.read_bytes()

    result = _run_update(client, tmp_path)

    combined = result.stdout + result.stderr
    assert result.returncode == 42, combined
    assert old_head != new_head
    assert _git(client, "rev-parse", "HEAD").stdout.strip() == old_head
    assert operator_config.read_bytes() == expected_config
    assert dashboard_secret.read_text(encoding="utf-8") == "PIXEAGLE_DEMO_PASSWORD=keep-me\n"
    staged = client / "configs" / ".config_default_preupdate.yaml"
    assert staged.is_file()
    assert yaml.safe_load(staged.read_text(encoding="utf-8"))["Streaming"][
        "STREAM_FPS"
    ] == 1
    assert "Previous source commit restored" in combined


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


def _prepare_bootstrap_remote(tmp_path: Path) -> tuple[Path, str, str]:
    publisher = tmp_path / "bootstrap-publisher"
    publisher.mkdir()
    _git(publisher, "init", "-b", "main")
    scripts = publisher / "scripts"
    scripts.mkdir()
    (scripts / "init.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "${PIXEAGLE_INSTALL_PROFILE:-unset}" > "${PIXEAGLE_BOOTSTRAP_TEST_MARKER:?}"
""",
        encoding="utf-8",
    )
    (publisher / "source-version.txt").write_text("pinned\n", encoding="utf-8")
    pinned_head = _commit(publisher, "pinned source")
    (publisher / "source-version.txt").write_text("mutable-latest\n", encoding="utf-8")
    mutable_head = _commit(publisher, "newer mutable source")

    remote = tmp_path / "bootstrap-remote.git"
    _run("git", "clone", "--bare", str(publisher), str(remote), cwd=tmp_path)
    return remote, pinned_head, mutable_head


def _bootstrap_env(
    tmp_path: Path, remote: Path, install_dir: Path, marker: Path
) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PIXEAGLE_BRANCH", None)
    env.pop("PIXEAGLE_COMMIT", None)
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PIXEAGLE_REPO_URL": str(remote),
            "PIXEAGLE_HOME": str(install_dir),
            "PIXEAGLE_NONINTERACTIVE": "1",
            "PIXEAGLE_INSTALL_PROFILE": "core",
            "PIXEAGLE_BOOTSTRAP_TEST_MARKER": str(marker),
        }
    )
    Path(env["HOME"]).mkdir()
    return env


def test_linux_installer_publishes_only_exact_detached_commit(tmp_path):
    remote, pinned_head, mutable_head = _prepare_bootstrap_remote(tmp_path)
    install_dir = tmp_path / "pinned-install"
    marker = tmp_path / "pinned-init-marker"
    env = _bootstrap_env(tmp_path, remote, install_dir, marker)
    env["PIXEAGLE_COMMIT"] = pinned_head

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert pinned_head != mutable_head
    assert _git(install_dir, "rev-parse", "HEAD").stdout.strip() == pinned_head
    assert _git(install_dir, "branch", "--show-current").stdout.strip() == ""
    assert (install_dir / "source-version.txt").read_text(encoding="utf-8") == "pinned\n"
    assert marker.read_text(encoding="utf-8") == "core\n"
    assert "production/RPi exact-commit" in combined
    assert f"Source HEAD: {pinned_head}" in combined
    assert not list(tmp_path.glob(".pixeagle-bootstrap.*"))


def test_linux_installer_labels_mutable_branch_as_lab_development(tmp_path):
    remote, _pinned_head, mutable_head = _prepare_bootstrap_remote(tmp_path)
    install_dir = tmp_path / "lab-install"
    marker = tmp_path / "lab-init-marker"
    env = _bootstrap_env(tmp_path, remote, install_dir, marker)

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert _git(install_dir, "rev-parse", "HEAD").stdout.strip() == mutable_head
    assert _git(install_dir, "branch", "--show-current").stdout.strip() == "main"
    assert "mutable and this path is for lab/development only" in combined
    assert "Source mode: mutable lab/development branch" in combined


def test_linux_installer_rejects_ambiguous_commit_before_install_path_mutation(tmp_path):
    install_dir = tmp_path / "not-created" / "PixEagle"
    env = os.environ.copy()
    env.pop("PIXEAGLE_BRANCH", None)
    env["PIXEAGLE_HOME"] = str(install_dir)
    env["PIXEAGLE_COMMIT"] = "main"
    env["PIXEAGLE_NONINTERACTIVE"] = "1"
    env["PIXEAGLE_INSTALL_PROFILE"] = "core"

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "must be one exact 40-hex Git commit" in (result.stdout + result.stderr)
    assert not install_dir.parent.exists()


def test_linux_installer_rejects_commit_plus_branch_as_ambiguous(tmp_path):
    install_dir = tmp_path / "not-created" / "PixEagle"
    env = os.environ.copy()
    env["PIXEAGLE_HOME"] = str(install_dir)
    env["PIXEAGLE_COMMIT"] = "a" * 40
    env["PIXEAGLE_BRANCH"] = "main"
    env["PIXEAGLE_NONINTERACTIVE"] = "1"
    env["PIXEAGLE_INSTALL_PROFILE"] = "core"

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Do not combine PIXEAGLE_COMMIT with PIXEAGLE_BRANCH" in (
        result.stdout + result.stderr
    )
    assert not install_dir.parent.exists()


def test_nvm_bootstrap_verifies_checksum_before_external_script_execution(tmp_path):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    execution_marker = tmp_path / "external-bash-ran"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/bin/sh
output=''
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--output" ]; then
        shift
        output="$1"
    fi
    shift
done
printf 'tampered installer\n' > "$output"
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o700)
    fake_bash = fake_bin / "bash"
    fake_bash.write_text(
        """#!/bin/sh
: > "$PIXEAGLE_NVM_EXEC_MARKER"
exit 0
""",
        encoding="utf-8",
    )
    fake_bash.chmod(0o700)
    home = tmp_path / "nvm-home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "PIXEAGLE_NVM_EXEC_MARKER": str(execution_marker),
        }
    )

    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f'source {shlex.quote(str(REPO_ROOT / "scripts" / "init.sh"))}; '
            'export NVM_DIR="$HOME/.nvm"; install_verified_nvm',
        ],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 11, result.stdout + result.stderr
    assert not execution_marker.exists()
    assert not (home / ".nvm").exists()
    assert not list(home.glob(".pixeagle-nvm-install.*"))


def test_nvm_bootstrap_contract_pins_script_hash_and_nvm_commit():
    source = (REPO_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    download = source.index('--output "$installer" "$NVM_INSTALL_URL"')
    verify = source.index("sha256sum --check --status", download)
    execute = source.index('bash "$installer"', verify)
    assert download < verify < execute
    assert 'NVM_INSTALL_VERSION="$NVM_INSTALL_COMMIT"' in source
    assert "curl -o-" not in source
    assert "| bash" not in source


def test_initializer_refuses_unverified_existing_nvm_and_lockfile_fallbacks():
    source = (REPO_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")

    existing_nvm_branch = source.index('if [[ -s "$NVM_DIR/nvm.sh" ]]')
    provenance_check = source.index(
        'if ! nvm_checkout_is_pinned "$NVM_DIR"', existing_nvm_branch
    )
    nvm_source = source.index('source "$NVM_DIR/nvm.sh"', provenance_check)
    assert existing_nvm_branch < provenance_check < nvm_source

    assert "npm ci --silent --no-audit --no-fund" in source
    assert "npm install --silent --no-audit --no-fund" not in source


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
