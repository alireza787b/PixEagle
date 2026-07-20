"""Regression tests for the guided Linux installer interaction contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name == "nt", reason="bash installer")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = PROJECT_ROOT / "scripts" / "init.sh"
INSTALL_SCRIPT = PROJECT_ROOT / "install.sh"
SHORTCUT_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "install-shell-shortcut.sh"
PYTORCH_COMPAT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "setup" / "check-pytorch-python-compat.py"
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


def test_pytorch_matrix_rejects_python_314_before_full_install():
    accepted = subprocess.run(
        [
            "python3",
            str(PYTORCH_COMPAT_SCRIPT),
            "--matrix",
            str(PYTORCH_MATRIX),
            "--python-version",
            "3.13",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    rejected = subprocess.run(
        [
            "python3",
            str(PYTORCH_COMPAT_SCRIPT),
            "--matrix",
            str(PYTORCH_MATRIX),
            "--python-version",
            "3.14",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "PyTorch 2.6.0" in accepted.stdout
    assert rejected.returncode == 3
    assert "outside the reviewed PyTorch 2.6.0 matrix" in rejected.stderr


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
