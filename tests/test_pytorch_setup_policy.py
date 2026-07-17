"""Supply-chain policy tests for the matrix-driven PyTorch installer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = PROJECT_ROOT / "scripts" / "setup" / "pytorch_matrix.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "setup" / "setup-pytorch.sh"
AI_INSTALLER_PATH = PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh"
CORE_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-core.txt"
AI_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-ai.txt"
NCNN_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-ai-ncnn.txt"
ULTRALYTICS_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-ultralytics.txt"
AGGREGATE_REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
OPENCV_BUILD_PATH = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
BOOTSTRAP_PATH = PROJECT_ROOT / "scripts" / "init.sh"
OPENCV_DOC_PATH = PROJECT_ROOT / "docs" / "OPENCV_GSTREAMER.md"
MODEL_SETUP_DOC_PATH = PROJECT_ROOT / "docs" / "MODEL_SETUP.md"


def test_pytorch_installer_does_not_retain_pip_tooling_cache():
    installer = SCRIPT_PATH.read_text(encoding="utf-8")

    assert (
        'run_cmd "Upgrading pip tooling" "$pip" install --upgrade '
        '--no-cache-dir pip setuptools wheel'
    ) in installer


def test_model_setup_pins_the_reviewed_lab_artifact():
    model_setup = MODEL_SETUP_DOC_PATH.read_text(encoding="utf-8")

    assert (
        "https://github.com/ultralytics/assets/releases/download/"
        "v8.4.0/yolo26n.pt"
    ) in model_setup
    assert (
        "9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef"
        in model_setup
    )
    assert "licens" in model_setup.lower()
    assert "--source-file" in model_setup
    assert "set -euo pipefail" in model_setup
    assert 'MODEL_TMP="$(mktemp)"' in model_setup
    assert "trap 'test ! -e \"$MODEL_TMP\" || unlink \"$MODEL_TMP\"' EXIT" in model_setup
    assert "install -m 600 /tmp/yolo26n.pt models/yolo26n.pt" not in model_setup


def test_supported_wheel_profiles_are_immutable_and_digest_pinned():
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    for name, profile in matrix["profiles"].items():
        if not profile.get("supported") or profile.get("install_method") != "wheels":
            continue
        wheels = profile.get("wheels", {})
        digests = profile.get("wheel_sha256", {})
        for component in ("torch", "torchvision"):
            source = wheels.get(component, "")
            digest = digests.get(component, "")
            assert source, f"{name}.{component} has no wheel"
            assert "refs/heads/" not in source
            assert len(digest) == 64
            int(digest, 16)

        prereq = profile.get("prereqs", {}).get("cusparselt", {})
        if prereq.get("enabled"):
            digest = prereq.get("repo_deb_sha256", "")
            assert len(digest) == 64
            int(digest, 16)


def test_jetson_profiles_fail_closed_without_verified_overrides():
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    for name in ("jetson_jp61", "jetson_jp62"):
        profile = matrix["profiles"][name]
        assert profile["supported"] is False
        assert profile["wheels"]["torch"] == ""
        assert profile["wheels"]["torchvision"] == ""
        assert "sha256" in profile["manual_hint"].lower()


def test_local_wheel_source_requires_and_verifies_sha256(tmp_path):
    wheel = tmp_path / "torch-test.whl"
    wheel.write_bytes(b"pixeagle-test-wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    shell = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
REPORT_JSON=""
resolved=""
resolve_wheel_source "$1" "$2" "$3" resolved
printf '%s' "$resolved"
"""

    valid = subprocess.run(
        ["bash", "-c", shell, "test", str(wheel), digest, str(tmp_path / "cache")],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr
    staged_wheel = tmp_path / "cache" / wheel.name
    assert valid.stdout == str(staged_wheel)
    assert staged_wheel.read_bytes() == wheel.read_bytes()
    assert staged_wheel.stat().st_mode & 0o777 == 0o600

    invalid = subprocess.run(
        ["bash", "-c", shell, "test", str(wheel), "0" * 64, str(tmp_path / "cache")],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid.returncode != 0
    assert "SHA-256 verification failed" in invalid.stdout


def test_verification_payload_is_data_not_shell_code(tmp_path):
    marker = tmp_path / "parser-injection-marker"
    hostile = f'NVIDIA GeForce "Lab"\n$(touch {marker}) ; `touch {marker}`'
    payload = json.dumps(
        {
            "torch_ok": True,
            "torchvision_ok": True,
            "torchaudio_ok": True,
            "torch_version": hostile,
            "torchvision_version": hostile,
            "torchaudio_version": hostile,
            "cuda_available": True,
            "cuda_tensor_ok": True,
            "cuda_device_name": hostile,
            "mps_available": False,
            "compatibility_errors": [hostile],
            "error": None,
        }
    )
    shell = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
parse_verification_payload "$1" 1 0
printf '%s\\0' "$OK" "$REASON" "$TORCH_VERSION" "$TORCHVISION_VERSION" \
  "$TORCHAUDIO_VERSION" "$CUDA_AVAILABLE" "$CUDA_DEVICE" "$MPS_AVAILABLE" \
  "$TORCHAUDIO_OK"
"""

    result = subprocess.run(
        ["bash", "-c", shell, "test", payload],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    fields = result.stdout.split(b"\0")[:-1]
    assert fields == [
        b"0",
        hostile.encode(),
        hostile.encode(),
        hostile.encode(),
        hostile.encode(),
        b"1",
        hostile.encode(),
        b"0",
        b"1",
    ]
    assert not marker.exists()


def test_matrix_profile_is_data_not_shell_code(tmp_path):
    marker = tmp_path / "matrix-injection-marker"
    hostile = f'Lab profile "quoted"\n$(touch {marker}) ; `touch {marker}`'
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "profiles": {
                    "hostile": {
                        "supported": True,
                        "description": hostile,
                        "install_method": "index",
                        "packages": {},
                        "wheels": {},
                        "wheel_sha256": {},
                        "verify": {},
                        "prereqs": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    shell = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
MATRIX_FILE="$1"
PROFILE_KEY=hostile
load_profile_from_matrix >/dev/null
printf '%s\\0' "$PROFILE_DESCRIPTION" "$PROFILE_INSTALL_METHOD"
"""

    result = subprocess.run(
        ["bash", "-c", shell, "test", str(matrix)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    fields = result.stdout.split(b"\0")[-3:-1]
    assert fields == [hostile.encode(), b"index"]
    assert not marker.exists()


def test_custom_matrix_cannot_request_privileged_apt_packages(tmp_path):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "profiles": {
                    "custom": {
                        "supported": True,
                        "description": "custom",
                        "install_method": "index",
                        "index_url": "https://download.pytorch.org/whl/cpu",
                        "packages": {"torch": "2.6.0"},
                        "verify": {},
                        "prereqs": {"apt_packages": ["--option-injection"]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    shell = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
MATRIX_FILE="$1"
MATRIX_SHA256="$(sha256sum "$1" | awk '{{print $1}}')"
PROFILE_KEY=custom
load_profile_from_matrix
"""

    result = subprocess.run(
        ["bash", "-c", shell, "test", str(matrix)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Custom matrices may not request privileged apt packages" in result.stdout


def test_matrix_digest_change_fails_before_profile_use(tmp_path):
    matrix = tmp_path / "matrix.json"
    matrix.write_text('{"profiles": {}}\n', encoding="utf-8")
    shell = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
MATRIX_FILE="$1"
MATRIX_SHA256="{'0' * 64}"
PROFILE_KEY=missing
load_profile_from_matrix
"""

    result = subprocess.run(
        ["bash", "-c", shell, "test", str(matrix)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Failed to parse matrix profile" in result.stdout


def test_unsupported_profile_requires_explicit_verification_only_mode(tmp_path):
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "profiles": {
                    "jetson": {
                        "supported": False,
                        "description": "manual Jetson runtime",
                        "install_method": "wheels",
                        "wheels": {},
                        "wheel_sha256": {},
                        "verify": {"require_cuda": True},
                        "prereqs": {"apt_packages": []},
                        "manual_hint": "provide digest-verified wheels",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    common = f"""
set -euo pipefail
source {SCRIPT_PATH!s}
MATRIX_FILE="$1"
MATRIX_SHA256="$(sha256sum "$1" | awk '{{print $1}}')"
PROFILE_KEY=jetson
"""
    denied = subprocess.run(
        ["bash", "-c", common + "load_profile_from_matrix\n", "test", str(matrix)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    allowed = subprocess.run(
        [
            "bash",
            "-c",
            common
            + "ACCEPT_EXISTING_VERIFIED=true\n"
            + "load_profile_from_matrix >/dev/null\n"
            + "printf '%s' \"$PROFILE_EXISTING_ONLY\"\n",
            "test",
            str(matrix),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert denied.returncode != 0
    assert "currently marked unsupported" in denied.stdout
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert allowed.stdout == "true"


def test_ai_verification_payload_is_data_not_shell_code(tmp_path):
    marker = tmp_path / "ai-parser-injection-marker"
    hostile = f'AI error "quoted"\n$(touch {marker}) ; `touch {marker}`'
    payload = json.dumps(
        {
            "ultralytics": False,
            "lap": True,
            "ncnn": None,
            "pnnx": None,
            "error": hostile,
        }
    )
    shell = f"""
set -euo pipefail
source {AI_INSTALLER_PATH!s}
parse_ai_verification_payload "$1"
printf '%s\\0' "$OK" "$ULTRA" "$LAP" "$NCNN" "$PNNX" "$ERR"
"""

    result = subprocess.run(
        ["bash", "-c", shell, "test", payload],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.split(b"\0")[:-1] == [
        b"0",
        b"0",
        b"1",
        b"0",
        b"0",
        hostile.encode(),
    ]
    assert not marker.exists()


def test_ai_verifier_uses_private_result_channel_for_import_output(tmp_path):
    modules = tmp_path / "modules"
    ultralytics = modules / "ultralytics"
    ultralytics.mkdir(parents=True)
    (ultralytics / "__init__.py").write_text(
        "print('first-run settings notice')\nYOLO = object()\n",
        encoding="utf-8",
    )
    (modules / "lap.py").write_text(
        "print('lap import notice')\n",
        encoding="utf-8",
    )
    shell = f"""
set -euo pipefail
source {AI_INSTALLER_PATH!s}
trap - EXIT
VENV_PYTHON="$1"
WITH_NCNN=false
verify_ai_runtime
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(modules)

    result = subprocess.run(
        ["bash", "-c", shell, "test", sys.executable],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ultralytics import OK" in result.stdout
    assert "lap import OK" in result.stdout
    assert "AI runtime verification passed" in result.stdout
    assert "first-run settings notice" in result.stderr
    assert "lap import notice" in result.stderr
    assert "invalid AI verification payload" not in result.stdout + result.stderr


def _run_full_bootstrap_python_phase(tmp_path, *, pytorch_exit_code: int):
    root = tmp_path / "project"
    bin_dir = root / ".venv" / "bin"
    setup_dir = root / "scripts" / "setup"
    bin_dir.mkdir(parents=True)
    setup_dir.mkdir(parents=True)
    (root / "requirements-core.txt").write_text(
        "# no packages in the isolated policy test\n", encoding="utf-8"
    )
    (bin_dir / "activate").write_text(
        "deactivate() { :; }\n", encoding="utf-8"
    )
    for name in ("python", "pip"):
        path = bin_dir / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)

    pytorch_marker = tmp_path / "pytorch-args"
    ai_marker = tmp_path / "ai-called"
    pytorch = setup_dir / "setup-pytorch.sh"
    pytorch.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$PYTORCH_MARKER\"\n"
        f"exit {pytorch_exit_code}\n",
        encoding="utf-8",
    )
    pytorch.chmod(0o700)
    ai = setup_dir / "install-ai-deps.sh"
    ai.write_text(
        "#!/bin/sh\nprintf 'called\\n' > \"$AI_MARKER\"\nexit 0\n",
        encoding="utf-8",
    )
    ai.chmod(0o700)
    diagnostic = setup_dir / "check-ai-runtime.sh"
    diagnostic.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    diagnostic.chmod(0o700)

    state_file = tmp_path / "state"
    env = os.environ.copy()
    env.update(
        {
            "PYTORCH_MARKER": str(pytorch_marker),
            "AI_MARKER": str(ai_marker),
            "STATE_FILE": str(state_file),
        }
    )
    shell = f"""
set -euo pipefail
source {BOOTSTRAP_PATH}
PIXEAGLE_DIR="$1"
VENV_DIR="$PIXEAGLE_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_ACTIVATE="$VENV_DIR/bin/activate"
INSTALL_PROFILE=full
check_opencv_gstreamer() {{ return 1; }}
status=0
install_python_deps || status=$?
printf '%s|%s|%s|%s\n' "$status" "$PYTORCH_SETUP_PASSED" \
    "$PYTORCH_SETUP_FAILED" "$AI_VERIFY_PASSED" > "$STATE_FILE"
"""
    result = subprocess.run(
        ["bash", "-c", shell, "test", str(root)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, state_file, pytorch_marker, ai_marker


def test_full_bootstrap_always_runs_platform_pytorch_before_ai(tmp_path):
    result, state_file, pytorch_marker, ai_marker = _run_full_bootstrap_python_phase(
        tmp_path, pytorch_exit_code=0
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert state_file.read_text(encoding="utf-8").strip() == "0|true|false|true"
    assert pytorch_marker.read_text(encoding="utf-8").strip() == (
        "--mode auto --non-interactive --accept-existing-verified"
    )
    assert ai_marker.read_text(encoding="utf-8").strip() == "called"


def test_full_bootstrap_stops_before_ai_when_pytorch_does_not_validate(tmp_path):
    result, state_file, pytorch_marker, ai_marker = _run_full_bootstrap_python_phase(
        tmp_path, pytorch_exit_code=23
    )

    assert result.returncode == 0, result.stdout + result.stderr
    state = state_file.read_text(encoding="utf-8").strip().split("|")
    assert int(state[0]) != 0
    assert state[1:] == ["false", "true", "false"]
    assert pytorch_marker.exists()
    assert not ai_marker.exists()
    assert "Full profile stopped because PyTorch setup did not validate" in result.stdout


def test_help_exposes_digest_requirements():
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--torch-sha256" in result.stdout
    assert "--torchvision-sha256" in result.stdout
    assert "not artifact-verified" in result.stdout


def test_ai_setup_help_does_not_require_the_mutation_lock(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python_marker = tmp_path / "python-called"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\ntouch \"$PYTHON_MARKER\"\nexit 99\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["PYTHON_MARKER"] = str(python_marker)

    for script in (SCRIPT_PATH, AI_INSTALLER_PATH):
        result = subprocess.run(
            ["bash", str(script), "--help"],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Usage:" in result.stdout

    assert not python_marker.exists()


def test_core_requirements_have_one_opencv_distribution_owner():
    packages = []
    for raw_line in CORE_REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().lower()
        if line and not line.startswith("#") and line.startswith("opencv-"):
            packages.append(line.split()[0])

    assert packages == ["opencv-contrib-python-headless"]
    source = CORE_REQUIREMENTS_PATH.read_text(encoding="utf-8")
    assert "!= 4.13.0.90" in source
    assert "non-GStreamer" in source
    assert "fallback" in source
    assert "not a reproducible lock" in source


def _requirement_names(path: Path):
    names = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        names.append(Requirement(line).name.lower())
    return names


def test_ai_role_has_no_second_opencv_owner_or_implicit_ultralytics_install():
    names = _requirement_names(AI_REQUIREMENTS_PATH)

    assert "ultralytics" not in names
    assert not any(name.startswith("opencv-") for name in names)
    assert "ncnn" not in names
    assert "pnnx" not in names
    assert "lap" in names
    assert "nvidia-ml-py" in names
    assert "packaging" in names
    assert "torch" not in names
    assert "torchvision" not in names
    installer = AI_INSTALLER_PATH.read_text(encoding="utf-8")
    assert "PyTorch prerequisite compatibility check failed" in installer
    assert "scripts/setup/setup-pytorch.sh --mode auto" in installer
    assert "not fully reproducible" in AI_REQUIREMENTS_PATH.read_text(
        encoding="utf-8"
    )


def test_aggregate_requirements_cannot_bypass_ai_installer():
    aggregate = AGGREGATE_REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert "-r requirements-core.txt" in aggregate
    assert "-r requirements-dev.txt" in aggregate
    assert "-r requirements-ai.txt" not in aggregate
    assert "scripts/setup/install-ai-deps.sh" in aggregate


def test_ultralytics_wheel_is_exactly_versioned_and_hash_pinned():
    source = ULTRALYTICS_REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert "ultralytics==8.4.95" in source
    digest = "8a2097a7f792abcfac4d98e0ad799ab6c004f8d6e9b28e65d6d997841777f9ae"
    assert f"--hash=sha256:{digest}" in source
    assert len(digest) == 64
    int(digest, 16)
    assert "does not make the complete AI environment reproducible" in source


def test_ncnn_dependencies_are_explicit_opt_in():
    names = _requirement_names(NCNN_REQUIREMENTS_PATH)
    source = AI_INSTALLER_PATH.read_text(encoding="utf-8")
    requirements = NCNN_REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert names == ["ncnn", "pnnx"]
    assert "ncnn>=1.0.20250503" in requirements
    assert "pnnx==20260526" in requirements
    assert 'metadata.version("pnnx")' in source
    assert 'pnnx_version != "20260526"' in source
    assert "--with-ncnn" in source
    assert "requirements-ai-ncnn.txt" in source


def test_ai_runtime_diagnostic_never_rewrites_tracked_helpers():
    source = (PROJECT_ROOT / "scripts" / "setup" / "check-ai-runtime.sh").read_text(
        encoding="utf-8"
    )

    assert "sed -i" not in source
    assert "require_unix_line_endings" in source
    assert "Refusing to rewrite tracked helper" in source


def test_ai_installer_preserves_exact_opencv_provider_and_bypasses_resolver_for_ultralytics():
    source = AI_INSTALLER_PATH.read_text(encoding="utf-8")
    probe = (PROJECT_ROOT / "scripts" / "setup" / "opencv_provider_probe.py").read_text(
        encoding="utf-8"
    )

    assert 'OPENCV_BEFORE="$(opencv_fingerprint)"' in source
    assert 'if [[ "$OPENCV_AFTER" != "$OPENCV_BEFORE" ]]' in source
    assert "opencv_provider_probe.py" in source
    assert "multiple OpenCV distribution owners detected" in probe
    assert "OpenCV module is outside the selected virtual environment" in probe
    assert "build_information_sha256" in probe
    assert "fingerprinted_files" in probe
    assert "--only-binary=:all:" in source
    assert "--no-deps" in source
    assert "--force-reinstall" in source
    assert "--require-hashes" in source
    assert "verify_dependency_contract" in source
    assert "pytorch_fingerprint" in source
    assert "--allow-opencv-replacement" not in source
    assert "fix_line_endings" not in source
    assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]' in source


def test_core_rerun_preserves_gui_contrib_provider_without_requesting_headless_wheel(
    tmp_path,
):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(CORE_REQUIREMENTS_PATH, checkout / "requirements-core.txt")
    captured = tmp_path / "captured-requirements.txt"
    fake_pip = tmp_path / "pip"
    fake_pip.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ ${1:-} == install && ${2:-} == -r ]]; then "
        'cp -- "$3" "$PIXEAGLE_TEST_CAPTURED_REQUIREMENTS"; fi\n',
        encoding="utf-8",
    )
    fake_pip.chmod(0o755)
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "case ${1:-} in *pip_check_policy.py) exit 0 ;; esac\n"
        f"exec {sys.executable!s} \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    activate = tmp_path / "activate"
    activate.write_text("deactivate() { :; }\n", encoding="utf-8")
    gui_fingerprint = json.dumps(
        {
            "provider_kind": "managed_wheel",
            "distribution_owners": {
                "opencv-contrib-python": {"record_verified": True}
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    shell = f'''
set -euo pipefail
source "{PROJECT_ROOT / 'scripts' / 'init.sh'}"
trap - EXIT
PIXEAGLE_DIR="$1"
INSTALL_PROFILE=core
VENV_DIR="$2"
VENV_ACTIVATE="$3"
VENV_PYTHON="$4"
VENV_PIP="$5"
opencv_provider_fingerprint() {{ printf '%s\n' '{gui_fingerprint}'; }}
install_python_deps
'''
    environment = os.environ.copy()
    environment["PIXEAGLE_TEST_CAPTURED_REQUIREMENTS"] = str(captured)
    result = subprocess.run(
        [
            "bash",
            "-c",
            shell,
            "test",
            str(checkout),
            str(tmp_path / "venv"),
            str(activate),
            str(fake_python),
            str(fake_pip),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    requirements = captured.read_text(encoding="utf-8").lower()
    assert "opencv" not in requirements
    assert "numpy" in requirements
    assert "preserving the verified custom gui contrib wheel" in result.stdout.lower()


def _write_report_with_sourced_script(script: Path, report: Path, assignments: str):
    shell = f"""
set -euo pipefail
source {script!s}
REPORT_JSON="$1"
{assignments}
write_report_json 0
REPORT_JSON=""
"""
    result = subprocess.run(
        ["bash", "-c", shell, "test", str(report)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert report.stat().st_mode & 0o777 == 0o600
    return json.loads(report.read_text(encoding="utf-8"))


def test_ai_installer_report_separates_artifact_verification_from_reproducibility(
    tmp_path,
):
    report = tmp_path / "ai-report.json"
    payload = _write_report_with_sourced_script(
        AI_INSTALLER_PATH,
        report,
        """
REPORT_STATUS="success"
OPENCV_BEFORE='{"version":"test"}'
OPENCV_AFTER="$OPENCV_BEFORE"
PYTORCH_BEFORE='{"torch":{"version":"test"}}'
PYTORCH_AFTER="$PYTORCH_BEFORE"
RUNTIME_EVIDENCE='{"packages":{"ultralytics":{"version":"test"}}}'
""",
    )

    assert payload["status"] == "success"
    assert payload["reproducibility"]["fully_reproducible"] is False
    assert payload["reproducibility"]["artifact_verified"]
    assert payload["opencv"]["before"] == payload["opencv"]["after"]
    assert payload["installed_runtime"]["packages"]["ultralytics"]["version"] == "test"


def test_pytorch_report_labels_index_selection_as_not_hash_locked(tmp_path):
    report = tmp_path / "pytorch-report.json"
    payload = _write_report_with_sourced_script(
        SCRIPT_PATH,
        report,
        """
REPORT_STATUS="success"
REPORT_MESSAGE="test fixture"
PROFILE_KEY="linux_cpu"
PROFILE_DESCRIPTION="test"
PROFILE_INSTALL_METHOD="index"
PROFILE_INDEX_URL="https://download.pytorch.org/whl/cpu?secret=redacted"
PROFILE_TORCH_SPEC="2.6.0"
PROFILE_TORCHVISION_SPEC="0.21.0"
PROFILE_TORCHAUDIO_SPEC="2.6.0"
MATRIX_SHA256="test-matrix"
DRY_RUN="true"
VERIFY_JSON='{"torch_ok":true,"torchvision_ok":true}'
""",
    )

    reproducibility = payload["reproducibility"]
    assert reproducibility["fully_reproducible"] is False
    assert reproducibility["verified_direct_artifacts"] == []
    assert "without artifact hashes" in reproducibility["selection_policy"]
    assert "secret" not in payload["selected_profile"]["index_url"]
    assert payload["selected_profile"]["requested_versions"]["torch"] == "2.6.0"


def test_opencv_builder_pins_sources_and_writes_bounded_runtime_evidence(tmp_path):
    source = OPENCV_BUILD_PATH.read_text(encoding="utf-8")
    assert 'OPENCV_SOURCE_COMMIT="fe38fc608f6acb8b68953438a62305d8318f4fcd"' in source
    assert (
        'OPENCV_CONTRIB_SOURCE_COMMIT="d99ad2a188210cc35067c2e60076eed7c2442bc3"'
        in source
    )
    assert "RUNTIME_JSON:" in source
    assert "opencv_provider_probe.py" in source
    assert '"provider_kind") != "source_gstreamer"' in source
    assert "fully_reproducible" in source
    assert "--report-json" in source
    assert '"$VENV_DIR/bin/pip" install numpy' not in source

    report = tmp_path / "opencv-report.json"
    payload = _write_report_with_sourced_script(
        OPENCV_BUILD_PATH,
        report,
        """
REPORT_STATUS="test_fixture"
RUNTIME_EVIDENCE='{"version":"test","gstreamer":true}'
SOURCE_EVIDENCE='{"opencv":{"expected_commit":"test-opencv","archive_sha256":"test-archive"},"opencv_contrib":{"expected_commit":"test-contrib"}}'
BUILD_EVIDENCE='{"build_files":[{"path":"build/CMakeCache.txt","sha256":"test-build"}],"downloads":[]}'
OPENCV_WORK_CLEANUP_STATUS="removed"
""",
    )
    assert payload["schema_version"] == 2
    assert payload["reproducibility"]["fully_reproducible"] is False
    assert payload["selection"]["gstreamer_required"] is True
    assert payload["sources"]["opencv"]["expected_commit"] == "test-opencv"
    assert payload["build_evidence"]["build_files"][0]["sha256"] == "test-build"
    assert payload["work_root_cleanup"] == "removed"
    assert payload["installed_runtime"]["gstreamer"] is True


def test_owned_setup_docs_state_fallback_evidence_and_license_boundaries():
    opencv = OPENCV_DOC_PATH.read_text(encoding="utf-8")
    model = MODEL_SETUP_DOC_PATH.read_text(encoding="utf-8")

    assert "non-GStreamer" in opencv
    assert "fallback" in opencv
    assert "setup-evidence/opencv-gstreamer.json" in opencv
    assert "not a signed source release or a" in opencv
    assert "byte-reproducible build claim" in opencv
    assert "legal determination" in opencv
    assert "setup-evidence" in model
    assert "hash-lock" in model
    assert "not proof of a fully reproducible" in model
    assert "Component availability is not a licensing conclusion" in model
