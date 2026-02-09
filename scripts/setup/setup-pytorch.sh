#!/bin/bash

# ============================================================================
# scripts/setup/setup-pytorch.sh - Deterministic PyTorch Setup for PixEagle
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
# This script is deterministic and matrix-driven:
#   - Profile resolution is data-backed by pytorch_matrix.json
#   - Jetson path is explicit and not best-effort generic pip
#   - Verification is strict for requested acceleration mode
#
# Runtime fallback note:
#   SmartTracker runtime CPU fallback is controlled by:
#   SMART_TRACKER_FALLBACK_TO_CPU in configs/config.yaml
# ============================================================================

set -euo pipefail

# ----------------------------------------------------------------------------
# Paths / Defaults
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
VENV_DIR="$PIXEAGLE_DIR/venv"
DEFAULT_MATRIX_FILE="$SCRIPT_DIR/pytorch_matrix.json"

TOTAL_STEPS=6

MATRIX_FILE="$DEFAULT_MATRIX_FILE"
MODE="auto"                     # auto|gpu|cpu
NON_INTERACTIVE=false
DRY_RUN=false
SKIP_PREREQS=false
REPORT_JSON=""
AUTO_CPU_FALLBACK=true

# Manual override wheels (mainly for Jetson / air-gapped installs)
OVERRIDE_TORCH_WHEEL=""
OVERRIDE_TORCHVISION_WHEEL=""
OVERRIDE_TORCHAUDIO_WHEEL=""

# Runtime state / report fields
REPORT_STATUS="running"
REPORT_MESSAGE=""
REPORT_ERROR=""
VERIFY_JSON='{}'

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
PROFILE_PYTHON_TAG=""
PROFILE_REQUIRE_CUDA=0
PROFILE_REQUIRE_MPS=0
PROFILE_MANUAL_HINT=""
PROFILE_APT_PACKAGES=""
PROFILE_CUSPARSELT_ENABLED=0
PROFILE_CUSPARSELT_REPO_DEB_URL=""
PROFILE_CUSPARSELT_REPO_DEB_FILENAME=""
PROFILE_CUSPARSELT_KEYRING_SRC=""
PROFILE_CUSPARSELT_KEYRING_DST=""
PROFILE_CUSPARSELT_APT_PACKAGES=""

# ----------------------------------------------------------------------------
# Shared logging
# ----------------------------------------------------------------------------
fix_line_endings() {
    local file="$1"
    if [[ -f "$file" ]] && grep -q $'\r' "$file" 2>/dev/null; then
        sed -i.bak 's/\r$//' "$file" 2>/dev/null || true
        rm -f "${file}.bak" 2>/dev/null || true
    fi
}

fix_line_endings "$SCRIPTS_DIR/lib/common.sh"
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    CHECK="[OK]"; CROSS="[X]"; WARN="[!]"; INFO="[i]"
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

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
show_help() {
    cat <<'USAGE'
Usage: bash scripts/setup/setup-pytorch.sh [OPTIONS]

Deterministic PyTorch installer for PixEagle with platform-aware acceleration.

Options:
  --mode auto|gpu|cpu        Requested acceleration mode (default: auto)
  --cpu                      Alias for --mode cpu
  --non-interactive          No prompts (CI/automation mode)
  --no-auto-cpu-fallback     In non-interactive mode, fail instead of auto CPU fallback
  --dry-run                  Resolve profile and print plan without changes
  --skip-prereqs             Skip system prerequisite installation
  --matrix-file <path>       Use custom matrix file (default: scripts/setup/pytorch_matrix.json)
  --report-json <path>       Write machine-readable setup report JSON

  --torch-wheel <path|url>        Override torch wheel (Jetson/manual mode)
  --torchvision-wheel <path|url>   Override torchvision wheel
  --torchaudio-wheel <path|url>    Override torchaudio wheel (optional)

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

    if [[ -z "$REPORT_JSON" ]]; then
        return 0
    fi

    python3 - "$REPORT_JSON" "$exit_code" "$REPORT_STATUS" "$REPORT_MESSAGE" "$REPORT_ERROR" \
        "$MODE" "$PROFILE_KEY" "$PROFILE_DESCRIPTION" "$VERIFY_JSON" \
        "$DETECTED_OS" "$DETECTED_ARCH" "$DETECTED_OS_DETAIL" \
        "$DETECTED_PYTHON_VERSION" "$DETECTED_PYTHON_TAG" \
        "$DETECTED_CUDA_VERSION" "$DETECTED_GPU_NAME" \
        "$IS_JETSON" "$DETECTED_JETPACK_VERSION" "$DETECTED_L4T_RELEASE" <<'PY'
import json
import os
import sys
from datetime import datetime

report_path = sys.argv[1]
exit_code = int(sys.argv[2])
status = sys.argv[3]
message = sys.argv[4]
error = sys.argv[5]
mode = sys.argv[6]
profile_key = sys.argv[7]
profile_description = sys.argv[8]
verify_json_raw = sys.argv[9]
os_name = sys.argv[10]
arch = sys.argv[11]
os_detail = sys.argv[12]
py_ver = sys.argv[13]
py_tag = sys.argv[14]
cuda_ver = sys.argv[15]
gpu_name = sys.argv[16]
is_jetson = sys.argv[17].lower() == "true"
jetpack = sys.argv[18]
l4t = sys.argv[19]

try:
    verify = json.loads(verify_json_raw) if verify_json_raw else {}
except Exception:
    verify = {"raw": verify_json_raw}

payload = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "exit_code": exit_code,
    "status": status,
    "message": message,
    "error": error,
    "requested_mode": mode,
    "selected_profile": {
        "key": profile_key,
        "description": profile_description,
    },
    "detected": {
        "os": os_name,
        "arch": arch,
        "os_detail": os_detail,
        "python_version": py_ver,
        "python_tag": py_tag,
        "cuda_version": cuda_ver,
        "gpu_name": gpu_name,
        "is_jetson": is_jetson,
        "jetpack_version": jetpack,
        "l4t_release": l4t,
    },
    "verification": verify,
}

os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
PY

    log_info "Wrote setup report: $REPORT_JSON"
}

on_exit() {
    local exit_code=$?
    write_report_json "$exit_code" || true
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
            --torchvision-wheel)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchvision-wheel"
                OVERRIDE_TORCHVISION_WHEEL="$1"
                ;;
            --torchaudio-wheel)
                shift
                [[ $# -gt 0 ]] || fail "Missing value for --torchaudio-wheel"
                OVERRIDE_TORCHAUDIO_WHEEL="$1"
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

    [[ -f "$MATRIX_FILE" ]] || fail "Matrix file not found: $MATRIX_FILE"
    [[ -d "$VENV_DIR" ]] || fail "Virtual environment not found: $VENV_DIR (run make init first)"
    [[ -f "$VENV_DIR/bin/python" ]] || fail "venv python not found: $VENV_DIR/bin/python"
    [[ -f "$VENV_DIR/bin/pip" ]] || fail "venv pip not found: $VENV_DIR/bin/pip"

    require_cmd python3 || fail "python3 is required"

    DETECTED_PYTHON_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    DETECTED_PYTHON_TAG="$($VENV_DIR/bin/python -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"

    log_success "Matrix file: $MATRIX_FILE"
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
    local payload

    if ! payload="$(python3 - "$MATRIX_FILE" "$PROFILE_KEY" <<'PY'
import json
import shlex
import sys

matrix_path = sys.argv[1]
profile_key = sys.argv[2]

with open(matrix_path, "r", encoding="utf-8") as f:
    data = json.load(f)

profile = data.get("profiles", {}).get(profile_key)
if profile is None:
    print("__ERROR__=1")
    sys.exit(0)

packages = profile.get("packages", {})
wheels = profile.get("wheels", {})
verify = profile.get("verify", {})
prereqs = profile.get("prereqs", {})
cusparselt = prereqs.get("cusparselt", {})


def emit(key, value):
    print(f"{key}={shlex.quote(str(value))}")

emit("__ERROR__", 0)
emit("PROFILE_SUPPORTED", 1 if profile.get("supported", True) else 0)
emit("PROFILE_DESCRIPTION", profile.get("description", ""))
emit("PROFILE_INSTALL_METHOD", profile.get("install_method", ""))
emit("PROFILE_INDEX_URL", profile.get("index_url", ""))
emit("PROFILE_TORCH_SPEC", packages.get("torch", ""))
emit("PROFILE_TORCHVISION_SPEC", packages.get("torchvision", ""))
emit("PROFILE_TORCHAUDIO_SPEC", packages.get("torchaudio", ""))
emit("PROFILE_WHEEL_TORCH", wheels.get("torch", ""))
emit("PROFILE_WHEEL_TORCHVISION", wheels.get("torchvision", ""))
emit("PROFILE_WHEEL_TORCHAUDIO", wheels.get("torchaudio", ""))
emit("PROFILE_PYTHON_TAG", profile.get("python_tag", ""))
emit("PROFILE_REQUIRE_CUDA", 1 if verify.get("require_cuda", False) else 0)
emit("PROFILE_REQUIRE_MPS", 1 if verify.get("require_mps", False) else 0)
emit("PROFILE_MANUAL_HINT", profile.get("manual_hint", ""))
emit("PROFILE_APT_PACKAGES", " ".join(prereqs.get("apt_packages", [])))
emit("PROFILE_CUSPARSELT_ENABLED", 1 if cusparselt.get("enabled", False) else 0)
emit("PROFILE_CUSPARSELT_REPO_DEB_URL", cusparselt.get("repo_deb_url", ""))
emit("PROFILE_CUSPARSELT_REPO_DEB_FILENAME", cusparselt.get("repo_deb_filename", ""))
emit("PROFILE_CUSPARSELT_KEYRING_SRC", cusparselt.get("keyring_src", ""))
emit("PROFILE_CUSPARSELT_KEYRING_DST", cusparselt.get("keyring_dst", ""))
emit("PROFILE_CUSPARSELT_APT_PACKAGES", " ".join(cusparselt.get("apt_packages", [])))
PY
)"; then
        fail "Failed to parse matrix profile '$PROFILE_KEY' from $MATRIX_FILE"
    fi

    eval "$payload"

    if [[ "$__ERROR__" -ne 0 ]]; then
        fail "Profile '$PROFILE_KEY' not found in matrix: $MATRIX_FILE"
    fi

    if [[ "$PROFILE_SUPPORTED" -ne 1 ]]; then
        fail "Profile '$PROFILE_KEY' is currently marked unsupported. ${PROFILE_MANUAL_HINT}"
    fi

    log_success "Resolved profile: $PROFILE_KEY"
    log_detail "$PROFILE_DESCRIPTION"
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
        echo "Index URL:          $PROFILE_INDEX_URL"
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
    if [[ -n "$PROFILE_WHEEL_TORCH" || -n "$PROFILE_WHEEL_TORCHVISION" ]]; then
        echo "Wheel torch:        ${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}"
        echo "Wheel torchvision:  ${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}"
        if [[ -n "${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}" ]]; then
            echo "Wheel torchaudio:   ${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}"
        fi
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

    local need_sudo=false
    if [[ -n "$PROFILE_APT_PACKAGES" ]]; then
        need_sudo=true
    fi
    if [[ "$PROFILE_CUSPARSELT_ENABLED" -eq 1 ]]; then
        need_sudo=true
    fi

    if [[ "$need_sudo" == "false" ]]; then
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

    local apt_updated=false

    if [[ -n "$PROFILE_APT_PACKAGES" ]]; then
        read -r -a apt_pkgs <<<"$PROFILE_APT_PACKAGES"
        if [[ ${#apt_pkgs[@]} -gt 0 ]]; then
            run_cmd "Updating apt package lists" sudo_run apt-get update
            apt_updated=true
            run_cmd "Installing apt prerequisites" sudo_run apt-get install -y "${apt_pkgs[@]}"
        fi
    fi

    if [[ "$PROFILE_CUSPARSELT_ENABLED" -eq 1 ]]; then
        local need_install=true
        if dpkg -s cusparselt-cuda-12 >/dev/null 2>&1; then
            need_install=false
            log_success "cuSPARSELT already installed"
        fi

        if [[ "$need_install" == "true" ]]; then
            local tmp_dir="/tmp/pixeagle-pytorch"
            local deb_path="$tmp_dir/$PROFILE_CUSPARSELT_REPO_DEB_FILENAME"

            run_cmd "Preparing temporary directory" mkdir -p "$tmp_dir"

            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[dry-run] Would download: $PROFILE_CUSPARSELT_REPO_DEB_URL"
            else
                if command -v curl >/dev/null 2>&1; then
                    run_cmd "Downloading cuSPARSELT repo package" curl -fsSL "$PROFILE_CUSPARSELT_REPO_DEB_URL" -o "$deb_path"
                elif command -v wget >/dev/null 2>&1; then
                    run_cmd "Downloading cuSPARSELT repo package" wget -qO "$deb_path" "$PROFILE_CUSPARSELT_REPO_DEB_URL"
                else
                    fail "Neither curl nor wget is available for downloading prerequisites"
                fi
            fi

            run_cmd "Installing cuSPARSELT repo package" sudo_run dpkg -i "$deb_path"

            if [[ -n "$PROFILE_CUSPARSELT_KEYRING_SRC" && -n "$PROFILE_CUSPARSELT_KEYRING_DST" ]]; then
                run_cmd "Installing cuSPARSELT keyring" sudo_run cp "$PROFILE_CUSPARSELT_KEYRING_SRC" "$PROFILE_CUSPARSELT_KEYRING_DST"
            fi

            run_cmd "Updating apt package lists for cuSPARSELT" sudo_run apt-get update
            apt_updated=true

            if [[ -n "$PROFILE_CUSPARSELT_APT_PACKAGES" ]]; then
                read -r -a cusparselt_pkgs <<<"$PROFILE_CUSPARSELT_APT_PACKAGES"
                run_cmd "Installing cuSPARSELT runtime packages" sudo_run apt-get install -y "${cusparselt_pkgs[@]}"
            fi
        fi
    fi

    if [[ "$apt_updated" == "false" ]]; then
        log_success "No extra system prerequisites required"
    fi
}

resolve_wheel_source() {
    local source_value="$1"
    local destination_dir="$2"
    local out_var="$3"
    local resolved_path=""

    if [[ -z "$source_value" ]]; then
        printf -v "$out_var" '%s' ""
        return 0
    fi

    if [[ -f "$source_value" ]]; then
        resolved_path="$source_value"
        printf -v "$out_var" '%s' "$resolved_path"
        return 0
    fi

    if [[ "$source_value" =~ ^https?:// ]]; then
        local filename
        filename="$(basename "$source_value")"
        local target_path="$destination_dir/$filename"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[dry-run] Would download wheel: $source_value"
            resolved_path="$target_path"
            printf -v "$out_var" '%s' "$resolved_path"
            return 0
        fi

        mkdir -p "$destination_dir" || return 1
        if command -v curl >/dev/null 2>&1; then
            run_cmd "Downloading wheel: $filename" curl -fsSL "$source_value" -o "$target_path" || return 1
        elif command -v wget >/dev/null 2>&1; then
            run_cmd "Downloading wheel: $filename" wget -qO "$target_path" "$source_value" || return 1
        else
            fail "Neither curl nor wget is available to download wheel: $source_value"
        fi

        resolved_path="$target_path"
        printf -v "$out_var" '%s' "$resolved_path"
        return 0
    fi

    fail "Wheel source is neither a local file nor URL: $source_value"
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
                run_cmd "Installing torch stack from custom index" "$pip" install --upgrade --no-cache-dir --index-url "$PROFILE_INDEX_URL" "${pkgs[@]}" || return 1
            else
                run_cmd "Installing torch stack from default PyPI" "$pip" install --upgrade --no-cache-dir "${pkgs[@]}" || return 1
            fi
            ;;

        pypi)
            local pypi_pkgs=()
            [[ -n "$PROFILE_TORCH_SPEC" ]] && pypi_pkgs+=("torch==$PROFILE_TORCH_SPEC")
            [[ -n "$PROFILE_TORCHVISION_SPEC" ]] && pypi_pkgs+=("torchvision==$PROFILE_TORCHVISION_SPEC")
            [[ -n "$PROFILE_TORCHAUDIO_SPEC" ]] && pypi_pkgs+=("torchaudio==$PROFILE_TORCHAUDIO_SPEC")

            [[ ${#pypi_pkgs[@]} -gt 0 ]] || fail "No package specs defined for profile $PROFILE_KEY"
            run_cmd "Installing torch stack from PyPI" "$pip" install --upgrade --no-cache-dir "${pypi_pkgs[@]}" || return 1
            ;;

        wheels)
            local torch_source="${OVERRIDE_TORCH_WHEEL:-$PROFILE_WHEEL_TORCH}"
            local torchvision_source="${OVERRIDE_TORCHVISION_WHEEL:-$PROFILE_WHEEL_TORCHVISION}"
            local torchaudio_source="${OVERRIDE_TORCHAUDIO_WHEEL:-$PROFILE_WHEEL_TORCHAUDIO}"
            local wheel_tmp="/tmp/pixeagle-pytorch-wheels"

            [[ -n "$torch_source" ]] || fail "Torch wheel is required for profile $PROFILE_KEY"
            [[ -n "$torchvision_source" ]] || fail "Torchvision wheel is required for profile $PROFILE_KEY"

            if [[ -n "$PROFILE_PYTHON_TAG" && "$DETECTED_PYTHON_TAG" != "$PROFILE_PYTHON_TAG" ]]; then
                fail "Python ABI mismatch: profile requires $PROFILE_PYTHON_TAG but venv is $DETECTED_PYTHON_TAG"
            fi

            local torch_wheel=""
            local torchvision_wheel=""
            local torchaudio_wheel=""

            resolve_wheel_source "$torch_source" "$wheel_tmp" torch_wheel || return 1
            resolve_wheel_source "$torchvision_source" "$wheel_tmp" torchvision_wheel || return 1
            resolve_wheel_source "$torchaudio_source" "$wheel_tmp" torchaudio_wheel || return 1

            run_cmd "Installing torch wheel" "$pip" install --upgrade --no-cache-dir "$torch_wheel" || return 1
            run_cmd "Installing torchvision wheel" "$pip" install --upgrade --no-cache-dir --no-deps "$torchvision_wheel" || return 1

            if [[ -n "$torchaudio_wheel" ]]; then
                if ! run_cmd "Installing torchaudio wheel" "$pip" install --upgrade --no-cache-dir --no-deps "$torchaudio_wheel"; then
                    log_warn "torchaudio install failed (continuing, not required for SmartTracker)"
                fi
            else
                log_warn "No torchaudio wheel configured for this profile (continuing)"
            fi
            ;;

        *)
            fail "Unknown install method '$PROFILE_INSTALL_METHOD' for profile $PROFILE_KEY"
            ;;
    esac
}

verify_installation() {
    log_step 6 "Verifying installation"

    local output
    if ! output="$($VENV_DIR/bin/python <<'PY'
import json

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
    "error": None,
}

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

print(json.dumps(result))
PY
)"; then
        log_error "Verification failed: could not execute runtime verification Python snippet"
        return 1
    fi

    VERIFY_JSON="$output"

    local parsed
    if ! parsed="$(python3 - "$output" "$PROFILE_REQUIRE_CUDA" "$PROFILE_REQUIRE_MPS" <<'PY'
import json
import sys

raw = sys.argv[1]
need_cuda = int(sys.argv[2])
need_mps = int(sys.argv[3])

try:
    data = json.loads(raw)
except Exception as e:
    print("OK=0")
    print(f"REASON=invalid verification payload: {e}")
    sys.exit(0)

ok = bool(data.get("torch_ok")) and bool(data.get("torchvision_ok"))
reason = ""

if not data.get("torch_ok"):
    ok = False
    reason = "torch import failed"
elif not data.get("torchvision_ok"):
    ok = False
    reason = "torchvision import failed"
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

print(f"OK={1 if ok else 0}")
print(f"REASON={reason}")
print(f"TORCH_VERSION={data.get('torch_version')}")
print(f"TORCHVISION_VERSION={data.get('torchvision_version')}")
print(f"TORCHAUDIO_VERSION={data.get('torchaudio_version')}")
print(f"CUDA_AVAILABLE={1 if data.get('cuda_available') else 0}")
print(f"CUDA_DEVICE={data.get('cuda_device_name') or ''}")
print(f"MPS_AVAILABLE={1 if data.get('mps_available') else 0}")
print(f"TORCHAUDIO_OK={1 if data.get('torchaudio_ok') else 0}")
PY
)"; then
        log_error "Verification failed: could not parse runtime verification output"
        return 1
    fi

    eval "$parsed"

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
    echo ""
    echo "SmartTracker runtime fallback behavior:"
    echo "  SMART_TRACKER_USE_GPU: true"
    echo "  SMART_TRACKER_FALLBACK_TO_CPU: true"
    echo "  (configured in configs/config.yaml)"
    echo -e "${CYAN}======================================================================${NC}"
    echo ""
}

main() {
    parse_args "$@"

    display_pixeagle_banner "PyTorch Setup" "Deterministic accelerator-aware installation"

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

    ensure_sudo_if_needed
    install_prerequisites

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
    show_summary
}

main "$@"
