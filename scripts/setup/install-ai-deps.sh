#!/bin/bash

# ============================================================================
# scripts/setup/install-ai-deps.sh - Safe AI dependency installer
# ============================================================================
# Installs PixEagle AI packages while preserving the single existing OpenCV
# provider (contrib wheel or source-built GStreamer OpenCV).
#
# Usage:
#   bash scripts/setup/install-ai-deps.sh
#   bash scripts/setup/install-ai-deps.sh --with-ncnn
# ============================================================================

set -euo pipefail

TOTAL_STEPS=5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

ALLOW_CORE_UPGRADES=false
WITH_NCNN=false
CONSTRAINTS_FILE=""
REPORT_JSON=""
REPORT_STATUS="not_started"
REPORT_ERROR=""
OPENCV_BEFORE=""
OPENCV_AFTER=""
PYTORCH_BEFORE=""
PYTORCH_AFTER=""
RUNTIME_EVIDENCE='{}'
AI_INSTALL_COMMITTED=false

# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    CHECK="[OK]"; CROSS="[X]"; WARN="[!]"
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}${CHECK}${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}${WARN}${NC} $1"; }
    log_error() { echo -e "   ${RED}${CROSS}${NC} $1"; }
    log_step() { echo -e "\n${CYAN}[${1}/${TOTAL_STEPS}]${NC} $2"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}\n"
    }
fi
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/setup_lock.sh" 2>/dev/null; then
    echo "Error: Could not source the required setup lock helper" >&2
    exit 1
fi
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/venv_transaction.sh" 2>/dev/null; then
    echo "Error: Could not source the required venv transaction helper" >&2
    exit 1
fi

if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
    VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
else
    VENV_DIR="${PIXEAGLE_VENV_DIR:-$PIXEAGLE_DIR/venv}"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

cleanup() {
    if [[ -n "${CONSTRAINTS_FILE:-}" && -f "${CONSTRAINTS_FILE:-}" ]]; then
        if ! rm -f -- "$CONSTRAINTS_FILE"; then
            return 1
        fi
        CONSTRAINTS_FILE=""
    fi
    return 0
}

fail() {
    REPORT_STATUS="failed"
    REPORT_ERROR="$1"
    log_error "$1"
    exit "${2:-1}"
}

show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/install-ai-deps.sh [OPTIONS]

Install AI dependencies used by SmartTracker and model tooling:
  - hash-pinned ultralytics wheel (installed without dependency resolution)
  - lap
  - direct runtime dependencies
  - validation of the separately installed torch/torchvision runtime

Options:
  --allow-core-upgrades   Allow compatible NumPy/PyTorch changes; OpenCV is
                          always preserved exactly
  --with-ncnn             Also install NCNN inference/export dependencies
  --report-json <path>    Write an owner-only installed-runtime evidence report
  --help, -h              Show this help
USAGE
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --allow-core-upgrades)
                ALLOW_CORE_UPGRADES=true
                ;;
            --with-ncnn)
                WITH_NCNN=true
                ;;
            --report-json)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --report-json"
                REPORT_JSON="$1"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
        shift
    done
}

write_report_json() {
    local exit_code="$1"
    [[ -n "$REPORT_JSON" ]] || return 0

    python3 - "$REPORT_JSON" "$exit_code" "$REPORT_STATUS" "$REPORT_ERROR" \
        "$ALLOW_CORE_UPGRADES" "$WITH_NCNN" "$PIXEAGLE_DIR" "$SCRIPT_DIR" \
        "$VENV_DIR" \
        3<<<"$OPENCV_BEFORE" 4<<<"$OPENCV_AFTER" \
        5<<<"$PYTORCH_BEFORE" 6<<<"$PYTORCH_AFTER" \
        7<<<"$RUNTIME_EVIDENCE" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    report_path_raw,
    exit_code_raw,
    status,
    error,
    allow_core_upgrades_raw,
    with_ncnn_raw,
    root_raw,
    script_dir_raw,
    venv_raw,
) = sys.argv[1:]
opencv_before_raw = os.fdopen(3, encoding="utf-8").read()
opencv_after_raw = os.fdopen(4, encoding="utf-8").read()
pytorch_before_raw = os.fdopen(5, encoding="utf-8").read()
pytorch_after_raw = os.fdopen(6, encoding="utf-8").read()
runtime_raw = os.fdopen(7, encoding="utf-8").read()
sys.path.insert(0, script_dir_raw)
from evidence_path import atomic_write_json


def decode(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"unparsed": raw}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


root = Path(root_raw).resolve()
runtime = decode(runtime_raw) or {}
inputs = {}
for relative in (
    "requirements-ai.txt",
    "requirements-ai-ncnn.txt",
    "requirements-ultralytics.txt",
    "scripts/setup/install-ai-deps.sh",
):
    path = root / relative
    if path.is_file():
        inputs[relative] = {"sha256": sha256_file(path), "size": path.stat().st_size}

payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": status,
    "exit_code": int(exit_code_raw),
    "error": error or None,
    "selection": {
        "allow_core_upgrades": allow_core_upgrades_raw.lower() == "true",
        "with_ncnn": with_ncnn_raw.lower() == "true",
        "venv": str(Path(venv_raw).resolve()),
    },
    "reproducibility": {
        "fully_reproducible": False,
        "artifact_verified": (
            ["The installed Ultralytics wheel was exact-version and SHA-256 verified."]
            if status == "success" and runtime.get("packages", {}).get("ultralytics")
            else []
        ),
        "artifact_verification_policy": (
            "Ultralytics is force-reinstalled from a binary artifact under "
            "--require-hashes."
        ),
        "resolver_managed": [
            "requirements-ai.txt concrete artifacts and transitive dependencies",
            "PyTorch index profiles and their transitive dependencies",
        ]
        + (
            ["requirements-ai-ncnn.txt concrete artifacts and transitive dependencies"]
            if with_ncnn_raw.lower() == "true"
            else []
        ),
        "claim": (
            "This report fingerprints the installed runtime; it is not a complete "
            "reproducible-environment attestation."
        ),
    },
    "inputs": inputs,
    "opencv": {
        "policy": "preserve_exact_provider",
        "before": decode(opencv_before_raw),
        "after": decode(opencv_after_raw),
    },
    "pytorch": {
        "before": decode(pytorch_before_raw),
        "after": decode(pytorch_after_raw),
    },
    "installed_runtime": runtime,
}

atomic_write_json(report_path_raw, payload)
PY

    log_info "Wrote AI dependency evidence: $REPORT_JSON"
}

on_exit() {
    local exit_code=$?
    local cleanup_failed=false
    trap - EXIT

    if [[ "$exit_code" -ne 0 && "$REPORT_STATUS" != "failed" ]]; then
        REPORT_STATUS="failed"
        REPORT_ERROR="${REPORT_ERROR:-installer exited with code $exit_code}"
    fi
    if ! cleanup; then
        cleanup_failed=true
        if [[ "$AI_INSTALL_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_cleanup_failed"
            REPORT_ERROR="verified AI runtime was committed, but temporary-file cleanup failed"
            exit_code=75
        else
            REPORT_STATUS="failed"
            REPORT_ERROR="temporary-file cleanup failed before the AI transaction committed"
            [[ "$exit_code" -ne 0 ]] || exit_code=1
        fi
        log_error "$REPORT_ERROR"
    fi
    if ! pixeagle_finalize_venv_transaction; then
        log_error "AI dependency failure rollback was incomplete"
        [[ "$exit_code" -ne 0 ]] || exit_code=1
    fi
    if ! write_report_json "$exit_code"; then
        if [[ "$AI_INSTALL_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_evidence_failed"
            REPORT_ERROR="verified AI runtime was committed, but evidence publication failed"
            log_error "$REPORT_ERROR: $REPORT_JSON"
            log_error "The installed runtime was retained; this failure does not mean rollback occurred"
            exit_code=74
        else
            log_error "Could not write requested AI dependency evidence: $REPORT_JSON"
            [[ "$exit_code" -ne 0 ]] || exit_code=1
        fi
    fi
    if [[ "$cleanup_failed" == true && -n "${CONSTRAINTS_FILE:-}" ]]; then
        log_error "Temporary constraints file was retained: $CONSTRAINTS_FILE"
    fi
    pixeagle_release_setup_lock
    exit "$exit_code"
}
trap on_exit EXIT

pytorch_fingerprint() {
    "$VENV_PYTHON" - "$PIXEAGLE_DIR/scripts/setup/pytorch_matrix.json" <<'PY'
import hashlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name
except ImportError:
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.utils import canonicalize_name


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_evidence(path):
    path = Path(path).resolve()
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def distribution_evidence(name):
    dist = md.distribution(name)
    dist_path = Path(getattr(dist, "_path", ""))
    evidence = {"name": name, "version": dist.version}
    for filename in ("METADATA", "RECORD", "direct_url.json"):
        candidate = dist_path / filename
        if candidate.is_file():
            evidence[filename.lower().replace(".", "_") + "_sha256"] = sha256_file(
                candidate
            )
    return evidence


def check_dependency(distribution, dependency, installed_version, errors):
    dependency_name = canonicalize_name(dependency)
    for raw in md.requires(distribution) or []:
        requirement = Requirement(raw)
        if canonicalize_name(requirement.name) != dependency_name:
            continue
        if requirement.marker and not requirement.marker.evaluate(default_environment()):
            continue
        if requirement.specifier and installed_version not in requirement.specifier:
            errors.append(
                f"{distribution} requires {requirement}, found "
                f"{dependency} {installed_version}"
            )


try:
    import torch
    import torchvision
except Exception as exc:
    raise SystemExit(f"PyTorch/torchvision import failed: {type(exc).__name__}: {exc}")

try:
    torch_version = md.version("torch")
    vision_version = md.version("torchvision")
except md.PackageNotFoundError as exc:
    raise SystemExit(
        f"PyTorch distribution metadata is missing for imported module: {exc}"
    )
errors = []
if torch_version not in SpecifierSet(">=1.8.0"):
    errors.append(f"Ultralytics requires torch>=1.8.0, found {torch_version}")
if vision_version not in SpecifierSet(">=0.9.0"):
    errors.append(f"Ultralytics requires torchvision>=0.9.0, found {vision_version}")
check_dependency("torchvision", "torch", torch_version, errors)

try:
    audio_version = md.version("torchaudio")
except md.PackageNotFoundError:
    audio_version = None
if audio_version:
    check_dependency("torchaudio", "torch", torch_version, errors)

module_versions = {
    "torch": str(getattr(torch, "__version__", "")),
    "torchvision": str(getattr(torchvision, "__version__", "")),
}
venv_path = Path(sys.prefix).resolve()
for name, module in (("torch", torch), ("torchvision", torchvision)):
    module_path = Path(module.__file__).resolve()
    if not module_path.is_relative_to(venv_path):
        errors.append(
            f"{name} module is outside the selected virtual environment: {module_path}"
        )
for name, metadata_version in (
    ("torch", torch_version),
    ("torchvision", vision_version),
):
    if module_versions[name].split("+", 1)[0] != metadata_version.split("+", 1)[0]:
        errors.append(
            f"{name} import version {module_versions[name]} does not match "
            f"installed metadata {metadata_version}"
        )

if errors:
    raise SystemExit("PyTorch compatibility check failed: " + "; ".join(errors))

native_files = []
for candidate in (
    Path(torch.__file__).resolve(),
    Path(torch._C.__file__).resolve(),
    Path(torchvision.__file__).resolve(),
):
    if candidate.is_file() and candidate not in native_files:
        native_files.append(candidate)
vision_root = Path(torchvision.__file__).resolve().parent
for candidate in sorted(vision_root.glob("_C.*")):
    if candidate.is_file() and candidate not in native_files:
        native_files.append(candidate)

matrix_path = Path(sys.argv[1]).resolve()
matrix_matches = []
if matrix_path.is_file():
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    for key, profile in matrix.get("profiles", {}).items():
        packages = profile.get("packages", {})
        if (
            packages.get("torch") == torch_version.split("+", 1)[0]
            and packages.get("torchvision") == vision_version.split("+", 1)[0]
        ):
            matrix_matches.append(key)

payload = {
    "torch": distribution_evidence("torch"),
    "torchvision": distribution_evidence("torchvision"),
    "torchaudio": distribution_evidence("torchaudio") if audio_version else None,
    "module_versions": module_versions,
    "fingerprinted_files": [file_evidence(path) for path in native_files],
    "fingerprint_scope": "distribution metadata/RECORD plus imported entry points",
    "matrix_sha256": sha256_file(matrix_path) if matrix_path.is_file() else None,
    "matching_matrix_profiles": matrix_matches,
    "compatibility_checked": True,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY
}

check_prereqs() {
    log_step 1 "Checking environment"

    [[ -x "$VENV_PIP" ]] || fail "Missing venv pip: $VENV_PIP"
    [[ -x "$VENV_PYTHON" ]] || fail "Missing venv python: $VENV_PYTHON"

    if ! PYTORCH_BEFORE="$(pytorch_fingerprint)"; then
        log_error "Compatible PyTorch/torchvision prerequisites are missing or broken"
        log_detail "Run: bash scripts/setup/setup-pytorch.sh --mode auto"
        fail "PyTorch prerequisite compatibility check failed"
    fi

    log_success "Using venv: $VENV_DIR"
    log_success "PyTorch/torchvision imports and metadata are compatible"
    log_detail "$PYTORCH_BEFORE"

    if ! OPENCV_BEFORE="$(opencv_fingerprint)"; then
        fail "OpenCV provider validation failed"
    fi
    log_success "OpenCV provider is ready and will be preserved"
    log_detail "$OPENCV_BEFORE"
}

opencv_fingerprint() {
    "$VENV_PYTHON" "$SCRIPT_DIR/opencv_provider_probe.py"
}

build_constraints() {
    log_step 2 "Preparing dependency constraints"

    if [[ "$ALLOW_CORE_UPGRADES" == "true" ]]; then
        log_warn "Core package upgrades allowed (--allow-core-upgrades)"
        return 0
    fi

    CONSTRAINTS_FILE="$(mktemp)"

    "$VENV_PYTHON" - "$CONSTRAINTS_FILE" <<'PY'
import importlib.metadata as md
import sys

target = sys.argv[1]
protected = [
    "numpy",
    "opencv-python",
    "opencv-contrib-python",
    "opencv-python-headless",
    "opencv-contrib-python-headless",
    "torch",
    "torchvision",
    "torchaudio",
]

lines = []
for name in protected:
    try:
        version = md.version(name)
    except md.PackageNotFoundError:
        continue
    lines.append(f"{name}=={version}")

with open(target, "w", encoding="utf-8") as f:
    if lines:
        f.write("\n".join(lines) + "\n")
PY

    if [[ -s "$CONSTRAINTS_FILE" ]]; then
        log_success "Constraint lockfile generated"
        log_detail "Protected packages:"
        while IFS= read -r line; do
            [[ -n "$line" ]] && log_detail "- $line"
        done < "$CONSTRAINTS_FILE"
    else
        log_warn "No protected packages detected in current venv"
        rm -f "$CONSTRAINTS_FILE"
        CONSTRAINTS_FILE=""
    fi
}

install_ai_packages() {
    log_step 3 "Installing AI packages"

    local ai_requirements="$PIXEAGLE_DIR/requirements-ai.txt"
    local ultralytics_requirements="$PIXEAGLE_DIR/requirements-ultralytics.txt"
    [[ -f "$ai_requirements" ]] || {
        log_error "Missing requirements-ai.txt"
        return 1
    }
    [[ -f "$ultralytics_requirements" ]] || {
        log_error "Missing requirements-ultralytics.txt"
        return 1
    }

    local cmd=("$VENV_PIP" install --prefer-binary -r "$ai_requirements")
    if [[ -n "$CONSTRAINTS_FILE" ]]; then
        cmd=("$VENV_PIP" install --prefer-binary -c "$CONSTRAINTS_FILE" -r "$ai_requirements")
    fi

    log_info "Installing resolver-managed AI runtime dependencies"
    "${cmd[@]}"

    log_info "Installing the exact hash-verified Ultralytics wheel without dependency resolution"
    "$VENV_PIP" install \
        --only-binary=:all: \
        --no-deps \
        --force-reinstall \
        --require-hashes \
        -r "$ultralytics_requirements"

    if [[ "$WITH_NCNN" == "true" ]]; then
        local ncnn_requirements="$PIXEAGLE_DIR/requirements-ai-ncnn.txt"
        [[ -f "$ncnn_requirements" ]] || {
            log_error "Missing requirements-ai-ncnn.txt"
            return 1
        }
        local ncnn_cmd=("$VENV_PIP" install --prefer-binary -r "$ncnn_requirements")
        if [[ -n "$CONSTRAINTS_FILE" ]]; then
            ncnn_cmd=("$VENV_PIP" install --prefer-binary -c "$CONSTRAINTS_FILE" -r "$ncnn_requirements")
        fi
        log_info "Installing explicitly requested NCNN dependencies"
        "${ncnn_cmd[@]}"
    fi

    log_success "AI packages installation command completed"
}

parse_ai_verification_payload() {
    local raw="$1"
    local -a values=()

    mapfile -d '' -t values < <(python3 - "$raw" <<'PY'
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception as exc:
    data = {}
    error = f"invalid AI verification payload: {exc}"
else:
    error = str(data.get("error") or "")

optional_ok = data.get("ncnn") is not False and data.get("pnnx") is not False
ok = bool(data.get("ultralytics")) and bool(data.get("lap")) and optional_ok
values = (
    "1" if ok else "0",
    "1" if data.get("ultralytics") else "0",
    "1" if data.get("lap") else "0",
    "1" if data.get("ncnn") else "0",
    "1" if data.get("pnnx") else "0",
    error,
)
sys.stdout.buffer.write(b"\0".join(value.encode("utf-8") for value in values) + b"\0")
PY
    )

    if [[ "${#values[@]}" -ne 6 ]]; then
        log_error "AI verification parser returned an incomplete payload"
        return 1
    fi

    OK="${values[0]}"
    ULTRA="${values[1]}"
    LAP="${values[2]}"
    NCNN="${values[3]}"
    PNNX="${values[4]}"
    ERR="${values[5]}"
}

verify_ai_runtime() {
    log_step 4 "Verifying imports and dependency metadata"

    local payload
    # Keep import-time library output away from the machine-readable result.
    # Ultralytics writes its first-run settings notice to stdout, so fd 3 retains
    # the command-substitution pipe while regular stdout is sent to stderr.
    payload="$("$VENV_PYTHON" - "$WITH_NCNN" 3>&1 1>&2 <<'PY'
import importlib.metadata as metadata
import json
import os
import sys

with_ncnn = sys.argv[1].lower() == "true"

status = {
    "ultralytics": False,
    "lap": False,
    "ncnn": None,
    "pnnx": None,
    "pnnx_version": None,
    "error": None,
}

try:
    from ultralytics import YOLO  # noqa: F401
    status["ultralytics"] = True
except Exception as e:
    status["error"] = f"ultralytics import failed: {e}"

try:
    import lap  # noqa: F401
    status["lap"] = True
except Exception as e:
    if not status["error"]:
        status["error"] = f"lap import failed: {e}"

if with_ncnn:
    try:
        import ncnn  # noqa: F401
        status["ncnn"] = True
    except Exception as e:
        status["ncnn"] = False
        if not status["error"]:
            status["error"] = f"ncnn import failed: {e}"
    try:
        import pnnx  # noqa: F401
        status["pnnx"] = True
        status["pnnx_version"] = metadata.version("pnnx")
        if status["pnnx_version"] != "20260526":
            status["pnnx"] = False
            status["error"] = (
                "pnnx 20260526 is required by the pinned Ultralytics NCNN exporter; "
                f"found {status['pnnx_version']}"
            )
    except Exception as e:
        status["pnnx"] = False
        if not status["error"]:
            status["error"] = f"pnnx import failed: {e}"

with os.fdopen(3, "w", encoding="utf-8") as result_stream:
    json.dump(status, result_stream)
PY
)"

    if ! parse_ai_verification_payload "$payload"; then
        return 1
    fi

    if [[ "$ULTRA" -eq 1 ]]; then
        log_success "ultralytics import OK"
    else
        log_warn "ultralytics import failed"
    fi
    if [[ "$LAP" -eq 1 ]]; then
        log_success "lap import OK"
    else
        log_warn "lap import failed"
    fi
    if [[ "$WITH_NCNN" == "true" ]]; then
        if [[ "$NCNN" -eq 1 ]]; then
            log_success "ncnn import OK"
        else
            log_warn "ncnn import failed"
        fi
        if [[ "$PNNX" -eq 1 ]]; then
            log_success "pnnx import OK"
        else
            log_warn "pnnx import failed"
        fi
    else
        log_info "NCNN dependencies not requested"
    fi

    if [[ "$OK" -ne 1 ]]; then
        log_error "AI verification failed: ${ERR:-unknown}"
        return 1
    fi

    log_success "AI runtime verification passed"
    return 0
}

verify_dependency_contract() {
    log_step 5 "Verifying OpenCV ownership and package consistency"

    OPENCV_AFTER="$(opencv_fingerprint)" || return 1
    if [[ "$OPENCV_AFTER" != "$OPENCV_BEFORE" ]]; then
        log_error "AI installation changed the OpenCV provider"
        log_detail "Before: $OPENCV_BEFORE"
        log_detail "After:  $OPENCV_AFTER"
        return 1
    fi

    PYTORCH_AFTER="$(pytorch_fingerprint)" || {
        log_error "AI installation left an incompatible PyTorch/torchvision runtime"
        return 1
    }
    if [[ "$ALLOW_CORE_UPGRADES" != "true" && "$PYTORCH_AFTER" != "$PYTORCH_BEFORE" ]]; then
        log_error "AI installation changed the protected PyTorch runtime"
        log_detail "Before: $PYTORCH_BEFORE"
        log_detail "After:  $PYTORCH_AFTER"
        return 1
    fi

    "$VENV_PYTHON" - "$WITH_NCNN" <<'PY'
import importlib.metadata as md
import sys
from packaging.requirements import Requirement

import cv2

errors = []
with_ncnn = sys.argv[1].lower() == "true"
if with_ncnn:
    try:
        pnnx_version = md.version("pnnx")
    except md.PackageNotFoundError:
        errors.append("missing pnnx==20260526")
    else:
        if pnnx_version != "20260526":
            errors.append(f"pnnx {pnnx_version} does not match required 20260526")
for raw_requirement in md.requires("ultralytics") or []:
    requirement = Requirement(raw_requirement)
    if requirement.marker and not requirement.marker.evaluate():
        continue
    normalized = requirement.name.lower().replace("_", "-")
    if normalized == "opencv-python":
        installed = cv2.__version__
    else:
        try:
            installed = md.version(requirement.name)
        except md.PackageNotFoundError:
            errors.append(f"missing {requirement}")
            continue
    if requirement.specifier and installed not in requirement.specifier:
        errors.append(
            f"{requirement.name} {installed} does not satisfy {requirement.specifier}"
        )

if errors:
    raise SystemExit("Ultralytics dependency contract failed: " + "; ".join(errors))
PY

    if ! "$VENV_PYTHON" "$SCRIPT_DIR/pip_check_policy.py"; then
        log_error "pip reported dependency inconsistencies outside the reviewed OpenCV policy"
        return 1
    fi

    RUNTIME_EVIDENCE="$(collect_runtime_evidence)" || {
        log_error "Could not fingerprint the installed AI runtime"
        return 1
    }

    log_success "OpenCV preservation and AI dependency compatibility verified"
    log_detail "$RUNTIME_EVIDENCE"
}

collect_runtime_evidence() {
    "$VENV_PYTHON" - "$WITH_NCNN" <<'PY'
import hashlib
import importlib.metadata as md
import importlib.util
import json
import platform
import sys
import sysconfig
from pathlib import Path

with_ncnn = sys.argv[1].lower() == "true"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def distribution_evidence(name, module_name=None):
    dist = md.distribution(name)
    dist_path = Path(getattr(dist, "_path", ""))
    evidence = {"version": dist.version}
    for filename in ("METADATA", "RECORD", "direct_url.json"):
        candidate = dist_path / filename
        if candidate.is_file():
            evidence[filename.lower().replace(".", "_") + "_sha256"] = sha256_file(
                candidate
            )
    if module_name:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin and spec.origin not in {"built-in", "frozen"}:
            origin = Path(spec.origin).resolve()
            if origin.is_file():
                evidence["module_file"] = str(origin)
                evidence["module_file_sha256"] = sha256_file(origin)
    return evidence


requested = {
    "torch": "torch",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
    "ultralytics": "ultralytics",
    "lap": "lap",
    "matplotlib": "matplotlib",
    "polars": "polars",
    "ultralytics-thop": "thop",
    "nvidia-ml-py": "pynvml",
    "packaging": "packaging",
}
if with_ncnn:
    requested.update({"ncnn": "ncnn", "pnnx": "pnnx"})

packages = {}
for name, module_name in requested.items():
    try:
        packages[name] = distribution_evidence(name, module_name)
    except md.PackageNotFoundError:
        if name == "torchaudio":
            packages[name] = None
        else:
            raise SystemExit(f"required installed distribution is missing: {name}")

payload = {
    "python": {
        "executable": str(Path(sys.executable).resolve()),
        "prefix": str(Path(sys.prefix).resolve()),
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": sysconfig.get_platform(),
    },
    "packages": packages,
    "fingerprint_scope": (
        "installed versions, distribution metadata/RECORD, and import entry points; "
        "this is not a hash of every installed file"
    ),
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY
}

main() {
    parse_args "$@"
    if ! pixeagle_acquire_setup_lock "$VENV_DIR" "AI dependency setup" 30; then
        fail "Another PixEagle setup operation is active"
    fi
    REPORT_STATUS="running"
    if [[ -n "$REPORT_JSON" ]]; then
        if ! REPORT_JSON="$(python3 "$SCRIPT_DIR/evidence_path.py" "$REPORT_JSON")"; then
            fail "AI evidence destination failed owner/type/write preflight"
        fi
    fi
    display_pixeagle_banner "AI Dependency Setup" "Verified Ultralytics artifact with one OpenCV provider"

    check_prereqs
    build_constraints
    if ! pixeagle_begin_venv_transaction "$VENV_DIR" "AI dependency setup"; then
        fail "Could not create the exact AI dependency rollback boundary"
    fi
    install_ai_packages
    verify_ai_runtime
    verify_dependency_contract

    if ! pixeagle_commit_venv_transaction; then
        fail "Could not commit the verified AI environment"
    fi
    AI_INSTALL_COMMITTED=true

    REPORT_STATUS="success"
    echo ""
    log_success "AI dependencies are ready"
    if [[ -z "$REPORT_JSON" ]]; then
        log_warn "No JSON evidence path requested; rerun with --report-json <path> to retain provenance"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
        trap - EXIT
        show_help
    elif pixeagle_setup_lock_context_present; then
        main "$@"
    else
        trap - EXIT
        pixeagle_run_with_setup_lock \
            "$VENV_DIR" "AI dependency setup" 30 bash "${BASH_SOURCE[0]}" "$@"
    fi
fi
