#!/bin/bash

# ============================================================================
# scripts/setup/setup-pytorch.sh - Matrix-driven PyTorch Setup for PixEagle
# ============================================================================
# Installs and validates PyTorch with platform-aware acceleration support.
#
# Supported target classes:
#   - Linux x86_64 + NVIDIA GPU (CUDA wheels via official PyTorch index)
#   - NVIDIA Jetson (JetPack-matched wheel profiles)
#   - Linux CPU-only
#   - macOS Apple Silicon (MPS or CPU-only)
#   - macOS Intel CPU-only
#
# Profile selection is deterministic and matrix-driven, but index profiles are
# version-constrained rather than artifact-locked:
#   - Profile resolution is data-backed by pytorch_matrix.json
#   - Jetson path is explicit and not best-effort generic pip
#   - Verification is strict for requested acceleration mode
#   - Digest-verified wheel overrides prove those wheel artifacts only
#
# Runtime fallback note:
#   SmartTracker runtime CPU fallback is controlled by:
#   SMART_TRACKER_FALLBACK_TO_CPU in configs/config.yaml
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# Paths / Defaults
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
DEFAULT_MATRIX_FILE="$SCRIPT_DIR/pytorch_matrix.json"

TOTAL_STEPS=6

MATRIX_FILE="$DEFAULT_MATRIX_FILE"
MODE="auto"                     # auto|gpu|cpu
NON_INTERACTIVE=false
DRY_RUN=false
SKIP_PREREQS=false
REPORT_JSON=""
AUTO_CPU_FALLBACK=true
ACCEPT_EXISTING_VERIFIED=false
PROFILE_EXISTING_ONLY=false

# Manual override wheels (mainly for Jetson / air-gapped installs)
OVERRIDE_TORCH_WHEEL=""
OVERRIDE_TORCHVISION_WHEEL=""
OVERRIDE_TORCHAUDIO_WHEEL=""
OVERRIDE_TORCH_SHA256=""
OVERRIDE_TORCHVISION_SHA256=""
OVERRIDE_TORCHAUDIO_SHA256=""

# Runtime state / report fields
REPORT_STATUS="running"
REPORT_MESSAGE=""
REPORT_ERROR=""
VERIFY_JSON='{}'
MATRIX_SHA256=""
PYTORCH_INSTALL_COMMITTED=false

DETECTED_OS=""
DETECTED_ARCH=""
DETECTED_OS_DETAIL=""
DETECTED_PYTHON_VERSION=""
DETECTED_PYTHON_TAG=""
DETECTED_CUDA_VERSION="none"
DETECTED_CUDA_MAJOR=""
DETECTED_CUDA_MINOR=""
DETECTED_GPU_NAME="none"
HAS_NVIDIA_GPU=false
IS_JETSON=false
DETECTED_JETPACK_VERSION="unknown"
DETECTED_L4T_RELEASE="unknown"

PROFILE_KEY=""
PROFILE_SUPPORTED=0
PROFILE_DESCRIPTION=""
PROFILE_INSTALL_METHOD=""
PROFILE_INDEX_URL=""
PROFILE_TORCH_SPEC=""
PROFILE_TORCHVISION_SPEC=""
PROFILE_TORCHAUDIO_SPEC=""
PROFILE_WHEEL_TORCH=""
PROFILE_WHEEL_TORCHVISION=""
PROFILE_WHEEL_TORCHAUDIO=""
PROFILE_WHEEL_TORCH_SHA256=""
PROFILE_WHEEL_TORCHVISION_SHA256=""
PROFILE_WHEEL_TORCHAUDIO_SHA256=""
PROFILE_PYTHON_TAG=""
PROFILE_REQUIRE_CUDA=0
PROFILE_REQUIRE_MPS=0
PROFILE_MANUAL_HINT=""
PROFILE_APT_PACKAGES=""
PYTORCH_TEMP_DIRS=()

# ----------------------------------------------------------------------------
# Shared logging
# ----------------------------------------------------------------------------
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

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/setup-pytorch.sh [OPTIONS]

Matrix-driven PyTorch installer for PixEagle with platform-aware acceleration.

Exact versions selected from an index are not artifact-verified. Use
digest-pinned wheel overrides when direct wheel verification is required.

Options:
  --mode auto|gpu|cpu        Requested acceleration mode (default: auto)
  --cpu                      Alias for --mode cpu
  --non-interactive          No prompts (CI/automation mode)
  --no-auto-cpu-fallback     In non-interactive mode, fail instead of auto CPU fallback
  --accept-existing-verified Allow an unsupported profile only when the existing
                             venv passes its full runtime/accelerator checks
  --dry-run                  Resolve profile and print plan without changes
  --skip-prereqs             Skip system prerequisite installation
  --matrix-file <path>       Use custom matrix file (default: scripts/setup/pytorch_matrix.json)
  --report-json <path>       Write owner-only runtime/provenance evidence JSON

  --torch-wheel <path|url>        Override torch wheel (Jetson/manual mode)
  --torch-sha256 <digest>         Required SHA-256 for the torch override
  --torchvision-wheel <path|url>   Override torchvision wheel
  --torchvision-sha256 <digest>    Required SHA-256 for the torchvision override
  --torchaudio-wheel <path|url>    Override torchaudio wheel (optional)
  --torchaudio-sha256 <digest>     Required SHA-256 for a torchaudio override

  --help, -h                 Show this help

Examples:
  bash scripts/setup/setup-pytorch.sh
  bash scripts/setup/setup-pytorch.sh --mode gpu
  bash scripts/setup/setup-pytorch.sh --mode cpu --non-interactive
  bash scripts/setup/setup-pytorch.sh --mode auto --non-interactive
  bash scripts/setup/setup-pytorch.sh --dry-run
USAGE
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log_error "Required command not found: $cmd"
        return 1
    fi
}

sudo_run() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

run_cmd() {
    local description="$1"
    shift
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[dry-run] $description"
        log_detail "$*"
        return 0
    fi

    log_info "$description"
    "$@"
}

display_source() {
    python3 - "$1" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

value = sys.argv[1]
parsed = urlsplit(value)
if parsed.scheme in {"http", "https"}:
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    print(urlunsplit((parsed.scheme, host, parsed.path, "", "")))
else:
    print(value)
PY
}

ask_yes_no() {
    local prompt="$1"
    local default_yes="${2:-true}"

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ "$default_yes" == "true" ]]; then
            return 0
        else
            return 1
        fi
    fi

    local answer
    if [[ "$default_yes" == "true" ]]; then
        echo -en "${prompt} [Y/n]: "
    else
        echo -en "${prompt} [y/N]: "
    fi
    read -r answer

    if [[ -z "$answer" ]]; then
        [[ "$default_yes" == "true" ]]
        return
    fi

    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

fail() {
    REPORT_STATUS="failed"
    REPORT_ERROR="$1"
    log_error "$1"
    exit 1
}

write_report_json() {
    local exit_code="$1"

    [[ -n "$REPORT_JSON" ]] || return 0

    python3 - "$REPORT_JSON" "$exit_code" "$REPORT_STATUS" "$REPORT_MESSAGE" "$REPORT_ERROR" \
        "$MODE" "$PROFILE_KEY" "$PROFILE_DESCRIPTION" "$PROFILE_INSTALL_METHOD" \
        "$PROFILE_INDEX_URL" "$PROFILE_TORCH_SPEC" "$PROFILE_TORCHVISION_SPEC" \
        "$PROFILE_TORCHAUDIO_SPEC" \
        "${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}" \
        "${OVERRIDE_TORCH_SHA256:-$PROFILE_WHEEL_TORCH_SHA256}" \
        "${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}" \
        "${OVERRIDE_TORCHVISION_SHA256:-$PROFILE_WHEEL_TORCHVISION_SHA256}" \
        "${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}" \
        "${OVERRIDE_TORCHAUDIO_SHA256:-$PROFILE_WHEEL_TORCHAUDIO_SHA256}" \
        "$MATRIX_FILE" "$MATRIX_SHA256" \
        "$DETECTED_OS" "$DETECTED_ARCH" "$DETECTED_OS_DETAIL" \
        "$DETECTED_PYTHON_VERSION" "$DETECTED_PYTHON_TAG" \
        "$DETECTED_CUDA_VERSION" "$DETECTED_GPU_NAME" \
        "$IS_JETSON" "$DETECTED_JETPACK_VERSION" "$DETECTED_L4T_RELEASE" \
        "$DRY_RUN" "$PIXEAGLE_DIR" "$SCRIPT_DIR" \
        3<<<"$VERIFY_JSON" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

(
    report_path_raw,
    exit_code_raw,
    status,
    message,
    error,
    mode,
    profile_key,
    profile_description,
    install_method,
    index_url,
    torch_spec,
    vision_spec,
    audio_spec,
    torch_source,
    torch_sha256,
    vision_source,
    vision_sha256,
    audio_source,
    audio_sha256,
    matrix_file_raw,
    matrix_sha256,
    os_name,
    arch,
    os_detail,
    py_ver,
    py_tag,
    cuda_ver,
    gpu_name,
    is_jetson_raw,
    jetpack,
    l4t,
    dry_run_raw,
    root_raw,
    script_dir_raw,
) = sys.argv[1:]
verify_json_raw = os.fdopen(3, encoding="utf-8").read()
sys.path.insert(0, script_dir_raw)
from evidence_path import atomic_write_json


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitized_location(value):
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return str(Path(value).expanduser().resolve())


def source_evidence(value, digest):
    if not value:
        return None
    parsed = urlsplit(value)
    return {
        "kind": "url" if parsed.scheme in {"http", "https"} else "local_file",
        "location": sanitized_location(value),
        "expected_sha256": digest or None,
    }

try:
    verify = json.loads(verify_json_raw) if verify_json_raw else {}
except json.JSONDecodeError:
    verify = {"raw": verify_json_raw}

dry_run = dry_run_raw.lower() == "true"
wheel_artifacts = {
    "torch": source_evidence(torch_source, torch_sha256),
    "torchvision": source_evidence(vision_source, vision_sha256),
    "torchaudio": source_evidence(audio_source, audio_sha256),
}
verified_artifacts = []
if status == "success" and not dry_run and install_method == "wheels":
    for name in ("torch", "torchvision", "torchaudio"):
        artifact = wheel_artifacts[name]
        if artifact and artifact.get("expected_sha256"):
            verified_artifacts.append(
                {"name": name, "sha256": artifact["expected_sha256"]}
            )

root = Path(root_raw).resolve()
inputs = {}
for path in (Path(matrix_file_raw).expanduser().resolve(), root / "scripts/setup/setup-pytorch.sh"):
    if path.is_file():
        inputs[str(path)] = {"sha256": sha256_file(path), "size": path.stat().st_size}

payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "exit_code": int(exit_code_raw),
    "status": status,
    "message": message or None,
    "error": error or None,
    "requested_mode": mode,
    "selected_profile": {
        "key": profile_key,
        "description": profile_description,
        "install_method": install_method,
        "requested_versions": {
            "torch": torch_spec or None,
            "torchvision": vision_spec or None,
            "torchaudio": audio_spec or None,
        },
        "index_url": sanitized_location(index_url),
        "wheel_artifacts": wheel_artifacts,
    },
    "matrix": {
        "path": str(Path(matrix_file_raw).expanduser().resolve()),
        "sha256": matrix_sha256 or None,
    },
    "reproducibility": {
        "fully_reproducible": False,
        "verified_direct_artifacts": verified_artifacts,
        "selection_policy": (
            "direct wheels require SHA-256 verification"
            if install_method == "wheels"
            else "exact versions selected from an index without artifact hashes"
        ),
        "claim": (
            "Version constraints and installed-runtime fingerprints do not prove "
            "a fully reproducible environment or hash-lock transitive dependencies."
        ),
    },
    "detected": {
        "os": os_name,
        "arch": arch,
        "os_detail": os_detail,
        "python_version": py_ver,
        "python_tag": py_tag,
        "cuda_version": cuda_ver,
        "gpu_name": gpu_name,
        "is_jetson": is_jetson_raw.lower() == "true",
        "jetpack_version": jetpack,
        "l4t_release": l4t,
    },
    "inputs": inputs,
    "verification": verify,
}

atomic_write_json(report_path_raw, payload)
PY

    log_info "Wrote setup report: $REPORT_JSON"
}

on_exit() {
    local exit_code=$?
    local cleanup_failed=false
    trap - EXIT
    if [[ "$exit_code" -ne 0 && "$REPORT_STATUS" != "failed" ]]; then
        REPORT_STATUS="failed"
        REPORT_ERROR="${REPORT_ERROR:-installer exited with code $exit_code}"
    fi
    local temp_dir
    for temp_dir in "${PYTORCH_TEMP_DIRS[@]}"; do
        if [[ -L "$temp_dir" ]]; then
            if ! rm -f -- "$temp_dir"; then
                cleanup_failed=true
            fi
        elif [[ -d "$temp_dir" ]]; then
            if ! rm -rf --one-file-system -- "$temp_dir"; then
                cleanup_failed=true
            fi
        fi
    done
    if [[ "$cleanup_failed" == true ]]; then
        if [[ "$PYTORCH_INSTALL_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_cleanup_failed"
            REPORT_ERROR="verified PyTorch runtime was committed, but temporary-file cleanup failed"
            exit_code=75
        else
            REPORT_STATUS="failed"
            REPORT_ERROR="temporary-file cleanup failed before the PyTorch transaction committed"
            [[ "$exit_code" -ne 0 ]] || exit_code=1
        fi
        log_error "$REPORT_ERROR"
    fi
    if ! pixeagle_finalize_venv_transaction; then
        log_error "PyTorch failure rollback was incomplete"
        [[ "$exit_code" -ne 0 ]] || exit_code=1
    fi
    if ! write_report_json "$exit_code"; then
        if [[ "$PYTORCH_INSTALL_COMMITTED" == true ]]; then
            REPORT_STATUS="installed_evidence_failed"
            REPORT_ERROR="verified PyTorch runtime was committed, but evidence publication failed"
            log_error "$REPORT_ERROR: $REPORT_JSON"
            log_error "The installed runtime was retained; this failure does not mean rollback occurred"
            [[ "$exit_code" -eq 75 ]] || exit_code=74
        else
            log_error "Could not write requested PyTorch evidence: $REPORT_JSON"
            [[ "$exit_code" -ne 0 ]] || exit_code=1
        fi
    fi
    pixeagle_release_setup_lock
    exit "$exit_code"
}
trap on_exit EXIT

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mode)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --mode"
                MODE="${1,,}"
                ;;
            --cpu)
                MODE="cpu"
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                ;;
            --no-auto-cpu-fallback)
                AUTO_CPU_FALLBACK=false
                ;;
            --accept-existing-verified)
                ACCEPT_EXISTING_VERIFIED=true
                ;;
            --dry-run)
                DRY_RUN=true
                ;;
            --skip-prereqs)
                SKIP_PREREQS=true
                ;;
            --matrix-file)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --matrix-file"
                MATRIX_FILE="$1"
                ;;
            --report-json)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --report-json"
                REPORT_JSON="$1"
                ;;
            --torch-wheel)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torch-wheel"
                OVERRIDE_TORCH_WHEEL="$1"
                ;;
            --torch-sha256)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torch-sha256"
                OVERRIDE_TORCH_SHA256="${1,,}"
                ;;
            --torchvision-wheel)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchvision-wheel"
                OVERRIDE_TORCHVISION_WHEEL="$1"
                ;;
            --torchvision-sha256)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchvision-sha256"
                OVERRIDE_TORCHVISION_SHA256="${1,,}"
                ;;
            --torchaudio-wheel)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchaudio-wheel"
                OVERRIDE_TORCHAUDIO_WHEEL="$1"
                ;;
            --torchaudio-sha256)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchaudio-sha256"
                OVERRIDE_TORCHAUDIO_SHA256="${1,,}"
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                fail "Unknown option: $1"
                ;;
        esac
        shift
    done

    case "$MODE" in
        auto|gpu|cpu) ;;
        *) fail "Invalid --mode '$MODE'. Expected auto|gpu|cpu" ;;
    esac
}

check_prerequisites() {
    log_step 1 "Checking prerequisites"

    [[ -f "$MATRIX_FILE" && ! -L "$MATRIX_FILE" ]] \
        || fail "Matrix file must be a regular non-symlink file: $MATRIX_FILE"
    [[ "$(stat -Lc '%u:%h' -- "$MATRIX_FILE" 2>/dev/null || true)" == "$(id -u):1" ]] \
        || fail "Matrix file must be owner-controlled with one link: $MATRIX_FILE"
    [[ -d "$VENV_DIR" ]] || fail "Virtual environment not found: $VENV_DIR (run make init first)"
    [[ -f "$VENV_DIR/bin/python" ]] || fail "venv python not found: $VENV_DIR/bin/python"
    [[ -f "$VENV_DIR/bin/pip" ]] || fail "venv pip not found: $VENV_DIR/bin/pip"

    require_cmd python3 || fail "python3 is required"

    MATRIX_SHA256="$(python3 - "$MATRIX_FILE" <<'PY'
import hashlib
import pathlib
import sys

digest = hashlib.sha256()
with pathlib.Path(sys.argv[1]).open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"

    DETECTED_PYTHON_VERSION="$("$VENV_DIR/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    DETECTED_PYTHON_TAG="$("$VENV_DIR/bin/python" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"

    log_success "Matrix file: $MATRIX_FILE"
    log_detail "Matrix SHA-256: $MATRIX_SHA256"
    log_success "PixEagle venv: $VENV_DIR"
    log_success "Python: $DETECTED_PYTHON_VERSION ($DETECTED_PYTHON_TAG)"
}

extract_cuda_from_version_json() {
    local version_json="$1"
    python3 - "$version_json" <<'PY'
import json
import sys
p = sys.argv[1]
try:
    data = json.load(open(p, "r", encoding="utf-8"))
except Exception:
    print("none")
    sys.exit(0)

cuda = data.get("cuda", {})
v = cuda.get("version")
print(v if v else "none")
PY
}

detect_platform() {
    log_step 2 "Detecting platform"

    case "$(uname -s)" in
        Linux*) DETECTED_OS="Linux" ;;
        Darwin*) DETECTED_OS="macOS" ;;
        *) DETECTED_OS="Unknown" ;;
    esac

    DETECTED_ARCH="$(uname -m)"

    if [[ "$DETECTED_OS" == "Linux" && -f /etc/os-release ]]; then
        DETECTED_OS_DETAIL="$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)"
    elif [[ "$DETECTED_OS" == "macOS" ]]; then
        DETECTED_OS_DETAIL="$(sw_vers -productVersion 2>/dev/null || echo "unknown")"
    else
        DETECTED_OS_DETAIL="unknown"
    fi

    IS_JETSON=false
    if [[ "$DETECTED_OS" == "Linux" ]]; then
        if [[ -f /proc/device-tree/model ]] && tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi jetson; then
            IS_JETSON=true
        elif command -v dpkg-query >/dev/null 2>&1 && dpkg-query -W -f='${Status}' nvidia-l4t-core 2>/dev/null | grep -q "install ok installed"; then
            IS_JETSON=true
        elif [[ -f /etc/nv_tegra_release ]]; then
            IS_JETSON=true
        fi
    fi

    DETECTED_JETPACK_VERSION="unknown"
    if [[ "$IS_JETSON" == "true" ]] && command -v dpkg-query >/dev/null 2>&1; then
        local jp
        jp="$(dpkg-query -W -f='${Version}' nvidia-jetpack 2>/dev/null || true)"
        if [[ -n "$jp" ]]; then
            DETECTED_JETPACK_VERSION="${jp%%+*}"
        fi
    fi

    DETECTED_L4T_RELEASE="unknown"
    if [[ "$IS_JETSON" == "true" ]] && [[ -f /etc/nv_tegra_release ]]; then
        DETECTED_L4T_RELEASE="$(sed -n '1p' /etc/nv_tegra_release | sed 's/^# //')"
    fi

    HAS_NVIDIA_GPU=false
    DETECTED_GPU_NAME="none"
    if [[ "$DETECTED_OS" == "Linux" ]] && command -v nvidia-smi >/dev/null 2>&1; then
        local gpu
        gpu="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
        if [[ -n "$gpu" ]]; then
            HAS_NVIDIA_GPU=true
            DETECTED_GPU_NAME="$gpu"
        fi
    elif [[ "$IS_JETSON" == "true" ]]; then
        HAS_NVIDIA_GPU=true
        DETECTED_GPU_NAME="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo "NVIDIA Jetson")"
    fi

    DETECTED_CUDA_VERSION="none"
    if [[ "$DETECTED_OS" == "Linux" ]] && command -v nvidia-smi >/dev/null 2>&1; then
        local smi_cuda
        smi_cuda="$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([0-9]\+\.[0-9]\+\).*/\1/p' | head -1 || true)"
        if [[ -n "$smi_cuda" ]]; then
            DETECTED_CUDA_VERSION="$smi_cuda"
        fi
    fi

    if [[ "$DETECTED_CUDA_VERSION" == "none" ]] && command -v nvcc >/dev/null 2>&1; then
        local nvcc_cuda
        nvcc_cuda="$(nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9]\+\.[0-9]\+\).*/\1/p' | head -1 || true)"
        if [[ -n "$nvcc_cuda" ]]; then
            DETECTED_CUDA_VERSION="$nvcc_cuda"
        fi
    fi

    if [[ "$DETECTED_CUDA_VERSION" == "none" ]] && [[ -f /usr/local/cuda/version.json ]]; then
        local json_cuda
        json_cuda="$(extract_cuda_from_version_json /usr/local/cuda/version.json || echo "none")"
        if [[ -n "$json_cuda" && "$json_cuda" != "none" ]]; then
            DETECTED_CUDA_VERSION="$json_cuda"
        fi
    fi

    if [[ "$DETECTED_CUDA_VERSION" == "none" ]] && [[ -f /usr/local/cuda/version.txt ]]; then
        local txt_cuda
        txt_cuda="$(grep -oE '[0-9]+\.[0-9]+' /usr/local/cuda/version.txt | head -1 || true)"
        if [[ -n "$txt_cuda" ]]; then
            DETECTED_CUDA_VERSION="$txt_cuda"
        fi
    fi

    if [[ "$DETECTED_CUDA_VERSION" != "none" ]]; then
        DETECTED_CUDA_MAJOR="${DETECTED_CUDA_VERSION%%.*}"
        DETECTED_CUDA_MINOR="${DETECTED_CUDA_VERSION#*.}"
        DETECTED_CUDA_MINOR="${DETECTED_CUDA_MINOR%%.*}"
    else
        DETECTED_CUDA_MAJOR=""
        DETECTED_CUDA_MINOR=""
    fi

    log_success "OS: $DETECTED_OS ($DETECTED_OS_DETAIL)"
    log_success "Arch: $DETECTED_ARCH"
    log_success "GPU: $DETECTED_GPU_NAME"
    log_success "CUDA: $DETECTED_CUDA_VERSION"
    if [[ "$IS_JETSON" == "true" ]]; then
        log_success "Jetson: yes (JetPack=$DETECTED_JETPACK_VERSION)"
        log_detail "L4T: $DETECTED_L4T_RELEASE"
    fi
}

resolve_profile_key() {
    log_step 3 "Resolving install profile"

    local jetpack_mm=""
    if [[ "$DETECTED_JETPACK_VERSION" != "unknown" ]]; then
        jetpack_mm="$(echo "$DETECTED_JETPACK_VERSION" | cut -d. -f1-2)"
    fi

    if [[ "$MODE" == "cpu" ]]; then
        if [[ "$DETECTED_OS" == "macOS" && "$DETECTED_ARCH" == "arm64" ]]; then
            PROFILE_KEY="macos_arm64_cpu"
        elif [[ "$DETECTED_OS" == "macOS" ]]; then
            PROFILE_KEY="macos_x86_cpu"
        else
            PROFILE_KEY="linux_cpu"
        fi
        return 0
    fi

    if [[ "$DETECTED_OS" == "macOS" && "$DETECTED_ARCH" == "arm64" ]]; then
        PROFILE_KEY="macos_arm64_mps"
        return 0
    fi

    if [[ "$DETECTED_OS" == "Linux" && "$IS_JETSON" == "true" ]]; then
        if [[ "$jetpack_mm" == "6.2" ]]; then
            PROFILE_KEY="jetson_jp62"
            return 0
        fi
        if [[ "$jetpack_mm" == "6.1" ]]; then
            PROFILE_KEY="jetson_jp61"
            return 0
        fi

        fail "Unsupported Jetson JetPack version '$DETECTED_JETPACK_VERSION'. Use --mode cpu or provide wheel overrides."
    fi

    if [[ "$DETECTED_OS" == "Linux" && "$DETECTED_ARCH" == "x86_64" ]]; then
        if [[ "$HAS_NVIDIA_GPU" != "true" || "$DETECTED_CUDA_VERSION" == "none" ]]; then
            if [[ "$MODE" == "gpu" ]]; then
                fail "GPU mode requested but CUDA GPU was not detected on this host."
            fi
            PROFILE_KEY="linux_cpu"
            return 0
        fi

        if [[ "$DETECTED_CUDA_MAJOR" -ge 12 ]]; then
            PROFILE_KEY="linux_x86_cuda12"
            return 0
        fi

        if [[ "$DETECTED_CUDA_MAJOR" -eq 11 ]]; then
            PROFILE_KEY="linux_x86_cuda11"
            return 0
        fi

        fail "Detected CUDA $DETECTED_CUDA_VERSION is not mapped in matrix. Use --mode cpu or update matrix."
    fi

    # Fallback
    PROFILE_KEY="linux_cpu"
}

load_profile_from_matrix() {
    local -a values=()

    mapfile -d '' -t values < <(python3 - "$MATRIX_FILE" "$PROFILE_KEY" "$MATRIX_SHA256" <<'PY'
import hashlib
import json
import sys

matrix_path = sys.argv[1]
profile_key = sys.argv[2]
expected_sha256 = sys.argv[3]

with open(matrix_path, "rb") as f:
    matrix_bytes = f.read()
if expected_sha256 and hashlib.sha256(matrix_bytes).hexdigest() != expected_sha256:
    raise SystemExit("matrix changed after prerequisite validation")
data = json.loads(matrix_bytes.decode("utf-8"))

profile = data.get("profiles", {}).get(profile_key)
if profile is None:
    values = ("1",) + ("",) * 18
    sys.stdout.buffer.write(b"\0".join(value.encode("utf-8") for value in values) + b"\0")
    raise SystemExit(0)

packages = profile.get("packages", {})
wheels = profile.get("wheels", {})
wheel_sha256 = profile.get("wheel_sha256", {})
verify = profile.get("verify", {})
prereqs = profile.get("prereqs", {})


values = (
    "0",
    "1" if profile.get("supported", True) else "0",
    str(profile.get("description", "")),
    str(profile.get("install_method", "")),
    str(profile.get("index_url", "")),
    str(packages.get("torch", "")),
    str(packages.get("torchvision", "")),
    str(packages.get("torchaudio", "")),
    str(wheels.get("torch", "")),
    str(wheels.get("torchvision", "")),
    str(wheels.get("torchaudio", "")),
    str(wheel_sha256.get("torch", "")),
    str(wheel_sha256.get("torchvision", "")),
    str(wheel_sha256.get("torchaudio", "")),
    str(profile.get("python_tag", "")),
    "1" if verify.get("require_cuda", False) else "0",
    "1" if verify.get("require_mps", False) else "0",
    str(profile.get("manual_hint", "")),
    " ".join(str(value) for value in prereqs.get("apt_packages", [])),
)
if any("\0" in value for value in values):
    raise SystemExit("matrix profile contains a NUL byte")
sys.stdout.buffer.write(b"\0".join(value.encode("utf-8") for value in values) + b"\0")
PY
    )

    if [[ "${#values[@]}" -ne 19 ]]; then
        fail "Failed to parse matrix profile '$PROFILE_KEY' from $MATRIX_FILE"
    fi

    __ERROR__="${values[0]}"
    PROFILE_SUPPORTED="${values[1]}"
    PROFILE_DESCRIPTION="${values[2]}"
    PROFILE_INSTALL_METHOD="${values[3]}"
    PROFILE_INDEX_URL="${values[4]}"
    PROFILE_TORCH_SPEC="${values[5]}"
    PROFILE_TORCHVISION_SPEC="${values[6]}"
    PROFILE_TORCHAUDIO_SPEC="${values[7]}"
    PROFILE_WHEEL_TORCH="${values[8]}"
    PROFILE_WHEEL_TORCHVISION="${values[9]}"
    PROFILE_WHEEL_TORCHAUDIO="${values[10]}"
    PROFILE_WHEEL_TORCH_SHA256="${values[11]}"
    PROFILE_WHEEL_TORCHVISION_SHA256="${values[12]}"
    PROFILE_WHEEL_TORCHAUDIO_SHA256="${values[13]}"
    PROFILE_PYTHON_TAG="${values[14]}"
    PROFILE_REQUIRE_CUDA="${values[15]}"
    PROFILE_REQUIRE_MPS="${values[16]}"
    PROFILE_MANUAL_HINT="${values[17]}"
    PROFILE_APT_PACKAGES="${values[18]}"

    validate_profile_contract

    if [[ "$__ERROR__" -ne 0 ]]; then
        fail "Profile '$PROFILE_KEY' not found in matrix: $MATRIX_FILE"
    fi

    if [[ "$PROFILE_SUPPORTED" -ne 1 ]]; then
        if [[ "$PROFILE_INSTALL_METHOD" == "wheels" \
            && -n "$OVERRIDE_TORCH_WHEEL" && -n "$OVERRIDE_TORCH_SHA256" \
            && -n "$OVERRIDE_TORCHVISION_WHEEL" && -n "$OVERRIDE_TORCHVISION_SHA256" ]]; then
            log_warn "Using operator-supplied, digest-verified wheels for unsupported profile '$PROFILE_KEY'"
        elif [[ "$ACCEPT_EXISTING_VERIFIED" == true ]]; then
            PROFILE_EXISTING_ONLY=true
            log_warn "Unsupported profile is verification-only; no package installation is allowed"
        else
            fail "Profile '$PROFILE_KEY' is currently marked unsupported. ${PROFILE_MANUAL_HINT}"
        fi
    fi

    log_success "Resolved profile: $PROFILE_KEY"
    log_detail "$PROFILE_DESCRIPTION"
}

validate_profile_contract() {
    [[ "$PROFILE_SUPPORTED" =~ ^[01]$ ]] || fail "Matrix supported flag must be boolean"
    [[ "$PROFILE_REQUIRE_CUDA" =~ ^[01]$ ]] || fail "Matrix require_cuda flag must be boolean"
    [[ "$PROFILE_REQUIRE_MPS" =~ ^[01]$ ]] || fail "Matrix require_mps flag must be boolean"
    case "$PROFILE_INSTALL_METHOD" in
        index|pypi|wheels) ;;
        *) fail "Matrix install_method must be index, pypi, or wheels" ;;
    esac

    local version
    for version in "$PROFILE_TORCH_SPEC" "$PROFILE_TORCHVISION_SPEC" "$PROFILE_TORCHAUDIO_SPEC"; do
        [[ -z "$version" || "$version" =~ ^[0-9][A-Za-z0-9.+_-]*$ ]] \
            || fail "Matrix package version contains unsupported syntax: $version"
    done

    if [[ -n "$PROFILE_INDEX_URL" ]]; then
        python3 - "$PROFILE_INDEX_URL" <<'PY' || fail "Matrix index_url must be credential-free HTTPS"
import sys
from urllib.parse import urlsplit

parsed = urlsplit(sys.argv[1])
valid = (
    parsed.scheme == "https"
    and bool(parsed.hostname)
    and parsed.username is None
    and parsed.password is None
    and not parsed.query
    and not parsed.fragment
)
raise SystemExit(0 if valid else 1)
PY
    fi

    if [[ -n "$PROFILE_APT_PACKAGES" ]]; then
        [[ "$(realpath -e -- "$MATRIX_FILE" 2>/dev/null || true)" == \
           "$(realpath -e -- "$DEFAULT_MATRIX_FILE" 2>/dev/null || true)" ]] \
            || fail "Custom matrices may not request privileged apt packages"
        local package
        local -a apt_packages=()
        read -r -a apt_packages <<<"$PROFILE_APT_PACKAGES"
        for package in "${apt_packages[@]}"; do
            [[ "$package" =~ ^[a-z0-9][a-z0-9+.-]*$ ]] \
                || fail "Matrix apt package contains unsupported syntax: $package"
        done
    fi
}

print_plan() {
    echo ""
    echo -e "${CYAN}======================================================================${NC}"
    echo -e "${BOLD}PyTorch Install Plan${NC}"
    echo -e "${CYAN}======================================================================${NC}"
    echo "Requested mode:     $MODE"
    echo "Resolved profile:   $PROFILE_KEY"
    echo "Description:        $PROFILE_DESCRIPTION"
    echo "Install method:     $PROFILE_INSTALL_METHOD"
    if [[ -n "$PROFILE_INDEX_URL" ]]; then
        echo "Index URL:          $(display_source "$PROFILE_INDEX_URL")"
    fi
    if [[ -n "$PROFILE_TORCH_SPEC" ]]; then
        echo "Torch spec:         torch==$PROFILE_TORCH_SPEC"
    fi
    if [[ -n "$PROFILE_TORCHVISION_SPEC" ]]; then
        echo "Torchvision spec:   torchvision==$PROFILE_TORCHVISION_SPEC"
    fi
    if [[ -n "$PROFILE_TORCHAUDIO_SPEC" ]]; then
        echo "Torchaudio spec:    torchaudio==$PROFILE_TORCHAUDIO_SPEC"
    fi
    if [[ -n "${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}" \
        || -n "${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}" ]]; then
        echo "Wheel torch:        $(display_source "${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}")"
        echo "Torch SHA-256:      ${OVERRIDE_TORCH_SHA256:-$PROFILE_WHEEL_TORCH_SHA256}"
        echo "Wheel torchvision:  $(display_source "${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}")"
        echo "Vision SHA-256:     ${OVERRIDE_TORCHVISION_SHA256:-$PROFILE_WHEEL_TORCHVISION_SHA256}"
        if [[ -n "${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}" ]]; then
            echo "Wheel torchaudio:   $(display_source "${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}")"
            echo "Audio SHA-256:      ${OVERRIDE_TORCHAUDIO_SHA256:-$PROFILE_WHEEL_TORCHAUDIO_SHA256}"
        fi
    fi
    if [[ "$PROFILE_INSTALL_METHOD" == "wheels" ]]; then
        echo "Artifact policy:    Direct wheels require SHA-256 verification"
    else
        echo "Artifact policy:    Version-constrained index resolution (not hash-locked)"
    fi
    if [[ "$PROFILE_REQUIRE_CUDA" -eq 1 ]]; then
        echo "Verify target:      CUDA must be available"
    elif [[ "$PROFILE_REQUIRE_MPS" -eq 1 ]]; then
        echo "Verify target:      MPS must be available"
    else
        echo "Verify target:      CPU-only install valid"
    fi
    echo -e "${CYAN}======================================================================${NC}"
    echo ""
}

ensure_sudo_if_needed() {
    if [[ "$DRY_RUN" == "true" || "$SKIP_PREREQS" == "true" ]]; then
        return 0
    fi

    if [[ -z "$PROFILE_APT_PACKAGES" ]]; then
        return 0
    fi

    if [[ "$EUID" -ne 0 ]]; then
        log_info "Sudo access required for prerequisite packages"
        sudo -v || fail "Failed to obtain sudo privileges"
    fi
}

install_prerequisites() {
    log_step 4 "Installing system prerequisites"

    if [[ "$SKIP_PREREQS" == "true" ]]; then
        log_warn "Skipping prerequisites (--skip-prereqs enabled)"
        return 0
    fi

    if [[ "$DETECTED_OS" != "Linux" ]]; then
        log_info "No Linux apt prerequisites required for $DETECTED_OS"
        return 0
    fi

    if [[ -n "$PROFILE_APT_PACKAGES" ]]; then
        local -a apt_pkgs=()
        read -r -a apt_pkgs <<<"$PROFILE_APT_PACKAGES"
        if [[ ${#apt_pkgs[@]} -gt 0 ]]; then
            run_cmd "Updating apt package lists" sudo_run apt-get update
            run_cmd "Installing apt prerequisites" sudo_run apt-get install -y "${apt_pkgs[@]}"
        fi
    else
        log_success "No extra system prerequisites required"
    fi
}

validate_sha256() {
    [[ "$1" =~ ^[0-9a-fA-F]{64}$ ]]
}

verify_file_sha256() {
    local path="$1"
    local expected="${2,,}"
    validate_sha256 "$expected" || return 1
    python3 - "$path" "$expected" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
digest = hashlib.sha256()
with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
raise SystemExit(0 if digest.hexdigest() == expected else 1)
PY
}

resolve_wheel_source() {
    local source_value="$1"
    local expected_sha256="${2,,}"
    local destination_dir="$3"
    local out_var="$4"
    local resolved_path=""

    if [[ -z "$source_value" ]]; then
        [[ -z "$expected_sha256" ]] || fail "Wheel SHA-256 was supplied without a wheel source"
        printf -v "$out_var" '%s' ""
        return 0
    fi

    validate_sha256 "$expected_sha256" \
        || fail "Wheel source requires a valid SHA-256 digest: $source_value"

    mkdir -p -- "$destination_dir" || return 1
    chmod 0700 -- "$destination_dir" || return 1
    local filename source_path
    if [[ -f "$source_value" ]]; then
        filename="$(basename "$source_value")"
        source_path="$source_value"
    elif [[ "$source_value" =~ ^https:// ]]; then
        filename="$(basename "${source_value%%[?#]*}")"
        source_path=""
    else
        fail "Wheel source must be a local file or HTTPS URL: $source_value"
    fi
    [[ "$filename" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*\.whl$ ]] \
        || fail "Wheel source has an unsafe or non-wheel filename: $filename"
    local target_path="$destination_dir/$filename"

    if [[ "$DRY_RUN" == "true" ]]; then
        [[ -n "$source_path" ]] || log_info "[dry-run] Would download wheel: $source_value"
        printf -v "$out_var" '%s' "$target_path"
        return 0
    fi

    local partial_path
    partial_path="$(mktemp "$destination_dir/.${filename}.partial.XXXXXX")" || return 1
    if [[ -n "$source_path" ]]; then
        cp -- "$source_path" "$partial_path" || { rm -f -- "$partial_path"; return 1; }
    else
        [[ -n "$filename" && "$filename" != "." && "$filename" != "/" ]] \
            || fail "Unable to derive wheel filename from URL: $source_value"
        if command -v curl >/dev/null 2>&1; then
            run_cmd "Downloading wheel: $filename" curl -fsSL "$source_value" -o "$partial_path" \
                || { rm -f "$partial_path"; return 1; }
        elif command -v wget >/dev/null 2>&1; then
            run_cmd "Downloading wheel: $filename" wget -qO "$partial_path" "$source_value" \
                || { rm -f "$partial_path"; return 1; }
        else
            rm -f "$partial_path"
            fail "Neither curl nor wget is available to download wheel: $source_value"
        fi
    fi
    chmod 0600 -- "$partial_path"
    if ! verify_file_sha256 "$partial_path" "$expected_sha256"; then
        rm -f -- "$partial_path"
        fail "Wheel SHA-256 verification failed: $source_value"
    fi
    mv -- "$partial_path" "$target_path"
    resolved_path="$target_path"
    printf -v "$out_var" '%s' "$resolved_path"
}

install_python_stack() {
    log_step 5 "Installing PyTorch packages"

    local pip="$VENV_DIR/bin/pip"

    run_cmd "Upgrading pip tooling" "$pip" install --upgrade pip setuptools wheel || return 1

    case "$PROFILE_INSTALL_METHOD" in
        index)
            local pkgs=()
            [[ -n "$PROFILE_TORCH_SPEC" ]] && pkgs+=("torch==$PROFILE_TORCH_SPEC")
            [[ -n "$PROFILE_TORCHVISION_SPEC" ]] && pkgs+=("torchvision==$PROFILE_TORCHVISION_SPEC")
            [[ -n "$PROFILE_TORCHAUDIO_SPEC" ]] && pkgs+=("torchaudio==$PROFILE_TORCHAUDIO_SPEC")

            [[ ${#pkgs[@]} -gt 0 ]] || fail "No package specs defined for profile $PROFILE_KEY"

            if [[ -n "$PROFILE_INDEX_URL" ]]; then
                run_cmd "Installing version-constrained torch stack from custom index" "$pip" install --upgrade --no-cache-dir --index-url "$PROFILE_INDEX_URL" "${pkgs[@]}" || return 1
            else
                run_cmd "Installing version-constrained torch stack from default PyPI" "$pip" install --upgrade --no-cache-dir "${pkgs[@]}" || return 1
            fi
            ;;

        pypi)
            local pypi_pkgs=()
            [[ -n "$PROFILE_TORCH_SPEC" ]] && pypi_pkgs+=("torch==$PROFILE_TORCH_SPEC")
            [[ -n "$PROFILE_TORCHVISION_SPEC" ]] && pypi_pkgs+=("torchvision==$PROFILE_TORCHVISION_SPEC")
            [[ -n "$PROFILE_TORCHAUDIO_SPEC" ]] && pypi_pkgs+=("torchaudio==$PROFILE_TORCHAUDIO_SPEC")

            [[ ${#pypi_pkgs[@]} -gt 0 ]] || fail "No package specs defined for profile $PROFILE_KEY"
            run_cmd "Installing version-constrained torch stack from PyPI" "$pip" install --upgrade --no-cache-dir "${pypi_pkgs[@]}" || return 1
            ;;

        wheels)
            local torch_source="${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}"
            local torchvision_source="${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}"
            local torchaudio_source="${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}"
            local torch_sha256="${OVERRIDE_TORCH_SHA256:-$PROFILE_WHEEL_TORCH_SHA256}"
            local torchvision_sha256="${OVERRIDE_TORCHVISION_SHA256:-$PROFILE_WHEEL_TORCHVISION_SHA256}"
            local torchaudio_sha256="${OVERRIDE_TORCHAUDIO_SHA256:-$PROFILE_WHEEL_TORCHAUDIO_SHA256}"
            local wheel_tmp
            wheel_tmp="$(mktemp -d "/var/tmp/pixeagle-pytorch-wheels.XXXXXX")" || return 1
            chmod 0700 -- "$wheel_tmp"
            PYTORCH_TEMP_DIRS+=("$wheel_tmp")

            [[ -n "$torch_source" ]] || fail "Torch wheel is required for profile $PROFILE_KEY"
            [[ -n "$torchvision_source" ]] || fail "Torchvision wheel is required for profile $PROFILE_KEY"

            if [[ -n "$PROFILE_PYTHON_TAG" && "$DETECTED_PYTHON_TAG" != "$PROFILE_PYTHON_TAG" ]]; then
                fail "Python ABI mismatch: profile requires $PROFILE_PYTHON_TAG but venv is $DETECTED_PYTHON_TAG"
            fi

            local torch_wheel=""
            local torchvision_wheel=""
            local torchaudio_wheel=""

            resolve_wheel_source "$torch_source" "$torch_sha256" "$wheel_tmp" torch_wheel || return 1
            resolve_wheel_source "$torchvision_source" "$torchvision_sha256" "$wheel_tmp" torchvision_wheel || return 1
            resolve_wheel_source "$torchaudio_source" "$torchaudio_sha256" "$wheel_tmp" torchaudio_wheel || return 1

            local -a wheel_packages=("$torch_wheel" "$torchvision_wheel")
            if [[ -n "$torchaudio_wheel" ]]; then
                wheel_packages+=("$torchaudio_wheel")
            else
                log_warn "No torchaudio wheel configured for this profile (continuing)"
            fi
            run_cmd "Installing digest-verified PyTorch wheels" \
                "$pip" install --upgrade --no-cache-dir "${wheel_packages[@]}" || return 1
            ;;

        *)
            fail "Unknown install method '$PROFILE_INSTALL_METHOD' for profile $PROFILE_KEY"
            ;;
    esac
}

parse_verification_payload() {
    local raw="$1"
    local need_cuda="$2"
    local need_mps="$3"
    local -a values=()

    mapfile -d '' -t values < <(python3 - "$raw" "$need_cuda" "$need_mps" <<'PY'
import json
import sys

raw = sys.argv[1]
need_cuda = int(sys.argv[2])
need_mps = int(sys.argv[3])

try:
    data = json.loads(raw)
except Exception as exc:
    data = {}
    ok = False
    reason = f"invalid verification payload: {exc}"
else:
    ok = bool(data.get("torch_ok")) and bool(data.get("torchvision_ok"))
    reason = ""
    if not data.get("torch_ok"):
        ok = False
        reason = "torch import failed"
    elif not data.get("torchvision_ok"):
        ok = False
        reason = "torchvision import failed"
    elif data.get("compatibility_errors"):
        ok = False
        reason = "; ".join(str(item) for item in data["compatibility_errors"])
    elif need_cuda and not data.get("cuda_available"):
        ok = False
        reason = "CUDA not available in installed torch build"
    elif need_cuda and not data.get("cuda_tensor_ok"):
        ok = False
        reason = "CUDA device test failed"
    elif need_mps and not data.get("mps_available"):
        ok = False
        reason = "MPS not available in installed torch build"
    if not reason and data.get("error"):
        reason = str(data.get("error"))

values = (
    "1" if ok else "0",
    reason,
    str(data.get("torch_version") or ""),
    str(data.get("torchvision_version") or ""),
    str(data.get("torchaudio_version") or ""),
    "1" if data.get("cuda_available") else "0",
    str(data.get("cuda_device_name") or ""),
    "1" if data.get("mps_available") else "0",
    "1" if data.get("torchaudio_ok") else "0",
)
sys.stdout.buffer.write(b"\0".join(value.encode("utf-8") for value in values) + b"\0")
PY
    )

    if [[ "${#values[@]}" -ne 9 ]]; then
        log_error "Verification failed: parser returned an incomplete payload"
        return 1
    fi

    OK="${values[0]}"
    REASON="${values[1]}"
    TORCH_VERSION="${values[2]}"
    TORCHVISION_VERSION="${values[3]}"
    TORCHAUDIO_VERSION="${values[4]}"
    CUDA_AVAILABLE="${values[5]}"
    CUDA_DEVICE="${values[6]}"
    MPS_AVAILABLE="${values[7]}"
    TORCHAUDIO_OK="${values[8]}"
}

verify_installation() {
    log_step 6 "Verifying installation"

    local output
    if ! output="$("$VENV_DIR/bin/python" - \
        "$PROFILE_TORCH_SPEC" "$PROFILE_TORCHVISION_SPEC" "$PROFILE_TORCHAUDIO_SPEC" <<'PY'
import hashlib
import importlib.metadata as md
import json
import sys
from pathlib import Path

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

expected_torch, expected_vision, expected_audio = sys.argv[1:4]


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
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return None
    dist_path = Path(getattr(dist, "_path", ""))
    evidence = {"version": dist.version}
    for filename in ("METADATA", "RECORD", "direct_url.json"):
        candidate = dist_path / filename
        if candidate.is_file():
            evidence[filename.lower().replace(".", "_") + "_sha256"] = sha256_file(
                candidate
            )
    return evidence


def public_version(value):
    return str(value or "").split("+", 1)[0]


def check_expected(name, actual, expected, errors):
    if expected and public_version(actual) != public_version(expected):
        errors.append(f"{name} {actual} does not match profile version {expected}")


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

result = {
    "torch_ok": False,
    "torchvision_ok": False,
    "torchaudio_ok": False,
    "torch_version": None,
    "torchvision_version": None,
    "torchaudio_version": None,
    "torch_cuda_version": None,
    "cuda_available": False,
    "cuda_tensor_ok": False,
    "cuda_device_name": None,
    "mps_available": False,
    "compatibility_errors": [],
    "distributions": {},
    "fingerprinted_files": [],
    "fingerprint_scope": "distribution metadata/RECORD plus imported entry points",
    "error": None,
}

torch = None
torchvision = None
torchaudio = None
try:
    import torch
    result["torch_ok"] = True
    result["torch_version"] = getattr(torch, "__version__", None)
    result["torch_cuda_version"] = getattr(getattr(torch, "version", None), "cuda", None)
    result["cuda_available"] = bool(torch.cuda.is_available())

    if result["cuda_available"]:
        try:
            x = torch.rand((2, 2), device="cuda")
            result["cuda_tensor_ok"] = bool(getattr(x, "is_cuda", False))
            result["cuda_device_name"] = torch.cuda.get_device_name(0)
        except Exception as e:
            result["cuda_tensor_ok"] = False
            result["error"] = f"CUDA tensor test failed: {e}"

    try:
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is not None:
            result["mps_available"] = bool(mps_backend.is_available())
    except Exception:
        result["mps_available"] = False

except Exception as e:
    result["error"] = f"torch import failed: {e}"

try:
    import torchvision
    result["torchvision_ok"] = True
    result["torchvision_version"] = getattr(torchvision, "__version__", None)
except Exception as e:
    if not result["error"]:
        result["error"] = f"torchvision import failed: {e}"

try:
    import torchaudio
    result["torchaudio_ok"] = True
    result["torchaudio_version"] = getattr(torchaudio, "__version__", None)
except Exception:
    # torchaudio may legitimately be absent on some Jetson combinations
    result["torchaudio_ok"] = False

for name in ("torch", "torchvision", "torchaudio"):
    evidence = distribution_evidence(name)
    result["distributions"][name] = evidence

torch_metadata = result["distributions"].get("torch")
vision_metadata = result["distributions"].get("torchvision")
audio_metadata = result["distributions"].get("torchaudio")
if result["torch_ok"] and not torch_metadata:
    result["compatibility_errors"].append("torch distribution metadata is missing")
if result["torchvision_ok"] and not vision_metadata:
    result["compatibility_errors"].append(
        "torchvision distribution metadata is missing"
    )
if torch_metadata:
    check_expected(
        "torch", torch_metadata["version"], expected_torch, result["compatibility_errors"]
    )
if vision_metadata:
    check_expected(
        "torchvision",
        vision_metadata["version"],
        expected_vision,
        result["compatibility_errors"],
    )
if audio_metadata and result["torchaudio_ok"]:
    check_expected(
        "torchaudio",
        audio_metadata["version"],
        expected_audio,
        result["compatibility_errors"],
    )
if torch_metadata and vision_metadata:
    check_dependency(
        "torchvision",
        "torch",
        torch_metadata["version"],
        result["compatibility_errors"],
    )
if torch_metadata and audio_metadata:
    check_dependency(
        "torchaudio",
        "torch",
        torch_metadata["version"],
        result["compatibility_errors"],
    )

venv_path = Path(sys.prefix).resolve()
for name, module, metadata in (
    ("torch", torch, torch_metadata),
    ("torchvision", torchvision, vision_metadata),
):
    if module is None:
        continue
    module_path = Path(module.__file__).resolve()
    if not module_path.is_relative_to(venv_path):
        result["compatibility_errors"].append(
            f"{name} module is outside the selected virtual environment: {module_path}"
        )
    if metadata and public_version(module.__version__) != public_version(
        metadata["version"]
    ):
        result["compatibility_errors"].append(
            f"{name} import version {module.__version__} does not match "
            f"installed metadata {metadata['version']}"
        )

files = []
if torch is not None:
    files.extend((Path(torch.__file__).resolve(), Path(torch._C.__file__).resolve()))
if torchvision is not None:
    vision_root = Path(torchvision.__file__).resolve().parent
    files.append(Path(torchvision.__file__).resolve())
    files.extend(sorted(path.resolve() for path in vision_root.glob("_C.*")))
if torchaudio is not None:
    files.append(Path(torchaudio.__file__).resolve())
seen = set()
for path in files:
    if path.is_file() and path not in seen:
        seen.add(path)
        result["fingerprinted_files"].append(file_evidence(path))

print(json.dumps(result))
PY
)"; then
        log_error "Verification failed: could not execute runtime verification Python snippet"
        return 1
    fi

    VERIFY_JSON="$output"

    if ! parse_verification_payload \
        "$output" "$PROFILE_REQUIRE_CUDA" "$PROFILE_REQUIRE_MPS"; then
        log_error "Verification failed: could not parse runtime verification output"
        return 1
    fi

    log_success "torch: ${TORCH_VERSION:-unknown}"
    log_success "torchvision: ${TORCHVISION_VERSION:-unknown}"

    if [[ "$TORCHAUDIO_OK" -eq 1 ]]; then
        log_success "torchaudio: ${TORCHAUDIO_VERSION:-unknown}"
    else
        log_warn "torchaudio not available (optional for SmartTracker)"
    fi

    if [[ "$CUDA_AVAILABLE" -eq 1 ]]; then
        log_success "CUDA available: yes"
        [[ -n "${CUDA_DEVICE:-}" ]] && log_detail "CUDA device: ${CUDA_DEVICE}"
    else
        log_info "CUDA available: no"
    fi

    if [[ "$MPS_AVAILABLE" -eq 1 ]]; then
        log_success "MPS available: yes"
    fi

    if [[ "$OK" -ne 1 ]]; then
        log_error "Verification failed: ${REASON:-unknown reason}"
        return 1
    fi

    return 0
}

cpu_profile_for_host() {
    if [[ "$DETECTED_OS" == "macOS" && "$DETECTED_ARCH" == "arm64" ]]; then
        echo "macos_arm64_cpu"
    elif [[ "$DETECTED_OS" == "macOS" ]]; then
        echo "macos_x86_cpu"
    else
        echo "linux_cpu"
    fi
}

handle_acceleration_failure() {
    local fail_reason="$1"

    REPORT_STATUS="failed"
    REPORT_ERROR="$fail_reason"

    log_warn "Requested accelerated install did not validate"
    log_detail "$fail_reason"

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ "$MODE" == "gpu" ]]; then
            log_warn "Non-interactive + explicit GPU mode: failing without CPU fallback"
            log_detail "Run CPU install explicitly: bash scripts/setup/setup-pytorch.sh --mode cpu --non-interactive"
            exit 20
        fi

        if [[ "$AUTO_CPU_FALLBACK" != "true" ]]; then
            log_warn "Non-interactive mode with --no-auto-cpu-fallback: leaving environment unchanged"
            log_detail "To install CPU profile explicitly: bash scripts/setup/setup-pytorch.sh --mode cpu --non-interactive"
            exit 20
        fi

        local cpu_profile
        cpu_profile="$(cpu_profile_for_host)"
        log_warn "Non-interactive mode: attempting automatic CPU fallback with profile $cpu_profile"
        PROFILE_KEY="$cpu_profile"
        load_profile_from_matrix
        print_plan
        ensure_sudo_if_needed
        install_prerequisites
        install_python_stack
        if verify_installation; then
            REPORT_STATUS="success"
            REPORT_MESSAGE="CPU fallback install completed after accelerated profile failure"
            return 0
        fi
        fail "CPU fallback installation also failed"
    fi

    echo ""
    echo "Choose next action:"
    echo "  1) Keep current environment and exit (recommended)"
    echo "  2) Install CPU profile now"
    echo "  3) Abort"
    echo -en "Selection [1/2/3]: "

    local choice
    read -r choice

    case "$choice" in
        2)
            local cpu_profile
            cpu_profile="$(cpu_profile_for_host)"
            log_info "Switching to CPU profile: $cpu_profile"
            PROFILE_KEY="$cpu_profile"
            load_profile_from_matrix
            print_plan
            ensure_sudo_if_needed
            install_prerequisites
            install_python_stack
            if verify_installation; then
                REPORT_STATUS="success"
                REPORT_MESSAGE="CPU fallback install completed after accelerated profile failure"
                return 0
            fi
            fail "CPU fallback installation also failed"
            ;;
        1|3|*)
            log_warn "Leaving current environment as-is from this point"
            exit 21
            ;;
    esac
}

show_summary() {
    echo ""
    echo -e "${CYAN}======================================================================${NC}"
    echo -e "${BOLD}PyTorch Setup Complete${NC}"
    echo -e "${CYAN}======================================================================${NC}"
    echo "Profile:       $PROFILE_KEY"
    echo "Description:   $PROFILE_DESCRIPTION"
    echo "Mode:          $MODE"
    echo ""
    echo "Recommended checks:"
    echo "  bash scripts/setup/check-ai-runtime.sh"
    if [[ -z "$REPORT_JSON" ]]; then
        echo "  Re-run with --report-json <path> to retain installed-runtime evidence"
    fi
    echo ""
    echo "SmartTracker runtime fallback behavior:"
    echo "  SMART_TRACKER_USE_GPU: true"
    echo "  SMART_TRACKER_FALLBACK_TO_CPU: true"
    echo "  (configured through dashboard settings or an optional local override)"
    echo -e "${CYAN}======================================================================${NC}"
    echo ""
}

main() {
    parse_args "$@"

    if ! pixeagle_acquire_setup_lock "$VENV_DIR" "PyTorch setup" 30; then
        fail "Another PixEagle setup operation is active"
    fi
    if [[ -n "$REPORT_JSON" ]]; then
        if ! REPORT_JSON="$(python3 "$SCRIPT_DIR/evidence_path.py" "$REPORT_JSON")"; then
            fail "PyTorch evidence destination failed owner/type/write preflight"
        fi
    fi

    display_pixeagle_banner "PyTorch Setup" "Matrix-driven accelerator-aware installation"

    check_prerequisites
    detect_platform
    resolve_profile_key
    load_profile_from_matrix
    print_plan

    if [[ "$DRY_RUN" == "true" ]]; then
        REPORT_STATUS="success"
        REPORT_MESSAGE="Dry-run completed; no changes applied"
        log_success "Dry-run complete"
        exit 0
    fi

    if ! ask_yes_no "Proceed with this installation plan?" true; then
        REPORT_STATUS="cancelled"
        REPORT_MESSAGE="Cancelled by user"
        log_warn "Installation cancelled"
        exit 0
    fi

    if [[ "$PROFILE_EXISTING_ONLY" == true ]]; then
        if ! verify_installation; then
            fail "Existing runtime did not satisfy unsupported profile '$PROFILE_KEY'. ${PROFILE_MANUAL_HINT}"
        fi
        REPORT_STATUS="success"
        REPORT_MESSAGE="Existing unsupported-profile runtime passed strict verification; no packages changed"
        show_summary
        return 0
    fi

    ensure_sudo_if_needed
    install_prerequisites

    if ! pixeagle_begin_venv_transaction "$VENV_DIR" "PyTorch setup"; then
        fail "Could not create the exact PyTorch rollback boundary"
    fi

    if ! install_python_stack; then
        fail "Package installation failed for profile $PROFILE_KEY"
    fi

    if ! verify_installation; then
        if [[ "$PROFILE_REQUIRE_CUDA" -eq 1 || "$PROFILE_REQUIRE_MPS" -eq 1 ]]; then
            handle_acceleration_failure "Verification did not meet accelerated profile requirements"
        else
            fail "Verification failed for profile $PROFILE_KEY"
        fi
    fi

    REPORT_STATUS="success"
    REPORT_MESSAGE="PyTorch setup and verification succeeded"
    if ! pixeagle_commit_venv_transaction; then
        fail "Could not commit the verified PyTorch environment"
    fi
    PYTORCH_INSTALL_COMMITTED=true
    show_summary
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
            "$VENV_DIR" "PyTorch setup" 30 bash "${BASH_SOURCE[0]}" "$@"
    fi
fi
