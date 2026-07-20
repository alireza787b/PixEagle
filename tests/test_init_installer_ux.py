"""Regression tests for the guided Linux installer interaction contract."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name == "nt", reason="bash installer")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = PROJECT_ROOT / "scripts" / "init.sh"
INSTALL_SCRIPT = PROJECT_ROOT / "install.sh"
DASHBOARD_DEPENDENCIES_HELPER = (
    PROJECT_ROOT / "scripts" / "lib" / "dashboard_dependencies.sh"
)
SHORTCUT_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "install-shell-shortcut.sh"
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
    kwargs: dict[str, object] = {}
    if no_controlling_tty:
        kwargs.update(stdin=subprocess.DEVNULL, preexec_fn=os.setsid)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


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
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / ".github" / "workflows" / "tests.yml",
            PROJECT_ROOT
            / ".github"
            / "workflows"
            / "production-remote-browser-e2e.yml",
        )
    )

    assert '"node": "24.x"' in package
    assert 'NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"' in initializer
    assert 'NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"' in component
    assert workflows.count("node-version-file: '.nvmrc'") == 2
    assert "node-version: '20'" not in workflows


def test_required_apt_operations_are_noninteractive_and_fail_closed():
    initializer = INIT_SCRIPT.read_text(encoding="utf-8")

    assert "DEBIAN_FRONTEND=noninteractive" in initializer
    assert 'apt-get "$@" </dev/null' in initializer
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
    assert "alias pixeagle=" in installed

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


def test_optional_selection_is_normalized_and_rejects_unknown_values():
    accepted = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "1, gstreamer, 3, service, dlib"
printf 'SELECTION=%s\n' "$OPTIONAL_COMPONENT_SELECTION"
'''
    )
    rejected = _run_bash(
        f'''
source "{INIT_SCRIPT}"
normalize_optional_component_selection "dlib,unknown-component"
'''
    )

    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "SELECTION=dlib,gstreamer,shell-shortcut,service" in accepted.stdout
    assert rejected.returncode != 0
    assert "Unknown optional component" in rejected.stdout
