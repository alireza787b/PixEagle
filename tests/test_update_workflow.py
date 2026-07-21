"""Contract tests for explicit source-plus-environment update reconciliation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "update.sh"
SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "lib" / "sync.sh"


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=PixEagle Update Test",
            "-c",
            "user.email=update@example.invalid",
            "commit",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def test_update_help_describes_noninteractive_profile_and_no_restart():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "PIXEAGLE_INSTALL_PROFILE=core|full" in result.stdout
    assert "never stops or restarts PixEagle" in result.stdout
    assert "never deletes untracked or" in result.stdout
    assert "manual runtime:  make stop" in result.stdout
    assert "managed runtime: pixeagle-service stop" in result.stdout


def test_update_orders_fast_forward_before_initializer_and_bounds_rollback():
    source = SCRIPT.read_text(encoding="utf-8")

    transaction = source.index("run_update_transaction()")
    sync_call = source.index("do_sync", transaction)
    init_call = source.index('bash "$INIT_SCRIPT"', sync_call)
    assert sync_call < init_call
    assert source.count('git reset --hard "$old_head"') == 1
    assert 'current_head" != "$new_head"' in source
    assert "tracked_checkout_is_clean" in source
    assert "git stash" not in source
    assert "git checkout" not in source
    assert "scripts/stop.sh" not in source
    assert "scripts/run.sh" not in source


def test_update_checks_runtime_before_waiting_for_the_outer_resource_lock():
    source = SCRIPT.read_text(encoding="utf-8")
    main = source.index("main()")
    preflight = source.index("if ! assert_runtime_stopped; then", main)
    lock = source.index("pixeagle_run_with_resource_locks", main)

    assert preflight < lock
    assert "Update was not started; no source, dependency, or config changes were made." in source


def test_internal_update_entrypoint_requires_real_supervisor_context():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--internal-update", "--dry-run"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 73
    assert "outside the supervised" in result.stdout + result.stderr


def test_systemd_active_job_and_query_failure_are_update_blockers(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        """#!/usr/bin/env bash
case "${TEST_SYSTEMD_STATE:-active}" in
  active) printf '%s\n' 'LoadState=loaded' 'ActiveState=active' 'Job=' ;;
  queued) printf '%s\n' 'LoadState=loaded' 'ActiveState=inactive' 'Job=/job/42' ;;
  failure) exit 42 ;;
esac
""",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    for state, expected in (
        ("active", "system pixeagle.service (active)"),
        ("queued", "has a queued systemd job"),
    ):
        env["TEST_SYSTEMD_STATE"] = state
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"source {SCRIPT!s}; systemd_scope_blockers system",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
        assert expected in result.stdout

    env["TEST_SYSTEMD_STATE"] = "failure"
    failed_query = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {SCRIPT!s}; "
                "systemd_scope_is_expected() { return 0; }; "
                "systemd_scope_blockers system"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert "state query failed" in failed_query.stdout


def test_lsof_execution_failure_is_an_update_blocker(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_lsof = fake_bin / "lsof"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    shell = f"""
set -euo pipefail
source {SCRIPT!s}
source {PROJECT_ROOT / 'scripts' / 'lib' / 'ports.sh'!s}
runtime_listener_labels
"""

    for body, expected_status in (
        ("exit 42", "42"),
        ("printf 'fatal lsof read failure\\n' >&2\nexit 1", "1"),
    ):
        fake_lsof.write_text(
            f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8"
        )
        fake_lsof.chmod(0o700)
        result = subprocess.run(
            ["bash", "-c", shell],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0
        assert "listener ownership query failed" in result.stdout
        assert f"lsof status {expected_status}" in result.stdout


def test_only_one_public_update_command_surface_remains():
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    service_cli = (PROJECT_ROOT / "scripts" / "service" / "cli.sh").read_text(
        encoding="utf-8"
    )

    assert "\nsync:" not in makefile
    assert "sync-restart:" not in makefile
    assert "pixeagle-service sync" not in service_cli
    assert "sync|update" not in service_cli
    assert not (PROJECT_ROOT / "scripts" / "service" / "sync_and_restart.sh").exists()


def test_service_update_command_delegates_all_options_to_canonical_updater(tmp_path):
    fake_root = tmp_path / "checkout"
    update_script = fake_root / "scripts" / "update.sh"
    update_script.parent.mkdir(parents=True)
    marker = tmp_path / "args.txt"
    update_script.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > {marker!s}\n",
        encoding="utf-8",
    )
    update_script.chmod(0o700)
    service_cli = PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    shell = f"""
set -euo pipefail
source {service_cli!s}
PROJECT_ROOT={fake_root!s}
detect_service_user() {{ SERVICE_USER="$(id -un)"; }}
update_command --dry-run --remote upstream --branch candidate
"""

    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == [
        "--dry-run",
        "--remote",
        "upstream",
        "--branch",
        "candidate",
    ]


def test_guarded_rollback_restores_source_but_preserves_ignored_operator_data(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("old\n", encoding="utf-8")
    (repo / ".gitignore").write_text("operator.secret\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    commit_args = [
        "git",
        "-c",
        "user.name=PixEagle Update Test",
        "-c",
        "user.email=update@example.invalid",
        "commit",
    ]
    subprocess.run([*commit_args, "-m", "old"], cwd=repo, check=True)
    old_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    tracked.write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
    subprocess.run([*commit_args, "-m", "new"], cwd=repo, check=True)
    new_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    secret = repo / "operator.secret"
    secret.write_text("keep-me\n", encoding="utf-8")

    shell = f"""
set -euo pipefail
source {SCRIPT!s}
source {SYNC_SCRIPT!s}
PIXEAGLE_SYNC_CHANGED=true
PIXEAGLE_SYNC_OLD_HEAD={old_head}
PIXEAGLE_SYNC_NEW_HEAD={new_head}
rollback_source_if_safe test-failure
"""
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        == old_head
    )
    assert tracked.read_text(encoding="utf-8") == "old\n"
    assert secret.read_text(encoding="utf-8") == "keep-me\n"


def test_candidate_publication_refuses_ignored_path_collision(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("operator.secret\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("old\n", encoding="utf-8")
    old_head = _commit_all(repo, "old")

    secret = repo / "operator.secret"
    secret.write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", "operator.secret"], cwd=repo, check=True)
    candidate_head = _commit_all(repo, "candidate tracks ignored path")
    subprocess.run(["git", "reset", "--hard", old_head], cwd=repo, check=True)
    secret.write_text("operator-owned\n", encoding="utf-8")

    shell = f"""
set -euo pipefail
source {SYNC_SCRIPT!s}
_target_tree_preserves_untracked_paths {old_head} {candidate_head}
"""
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "would overwrite untracked or ignored operator data" in (
        result.stdout + result.stderr
    )
    assert secret.read_text(encoding="utf-8") == "operator-owned\n"
    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip() == old_head


def test_guarded_rollback_refuses_ignored_path_collision(tmp_path):
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
    secret = repo / "operator.secret"
    secret.write_text("old-tracked\n", encoding="utf-8")
    old_head = _commit_all(repo, "old tracks path")

    secret.unlink()
    (repo / ".gitignore").write_text("operator.secret\n", encoding="utf-8")
    new_head = _commit_all(repo, "new ignores path")
    secret.write_text("operator-owned\n", encoding="utf-8")

    shell = f"""
set -euo pipefail
source {SCRIPT!s}
source {SYNC_SCRIPT!s}
PIXEAGLE_SYNC_CHANGED=true
PIXEAGLE_SYNC_OLD_HEAD={old_head}
PIXEAGLE_SYNC_NEW_HEAD={new_head}
rollback_source_if_safe test-failure
"""
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "rollback refused" in (result.stdout + result.stderr).lower()
    assert secret.read_text(encoding="utf-8") == "operator-owned\n"
    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip() == new_head


def test_noninteractive_update_requires_explicit_profile_before_sync():
    shell = f"""
set -euo pipefail
source {SCRIPT!s}
PIXEAGLE_NONINTERACTIVE=1
PIXEAGLE_INSTALL_PROFILE=""
validate_automation_profile
"""
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "requires PIXEAGLE_INSTALL_PROFILE=core|full" in (
        result.stdout + result.stderr
    )


def test_existing_checkout_installer_delegates_to_update_script(tmp_path):
    checkout = tmp_path / "existing"
    checkout.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=checkout, check=True)
    scripts = checkout / "scripts"
    scripts.mkdir()
    (scripts / "update.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'delegated\n' > "${PIXEAGLE_UPDATE_TEST_MARKER:?}"
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=PixEagle Update Test",
            "-c",
            "user.email=update@example.invalid",
            "commit",
            "-m",
            "test updater",
        ],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    marker = tmp_path / "update-marker"
    env = os.environ.copy()
    env.pop("PIXEAGLE_COMMIT", None)
    env.update(
        {
            "PIXEAGLE_HOME": str(checkout),
            "PIXEAGLE_BRANCH": "main",
            "PIXEAGLE_NONINTERACTIVE": "1",
            "PIXEAGLE_INSTALL_PROFILE": "core",
            "PIXEAGLE_UPDATE_TEST_MARKER": str(marker),
        }
    )

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "install.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding="utf-8") == "delegated\n"
    assert "Running the ownership-aware stopped-runtime updater" in result.stdout


def test_installer_does_not_reimplement_existing_checkout_merge():
    source = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "bash scripts/update.sh" in source
    assert "git merge --ff-only" not in source
    assert "git pull" not in source
