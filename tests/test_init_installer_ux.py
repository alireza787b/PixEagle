"""Regression tests for the guided Linux installer interaction contract."""

from __future__ import annotations

import os
import re
import signal
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name == "nt", reason="bash installer")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = PROJECT_ROOT / "scripts" / "init.sh"
INSTALL_SCRIPT = PROJECT_ROOT / "install.sh"
RUN_SCRIPT = PROJECT_ROOT / "scripts" / "run.sh"
COMMON_SCRIPT = PROJECT_ROOT / "scripts" / "lib" / "common.sh"
DASHBOARD_DEPENDENCIES_HELPER = (
    PROJECT_ROOT / "scripts" / "lib" / "dashboard_dependencies.sh"
)
SHORTCUT_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "install-shell-shortcut.sh"
OPENCV_BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
PYTORCH_COMPAT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "setup" / "check-python-compatibility.py"
)
PYTORCH_MATRIX = PROJECT_ROOT / "scripts" / "setup" / "pytorch_matrix.json"
NVM_COMMIT = "977563e97ddc66facf3a8e31c6cff01d236f09bd"


def _run_bash(
    script: str,
    *,
    env: dict[str, str] | None = None,
    no_controlling_tty: bool = False,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    if env is None or "PIXEAGLE_HOME" not in env:
        run_env["PIXEAGLE_HOME"] = str(PROJECT_ROOT)
    kwargs: dict[str, object] = {}
    if no_controlling_tty:
        kwargs.update(stdin=subprocess.DEVNULL, preexec_fn=os.setsid)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=PROJECT_ROOT,
        env=run_env,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def _create_legacy_checkout(path: Path) -> Path:
    checkout = path / "PixEagle"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "dashboard").mkdir()
    (checkout / "scripts" / "update.sh").write_text(
        "#!/usr/bin/env bash\n",
        encoding="utf-8",
    )
    (checkout / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(checkout)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "config", "user.name", "PixEagle Test"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "config",
            "user.email",
            "pixeagle-test@example.invalid",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "add", "scripts/update.sh", "tracked.txt"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
        text=True,
    )
    return checkout


def test_existing_checkout_preserves_known_generated_backups_after_confirmation(
    tmp_path: Path,
):
    checkout = _create_legacy_checkout(tmp_path)
    backup = checkout / "dashboard" / "backups" / "env_test.env"
    backup.parent.mkdir()
    backup.write_text("REACT_APP_API_URL=test\n", encoding="utf-8")

    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
read_user_input() {{ printf -v "$1" ""; }}
inspect_existing_checkout
git -C "$INSTALL_DIR" status --porcelain --untracked-files=all
''',
        env={"PIXEAGLE_HOME": str(checkout)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Found only generated dashboard settings backups" in result.stdout
    assert "Generated dashboard backups preserved" in result.stdout
    assert backup.read_text(encoding="utf-8") == "REACT_APP_API_URL=test\n"
    exclude = (checkout / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert "/dashboard/backups/" in exclude.splitlines()
    assert "?? dashboard/backups" not in result.stdout


def test_existing_checkout_does_not_hide_unknown_untracked_files(tmp_path: Path):
    checkout = _create_legacy_checkout(tmp_path)
    unknown = checkout / "operator-notes.txt"
    unknown.write_text("keep me\n", encoding="utf-8")

    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
inspect_existing_checkout
''',
        env={"PIXEAGLE_HOME": str(checkout)},
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "git stash push --include-untracked" in combined
    assert unknown.read_text(encoding="utf-8") == "keep me\n"
    exclude = (checkout / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert "/dashboard/backups/" not in exclude.splitlines()


def test_existing_checkout_honors_generated_backup_preservation_decline(
    tmp_path: Path,
):
    checkout = _create_legacy_checkout(tmp_path)
    backup = checkout / "dashboard" / "backups" / "env_test.env"
    backup.parent.mkdir()
    backup.write_text("keep me\n", encoding="utf-8")

    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
read_user_input() {{ printf -v "$1" "n"; }}
inspect_existing_checkout
''',
        env={"PIXEAGLE_HOME": str(checkout)},
    )

    assert result.returncode != 0
    assert "Generated backups were left unchanged" in result.stderr
    assert backup.read_text(encoding="utf-8") == "keep me\n"
    exclude = (checkout / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert "/dashboard/backups/" not in exclude.splitlines()


def test_generated_dashboard_backup_directory_is_ignored():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "dashboard/backups/" in ignored


def test_direct_profile_selection_requires_explicit_consent_without_terminal():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
unset PIXEAGLE_NONINTERACTIVE PIXEAGLE_INSTALL_PROFILE
select_installation_profile
''',
        no_controlling_tty=True,
    )

    assert result.returncode != 0
    assert "No controlling terminal is available" in result.stdout
    assert "/dev/tty: No such device" not in result.stdout + result.stderr


def test_one_line_bootstrap_selects_core_explicitly_without_terminal():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
unset PIXEAGLE_NONINTERACTIVE PIXEAGLE_INSTALL_PROFILE
prepare_noninteractive_profile
printf 'NONINTERACTIVE=%s PROFILE=%s\n' \
    "$PIXEAGLE_NONINTERACTIVE" "$PIXEAGLE_INSTALL_PROFILE"
''',
        no_controlling_tty=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "NONINTERACTIVE=1 PROFILE=core" in result.stdout
    assert "/dev/tty: No such device" not in result.stdout + result.stderr


def test_bootstrap_offers_to_install_missing_git_with_enter_default(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_path = shutil.which("python3")
    real_git = shutil.which("git")
    assert python_path is not None
    assert real_git is not None
    (fake_bin / "python3").symlink_to(python_path)

    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
FAKE_BIN={shlex.quote(str(fake_bin))}
REAL_GIT={shlex.quote(real_git)}
PATH="$FAKE_BIN"
read_user_input() {{ printf -v "$1" ""; }}
install_bootstrap_packages() {{
    printf 'INSTALL_PACKAGES=%s\n' "$*"
    /bin/ln -s "$REAL_GIT" "$FAKE_BIN/git"
}}
check_prerequisites
''',
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Missing bootstrap prerequisites: git" in result.stdout
    assert "Install missing bootstrap packages now? [Y/n]:" in result.stdout
    assert "INSTALL_PACKAGES=git" in result.stdout
    assert "Bootstrap prerequisites available" in result.stdout


def test_bootstrap_missing_git_without_terminal_is_actionable(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_path = shutil.which("python3")
    assert python_path is not None
    (fake_bin / "python3").symlink_to(python_path)

    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=noninteractive
unset PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES
PATH={shlex.quote(str(fake_bin))}
check_prerequisites
''',
        no_controlling_tty=True,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Missing bootstrap prerequisites: git" in combined
    assert "PIXEAGLE_INSTALL_BOOTSTRAP_PACKAGES=1" in combined
    assert "/dev/tty: No such device" not in combined


def test_bootstrap_prepares_terminal_mode_before_prerequisite_recovery():
    source = INSTALL_SCRIPT.read_text(encoding="utf-8")
    main_source = source[source.index("main() {") :]

    assert main_source.index("prepare_noninteractive_profile") < main_source.index(
        "check_prerequisites"
    )


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_curl_piped_bootstrap_forwards_ssh_tty_to_profile_prompt():
    child = f'''
source "{INIT_SCRIPT}"
select_installation_profile
printf 'SELECTED_PROFILE=%s\\n' "$INSTALL_PROFILE"
'''
    payload = f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
unset PIXEAGLE_NONINTERACTIVE PIXEAGLE_INSTALL_PROFILE
prepare_noninteractive_profile
printf 'INPUT_MODE=%s NONINTERACTIVE=%s\\n' \
    "$GUIDED_INPUT_MODE" "${{PIXEAGLE_NONINTERACTIVE-unset}}"
run_guided_command bash -c {shlex.quote(child)}
'''
    command = f"printf %s {shlex.quote(payload)} | bash"

    result = subprocess.run(
        ["script", "-qfec", command, "/dev/null"],
        cwd=PROJECT_ROOT,
        input="2\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "INPUT_MODE=tty NONINTERACTIVE=unset" in result.stdout
    assert "SELECTED_PROFILE=full" in result.stdout
    assert "No controlling terminal is available" not in result.stdout
    installer = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "run_guided_command env" in installer
    assert "PIXEAGLE_BOOTSTRAP_CONTEXT=1" in installer
    assert "PIXEAGLE_SETUP_ACTION=fresh" in installer
    assert "PIXEAGLE_SETUP_ACTION=update-repair" in installer
    assert "bash scripts/update.sh" in installer


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_curl_piped_bootstrap_forwards_terminal_to_sudo_password(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo_log = tmp_path / "sudo-args.log"
    sudo_state = tmp_path / "sudo-authenticated"
    fake_sudo = fake_bin / "sudo"
    fake_sudo.write_text(
        """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$PIXEAGLE_FAKE_SUDO_LOG"
if [[ "${1:-}" == "-n" && "${2:-}" == "-v" ]]; then
    [[ -f "$PIXEAGLE_FAKE_SUDO_STATE" ]]
    exit
fi
if [[ "${1:-}" == "-S" && "${2:-}" == "-v" ]]; then
    IFS= read -r password
    [[ "$password" == "test-only-password" ]]
    : > "$PIXEAGLE_FAKE_SUDO_STATE"
    exit
fi
if [[ "${1:-}" == "-n" ]]; then
    shift
    "$@"
    exit
fi
exit 64
""",
        encoding="utf-8",
    )
    fake_sudo.chmod(0o700)
    fake_apt_get = fake_bin / "apt-get"
    fake_apt_get.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_apt_get.chmod(0o700)

    child = f'''
source "{INIT_SCRIPT}"
pixeagle_running_as_root() {{ return 1; }}
prompt_sudo
run_apt_get update
printf 'SUDO_PROMPT_READY=yes\\n'
'''
    payload = f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
unset PIXEAGLE_NONINTERACTIVE PIXEAGLE_INSTALL_PROFILE
prepare_noninteractive_profile
run_guided_command bash -c {shlex.quote(child)}
'''
    command = f"printf %s {shlex.quote(payload)} | bash"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["PIXEAGLE_FAKE_SUDO_LOG"] = str(sudo_log)
    env["PIXEAGLE_FAKE_SUDO_STATE"] = str(sudo_state)

    result = subprocess.run(
        ["script", "-qfec", command, "/dev/null"],
        cwd=PROJECT_ROOT,
        env=env,
        input="test-only-password\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SUDO_PROMPT_READY=yes" in result.stdout
    sudo_calls = sudo_log.read_text(encoding="utf-8").splitlines()
    assert sudo_calls == [
        "-n -v",
        "-S -v",
        "-n -v",
        "-n env DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none apt-get update",
    ]
    assert "test-only-password" not in sudo_log.read_text(encoding="utf-8")


def test_unattended_sudo_validation_fails_without_password_read(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo_log = tmp_path / "sudo-args.log"
    fake_sudo = fake_bin / "sudo"
    fake_sudo.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$PIXEAGLE_FAKE_SUDO_LOG"
exit 1
""",
        encoding="utf-8",
    )
    fake_sudo.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["PIXEAGLE_FAKE_SUDO_LOG"] = str(sudo_log)

    result = _run_bash(
        f'''
source "{COMMON_SCRIPT}"
pixeagle_running_as_root() {{ return 1; }}
PIXEAGLE_NONINTERACTIVE=1
if pixeagle_sudo_validate; then
    exit 31
fi
printf 'SUDO_REASON=%s\\n' "$PIXEAGLE_SUDO_FAILURE_REASON"
''',
        env=env,
        no_controlling_tty=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SUDO_REASON=authentication_required_noninteractive" in result.stdout
    assert sudo_log.read_text(encoding="utf-8").splitlines() == ["-n -v"]


def test_interactive_yes_no_prompt_retries_invalid_answer():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
responses=(maybe y)
response_index=0
pixeagle_has_interactive_input() {{ return 0; }}
pixeagle_read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
if ask_yes_no 'Continue setup? [Y/n]: ' y; then
    printf 'YES_NO_RESULT=yes\\n'
fi
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Please enter y or n" in result.stdout
    assert "YES_NO_RESULT=yes" in result.stdout


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_real_tty_yes_no_answers_reach_caller_and_enter_uses_default():
    child = f'''
source "{INIT_SCRIPT}"
if ask_yes_no 'Explicit yes? [y/N]: ' n; then
    printf 'EXPLICIT_YES=yes\n'
else
    exit 21
fi
if ask_yes_no 'Explicit no? [Y/n]: ' y; then
    exit 22
else
    printf 'EXPLICIT_NO=no\n'
fi
if ask_yes_no 'Default yes? [Y/n]: ' y; then
    printf 'DEFAULT_YES=yes\n'
else
    exit 23
fi
'''
    result = subprocess.run(
        ["script", "-qfec", f"bash -c {shlex.quote(child)}", "/dev/null"],
        cwd=PROJECT_ROOT,
        input="y\nn\n\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXPLICIT_YES=yes" in result.stdout
    assert "EXPLICIT_NO=no" in result.stdout
    assert "DEFAULT_YES=yes" in result.stdout


def test_closed_guided_prompt_aborts_instead_of_applying_default():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
pixeagle_has_interactive_input() {{ return 0; }}
pixeagle_read_user_input() {{ return 1; }}
ask_yes_no 'Continue setup? [Y/n]: ' y
printf 'UNREACHABLE\n'
'''
    )

    assert result.returncode == 2
    assert "Terminal input closed" in result.stdout
    assert "verified components will be reused" in result.stdout
    assert "UNREACHABLE" not in result.stdout


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_guided_enter_defaults_to_core_and_shell_shortcut(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    child = f'''
source "{INIT_SCRIPT}"
select_installation_profile
configure_optional_components
printf 'PROFILE=%s OPTIONAL=%s\n' "$INSTALL_PROFILE" "$OPTIONAL_COMPONENT_SELECTION"
'''
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("PIXEAGLE_INSTALL_PROFILE", None)
    env.pop("PIXEAGLE_OPTIONAL_COMPONENTS", None)
    env.pop("PIXEAGLE_NONINTERACTIVE", None)
    result = subprocess.run(
        ["script", "-qfec", f"bash -c {shlex.quote(child)}", "/dev/null"],
        cwd=PROJECT_ROOT,
        env=env,
        input="\n\n\n\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROFILE=core OPTIONAL=shell-shortcut" in result.stdout
    assert "Install pixeagle-service command now?" not in result.stdout
    assert "pixeagle() {" in (home / ".bashrc").read_text(encoding="utf-8")


def test_existing_checkout_update_prompt_retries_invalid_answer():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
responses=(repair y)
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
if confirm_existing_update; then
    printf 'EXISTING_ACTION=update-repair\n'
fi
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Please enter y or n" in result.stdout
    assert "EXISTING_ACTION=update-repair" in result.stdout
    assert "Reset:     never performed" in result.stdout


def test_one_line_browser_lab_defaults_to_detected_public_host_and_starts(tmp_path):
    secret_dir = tmp_path / "secrets"
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
PIXEAGLE_QUICK_DEMO_HOST=204.168.181.45
PIXEAGLE_QUICK_DEMO_SECRET_DIR={shlex.quote(str(secret_dir))}
responses=("" "")
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
start_browser_lab
printf 'STARTED=%s URL=%s\n' "$BROWSER_LAB_STARTED" "$BROWSER_LAB_URL"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Dashboard access (Enter enables network access on 0.0.0.0):" in result.stdout
    assert "204.168.181.45 (requested) [default]" in result.stdout
    assert "listen on all interfaces (0.0.0.0)" in result.stdout
    assert "Temporary public HTTP lab; use only for testing" in result.stdout
    assert "ALLOW_PUBLIC_HTTP_DEMO=1" in result.stdout
    assert "OPEN_FIREWALL=1" in result.stdout
    assert "STARTED=true URL=http://204.168.181.45:3040/" in result.stdout


def test_one_line_handoff_explains_px4_router_outputs():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
SOURCE_MODE=branch
SOURCE_HEAD=0123456789abcdef
BROWSER_LAB_STARTED=false
show_result
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PX4: route MAVLink to 127.0.0.1:14540 and 127.0.0.1:14569" in result.stdout
    assert "docs/drone-interface/04-infrastructure/port-configuration.md" in result.stdout


def test_one_line_handoff_identifies_started_manual_runtime_and_managed_switch():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
SOURCE_MODE=branch
SOURCE_HEAD=0123456789abcdef
BROWSER_LAB_STARTED=true
BROWSER_LAB_MODE=network
BROWSER_LAB_URL=http://192.168.10.42:3040/
show_result
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Runtime: manual browser lab; boot policy unchanged" in result.stdout
    assert "Stop:" in result.stdout


def test_guided_bootstrap_uses_compact_runtime_handoff():
    result = _run_bash(
        f'''
PIXEAGLE_LAUNCH_COMPACT=1
source "{RUN_SCRIPT}"
PIXEAGLE_RUNTIME_LOG_DIR=/tmp/pixeagle-runtime-tests
PIXEAGLE_RUN_ID=pixeagle_manual_compact-test
display_startup_banner
runtime_log_step 1 "Checking runtime prerequisites"
runtime_log_success "routine success hidden"
show_final_summary
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Starting PixEagle runtime" in result.stdout
    assert "Checking runtime prerequisites" in result.stdout
    assert "PixEagle runtime is ready" in result.stdout
    assert "routine success hidden" not in result.stdout
    assert "Configured Service Endpoints" not in result.stdout


def test_one_line_update_handoff_reports_preserved_login_and_service_policy():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
EXISTING_CHECKOUT=true
SOURCE_MODE=branch
SOURCE_HEAD=0123456789abcdef
BROWSER_LAB_STARTED=true
BROWSER_LAB_MODE=network
BROWSER_LAB_URL=http://192.168.10.42:3040/
BROWSER_CREDENTIALS_REUSED=true
show_result
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "existing dashboard account preserved" in result.stdout
    assert "existing installation and boot policy preserved" in result.stdout
    assert "selected above" not in result.stdout


def test_one_line_browser_choice_can_start_local_only_demo(tmp_path):
    secret_dir = tmp_path / "secrets"
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
PIXEAGLE_QUICK_DEMO_HOST=192.168.10.42
PIXEAGLE_QUICK_DEMO_SECRET_DIR={shlex.quote(str(secret_dir))}
responses=(l)
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
start_browser_lab
printf 'STARTED=%s MODE=%s URL=%s\n' "$BROWSER_LAB_STARTED" "$BROWSER_LAB_MODE" "$BROWSER_LAB_URL"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Local browser lab will require the dashboard login" in result.stdout
    assert "LAN_HOST=127.0.0.1" in result.stdout
    assert "OPEN_FIREWALL=0" in result.stdout
    assert "quick-browser-demo" in result.stdout
    assert "GUIDED=demo" not in result.stdout
    assert "STARTED=true MODE=local URL=http://127.0.0.1:3040/" in result.stdout


def test_one_line_browser_choice_can_replace_detected_address(tmp_path):
    secret_dir = tmp_path / "secrets"
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
PIXEAGLE_QUICK_DEMO_HOST=10.0.0.5
PIXEAGLE_QUICK_DEMO_SECRET_DIR={shlex.quote(str(secret_dir))}
responses=(c 192.168.10.42 "")
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
start_browser_lab
printf 'STARTED=%s MODE=%s URL=%s\n' "$BROWSER_LAB_STARTED" "$BROWSER_LAB_MODE" "$BROWSER_LAB_URL"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Browser-reachable device IP or hostname [10.0.0.5]" in result.stdout
    assert "LAN_HOST=192.168.10.42" in result.stdout
    assert "STARTED=true MODE=network URL=http://192.168.10.42:3040/" in result.stdout


def test_existing_browser_login_can_be_preserved_or_rotated(tmp_path):
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    (secret_dir / "demo-browser-users.json").write_text("{}\n", encoding="utf-8")

    preserved = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
PIXEAGLE_QUICK_DEMO_HOST=192.168.10.42
PIXEAGLE_QUICK_DEMO_SECRET_DIR={shlex.quote(str(secret_dir))}
responses=("" "")
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
start_browser_lab
printf 'REUSED=%s\n' "$BROWSER_CREDENTIALS_REUSED"
'''
    )
    rotated = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
PIXEAGLE_QUICK_DEMO_HOST=192.168.10.42
PIXEAGLE_QUICK_DEMO_SECRET_DIR={shlex.quote(str(secret_dir))}
responses=("" n)
response_index=0
read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
start_browser_lab
printf 'REUSED=%s\n' "$BROWSER_CREDENTIALS_REUSED"
'''
    )

    assert preserved.returncode == 0, preserved.stdout + preserved.stderr
    assert "Keep the existing dashboard login? [Y/n]" in preserved.stdout
    assert "ROTATE_DEMO_CREDENTIALS=0" in preserved.stdout
    assert "REUSED=true" in preserved.stdout
    assert rotated.returncode == 0, rotated.stdout + rotated.stderr
    assert "Choose a replacement login next" in rotated.stdout
    assert "ROTATE_DEMO_CREDENTIALS=1" in rotated.stdout
    assert "REUSED=false" in rotated.stdout


def test_existing_update_offers_service_review_after_transaction():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
EXISTING_CHECKOUT=true
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=tty
INSTALL_DIR={shlex.quote(str(PROJECT_ROOT))}
run_guided_command() {{ printf 'GUIDED=%q ' "$@"; printf '\n'; }}
run_update_service_onboarding
printf 'REVIEWED=%s\n' "$SERVICE_ONBOARDING_REVIEWED"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PIXEAGLE_SERVICE_INSTALL_DEFAULT=n" in result.stdout
    assert "--service-onboarding-only" in result.stdout
    assert "REVIEWED=true" in result.stdout


def test_noninteractive_public_browser_lab_requires_explicit_http_override():
    result = _run_bash(
        f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
SETUP_RECONCILED=true
GUIDED_INPUT_MODE=noninteractive
PIXEAGLE_START_BROWSER_LAB=1
PIXEAGLE_QUICK_DEMO_HOST=204.168.181.45
start_browser_lab
'''
    )

    assert result.returncode != 0
    assert "PIXEAGLE_ALLOW_PUBLIC_HTTP_DEMO=1" in result.stderr


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_existing_checkout_real_tty_explicit_no_refuses_update():
    child = f'''
source <(sed '$d' "{INSTALL_SCRIPT}")
GUIDED_INPUT_MODE=tty
if confirm_existing_update; then
    exit 31
fi
printf 'EXISTING_ACTION=unchanged\n'
'''
    result = subprocess.run(
        ["script", "-qfec", f"bash -c {shlex.quote(child)}", "/dev/null"],
        cwd=PROJECT_ROOT,
        input="n\n",
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXISTING_ACTION=unchanged" in result.stdout


def test_setup_action_distinguishes_fresh_and_interrupted_state(tmp_path: Path):
    fresh = tmp_path / "fresh"
    interrupted = tmp_path / "interrupted"
    fresh.mkdir()
    (interrupted / "dashboard").mkdir(parents=True)
    (interrupted / "dashboard" / ".env").write_text(
        "PORT=3040\n", encoding="utf-8"
    )

    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_DIR={shlex.quote(str(fresh))}
VENV_PYTHON="$PIXEAGLE_DIR/.venv/bin/python"
describe_setup_action
PIXEAGLE_DIR={shlex.quote(str(interrupted))}
VENV_PYTHON="$PIXEAGLE_DIR/.venv/bin/python"
PIXEAGLE_SETUP_ACTION=repair
describe_setup_action
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fresh PixEagle setup detected" in result.stdout
    assert "Existing or interrupted PixEagle setup detected" in result.stdout
    assert "verify and repair the current source in place" in result.stdout
    assert "This is not a reset" in result.stdout


def test_service_onboarding_runs_only_after_setup_lock_supervisor_returns(tmp_path):
    events = tmp_path / "events"
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
pixeagle_setup_lock_context_present() {{ return 1; }}
pixeagle_run_with_setup_lock() {{ printf 'setup-finished\n' >> "{events}"; }}
run_post_setup_onboarding() {{ printf 'service-onboarding\n' >> "{events}"; }}
run_initialization_entrypoint
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert events.read_text(encoding="utf-8").splitlines() == [
        "setup-finished",
        "service-onboarding",
    ]


def test_service_onboarding_only_entrypoint_does_not_enter_setup_lock():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
pixeagle_setup_lock_context_present() {{ printf 'UNEXPECTED_LOCK_CHECK\n'; return 1; }}
pixeagle_run_with_setup_lock() {{ printf 'UNEXPECTED_SETUP_LOCK\n'; return 91; }}
run_post_setup_onboarding() {{ printf 'SERVICE_ONLY\n'; }}
run_initialization_entrypoint --service-onboarding-only
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SERVICE_ONLY" in result.stdout
    assert "UNEXPECTED" not in result.stdout


def test_bootstrap_context_uses_compact_setup_summary():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_BOOTSTRAP_CONTEXT=1
PYTHON_FULL_VERSION=3.12.3
INSTALL_PROFILE=core
NODE_SETUP_STATE=ready
NODE_SETUP_DETAIL=reused
DASHBOARD_DEPS_STATE=ready
DASHBOARD_DEPS_DETAIL=reused
CONFIG_DEFAULTS_STATE=ready
CONFIG_DEFAULTS_DETAIL=preserved
DASHBOARD_ENV_STATE=ready
DASHBOARD_ENV_DETAIL=preserved
MAVSDK_BINARY_STATE=ready
MAVSDK_BINARY_DETAIL=verified
MAVLINK2REST_BINARY_STATE=ready
MAVLINK2REST_BINARY_DETAIL=verified
OPTIONAL_COMPONENT_SELECTION=""
show_summary
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Setup reconciliation" in result.stdout
    assert "Dashboard access and managed-service choices follow" in result.stdout
    assert "Installation Summary" not in result.stdout
    assert "PX4 Connection" not in result.stdout


def test_service_onboarding_refuses_any_inherited_resource_lock():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
pixeagle_resource_lock_context_present() {{ return 0; }}
configure_service_autostart
'''
    )

    assert result.returncode != 0
    assert "cannot run inside a setup transaction" in result.stdout


def test_service_onboarding_reports_observed_policy_not_assumed_defaults():
    source = INIT_SCRIPT.read_text(encoding="utf-8")

    assert "Auto-start policy unchanged" in source
    assert "SSH login hint policy unchanged" in source
    assert "systemctl is-enabled pixeagle.service" in source
    assert "Auto-start remains disabled" not in source
    assert "SSH login hint disabled" not in source


@pytest.mark.skipif(shutil.which("script") is None, reason="util-linux script")
def test_generated_ssh_hint_prints_configured_network_dashboard_url(tmp_path: Path):
    home = tmp_path / "home"
    repo = home / "PixEagle"
    (repo / "configs").mkdir(parents=True)
    (repo / "dashboard").mkdir()
    (repo / "configs" / "config.yaml").write_text(
        """Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  HTTP_STREAM_PORT: 5077
  API_ALLOWED_HOSTS:
    - 127.0.0.1
    - 0.0.0.0
    - 192.168.0.226
  API_AUTH_MODE: browser_session
""",
        encoding="utf-8",
    )
    (repo / "dashboard" / "env_default.yaml").write_text(
        "PORT: 3040\n",
        encoding="utf-8",
    )
    hint = tmp_path / "pixeagle-login-hint.sh"
    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    generated = _run_bash(
        f'''source "{utils}"
write_login_hint_script {shlex.quote(str(hint))} test
''',
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_systemctl.chmod(0o700)
    command = (
        f"env HOME={shlex.quote(str(home))} SSH_CONNECTION='client 1 host 22' "
        f"PATH={shlex.quote(str(fake_bin))}:$PATH "
        "bash --noprofile --norc -ic "
        + shlex.quote(f"source {shlex.quote(str(hint))}")
    )
    result = subprocess.run(
        ["script", "-qfec", command, "/dev/null"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "network dashboard: http://192.168.0.226:3040" in result.stdout
    assert "network dashboard: http://0.0.0.0:3040" not in result.stdout
    assert "local dashboard: http://127.0.0.1:3040" in result.stdout
    assert (
        "configured authenticated lab dashboard is network-reachable"
        in result.stdout
    )
    assert (
        f"Network change: run make quick-browser-demo from {repo} "
        "after changing router or LAN."
    ) in result.stdout


def _dashboard_dependency_test_env(tmp_path: Path, *, npm_exit: int = 0):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"$*\" == \"ls --all --silent\" ]] || exit 64\n"
        f"exit {npm_exit}\n",
        encoding="utf-8",
    )
    fake_npm.chmod(0o700)
    (tmp_path / ".nvmrc").write_text("24\n", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    return env


def test_dashboard_dependency_cache_requires_matching_manifests_and_tree(
    tmp_path: Path,
):
    dashboard = tmp_path / "dashboard"
    (dashboard / "node_modules").mkdir(parents=True)
    (dashboard / "package.json").write_text(
        '{"name":"dashboard"}\n', encoding="utf-8"
    )
    lock_file = dashboard / "package-lock.json"
    lock_file.write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    env = _dashboard_dependency_test_env(tmp_path)

    recorded = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_record_dashboard_dependency_fingerprint {shlex.quote(str(dashboard))}
pixeagle_dashboard_dependencies_ready {shlex.quote(str(dashboard))}
''',
        env=env,
    )
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr

    lock_file.write_text('{"lockfileVersion":3,"changed":true}\n', encoding="utf-8")
    stale = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_dashboard_dependencies_ready {shlex.quote(str(dashboard))}
''',
        env=env,
    )
    assert stale.returncode != 0


def test_dashboard_dependency_cache_rejects_failed_tree_validation(tmp_path: Path):
    dashboard = tmp_path / "dashboard"
    (dashboard / "node_modules").mkdir(parents=True)
    (dashboard / "package.json").write_text(
        '{"name":"dashboard"}\n', encoding="utf-8"
    )
    (dashboard / "package-lock.json").write_text(
        '{"lockfileVersion":3}\n', encoding="utf-8"
    )
    good_env = _dashboard_dependency_test_env(tmp_path)
    recorded = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_record_dashboard_dependency_fingerprint {shlex.quote(str(dashboard))}
''',
        env=good_env,
    )
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr

    fake_npm = tmp_path / "fake-bin" / "npm"
    fake_npm.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fake_npm.chmod(0o700)
    rejected = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_dashboard_dependencies_ready {shlex.quote(str(dashboard))}
''',
        env=good_env,
    )
    assert rejected.returncode != 0


def test_dashboard_dependency_cache_includes_npmrc_and_node_abi(tmp_path: Path):
    dashboard = tmp_path / "dashboard"
    (dashboard / "node_modules").mkdir(parents=True)
    (dashboard / "package.json").write_text(
        '{"name":"dashboard"}\n', encoding="utf-8"
    )
    (dashboard / "package-lock.json").write_text(
        '{"lockfileVersion":3}\n', encoding="utf-8"
    )
    npmrc = dashboard / ".npmrc"
    npmrc.write_text("fund=false\n", encoding="utf-8")
    env = _dashboard_dependency_test_env(tmp_path)

    fingerprint = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_dashboard_dependency_fingerprint {shlex.quote(str(dashboard))}
''',
        env=env,
    )
    assert fingerprint.returncode == 0, fingerprint.stdout + fingerprint.stderr
    node_runtime = subprocess.run(
        [
            "node",
            "-p",
            '`${process.platform}:${process.arch}:abi-${process.versions.modules || "none"}`',
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert fingerprint.stdout.strip().endswith(f"_{node_runtime}")

    recorded = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_record_dashboard_dependency_fingerprint {shlex.quote(str(dashboard))}
pixeagle_dashboard_dependencies_ready {shlex.quote(str(dashboard))}
''',
        env=env,
    )
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr

    npmrc.write_text("fund=true\n", encoding="utf-8")
    changed_npmrc = _run_bash(
        f'''
source "{DASHBOARD_DEPENDENCIES_HELPER}"
pixeagle_dashboard_dependencies_ready {shlex.quote(str(dashboard))}
''',
        env=env,
    )
    assert changed_npmrc.returncode != 0


def test_dashboard_dependency_authority_is_shared_by_setup_and_runtime():
    initializer = INIT_SCRIPT.read_text(encoding="utf-8")
    component = (
        PROJECT_ROOT / "scripts" / "components" / "dashboard.sh"
    ).read_text(encoding="utf-8")

    for source in (initializer, component):
        assert "lib/dashboard_dependencies.sh" in source
        assert "pixeagle_dashboard_dependencies_ready" in source
        assert "pixeagle_record_dashboard_dependency_fingerprint" in source
    assert "needs_dependency_install" not in component
    assert "|| npm install --no-audit" not in component


def test_explicit_noninteractive_core_profile_is_accepted():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_NONINTERACTIVE=1
PIXEAGLE_INSTALL_PROFILE=core
select_installation_profile
printf 'PROFILE=%s\n' "$INSTALL_PROFILE"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROFILE=core" in result.stdout


def test_yes_no_prompt_uses_default_without_controlling_terminal():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
unset PIXEAGLE_NONINTERACTIVE
if ask_yes_no "Install optional component? [y/N]: " n; then
    printf 'ANSWER=yes\n'
else
    printf 'ANSWER=no\n'
fi
''',
        no_controlling_tty=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ANSWER=no" in result.stdout
    assert "(auto: n)" in result.stdout
    assert "/dev/tty" not in result.stderr


def test_spinner_cleanup_is_safe_under_errexit_without_a_live_child():
    result = _run_bash(
        f'''
set -e
source "{INIT_SCRIPT}"
spinner_pid=999999
stop_spinner
printf 'SPINNER_CLEANUP_OK\n'
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SPINNER_CLEANUP_OK" in result.stdout


def test_shared_heartbeat_starts_and_stops_without_waiting_for_interval():
    started_at = time.monotonic()
    result = _run_bash(
        f'''
set -euo pipefail
source "{COMMON_SCRIPT}"
heartbeat_pid=""
pixeagle_start_heartbeat heartbeat_pid "test operation" 30
[[ "$heartbeat_pid" =~ ^[1-9][0-9]*$ ]]
pixeagle_stop_heartbeat heartbeat_pid
[[ -z "$heartbeat_pid" ]]
printf 'HEARTBEAT_CLEANUP_OK\n'
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "HEARTBEAT_CLEANUP_OK" in result.stdout
    assert time.monotonic() - started_at < 5


def test_shared_heartbeat_retires_when_parent_shell_is_interrupted(tmp_path: Path):
    heartbeat_file = tmp_path / "heartbeat.pid"
    script = f'''
set -euo pipefail
source "{COMMON_SCRIPT}"
heartbeat_pid=""
pixeagle_start_heartbeat heartbeat_pid "interrupted operation" 30
printf '%s\\n' "$heartbeat_pid" > "{heartbeat_file}"
trap 'exit 143' INT TERM HUP
while true; do sleep 1; done
'''
    process = subprocess.Popen(
        ["bash", "-c", script],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    heartbeat_pid: int | None = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not heartbeat_file.exists():
            time.sleep(0.05)
        assert heartbeat_file.exists()
        heartbeat_pid = int(heartbeat_file.read_text(encoding="utf-8").strip())

        process.terminate()
        process.wait(timeout=5)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            stat_path = Path(f"/proc/{heartbeat_pid}/stat")
            if not stat_path.exists():
                break
            state = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
            if state == "Z":
                break
            time.sleep(0.05)
        else:
            pytest.fail("heartbeat remained active after its parent shell exited")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if heartbeat_pid is not None:
            try:
                os.kill(heartbeat_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_bootstrap_bridges_owned_manual_runtime_from_older_updater():
    source = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "prepare_legacy_updater_runtime" in source
    assert 'grep -Fq "ensure_runtime_stopped_before_update"' in source
    assert "Stop the owned manual runtime and continue? [Y/n]:" in source
    assert 'run_guided_command make -C "$INSTALL_DIR" stop' in source
    assert "PIXEAGLE_UPDATE_STOP_RUNTIME=1" in source


def test_verified_nvm_staging_creates_explicit_nvm_dir(tmp_path: Path):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    installer = tmp_path / "fake-nvm-installer.sh"
    installer.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
[[ -d "$NVM_DIR" ]] || { printf 'missing NVM_DIR\\n' >&2; exit 66; }
mkdir -p "$NVM_DIR/.git"
printf '# staged nvm\\n' > "$NVM_DIR/nvm.sh"
""",
        encoding="utf-8",
    )
    installer.chmod(0o700)

    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
output=''
while [[ $# -gt 0 ]]; do
    if [[ "$1" == '--output' ]]; then
        shift
        output="$1"
    fi
    shift
done
cp -- "$FAKE_NVM_INSTALLER" "$output"
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o700)

    fake_sha = fake_bin / "sha256sum"
    fake_sha.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_sha.chmod(0o700)

    fake_git = fake_bin / "git"
    fake_git.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{NVM_COMMIT}'\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o700)

    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "FAKE_NVM_INSTALLER": str(installer),
        }
    )
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
export NVM_DIR="$HOME/.nvm"
install_verified_nvm
test -s "$NVM_DIR/nvm.sh"
test -d "$NVM_DIR/.git"
''',
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".nvm" / "nvm.sh").is_file()
    assert not list(home.glob(".pixeagle-nvm-install.*"))


def test_python_transaction_is_committed_before_node_setup():
    source = INIT_SCRIPT.read_text(encoding="utf-8")
    main = source.split("main() {", 1)[1]

    install_python = main.index("install_python_deps")
    commit = main.index("pixeagle_commit_venv_transaction", install_python)
    finalize = main.index("pixeagle_finalize_venv_transaction", commit)
    node = main.index("setup_nodejs", finalize)

    assert install_python < commit < finalize < node


def test_required_python_failure_stops_before_later_setup_and_rolls_back(tmp_path):
    events = tmp_path / "events"
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
trap - EXIT
PIXEAGLE_DIR={shlex.quote(str(tmp_path))}
VENV_DIR="$PIXEAGLE_DIR/.venv"
INSTALL_PROFILE=full
record() {{ printf '%s\n' "$1" >> {shlex.quote(str(events))}; }}
pixeagle_acquire_setup_lock() {{ :; }}
pixeagle_validate_rebuild_components() {{ :; }}
display_banner() {{ :; }}
describe_setup_action() {{ :; }}
check_supported_platform() {{ :; }}
select_installation_profile() {{ :; }}
check_system_requirements() {{ :; }}
prepare_model_store() {{ :; }}
install_system_packages() {{ :; }}
reuse_verified_python_environment() {{ return 1; }}
pixeagle_begin_venv_transaction() {{ record begin; }}
create_venv() {{ record create; }}
install_python_deps() {{ record python-failed; return 23; }}
pixeagle_finalize_venv_transaction() {{ record rollback; }}
pixeagle_commit_venv_transaction() {{ record unexpected-commit; }}
setup_nodejs() {{ record unexpected-node; }}
main
'''
    )

    assert result.returncode != 0
    assert events.read_text(encoding="utf-8").splitlines() == [
        "begin",
        "create",
        "python-failed",
        "rollback",
    ]
    assert "later setup and onboarding were not started" in result.stdout


def _run_python_policy(*args: str):
    return subprocess.run(
        [
            "python3",
            str(PYTORCH_COMPAT_SCRIPT),
            "--policy",
            str(PYTORCH_MATRIX),
            *args,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_python_policy_is_profile_specific_and_supports_current_cpu_stack():
    cpu = _run_python_policy(
        "--profile", "linux_cpu", "--python-version", "3.14.4"
    )
    excluded_patch = _run_python_policy(
        "--profile", "linux_cpu", "--python-version", "3.14.1"
    )
    compatibility_cuda = _run_python_policy(
        "--profile", "linux_x86_cuda12", "--python-version", "3.14.4"
    )
    any_profile = _run_python_policy(
        "--any-supported-profile", "--python-version", "3.14.4"
    )
    future_major = _run_python_policy(
        "--runtime-role", "core", "--python-version", "4.0.0"
    )

    assert cpu.returncode == 0, cpu.stdout + cpu.stderr
    assert "linux_cpu (PyTorch 2.12.1)" in cpu.stdout
    assert excluded_patch.returncode == 3
    assert "explicitly excluded" in excluded_patch.stderr
    assert compatibility_cuda.returncode == 3
    assert "linux_x86_cuda12 (PyTorch 2.6.0)" in compatibility_cuda.stderr
    assert any_profile.returncode == 0, any_profile.stdout + any_profile.stderr
    assert "exact hardware profile is validated" in any_profile.stdout
    assert future_major.returncode == 3
    assert "outside the supported Python 3 language family" in future_major.stderr


def test_setup_python_resolution_honors_override_and_reuses_valid_venv(
    tmp_path: Path,
):
    host_python = shutil.which("python3")
    assert host_python is not None

    override = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_PYTHON={shlex.quote(host_python)}
VENV_PYTHON={shlex.quote(str(tmp_path / "missing-venv-python"))}
VENV_ACTIVATE={shlex.quote(str(tmp_path / "missing-activate"))}
resolve_setup_python
printf 'SOURCE=%s PYTHON=%s\n' "$SETUP_PYTHON_SOURCE" "$SETUP_PYTHON"
'''
    )
    assert override.returncode == 0, override.stdout + override.stderr
    assert "SOURCE=PIXEAGLE_PYTHON override" in override.stdout
    assert f"PYTHON={host_python}" in override.stdout

    venv_dir = tmp_path / "existing-venv"
    (venv_dir / "bin").mkdir(parents=True)
    venv_python = venv_dir / "bin" / "python"
    venv_python.symlink_to(host_python)
    activate = venv_dir / "bin" / "activate"
    activate.write_text("# test activation marker\n", encoding="utf-8")

    reuse = _run_bash(
        f'''
source "{INIT_SCRIPT}"
unset PIXEAGLE_PYTHON
VENV_PYTHON={shlex.quote(str(venv_python))}
VENV_ACTIVATE={shlex.quote(str(activate))}
resolve_setup_python
printf 'SOURCE=%s PYTHON=%s\n' "$SETUP_PYTHON_SOURCE" "$SETUP_PYTHON"
'''
    )
    assert reuse.returncode == 0, reuse.stdout + reuse.stderr
    assert "SOURCE=existing PixEagle virtual environment" in reuse.stdout
    assert f"PYTHON={venv_python}" in reuse.stdout

    installer = INIT_SCRIPT.read_text(encoding="utf-8")
    assert '"$SETUP_PYTHON" -m venv "$VENV_DIR"' in installer


def test_full_profile_incompatibility_offers_core_without_mutation():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
INSTALL_PROFILE=full
SETUP_PYTHON=python3
PYTHON_FULL_VERSION=3.15.0
responses=(y)
response_index=0
pixeagle_has_interactive_input() {{ return 0; }}
pixeagle_read_user_input() {{
    printf -v "$1" '%s' "${{responses[$response_index]}}"
    response_index=$((response_index + 1))
}}
check_full_ai_python_compatibility
printf 'PROFILE=%s\n' "$INSTALL_PROFILE"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Continue with Core instead?" in result.stdout
    assert "PROFILE=core" in result.stdout
    assert "no unsupported AI packages" in result.stdout


def test_unattended_full_profile_incompatibility_fails_closed():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
INSTALL_PROFILE=full
SETUP_PYTHON=python3
PYTHON_FULL_VERSION=3.15.0
pixeagle_has_interactive_input() {{ return 1; }}
check_full_ai_python_compatibility
''',
        no_controlling_tty=True,
    )

    assert result.returncode != 0
    assert "cannot change profile implicitly" in result.stdout
    assert "PIXEAGLE_INSTALL_PROFILE=core" in result.stdout


def test_node_runtime_contract_is_shared_by_setup_ci_and_dashboard():
    assert (PROJECT_ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "24"
    package = (PROJECT_ROOT / "dashboard" / "package.json").read_text(
        encoding="utf-8"
    )
    initializer = INIT_SCRIPT.read_text(encoding="utf-8")
    component = (
        PROJECT_ROOT / "scripts" / "components" / "dashboard.sh"
    ).read_text(encoding="utf-8")
    tests_workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
    ).read_text(encoding="utf-8")
    browser_workflow = (
        PROJECT_ROOT
        / ".github"
        / "workflows"
        / "production-remote-browser-e2e.yml"
    ).read_text(encoding="utf-8")
    workflows = "\n".join(
        [tests_workflow, browser_workflow]
    )

    assert '"node": "24.x"' in package
    assert 'NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"' in initializer
    assert 'NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"' in component
    assert tests_workflow.count("node-version-file: '.nvmrc'") == 2
    assert browser_workflow.count("node-version-file: '.nvmrc'") == 1
    assert "node-version: '20'" not in workflows


def test_required_apt_operations_are_noninteractive_and_fail_closed():
    initializer = INIT_SCRIPT.read_text(encoding="utf-8")

    assert "DEBIAN_FRONTEND=noninteractive" in initializer
    assert 'apt-get "$@" </dev/null' not in initializer
    assert "run_apt_get update" in initializer
    assert "run_privileged apt update -qq 2>&1 || true" not in initializer


def test_ascii_banner_is_shared_by_bootstrap_and_runtime_scripts():
    banner = (PROJECT_ROOT / "scripts" / "banner.txt").read_text(encoding="utf-8").strip()
    installer = INSTALL_SCRIPT.read_text(encoding="utf-8")
    common = (PROJECT_ROOT / "scripts" / "lib" / "common.sh").read_text(
        encoding="utf-8"
    )

    assert banner in installer
    assert 'banner_file="$common_dir/../banner.txt"' in common


def test_shell_shortcut_is_idempotent_and_removable(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    profile = home / ".bashrc"
    profile.write_text("# existing user content\n", encoding="utf-8")
    env = os.environ.copy()
    env["HOME"] = str(home)

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(SHORTCUT_SCRIPT), "--yes"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    installed = profile.read_text(encoding="utf-8")
    assert installed.count("# >>> PixEagle directory shortcut >>>") == 1
    assert installed.count("# <<< PixEagle directory shortcut <<<") == 1
    assert "# existing user content" in installed
    assert "pixeagle() {" in installed

    removed = subprocess.run(
        ["bash", str(SHORTCUT_SCRIPT), "--remove", "--yes"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert profile.read_text(encoding="utf-8") == "# existing user content\n"


def test_shell_shortcut_rejects_runtime_arguments_with_actionable_commands(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    profile = home / ".bashrc"
    env = os.environ.copy()
    env["HOME"] = str(home)

    installed = subprocess.run(
        ["bash", str(SHORTCUT_SCRIPT), "--yes"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; pixeagle start',
            "bash",
            str(profile),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "only changes to the PixEagle directory" in result.stderr
    assert "make run" in result.stderr
    assert "pixeagle-service start" in result.stderr


def test_shell_shortcut_help_includes_beginner_demo(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    profile = home / ".bashrc"
    env = os.environ.copy()
    env["HOME"] = str(home)
    installed = subprocess.run(
        ["bash", str(SHORTCUT_SCRIPT), "--yes"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    result = subprocess.run(
        ["bash", "-c", 'source "$1"; pixeagle help', "bash", str(profile)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "pixeagle && make demo" in result.stdout
    assert "pixeagle && make run" in result.stdout


def test_noninteractive_setup_skips_service_onboarding():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_NONINTERACTIVE=1
configure_service_autostart() {{ printf 'UNEXPECTED_SERVICE_PROMPT\n'; return 44; }}
run_post_setup_onboarding
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNEXPECTED_SERVICE_PROMPT" not in result.stdout


def test_optional_service_onboarding_failure_does_not_block_core_setup():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
pixeagle_has_interactive_input() {{ return 0; }}
configure_service_autostart() {{ return 44; }}
run_post_setup_onboarding
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Optional service onboarding did not complete" in result.stdout
    assert "Core setup remains usable" in result.stdout


def test_optional_selection_is_normalized_and_rejects_unknown_values():
    accepted = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "1, gstreamer, 3, dlib"
printf 'SELECTION=%s\n' "$OPTIONAL_COMPONENT_SELECTION"
'''
    )
    rejected = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "dlib,unknown-component"
'''
    )
    none_selected = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "none"
printf 'SELECTION=<%s>\n' "$OPTIONAL_COMPONENT_SELECTION"
'''
    )
    ambiguous = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "none,3"
'''
    )
    retired_service_option = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "service"
'''
    )

    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "SELECTION=dlib,gstreamer,shell-shortcut" in accepted.stdout
    assert rejected.returncode != 0
    assert "Unknown optional component" in rejected.stdout
    assert none_selected.returncode == 0, none_selected.stdout + none_selected.stderr
    assert "SELECTION=<>" in none_selected.stdout
    assert ambiguous.returncode != 0
    assert "cannot be combined" in ambiguous.stdout
    assert retired_service_option.returncode != 0
    assert "Allowed: dlib,gstreamer,shell-shortcut" in retired_service_option.stdout


def test_optional_gstreamer_reuses_verified_existing_provider():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_OPTIONAL_COMPONENTS=gstreamer
bash() {{
    if [[ "$*" == *"--verify-current"* ]]; then
        return 0
    fi
    printf 'UNEXPECTED_BUILD=%s\n' "$*"
    return 71
}}
configure_optional_components
printf 'STATE=%s DETAIL=%s\n' \
    "$OPTIONAL_GSTREAMER_STATE" "$OPTIONAL_GSTREAMER_DETAIL"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "UNEXPECTED_BUILD" not in result.stdout
    assert "STATE=ready" in result.stdout
    assert "version- and capability-matched OpenCV GStreamer provider reused" in result.stdout


def test_optional_gstreamer_build_is_reverified_before_ready_summary():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_OPTIONAL_COMPONENTS=gstreamer
verify_calls=0
bash() {{
    if [[ "$*" == *"--verify-current"* ]]; then
        verify_calls=$((verify_calls + 1))
        [[ "$verify_calls" -eq 2 ]]
        return
    fi
    [[ "$*" == *"build-opencv.sh --skip-confirm"* ]]
}}
configure_optional_components
printf 'STATE=%s DETAIL=%s VERIFY_CALLS=%s\n' \
    "$OPTIONAL_GSTREAMER_STATE" "$OPTIONAL_GSTREAMER_DETAIL" "$verify_calls"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATE=ready" in result.stdout
    assert "independently reverified" in result.stdout
    assert "VERIFY_CALLS=2" in result.stdout


def test_optional_gstreamer_never_reports_ready_when_final_probe_fails():
    result = _run_bash(
        f'''
source "{INIT_SCRIPT}"
PIXEAGLE_OPTIONAL_COMPONENTS=gstreamer
bash() {{
    [[ "$*" == *"--verify-current"* ]] && return 1
    [[ "$*" == *"build-opencv.sh --skip-confirm"* ]]
}}
if configure_optional_components; then
    exit 88
fi
printf 'STATE=%s DETAIL=%s\n' \
    "$OPTIONAL_GSTREAMER_STATE" "$OPTIONAL_GSTREAMER_DETAIL"
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATE=degraded" in result.stdout
    assert "failed final verification" in result.stdout


def test_opencv_reuse_check_explains_mismatch_without_false_build_failure():
    result = _run_bash(
        f'''
source "{OPENCV_BUILD_SCRIPT}"
pixeagle_acquire_setup_lock() {{ return 0; }}
verify_current_contract() {{
    CURRENT_CONTRACT_DETAIL="provider=managed_wheel (expected source_gstreamer); GStreamer=unavailable"
    return 1
}}
if main --verify-current --reuse-check; then
    exit 87
fi
'''
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "OpenCV/GStreamer rebuild required" in result.stdout
    assert "provider=managed_wheel" in result.stdout
    assert "installed OpenCV provider does not match" not in result.stdout


def test_unattended_sudo_validation_is_nonblocking():
    initializer = INIT_SCRIPT.read_text(encoding="utf-8")
    common = COMMON_SCRIPT.read_text(encoding="utf-8")
    guided_scripts = [
        INIT_SCRIPT,
        PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh",
        PROJECT_ROOT / "scripts" / "setup" / "setup-pytorch.sh",
        PROJECT_ROOT / "scripts" / "setup" / "install-dlib.sh",
        PROJECT_ROOT / "scripts" / "setup" / "quick-browser-demo.sh",
        PROJECT_ROOT / "scripts" / "setup" / "quick-browser-demo-cleanup.sh",
    ]

    assert "sudo -n -v" in common
    assert "sudo -S -v" in common
    assert "pixeagle_sudo_validate" in initializer
    assert "pixeagle_sudo_run" in initializer
    for path in guided_scripts:
        source = path.read_text(encoding="utf-8")
        assert "if ! sudo -v" not in source
        assert "sudo -v ||" not in source
        assert not re.search(
            r"(?:pixeagle_sudo_run|run_privileged)[^\n]*2>/dev/null",
            source,
        ), f"{path} hides a possible sudo prompt"
