#!/bin/bash

# ============================================================================
# scripts/init.sh - Professional Initialization Script for PixEagle
# ============================================================================
# This script sets up the complete PixEagle environment:
#   - Python virtual environment with all dependencies
#   - Node.js via nvm for the dashboard
#   - Configuration defaults
#   - MAVSDK and MAVLink2REST binaries
#
# Features:
#   - Auto-detection and installation of missing packages
#   - Progress indicators and professional UX
#   - Robust error handling with clear recovery instructions
#
# Usage:
#   make init                    (recommended)
#   bash scripts/init.sh         (direct)
# ============================================================================

set -o pipefail  # Catch pipe failures

# ============================================================================
# CRLF Line Ending Fix (Windows compatibility)
# ============================================================================
# When files are edited on Windows or checked out with wrong line endings,
# bash scripts fail with "command not found" errors. This fixes it automatically.
fix_line_endings() {
    local file="$1"
    if [[ -f "$file" ]] && file "$file" 2>/dev/null | grep -q "CRLF"; then
        # File has CRLF endings - fix them
        if command -v sed &>/dev/null; then
            sed -i.bak 's/\r$//' "$file" 2>/dev/null && rm -f "${file}.bak" 2>/dev/null
        elif command -v tr &>/dev/null; then
            tr -d '\r' < "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
        fi
    fi
    # Also check using grep for \r (more reliable on some systems)
    if [[ -f "$file" ]] && grep -q $'\r' "$file" 2>/dev/null; then
        if command -v sed &>/dev/null; then
            sed -i.bak 's/\r$//' "$file" 2>/dev/null && rm -f "${file}.bak" 2>/dev/null
        elif command -v tr &>/dev/null; then
            tr -d '\r' < "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
        fi
    fi
}

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=10
NVM_VERSION="v0.40.3"
NVM_INSTALL_COMMIT="977563e97ddc66facf3a8e31c6cff01d236f09bd"
NVM_INSTALL_SHA256="2d8359a64a3cb07c02389ad88ceecd43f2fa469c06104f92f98df5b6f315275f"
NVM_INSTALL_URL="https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_INSTALL_COMMIT}/install.sh"
NODE_VERSION=""
SETUP_PYTHON=""
SETUP_PYTHON_SOURCE=""
PYTHON_VERSION=""
PYTHON_FULL_VERSION=""
CORE_REQUIRED_DISK_MB="${PIXEAGLE_CORE_REQUIRED_DISK_MB:-2048}"
FULL_REQUIRED_DISK_MB="${PIXEAGLE_FULL_REQUIRED_DISK_MB:-8192}"
REQUIRED_DISK_MB="$CORE_REQUIRED_DISK_MB"

# Installation profile: "core" (no AI) or "full" (with AI/torch)
INSTALL_PROFILE="core"
# Python dependency installation status (used in final summary)
AI_VERIFY_PASSED=false
PYTORCH_SETUP_PASSED=false
PYTORCH_SETUP_SKIPPED=false
PYTORCH_SETUP_FAILED=false
NODE_SETUP_STATE="pending"
NODE_SETUP_DETAIL="not checked"
DASHBOARD_DEPS_STATE="pending"
DASHBOARD_DEPS_DETAIL="not checked"
CONFIG_DEFAULTS_STATE="pending"
CONFIG_DEFAULTS_DETAIL="not checked"
DASHBOARD_ENV_STATE="pending"
DASHBOARD_ENV_DETAIL="not checked"
MAVSDK_BINARY_STATE="pending"
MAVSDK_BINARY_DETAIL="not checked"
MAVLINK2REST_BINARY_STATE="pending"
MAVLINK2REST_BINARY_DETAIL="not checked"
OPTIONAL_DLIB_STATE="skipped"
OPTIONAL_DLIB_DETAIL="not selected"
OPTIONAL_GSTREAMER_STATE="skipped"
OPTIONAL_GSTREAMER_DETAIL="not selected"
OPTIONAL_SHORTCUT_STATE="skipped"
OPTIONAL_SHORTCUT_DETAIL="not selected"
SMART_TRACKER_STATE="skipped"
SMART_TRACKER_DETAIL="Full profile not selected"
# Platform detection
DETECTED_ARCH=""
IS_ARM_PLATFORM=false

# Get the scripts directory and PixEagle root
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
NODE_VERSION_FILE="$PIXEAGLE_DIR/.nvmrc"
PYTORCH_MATRIX_FILE="$SCRIPTS_DIR/setup/pytorch_matrix.json"
PYTHON_COMPATIBILITY_CHECK="$SCRIPTS_DIR/setup/check-python-compatibility.py"

# Fix line endings on critical files before sourcing
fix_line_endings "$SCRIPTS_DIR/lib/common.sh"
fix_line_endings "$0"  # Fix this script too

# Source shared functions (colors, logging, banner)
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    echo "Warning: Could not source common.sh, using fallback definitions"
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
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/dashboard_dependencies.sh" 2>/dev/null; then
    echo "Error: Could not source the required dashboard dependency helper" >&2
    exit 1
fi

if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
    VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
else
    VENV_DIR="$PIXEAGLE_DIR/.venv"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_ACTIVATE="$VENV_DIR/bin/activate"

# Fallback definitions if common.sh failed to load properly
if ! declare -f display_pixeagle_banner &>/dev/null; then
    # Minimal color definitions
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
    CHECK="OK"
    CROSS="X"
    WARN="!"
    INFO="i"
    PARTY="*"

    display_pixeagle_banner() {
        echo ""
        echo -e "${CYAN}+===============================================================+${NC}"
        echo -e "${CYAN}|${NC}              ${BOLD}PixEagle${NC}                                       ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}       Vision-Based Drone Tracking System                     ${CYAN}|${NC}"
        echo -e "${CYAN}+===============================================================+${NC}"
        echo ""
    }

    get_version_info() {
        local script_version="${1:-unknown}"
        if [[ -d "$PIXEAGLE_DIR/.git" ]]; then
            local git_tag
            local git_commit
            git_tag=$(git -C "$PIXEAGLE_DIR" describe --tags --abbrev=0 2>/dev/null || echo "")
            git_commit=$(git -C "$PIXEAGLE_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
            if [[ -n "$git_tag" ]]; then
                echo -e "  ${DIM}Version: ${git_tag} (${git_commit}) | Script: v${script_version}${NC}"
            else
                echo -e "  ${DIM}Commit: ${git_commit} | Script: v${script_version}${NC}"
            fi
        fi
    }

    log_step() {
        local step=$1
        local msg=$2
        echo ""
        echo -e "${CYAN}----------------------------------------------------------------${NC}"
        echo -e "   ${BOLD}Step ${step}/${TOTAL_STEPS}:${NC} ${msg}"
        echo -e "${CYAN}----------------------------------------------------------------${NC}"
    }

    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[${CHECK}]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[${WARN}]${NC} $1"; }
    log_error() { echo -e "   ${RED}[${CROSS}]${NC} $1"; }
fi

# ============================================================================
# Script-Specific Functions
# ============================================================================
log_detail() {
    echo -e "        ${DIM}$1${NC}"
}

prepare_model_store() {
    local model_dir="$PIXEAGLE_DIR/models"
    local owner_uid

    if [[ -L "$model_dir" ]]; then
        log_error "Model store must not be a symbolic link: $model_dir"
        return 1
    fi
    if [[ -e "$model_dir" && ! -d "$model_dir" ]]; then
        log_error "Model store path is not a directory: $model_dir"
        return 1
    fi
    if ! mkdir -p -- "$model_dir"; then
        log_error "Could not create model store: $model_dir"
        return 1
    fi
    owner_uid="$(stat -c '%u' -- "$model_dir" 2>/dev/null)" || {
        log_error "Could not inspect model-store ownership: $model_dir"
        return 1
    }
    if [[ "$owner_uid" != "$(id -u)" ]]; then
        log_error "Model store must be owned by the PixEagle runtime user"
        return 1
    fi
    if ! chmod 700 -- "$model_dir"; then
        log_error "Could not set owner-only model-store permissions"
        return 1
    fi
    log_success "Model store is owner-controlled (models/, mode 0700)"
}

# Read a yes/no choice from the prepared terminal or an explicit automation
# profile. Invalid interactive answers are retried instead of silently taking
# the default.
# Usage: ask_yes_no "prompt" [default]
# Returns 0 for yes and 1 for no. A closed interactive terminal aborts setup;
# treating a lost SSH session as an operator choice would produce false success.
ask_yes_no() {
    local prompt="$1"
    local default="${2:-y}"  # Default to yes
    local reply=""

    # Non-interactive mode: always use default (for automated installs, e.g., ARK-OS)
    if [[ "${PIXEAGLE_NONINTERACTIVE:-}" == "1" ]]; then
        printf "%b (auto: %s)\n" "$prompt" "$default"
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi

    if ! pixeagle_has_interactive_input; then
        printf "%b" "$prompt"
        printf " (auto: %s)\n" "$default"
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi

    while true; do
        printf "%b" "$prompt"
        if ! pixeagle_read_user_input reply; then
            printf "\n"
            log_error "Terminal input closed before a response was received"
            log_detail "Setup stopped. Rerun the installer; verified components will be reused."
            exit 2
        fi
        reply="${reply//[[:space:]]/}"
        [[ -z "$reply" ]] && reply="$default"
        case "$reply" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *)
                echo -e "   ${YELLOW}Please enter y or n; press Enter for the shown default.${NC}"
                ;;
        esac
    done
}

# ============================================================================
# Spinner for Long-Running Operations
# ============================================================================
spinner_pid=""

start_spinner() {
    local msg="$1"
    if [[ ! -t 1 ]]; then
        log_detail "$msg"
        spinner_pid=""
        return 0
    fi
    # shellcheck disable=SC1003  # A trailing backslash is a spinner glyph.
    local chars='|/-\'
    (
        while true; do
            for ((i=0; i<${#chars}; i++)); do
                printf "\r        ${CYAN}%s${NC} %s" "${chars:$i:1}" "$msg"
                sleep 0.1
            done
        done
    ) &
    spinner_pid=$!
}

stop_spinner() {
    if [[ -n "$spinner_pid" ]]; then
        kill "$spinner_pid" 2>/dev/null || true
        wait "$spinner_pid" 2>/dev/null || true
        spinner_pid=""
        printf "\r        \033[K"  # Clear line
    fi
}

# Cleanup on exit
cleanup() {
    local exit_code=$?
    trap - EXIT
    stop_spinner
    if ! pixeagle_finalize_venv_transaction; then
        log_error "Virtual-environment rollback was incomplete"
        [[ "$exit_code" -ne 0 ]] || exit_code=1
    fi
    pixeagle_release_setup_lock
    exit "$exit_code"
}
trap cleanup EXIT

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    if [[ "${PIXEAGLE_BOOTSTRAP_CONTEXT:-0}" == "1" ]]; then
        echo ""
        echo -e "${CYAN}${BOLD}PixEagle Setup${NC}"
    else
        pixeagle_has_interactive_input && clear
        display_pixeagle_banner "Setup" "Vision tracking and PX4 companion runtime"
    fi
    get_version_info "7.0.0-beta.16"
    if pixeagle_has_interactive_input; then
        echo -e "  ${DIM}10 guided steps; press Enter to accept a displayed default.${NC}"
    else
        echo -e "  ${DIM}10 unattended steps using the explicit setup profile.${NC}"
    fi
    echo ""
}

setup_has_existing_artifacts() {
    [[ -x "$VENV_PYTHON" \
        || -d "$PIXEAGLE_DIR/dashboard/node_modules" \
        || -f "$PIXEAGLE_DIR/dashboard/.env" \
        || -f "$PIXEAGLE_DIR/configs/config.yaml" \
        || -x "$PIXEAGLE_DIR/bin/mavsdk_server_bin" \
        || -x "$PIXEAGLE_DIR/bin/mavlink2rest" ]]
}

describe_setup_action() {
    local requested_action="${PIXEAGLE_SETUP_ACTION:-auto}"

    if setup_has_existing_artifacts || [[ "$requested_action" == "update-repair" ]]; then
        log_info "Existing or interrupted PixEagle setup detected"
        if [[ "$requested_action" == "update-repair" ]]; then
            log_detail "Action: fast-forward source update plus in-place setup repair"
        else
            log_detail "Action: verify and repair the current source in place"
        fi
        log_detail "Valid components are reused; missing, outdated, or incomplete components are reconciled."
        log_detail "Config, credentials, models, recordings, and evidence are preserved. This is not a reset."
    else
        log_info "Fresh PixEagle setup detected"
        log_detail "Action: install the selected profile without starting a runtime or service."
    fi
    echo ""
}

# ============================================================================
# Sudo Password Prompt
# ============================================================================
prompt_sudo() {
    if [[ "$EUID" -eq 0 ]]; then
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        log_error "Administrator access is required, but sudo is not installed"
        log_detail "Run this setup as root or install sudo and grant this user access."
        exit 1
    fi
    # Non-interactive mode: skip the fancy prompt, just validate sudo
    if [[ "${PIXEAGLE_NONINTERACTIVE:-}" == "1" ]]; then
        if ! sudo -n -v 2>/dev/null; then
            log_error "sudo authentication required but running in non-interactive mode"
            exit 1
        fi
        return
    fi

    echo ""
    echo -e "${YELLOW}+==========================================================================+${NC}"
    echo -e "${YELLOW}|${NC}                                                                          ${YELLOW}|${NC}"
    echo -e "${YELLOW}|${NC}   ${BOLD}SUDO PASSWORD REQUIRED${NC}                                                 ${YELLOW}|${NC}"
    echo -e "${YELLOW}|${NC}                                                                          ${YELLOW}|${NC}"
    echo -e "${YELLOW}|${NC}   System packages need to be installed. Please enter your password       ${YELLOW}|${NC}"
    echo -e "${YELLOW}|${NC}   when prompted below.                                                   ${YELLOW}|${NC}"
    echo -e "${YELLOW}|${NC}                                                                          ${YELLOW}|${NC}"
    echo -e "${YELLOW}+==========================================================================+${NC}"
    echo ""

    # Pre-authenticate sudo to cache credentials
    if ! sudo -v; then
        log_error "Failed to authenticate. Please try again."
        exit 1
    fi
    echo ""
}

run_privileged() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

run_apt_get() {
    run_privileged env \
        DEBIAN_FRONTEND=noninteractive \
        APT_LISTCHANGES_FRONTEND=none \
        apt-get "$@" </dev/null
}

# ============================================================================
# Installation Profile Selection
# ============================================================================
# Detects platform and prompts user for installation profile
select_installation_profile() {
    # Detect architecture
    DETECTED_ARCH=$(uname -m)
    IS_ARM_PLATFORM=false
    [[ "$DETECTED_ARCH" == "arm"* || "$DETECTED_ARCH" == "aarch64" ]] && IS_ARM_PLATFORM=true

    # Non-interactive mode: use PIXEAGLE_INSTALL_PROFILE env var (for automated installs, e.g., ARK-OS)
    if [[ -n "${PIXEAGLE_INSTALL_PROFILE:-}" ]]; then
        case "${PIXEAGLE_INSTALL_PROFILE,,}" in
            core|1)
                INSTALL_PROFILE="core"
                log_success "Non-interactive: Core installation profile selected"
                return
                ;;
            full|2)
                INSTALL_PROFILE="full"
                log_success "Non-interactive: Full installation profile selected"
                return
                ;;
            *)
                log_error "Unknown PIXEAGLE_INSTALL_PROFILE='$PIXEAGLE_INSTALL_PROFILE'"
                log_detail "Expected core or full. No installation changes were made."
                return 2
                ;;
        esac
    fi
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" ]]; then
        log_error "PIXEAGLE_NONINTERACTIVE=1 requires PIXEAGLE_INSTALL_PROFILE=core|full"
        log_detail "The one-line bootstrap supplies Core explicitly when no terminal is available."
        return 2
    fi

    log_section "Installation profile"
    echo -e "   Detected architecture: ${BOLD}$DETECTED_ARCH${NC}"
    echo ""
    echo -e "   ${BOLD}1) Core [default]${NC}"
    echo -e "      Complete runtime without local AI packages"
    echo -e "      ${DIM}Dashboard, OpenCV tracking, streaming, MAVSDK and MAVLink tools${NC}"
    echo ""
    echo -e "   ${BOLD}2) Full AI${NC}"
    echo -e "      Core plus PyTorch and Ultralytics dependencies"
    echo -e "      ${DIM}Register a trusted local detect/OBB model after installation${NC}"
    echo ""

    if ! pixeagle_has_interactive_input; then
        log_error "No controlling terminal is available for profile selection"
        log_detail "Use the one-line bootstrap, or set PIXEAGLE_NONINTERACTIVE=1 and PIXEAGLE_INSTALL_PROFILE=core|full."
        return 2
    fi

    while true; do
        echo -en "   Select profile [Enter=1, 2=Full AI]: "
        if ! pixeagle_read_user_input choice; then
            echo ""
            log_error "Terminal input closed before profile selection"
            log_detail "Reconnect with an interactive terminal or use PIXEAGLE_NONINTERACTIVE=1 with an explicit profile."
            return 2
        fi
        choice="${choice//[[:space:]]/}"
        if [[ -z "$choice" ]]; then
            choice=1
        fi

        case "$choice" in
            1)
                INSTALL_PROFILE="core"
                echo ""
                log_success "Selected: Core product installation (AI packages can be added later)"
                break
                ;;
            2)
                INSTALL_PROFILE="full"
                echo ""
                if [[ "$IS_ARM_PLATFORM" == true ]]; then
                    log_warn "Selected: Full installation with AI packages"
                    log_detail "If torch fails, you can reinstall with: make init (choose Core)"
                    log_detail "Recommended recovery: bash scripts/setup/setup-pytorch.sh --mode auto"
                    log_detail "Manual wheel overrides also require --torch-sha256/--torchvision-sha256"
                else
                    log_success "Selected: Full installation with AI packages"
                fi
                break
                ;;
            *)
                echo -e "   ${RED}Invalid choice. Please enter 1 or 2.${NC}"
                ;;
        esac
    done
    echo ""
}

check_supported_platform() {
    local os_release_file="${PIXEAGLE_OS_RELEASE_FILE:-/etc/os-release}"
    [[ "$(uname -s)" == "Linux" ]] || {
        log_error "The maintained guided installer is Linux-only"
        exit 1
    }
    [[ -r "$os_release_file" ]] || {
        log_error "Cannot identify this Linux distribution ($os_release_file missing)"
        exit 1
    }
    # shellcheck source=/etc/os-release
    source "$os_release_file"
    local distro_id="${ID,,}"
    local distro_like="${ID_LIKE,,}"
    if [[ "$distro_id" != "ubuntu" && "$distro_id" != "debian" && \
          "$distro_id" != "raspbian" && "$distro_like" != *"debian"* && \
          "$distro_like" != *"ubuntu"* ]]; then
        if [[ "${PIXEAGLE_ALLOW_UNVERIFIED_APT_DISTRO:-0}" != "1" ]]; then
            log_error "Unsupported guided-install distribution: ${PRETTY_NAME:-$ID}"
            log_detail "This installer uses apt/dpkg and is maintained for Debian-family Linux."
            log_detail "Experts may explicitly test an apt-compatible derivative with PIXEAGLE_ALLOW_UNVERIFIED_APT_DISTRO=1."
            exit 1
        fi
        log_warn "Proceeding on an unverified apt-compatible distribution by explicit override"
    fi
    for command_name in apt-get apt-cache dpkg; do
        command -v "$command_name" >/dev/null 2>&1 || {
            log_error "Required Debian-family package tool is missing: $command_name"
            exit 1
        }
    done
    case "$(uname -m)" in
        x86_64|amd64|aarch64|arm64) ;;
        *)
            if [[ "${PIXEAGLE_ALLOW_UNVERIFIED_ARCH:-0}" != "1" ]]; then
                log_error "Unsupported guided-install architecture: $(uname -m)"
                log_detail "Maintained bootstrap targets are x86_64 and ARM64."
                exit 1
            fi
            log_warn "Proceeding on an unverified architecture by explicit override"
            ;;
    esac
    log_success "Supported Debian-family Linux bootstrap detected (${PRETTY_NAME:-$ID}, $(uname -m))"
}

load_node_runtime_policy() {
    [[ -f "$NODE_VERSION_FILE" && ! -L "$NODE_VERSION_FILE" ]] || {
        log_error "Node.js version contract is missing or unsafe: $NODE_VERSION_FILE"
        return 1
    }
    NODE_VERSION="$(tr -d '[:space:]' < "$NODE_VERSION_FILE")"
    [[ "$NODE_VERSION" =~ ^[0-9]+$ ]] || {
        log_error "Invalid Node.js major in .nvmrc: '$NODE_VERSION'"
        return 1
    }
}

resolve_setup_python() {
    local candidate="${PIXEAGLE_PYTHON:-}"
    local resolved=""

    if [[ -z "$candidate" && -x "$VENV_PYTHON" && -f "$VENV_ACTIVATE" ]]; then
        candidate="$VENV_PYTHON"
        SETUP_PYTHON_SOURCE="existing PixEagle virtual environment"
    elif [[ -z "$candidate" ]]; then
        candidate="python3"
        SETUP_PYTHON_SOURCE="host default"
    else
        SETUP_PYTHON_SOURCE="PIXEAGLE_PYTHON override"
    fi

    resolved="$(command -v -- "$candidate" 2>/dev/null || true)"
    if [[ -z "$resolved" || ! -x "$resolved" ]]; then
        log_error "Requested Python interpreter is unavailable: $candidate"
        log_detail "Install Python 3, or set PIXEAGLE_PYTHON to an executable interpreter."
        return 1
    fi
    if ! "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' \
        >/dev/null 2>&1; then
        log_error "Requested interpreter is not Python 3: $resolved"
        return 1
    fi

    SETUP_PYTHON="$resolved"
    PYTHON_FULL_VERSION="$("$SETUP_PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    PYTHON_VERSION="$("$SETUP_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
}

check_core_python_compatibility() {
    [[ -f "$PYTORCH_MATRIX_FILE" && -f "$PYTHON_COMPATIBILITY_CHECK" ]] || {
        log_error "Python compatibility policy is missing"
        return 1
    }

    local compatibility_output=""
    if compatibility_output="$("$SETUP_PYTHON" "$PYTHON_COMPATIBILITY_CHECK" \
        --policy "$PYTORCH_MATRIX_FILE" \
        --runtime-role core \
        --python-version "$PYTHON_FULL_VERSION" 2>&1)"; then
        log_success "$compatibility_output"
        return 0
    fi

    log_error "$compatibility_output"
    return 1
}

check_full_ai_python_compatibility() {
    [[ "$INSTALL_PROFILE" == "full" ]] || return 0
    [[ -f "$PYTORCH_MATRIX_FILE" && -f "$PYTHON_COMPATIBILITY_CHECK" ]] || {
        log_error "Full AI compatibility policy is missing"
        return 1
    }

    local compatibility_output=""
    local compatibility_status=0
    compatibility_output="$("$SETUP_PYTHON" "$PYTHON_COMPATIBILITY_CHECK" \
        --policy "$PYTORCH_MATRIX_FILE" \
        --any-supported-profile \
        --python-version "$PYTHON_FULL_VERSION" 2>&1)" || compatibility_status=$?
    if [[ "$compatibility_status" -eq 0 ]]; then
        log_success "$compatibility_output"
        return 0
    fi

    if [[ "$compatibility_status" -ne 3 ]]; then
        log_error "$compatibility_output"
        return 1
    fi

    log_warn "$compatibility_output"
    log_detail "Core remains a complete working installation and AI can be added after the matrix supports this interpreter."
    if pixeagle_has_interactive_input; then
        if ask_yes_no "        Continue with Core instead? [Y/n]: " y; then
            INSTALL_PROFILE="core"
            log_success "Continuing with Core; no unsupported AI packages will be installed"
            return 0
        fi
        log_error "Installation cancelled before dependency changes"
        return 1
    fi

    log_error "Unattended Full AI cannot change profile implicitly"
    log_detail "Use PIXEAGLE_INSTALL_PROFILE=core, or provide a reviewed interpreter with PIXEAGLE_PYTHON."
    return 1
}

# ============================================================================
# Pre-flight Checks (Step 1)
# ============================================================================
check_system_requirements() {
    log_step 1 "Checking system requirements..."
    local errors=0

    if ! resolve_setup_python; then
        errors=$((errors + 1))
    else
        log_success "Python ${PYTHON_FULL_VERSION} selected ($SETUP_PYTHON_SOURCE)"
        log_detail "$SETUP_PYTHON"
        if ! check_core_python_compatibility; then
            errors=$((errors + 1))
        fi
    fi

    if ! load_node_runtime_policy; then
        errors=$((errors + 1))
    fi
    if [[ -n "$SETUP_PYTHON" ]] && ! check_full_ai_python_compatibility; then
        errors=$((errors + 1))
    fi

    if [[ "$INSTALL_PROFILE" == "full" ]]; then
        REQUIRED_DISK_MB="$FULL_REQUIRED_DISK_MB"
    else
        REQUIRED_DISK_MB="$CORE_REQUIRED_DISK_MB"
    fi

    # Check disk space for the selected profile.
    local available_mb
    available_mb=$(df -m . 2>/dev/null | awk 'NR==2 {print $4}')
    if [[ -n "$available_mb" ]] && [[ $available_mb -lt $REQUIRED_DISK_MB ]]; then
        log_error "Insufficient disk space (${available_mb}MB available, ${REQUIRED_DISK_MB}MB required)"
        errors=$((errors + 1))
    else
        log_success "Disk space OK (${available_mb}MB available)"
    fi

    # Check network (non-fatal warning)
    if command -v curl &>/dev/null; then
        if ! curl -s --head --connect-timeout 3 https://pypi.org >/dev/null 2>&1; then
            log_warn "Cannot reach PyPI - installation may fail"
        fi
    fi

    # Check if we're in the right directory
    if [[ ! -f "$PIXEAGLE_DIR/requirements.txt" ]]; then
        log_error "requirements.txt not found - are you in the PixEagle directory?"
        errors=$((errors + 1))
    else
        log_success "PixEagle directory verified"
    fi

    if [[ $errors -gt 0 ]]; then
        echo ""
        log_error "System requirements check failed with $errors error(s)"
        exit 1
    fi
}

# ============================================================================
# System Package Installation (Step 2)
# ============================================================================

# Helper: Check if a package is installed
pkg_installed() {
    dpkg -s "$1" &>/dev/null 2>&1
}

# Helper: Check if any package from a list is installed (for alternatives)
any_pkg_installed() {
    for pkg in "$@"; do
        pkg_installed "$pkg" && return 0
    done
    return 1
}

# Helper: Find first available package from alternatives
find_available_pkg() {
    for pkg in "$@"; do
        if apt-cache show "$pkg" &>/dev/null 2>&1; then
            echo "$pkg"
            return 0
        fi
    done
    return 1
}

# Helper: Install packages with error handling
install_packages() {
    local packages=("$@")
    local failed=()

    for pkg in "${packages[@]}"; do
        if run_apt_get install -y "$pkg" >/dev/null 2>&1; then
            log_success "Installed: $pkg"
        else
            failed+=("$pkg")
        fi
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        return 1
    fi
    return 0
}

install_system_packages() {
    log_step 2 "Installing system packages..."

    # Detect system info
    local ARCH
    ARCH=$(uname -m)
    local IS_ARM=false
    [[ "$ARCH" == "arm"* || "$ARCH" == "aarch64" ]] && IS_ARM=true

    if [[ "$IS_ARM" == true ]]; then
        log_info "ARM architecture detected ($ARCH)"
    fi

    # -------------------------------------------------------------------------
    # Required packages definition (with alternatives for different distros)
    # Format: "primary|alternative1|alternative2" or just "package"
    # -------------------------------------------------------------------------
    local REQUIRED_SPECS=(
        "libgl1|libgl1-mesa-glx"                         # OpenGL library
        "curl"                                            # HTTP client
        "ca-certificates"                                 # HTTPS trust store
        "git"                                             # Verified source checkouts
        "lsof"                                            # List open files
        "make"                                            # Project task entry point
        "tmux"                                            # Terminal multiplexer
        "xz-utils"                                        # Node.js release archives
    )
    if [[ "$SETUP_PYTHON_SOURCE" != "existing PixEagle virtual environment" ]]; then
        REQUIRED_SPECS=(
            "python${PYTHON_VERSION}-venv|python3-venv"
            "python${PYTHON_VERSION}-dev|python3-dev"
            "${REQUIRED_SPECS[@]}"
        )
    fi

    # Optional ARM build packages (for compiling if no wheel available)
    local ARM_OPTIONAL_SPECS=(
        "libblas-dev|libatlas-base-dev"                  # BLAS library
        "liblapack-dev"                                   # LAPACK library
        "libopenblas-dev"                                 # OpenBLAS (optimized)
        "gfortran"                                        # Fortran compiler
    )

    # -------------------------------------------------------------------------
    # Check which packages are missing
    # -------------------------------------------------------------------------
    local MISSING_PKGS=()
    local pkg_to_install

    for spec in "${REQUIRED_SPECS[@]}"; do
        # Split spec by | to get alternatives
        IFS='|' read -ra alternatives <<< "$spec"

        # Check if any alternative is installed
        if ! any_pkg_installed "${alternatives[@]}"; then
            # Find first available alternative
            pkg_to_install=$(find_available_pkg "${alternatives[@]}")
            if [[ -n "$pkg_to_install" ]]; then
                MISSING_PKGS+=("$pkg_to_install")
            else
                # Fallback to first option (apt will show proper error)
                MISSING_PKGS+=("${alternatives[0]}")
            fi
        fi
    done

    # Check ARM optional packages
    local ARM_PKGS=()
    if [[ "$IS_ARM" == true ]]; then
        for spec in "${ARM_OPTIONAL_SPECS[@]}"; do
            IFS='|' read -ra alternatives <<< "$spec"
            if ! any_pkg_installed "${alternatives[@]}"; then
                pkg_to_install=$(find_available_pkg "${alternatives[@]}")
                [[ -n "$pkg_to_install" ]] && ARM_PKGS+=("$pkg_to_install")
            fi
        done
    fi

    # -------------------------------------------------------------------------
    # Install required packages
    # -------------------------------------------------------------------------
    if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
        log_info "Missing required packages: ${MISSING_PKGS[*]}"

        if ask_yes_no "        Install automatically? [Y/n]: "; then
            echo ""
            prompt_sudo

            log_info "Updating package lists..."
            if ! run_apt_get update; then
                log_error "Package-list update failed; required packages were not installed"
                log_detail "Check apt sources, DNS, proxy, and repository signatures, then rerun make init."
                exit 1
            fi

            log_info "Installing required packages..."
            if run_apt_get install -y "${MISSING_PKGS[@]}"; then
                log_success "Required packages installed"
            else
                log_error "Some packages failed to install"
                log_detail "Try manually: sudo apt install ${MISSING_PKGS[*]}"
                log_detail "Or check package names for your distribution"
                exit 1
            fi
        else
            log_error "Required packages not installed"
            log_detail "Install manually: sudo apt install ${MISSING_PKGS[*]}"
            exit 1
        fi
    else
        log_success "All required packages already installed"
    fi

    # -------------------------------------------------------------------------
    # Install optional ARM packages (non-fatal)
    # -------------------------------------------------------------------------
    if [[ ${#ARM_PKGS[@]} -gt 0 ]]; then
        echo ""
        log_info "Optional ARM build packages available: ${ARM_PKGS[*]}"
        log_detail "These help compile packages if no pre-built wheel exists"

        if ask_yes_no "        Install optional packages? [Y/n]: "; then
            echo ""
            local failed_pkgs=()
            for pkg in "${ARM_PKGS[@]}"; do
                if run_apt_get install -y "$pkg" >/dev/null 2>&1; then
                    log_success "Installed: $pkg"
                else
                    failed_pkgs+=("$pkg")
                fi
            done

            if [[ ${#failed_pkgs[@]} -gt 0 ]]; then
                log_warn "Some optional packages unavailable: ${failed_pkgs[*]}"
                log_detail "This is OK - pip will use pre-built wheels when available"
            fi
        else
            log_info "Skipped optional packages (pip will use pre-built wheels)"
        fi
    fi

    return 0
}

# ============================================================================
# Python Virtual Environment (Step 3)
# ============================================================================
create_venv() {
    log_step 3 "Creating Python virtual environment..."

    cd "$PIXEAGLE_DIR" || exit 1

    if [[ -z "$VENV_DIR" || "$VENV_DIR" == "/" || "$VENV_DIR" == "$PIXEAGLE_DIR" ]]; then
        log_error "Unsafe virtual-environment path: $VENV_DIR"
        log_detail "Set PIXEAGLE_VENV_DIR to a dedicated directory."
        exit 1
    fi

    if [[ -d "$VENV_DIR" ]] && [[ -f "$VENV_ACTIVATE" ]]; then
        log_info "Existing virtual environment found - reusing"
        log_success "Virtual environment ready"
        return 0
    fi

    # Remove corrupted venv if exists
    if [[ -d "$VENV_DIR" ]]; then
        if [[ -n "${PIXEAGLE_VENV_DIR:-}" ]]; then
            log_error "Configured virtual environment is incomplete: $VENV_DIR"
            log_detail "Remove or repair it explicitly; init will not delete a custom path."
            exit 1
        fi
        log_warn "Removing corrupted virtual environment directory..."
        rm -rf -- "$VENV_DIR"
    fi

    start_spinner "Creating venv..."
    if "$SETUP_PYTHON" -m venv "$VENV_DIR" 2>&1; then
        stop_spinner
    else
        stop_spinner
        log_error "Failed to create virtual environment"
        log_detail "Try: sudo apt install python${PYTHON_VERSION}-venv"
        exit 1
    fi

    # Validate venv was created correctly
    if [[ ! -f "$VENV_ACTIVATE" ]]; then
        log_error "Virtual environment creation failed (activate script missing)"
        log_detail "Remove '$VENV_DIR' and re-run"
        exit 1
    fi

    log_success "Virtual environment created"
}

# ============================================================================
# Python Dependencies (Step 4)
# ============================================================================

# Validate the sole OpenCV provider using the same contract as AI setup.
opencv_provider_fingerprint() {
    "$VENV_PYTHON" "$SCRIPTS_DIR/setup/opencv_provider_probe.py"
}

install_python_deps() {
    log_step 4 "Installing Python dependencies..."

    cd "$PIXEAGLE_DIR" || exit 1

    # Source the virtual environment
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"

    # Reset status flags for this run
    AI_VERIFY_PASSED=false
    PYTORCH_SETUP_PASSED=false
    PYTORCH_SETUP_SKIPPED=false
    PYTORCH_SETUP_FAILED=false

    # Show profile and strategy
    log_info "Installing packages from role-based requirements files"
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        log_info "Profile: Core (requirements-core.txt; AI packages skipped)"
    else
        log_info "Profile: Full (core first, AI packages installed in final phase)"
        log_warn "Large AI packages may take several minutes on slower links/devices"
    fi
    echo ""

    # Classify an existing provider before pip changes. A source/GStreamer
    # provider is preserved byte-for-byte; unmanaged overlays fail closed.
    local SKIP_OPENCV=false
    local OPENCV_BEFORE=""
    local opencv_provider_kind=""
    local opencv_wheel_owner=""
    if "$VENV_PYTHON" -c 'import cv2' >/dev/null 2>&1; then
        if ! OPENCV_BEFORE="$(opencv_provider_fingerprint)"; then
            log_error "Existing OpenCV provider is ambiguous or unsupported"
            log_detail "Use a fresh PixEagle venv; do not overlay another provider in place."
            exit 1
        fi
        opencv_provider_kind="$(printf '%s' "$OPENCV_BEFORE" | \
            "$VENV_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["provider_kind"])')"
        opencv_wheel_owner="$(printf '%s' "$OPENCV_BEFORE" | \
            "$VENV_PYTHON" -c 'import json,sys; print(next(iter(json.load(sys.stdin)["distribution_owners"]), ""))')"
        if [[ "$opencv_provider_kind" == "source_gstreamer" ]]; then
            if [[ "${PIXEAGLE_REPLACE_CUSTOM_OPENCV:-0}" == "1" ]]; then
                log_error "In-place source-to-wheel OpenCV replacement is not supported"
                log_detail "Create a fresh venv for the Core wheel, or keep this verified GStreamer provider."
                exit 1
            fi
            log_info "Preserving the verified source/GStreamer OpenCV provider"
            SKIP_OPENCV=true
        elif [[ "$opencv_wheel_owner" == "opencv-contrib-python" ]]; then
            log_info "Preserving the verified custom GUI contrib wheel"
            SKIP_OPENCV=true
        else
            log_info "Existing Core headless contrib wheel will be reconciled from requirements-core.txt"
        fi
    fi

    # Upgrade pip first
    echo -e "        ${DIM}Upgrading pip...${NC}"
    "$VENV_PIP" install --no-warn-conflicts --upgrade pip -q 2>&1 || true

    # -------------------------------
    # Phase A: Install core packages
    # -------------------------------
    local core_req_source="requirements-core.txt"
    local core_req_file="$core_req_source"
    local core_req_temp=false
    if [[ ! -f "$core_req_source" ]]; then
        log_warn "requirements-core.txt not found; falling back to legacy requirements.txt filtering"
        core_req_source="requirements.txt"
        core_req_file=$(mktemp)
        core_req_temp=true
        grep -v -iE "ultralytics|ncnn|lap|pnnx|pytest|httpx|ipython" "$core_req_source" > "$core_req_file"
    fi
    if [[ "$SKIP_OPENCV" == true ]]; then
        local filtered_core_req_file
        filtered_core_req_file=$(mktemp)
        core_req_temp=true
        grep -v -iE "opencv" "$core_req_file" > "$filtered_core_req_file"
        if [[ "$core_req_file" != "$core_req_source" && -f "$core_req_file" ]]; then
            rm -f "$core_req_file"
        fi
        core_req_file="$filtered_core_req_file"
    fi

    local core_count
    core_count=$(grep -c -E '^[^#[:space:]]' "$core_req_file" 2>/dev/null || echo "0")
    log_info "Phase A/2: Installing ${core_count} core packages from $(basename "$core_req_source")"
    log_detail "AI packages are installed separately at the end in Full profile"
    log_detail "Dependency conflicts are reported by the completed-phase policy check, not intermediate pip state"

    if ! "$VENV_PIP" install --no-warn-conflicts -r "$core_req_file"; then
        [[ "$core_req_temp" == true ]] && rm -f "$core_req_file"
        log_error "Core dependency installation failed"
        log_detail "Retry with: make init"
        log_detail "For manual setup, use the core-first dependency flow in docs/INSTALLATION.md"
        deactivate
        exit 1
    fi
    [[ "$core_req_temp" == true ]] && rm -f "$core_req_file"

    # Verify core dependencies
    local OPENCV_AFTER=""
    if "$VENV_PYTHON" -c "import cv2; import numpy" 2>/dev/null \
        && OPENCV_AFTER="$(opencv_provider_fingerprint)"; then
        if [[ "$SKIP_OPENCV" == true ]]; then
            if [[ "$OPENCV_AFTER" != "$OPENCV_BEFORE" ]]; then
                log_error "Core setup changed the preserved OpenCV provider"
                log_detail "Restore the transaction backup and inspect dependency ownership."
                deactivate
                exit 1
            fi
            log_success "Core packages installed; selected OpenCV provider fingerprint preserved"
        else
            log_success "Core packages installed with one validated OpenCV provider"
        fi
    else
        log_error "Core packages (opencv, numpy) not installed correctly"
        log_detail "Retry with: make init"
        log_detail "For manual setup, use the core-first dependency flow in docs/INSTALLATION.md"
        deactivate
        exit 1
    fi

    # A resolver inconsistency is not a ready Core environment.
    if ! "$VENV_PYTHON" "$SCRIPTS_DIR/setup/pip_check_policy.py"; then
        log_error "Python dependency consistency check failed"
        deactivate
        exit 1
    fi

    # Core profile ends here
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        log_detail "To add AI features later:"
        log_detail "bash scripts/setup/setup-pytorch.sh --mode auto"
        log_detail "bash scripts/setup/install-ai-deps.sh"
        log_detail "bash scripts/setup/check-ai-runtime.sh --require-smart-tracker"
        deactivate
        return 0
    fi

    # -------------------------------
    # Phase B: Install AI packages
    # -------------------------------
    local pytorch_setup_script="$PIXEAGLE_DIR/scripts/setup/setup-pytorch.sh"
    if [[ ! -f "$pytorch_setup_script" ]]; then
        PYTORCH_SETUP_FAILED=true
        log_error "Required Full-profile helper is missing: scripts/setup/setup-pytorch.sh"
        deactivate
        return 1
    fi

    echo ""
    log_info "Phase B/2: Installing and verifying the platform PyTorch runtime"
    if bash "$pytorch_setup_script" --mode auto --non-interactive --accept-existing-verified; then
        PYTORCH_SETUP_PASSED=true
        log_success "Platform PyTorch runtime installed and verified"
    else
        PYTORCH_SETUP_FAILED=true
        log_error "Full profile stopped because PyTorch setup did not validate"
        log_detail "CPU hosts are handled automatically. Unsupported Jetson profiles require digest-verified wheel overrides."
        log_detail "Review: bash scripts/setup/setup-pytorch.sh --help"
        deactivate
        return 1
    fi

    echo ""
    log_info "Phase B/2: Installing AI packages (Ultralytics and tracking dependencies)"
    log_warn "Using the guarded AI installer to preserve the exact OpenCV provider"

    local ai_setup_script="$PIXEAGLE_DIR/scripts/setup/install-ai-deps.sh"
    if [[ ! -f "$ai_setup_script" ]]; then
        log_error "Required AI setup helper is missing: scripts/setup/install-ai-deps.sh"
        deactivate
        return 1
    fi
    if bash "$ai_setup_script"; then
        AI_VERIFY_PASSED=true
        log_success "Full AI dependencies installed and verified (ultralytics + lap)"
    else
        log_error "Full profile stopped because AI dependency verification failed"
        deactivate
        return 1
    fi

    local ai_runtime_check="$PIXEAGLE_DIR/scripts/setup/check-ai-runtime.sh"
    if [[ -x "$ai_runtime_check" ]] && \
       bash "$ai_runtime_check" --json --require-smart-tracker >/dev/null; then
        SMART_TRACKER_STATE="ready"
        SMART_TRACKER_DETAIL="dependencies and configured model load verified"
    else
        SMART_TRACKER_STATE="manual_follow_up"
        SMART_TRACKER_DETAIL="dependencies ready; add a local detect/OBB model, then rerun check-ai-runtime.sh"
    fi

    deactivate
}

# ============================================================================
# Node.js Setup via nvm (Step 5)
# ============================================================================
install_verified_nvm() (
    umask 077
    local final_nvm_dir="${NVM_DIR:-$HOME/.nvm}"
    local staging_root installer staged_nvm installed_head installer_log

    staging_root="$(mktemp -d "$HOME/.pixeagle-nvm-install.XXXXXX")" || exit 9
    trap 'rm -rf -- "$staging_root"' EXIT
    installer="$staging_root/install.sh"
    staged_nvm="$staging_root/nvm"
    installer_log="$staging_root/install.log"

    # nvm treats an explicitly configured but absent NVM_DIR as a user error.
    # Create the private destination before invoking the verified installer.
    mkdir -m 0700 -- "$staged_nvm" || exit 9

    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
        --output "$installer" "$NVM_INSTALL_URL" || exit 10
    printf '%s  %s\n' "$NVM_INSTALL_SHA256" "$installer" | \
        sha256sum --check --status || exit 11

    PROFILE=/dev/null NVM_DIR="$staged_nvm" \
        NVM_INSTALL_VERSION="$NVM_INSTALL_COMMIT" \
        bash "$installer" >"$installer_log" 2>&1 || {
            printf 'Verified nvm installer output (last 20 lines):\n' >&2
            tail -n 20 -- "$installer_log" >&2 || true
            exit 12
        }
    [[ -s "$staged_nvm/nvm.sh" && -d "$staged_nvm/.git" ]] || exit 13
    installed_head="$(git -C "$staged_nvm" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" || exit 13
    [[ "$installed_head" == "$NVM_INSTALL_COMMIT" ]] || exit 13

    [[ ! -e "$final_nvm_dir" && ! -L "$final_nvm_dir" ]] || exit 14
    mv -- "$staged_nvm" "$final_nvm_dir" || exit 14
)

nvm_checkout_is_pinned() {
    local nvm_dir="${1:-${NVM_DIR:-$HOME/.nvm}}"
    [[ -s "$nvm_dir/nvm.sh" && -d "$nvm_dir/.git" ]] || return 1
    [[ "$(git -C "$nvm_dir" rev-parse --verify 'HEAD^{commit}' 2>/dev/null)" == \
       "$NVM_INSTALL_COMMIT" ]]
}

node_runtime_meets_requirement() {
    command -v node >/dev/null 2>&1 || return 1
    command -v npm >/dev/null 2>&1 || return 1
    local current_major required_major npm_major
    current_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null)" || return 1
    required_major="${NODE_VERSION%%.*}"
    npm_major="$(npm --version 2>/dev/null | cut -d. -f1)" || return 1
    [[ "$current_major" =~ ^[0-9]+$ && "$required_major" =~ ^[0-9]+$ ]] || return 1
    [[ "$npm_major" =~ ^[0-9]+$ ]] || return 1
    (( current_major == required_major && npm_major >= 10 && npm_major < 12 ))
}

setup_nodejs() {
    log_step 5 "Setting up Node.js via nvm..."
    NODE_SETUP_STATE="pending"
    NODE_SETUP_DETAIL="Node.js setup started"

    if [[ -z "$NODE_VERSION" ]] && ! load_node_runtime_policy; then
        NODE_SETUP_STATE="manual_follow_up"
        NODE_SETUP_DETAIL=".nvmrc Node.js contract is missing or invalid"
        return 1
    fi

    # Set up NVM_DIR
    export NVM_DIR="$HOME/.nvm"

    if node_runtime_meets_requirement; then
        log_success "Existing Node.js $(node -v) and npm $(npm -v) satisfy the dashboard requirement"
        NODE_SETUP_STATE="ready"
        NODE_SETUP_DETAIL="Node.js $(node -v) from existing PATH"
        return 0
    fi

    # Check if nvm already installed
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        if ! nvm_checkout_is_pinned "$NVM_DIR"; then
            log_error "Existing nvm checkout is not the reviewed PixEagle pin"
            log_detail "Provide Node.js ${NODE_VERSION}.x on PATH or move $NVM_DIR aside and rerun"
            NODE_SETUP_STATE="manual_follow_up"
            NODE_SETUP_DETAIL="existing nvm provenance does not match the reviewed commit"
            return 1
        fi
        # shellcheck source=/dev/null
        source "$NVM_DIR/nvm.sh"
        log_info "Using verified nvm checkout ($(nvm --version))"
    else
        local nvm_install_status=0
        log_info "Installing nvm ${NVM_VERSION} from verified commit ${NVM_INSTALL_COMMIT}..."
        start_spinner "Downloading and verifying nvm..."
        install_verified_nvm || nvm_install_status=$?
        stop_spinner

        if (( nvm_install_status != 0 )); then
            case "$nvm_install_status" in
                9)  log_error "Could not create private nvm staging under HOME" ;;
                10) log_error "Pinned nvm installer download failed" ;;
                11) log_error "Pinned nvm installer SHA-256 verification failed" ;;
                12) log_error "Verified nvm installer could not stage the exact nvm commit" ;;
                13) log_error "Staged nvm checkout did not match the pinned commit" ;;
                14) log_error "The final nvm path changed during staging; refusing to overwrite it" ;;
                *)  log_error "Verified nvm setup failed (status $nvm_install_status)" ;;
            esac
            log_detail "No staged nvm content was published to $NVM_DIR"
            log_detail "Review network/proxy and HOME ownership, then re-run this script"
            NODE_SETUP_STATE="manual_follow_up"
            NODE_SETUP_DETAIL="verified nvm setup failed before publication"
            return 1
        fi

        # shellcheck source=/dev/null
        source "$NVM_DIR/nvm.sh"
        if command -v nvm &>/dev/null; then
            log_success "nvm installed at verified commit $NVM_INSTALL_COMMIT"
        else
            log_error "Verified nvm checkout was published but is not loadable"
            NODE_SETUP_STATE="manual_follow_up"
            NODE_SETUP_DETAIL="verified nvm checkout exists but nvm is not loadable"
            return 1
        fi
    fi

    # Check whether the verified nvm checkout already exposes a suitable Node.js.
    if node_runtime_meets_requirement; then
        local current_version
        current_version=$(node -v)
        log_info "Node.js ${current_version} already installed"
        log_success "Node.js ready"
        NODE_SETUP_STATE="ready"
        NODE_SETUP_DETAIL="Node.js ${current_version}"
        return 0
    fi

    # Install Node.js
    log_info "Installing Node.js ${NODE_VERSION}..."
    start_spinner "Installing Node.js..."
    local node_install_log=""
    node_install_log="$(mktemp "${TMPDIR:-/tmp}/pixeagle-node-install.XXXXXX")" || {
        stop_spinner
        log_error "Could not create a private Node.js setup log"
        NODE_SETUP_STATE="manual_follow_up"
        NODE_SETUP_DETAIL="could not create Node.js setup log"
        return 1
    }
    chmod 0600 -- "$node_install_log"

    if nvm install "$NODE_VERSION" >"$node_install_log" 2>&1 \
        && nvm alias default "$NODE_VERSION" >>"$node_install_log" 2>&1 \
        && nvm use "$NODE_VERSION" >>"$node_install_log" 2>&1 \
        && node_runtime_meets_requirement; then
        stop_spinner
        rm -f -- "$node_install_log"
        log_success "Node.js $(node -v) with npm $(npm -v) installed"
        NODE_SETUP_STATE="ready"
        NODE_SETUP_DETAIL="Node.js $(node -v)"
    else
        stop_spinner
        log_error "Node.js installation failed"
        log_detail "nvm output (last 20 lines):"
        tail -n 20 -- "$node_install_log" 2>/dev/null || true
        rm -f -- "$node_install_log"
        log_detail "Check network/proxy, disk space, and xz-utils; then rerun make init."
        NODE_SETUP_STATE="manual_follow_up"
        NODE_SETUP_DETAIL="Node.js ${NODE_VERSION} installation failed; exact nvm output was printed above"
        return 1
    fi
}

# ============================================================================
# Dashboard Dependencies (Step 6)
# ============================================================================
install_dashboard_deps() {
    log_step 6 "Installing dashboard dependencies..."
    DASHBOARD_DEPS_STATE="pending"
    DASHBOARD_DEPS_DETAIL="dashboard dependency setup started"

    cd "$PIXEAGLE_DIR" || exit 1

    if [[ ! -d "dashboard" ]]; then
        log_warn "Dashboard directory not found - skipping"
        DASHBOARD_DEPS_STATE="skipped"
        DASHBOARD_DEPS_DETAIL="dashboard directory not found"
        return 0
    fi

    # Load nvm only when npm is not already supplied by the reviewed host PATH.
    export NVM_DIR="$HOME/.nvm"
    if ! command -v npm >/dev/null 2>&1 && [[ -s "$NVM_DIR/nvm.sh" ]]; then
        if ! nvm_checkout_is_pinned "$NVM_DIR"; then
            log_warn "Refusing to source an unverified nvm checkout"
            DASHBOARD_DEPS_STATE="manual_follow_up"
            DASHBOARD_DEPS_DETAIL="nvm provenance mismatch; npm unavailable"
            return 1
        fi
        # shellcheck source=/dev/null
        source "$NVM_DIR/nvm.sh"
    fi

    if ! command -v npm &>/dev/null; then
        log_warn "npm not available - skipping dashboard setup"
        log_detail "Install Node.js first, then run: cd dashboard && npm ci"
        DASHBOARD_DEPS_STATE="manual_follow_up"
        DASHBOARD_DEPS_DETAIL="npm unavailable; install Node.js/npm, then run cd dashboard && npm ci"
        return 1
    fi

    if ! cd dashboard; then
        DASHBOARD_DEPS_STATE="degraded"
        DASHBOARD_DEPS_DETAIL="could not enter dashboard directory"
        return 1
    fi

    if pixeagle_dashboard_dependencies_ready "$PIXEAGLE_DIR/dashboard"; then
        log_success "Dashboard dependencies already match the lockfile"
        log_detail "Reused the existing dependency tree after a full offline npm validation."
        DASHBOARD_DEPS_STATE="ready"
        DASHBOARD_DEPS_DETAIL="existing lockfile-matched dependency tree verified and reused"
        cd "$PIXEAGLE_DIR" || return 1
        return 0
    fi

    if [[ -d "node_modules" ]]; then
        log_info "Dashboard dependency state is incomplete or outdated"
        log_detail "Running one clean lockfile reconciliation; npm ci replaces node_modules by design."
    else
        log_info "No verified dashboard dependency tree found"
    fi

    start_spinner "Reconciling npm packages from package-lock.json..."
    if npm ci --silent --no-audit --no-fund 2>&1; then
        stop_spinner
        log_success "Dashboard dependencies installed"
        if ! pixeagle_record_dashboard_dependency_fingerprint "$PIXEAGLE_DIR/dashboard"; then
            log_warn "Dashboard dependency cache could not be recorded"
            log_detail "The verified install remains usable; a later repair may run npm ci again."
        fi
        DASHBOARD_DEPS_STATE="ready"
        DASHBOARD_DEPS_DETAIL="npm dependencies reconciled from package-lock.json"
    else
        stop_spinner
        log_warn "npm ci failed"
        log_detail "Resolve the lockfile or registry error, then rerun: cd dashboard && npm ci"
        DASHBOARD_DEPS_STATE="degraded"
        DASHBOARD_DEPS_DETAIL="npm ci failed; preserve package-lock.json and inspect npm output"
        cd "$PIXEAGLE_DIR" || return 1
        return 1
    fi

    cd "$PIXEAGLE_DIR" || return 1
}

# ============================================================================
# Configuration Defaults (Step 7)
# ============================================================================
generate_env_from_yaml() {
    local yaml_file="$1"
    local env_file="$2"
    local conversion_status=0

    cd "$PIXEAGLE_DIR" || exit 1

    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"
    python3 << PYEOF
import yaml

config_file = "$yaml_file"
env_file = "$env_file"

with open(config_file, 'r') as f:
    config = yaml.safe_load(f)

with open(env_file, 'w') as f:
    for key, value in config.items():
        f.write(f"{key}={value}\n")
PYEOF
    conversion_status=$?
    deactivate
    return "$conversion_status"
}

setup_configs() {
    log_step 7 "Preparing configuration defaults..."
    CONFIG_DEFAULTS_STATE="pending"
    CONFIG_DEFAULTS_DETAIL="configuration check started"
    DASHBOARD_ENV_STATE="pending"
    DASHBOARD_ENV_DETAIL="dashboard env check started"

    local CONFIG_DIR="$PIXEAGLE_DIR/configs"
    local DEFAULT_CONFIG="$CONFIG_DIR/config_default.yaml"
    local USER_CONFIG="$CONFIG_DIR/config.yaml"
    local DASHBOARD_DIR="$PIXEAGLE_DIR/dashboard"
    local DASHBOARD_DEFAULT_CONFIG="$DASHBOARD_DIR/env_default.yaml"
    local DASHBOARD_ENV_FILE="$DASHBOARD_DIR/.env"
    local STAGED_DEFAULTS="$CONFIG_DIR/.config_default_preupdate.yaml"
    local CONFIG_SYNC_SCRIPT="$PIXEAGLE_DIR/scripts/setup/config-sync-status.py"
    local config_sync_python=""
    local config_sync_ready=true
    local config_sync_failure_detail="config lifecycle check did not complete"

    # Create configs directory if needed
    if [[ ! -d "$CONFIG_DIR" ]]; then
        mkdir -p "$CONFIG_DIR"
        log_info "Created configs directory"
    fi

    # Main config
    if [[ ! -f "$DEFAULT_CONFIG" ]]; then
        log_error "Default config not found: $DEFAULT_CONFIG"
        CONFIG_DEFAULTS_STATE="degraded"
        CONFIG_DEFAULTS_DETAIL="configs/config_default.yaml missing"
        return 1
    fi

    if [[ -f "$USER_CONFIG" ]]; then
        log_info "Keeping existing configs/config.yaml"
        log_detail "Use make reset-config or make setup-profile when you intentionally want a new local runtime config"
        CONFIG_DEFAULTS_STATE="ready"
        CONFIG_DEFAULTS_DETAIL="existing configs/config.yaml kept"
    else
        log_success "Using checked-in defaults from configs/config_default.yaml"
        log_detail "No configs/config.yaml created; setup profiles create local overrides only when needed"
        CONFIG_DEFAULTS_STATE="ready"
        CONFIG_DEFAULTS_DETAIL="using checked-in configs/config_default.yaml"
    fi

    if ! declare -F resolve_pixeagle_venv_python >/dev/null 2>&1; then
        config_sync_ready=false
        config_sync_failure_detail="shared virtual-environment resolver unavailable"
        log_warn "Config lifecycle helper is unavailable"
    else
        config_sync_python="$(resolve_pixeagle_venv_python "$PIXEAGLE_DIR")"
    fi

    if [[ "$config_sync_ready" == true && ! -x "$config_sync_python" ]]; then
        config_sync_ready=false
        config_sync_failure_detail="virtual-environment Python unavailable"
        log_warn "Config lifecycle Python is unavailable"
    fi
    if [[ "$config_sync_ready" == true && ! -f "$CONFIG_SYNC_SCRIPT" ]]; then
        config_sync_ready=false
        config_sync_failure_detail="config lifecycle status script unavailable"
        log_warn "Config lifecycle status script is unavailable"
    fi

    if [[ "$config_sync_ready" == true ]]; then
        if [[ -e "$STAGED_DEFAULTS" || -L "$STAGED_DEFAULTS" ]]; then
            if [[ ! -f "$STAGED_DEFAULTS" || -L "$STAGED_DEFAULTS" ]]; then
                config_sync_ready=false
                config_sync_failure_detail="pending pre-update defaults are unsafe"
                log_warn "Pending pre-update defaults are not a regular file"
            elif "$config_sync_python" "$CONFIG_SYNC_SCRIPT" \
                --initialize-baseline-from "$STAGED_DEFAULTS"; then
                if rm -f -- "$STAGED_DEFAULTS" &&
                   [[ ! -e "$STAGED_DEFAULTS" && ! -L "$STAGED_DEFAULTS" ]]; then
                    log_success "Pre-update config baseline consumed"
                else
                    config_sync_ready=false
                    config_sync_failure_detail="consumed pre-update staging file could not be removed"
                    log_warn "Consumed config baseline could not be removed"
                fi
            else
                config_sync_ready=false
                config_sync_failure_detail="pre-update baseline consumption or report failed"
                log_warn "Could not consume the preserved pre-update config baseline"
            fi
        elif "$config_sync_python" "$CONFIG_SYNC_SCRIPT" --initialize-baseline; then
            log_success "Config update baseline and retirement status checked"
        else
            config_sync_ready=false
            config_sync_failure_detail="fresh defaults baseline initialization or report failed"
            log_warn "Could not initialize or report config update metadata"
        fi
    fi

    if [[ "$config_sync_ready" != true ]]; then
        CONFIG_DEFAULTS_STATE="degraded"
        CONFIG_DEFAULTS_DETAIL="$config_sync_failure_detail"
        log_detail "Fix the reported issue, then rerun make init."
    fi

    # Dashboard .env
    if [[ -f "$DASHBOARD_DEFAULT_CONFIG" ]]; then
        if [[ -f "$DASHBOARD_ENV_FILE" ]]; then
            # Existing .env found - ask user what to do
            echo ""
            echo -e "        ${YELLOW}WARNING: Existing dashboard/.env found${NC}"
            echo -e "        ${DIM}New releases may include new dashboard settings.${NC}"

            if ask_yes_no "        Replace with latest default? [y/N]: " "n"; then
                # Backup existing .env
                local backup_name
                backup_name="${DASHBOARD_ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
                cp "$DASHBOARD_ENV_FILE" "$backup_name"
                if generate_env_from_yaml "$DASHBOARD_DEFAULT_CONFIG" "$DASHBOARD_ENV_FILE"; then
                    log_success "Replaced dashboard/.env (backup: ${backup_name##*/})"
                    DASHBOARD_ENV_STATE="ready"
                    DASHBOARD_ENV_DETAIL="replaced dashboard/.env; backup ${backup_name##*/}"
                else
                    log_warn "Could not regenerate dashboard/.env"
                    log_detail "Retry later with the dashboard env conversion in docs/INSTALLATION.md"
                    DASHBOARD_ENV_STATE="degraded"
                    DASHBOARD_ENV_DETAIL="dashboard/.env regeneration failed; use docs/INSTALLATION.md conversion"
                    return 1
                fi
            else
                log_info "Keeping existing dashboard/.env"
                DASHBOARD_ENV_STATE="ready"
                DASHBOARD_ENV_DETAIL="existing dashboard/.env kept"
            fi
        else
            # No existing .env - create new one
            if generate_env_from_yaml "$DASHBOARD_DEFAULT_CONFIG" "$DASHBOARD_ENV_FILE"; then
                log_success "Created dashboard/.env"
                DASHBOARD_ENV_STATE="ready"
                DASHBOARD_ENV_DETAIL="created dashboard/.env from env_default.yaml"
            else
                log_warn "Could not create dashboard/.env"
                log_detail "Retry later with the dashboard env conversion in docs/INSTALLATION.md"
                DASHBOARD_ENV_STATE="degraded"
                DASHBOARD_ENV_DETAIL="dashboard/.env creation failed; use docs/INSTALLATION.md conversion"
                return 1
            fi
        fi
    else
        log_warn "Dashboard env_default.yaml not found"
        DASHBOARD_ENV_STATE="manual_follow_up"
        DASHBOARD_ENV_DETAIL="dashboard/env_default.yaml missing; create dashboard/.env manually"
    fi
}

# ============================================================================
# MAVSDK Server Setup (Step 8)
# ============================================================================
setup_mavsdk_server() {
    log_step 8 "Setting up MAVSDK Server..."
    MAVSDK_BINARY_STATE="pending"
    MAVSDK_BINARY_DETAIL="MAVSDK Server binary check started"

    local mavsdk_binary="$PIXEAGLE_DIR/bin/mavsdk_server_bin"
    local download_script="$SCRIPTS_DIR/setup/download-binaries.sh"

    # Check if download script exists
    if [[ ! -f "$download_script" ]]; then
        log_warn "Binary download script not found"
        log_detail "Skipping MAVSDK Server setup"
        MAVSDK_BINARY_STATE="manual_follow_up"
        MAVSDK_BINARY_DETAIL="download script missing; install mavsdk_server_bin manually"
        return 1
    fi

    if [[ -f "$mavsdk_binary" ]] && [[ -x "$mavsdk_binary" ]]; then
        log_info "MAVSDK Server binary exists; verifying manifest checksum"
        if bash "$download_script" --mavsdk; then
            log_success "MAVSDK Server binary verified"
            MAVSDK_BINARY_STATE="ready"
            MAVSDK_BINARY_DETAIL="manifest checksum verified"
            return 0
        fi
        log_warn "Existing MAVSDK Server binary failed verification"
        MAVSDK_BINARY_STATE="degraded"
        MAVSDK_BINARY_DETAIL="existing binary failed manifest verification"
        return 1
    fi

    # Prompt user
    echo ""
    echo -e "        ${BLUE}${INFO}${NC}  MAVSDK Server is required for drone communication"

    if ask_yes_no "        Download MAVSDK Server now? [Y/n]: " "y"; then
        # Run download script with mavsdk flag
        if bash "$download_script" --mavsdk; then
            log_success "MAVSDK Server downloaded and verified"
            MAVSDK_BINARY_STATE="ready"
            MAVSDK_BINARY_DETAIL="downloaded and checksum verified"
            return 0
        else
            log_warn "MAVSDK Server installation failed (non-fatal)"
            log_detail "Download later: bash scripts/setup/download-binaries.sh --mavsdk"
            MAVSDK_BINARY_STATE="degraded"
            MAVSDK_BINARY_DETAIL="download or checksum verification failed; retry download-binaries.sh --mavsdk"
            return 1
        fi
    else
        log_info "MAVSDK Server download skipped"
        log_detail "Download later: bash scripts/setup/download-binaries.sh --mavsdk"
        MAVSDK_BINARY_STATE="skipped"
        MAVSDK_BINARY_DETAIL="operator skipped download; run download-binaries.sh --mavsdk before PX4/MAVSDK use"
        return 1
    fi
}

# ============================================================================
# MAVLink2REST Server Setup (Step 9)
# ============================================================================
setup_mavlink2rest() {
    log_step 9 "Setting up MAVLink2REST Server..."
    MAVLINK2REST_BINARY_STATE="pending"
    MAVLINK2REST_BINARY_DETAIL="MAVLink2REST binary check started"

    local mavlink2rest_binary="$PIXEAGLE_DIR/bin/mavlink2rest"
    local download_script="$SCRIPTS_DIR/setup/download-binaries.sh"

    # Check if download script exists
    if [[ ! -f "$download_script" ]]; then
        log_warn "Binary download script not found"
        log_detail "Skipping MAVLink2REST Server setup"
        MAVLINK2REST_BINARY_STATE="manual_follow_up"
        MAVLINK2REST_BINARY_DETAIL="download script missing; install mavlink2rest manually"
        return 1
    fi

    if [[ -f "$mavlink2rest_binary" ]] && [[ -x "$mavlink2rest_binary" ]]; then
        log_info "MAVLink2REST binary exists; verifying manifest checksum"
        if bash "$download_script" --mavlink2rest; then
            log_success "MAVLink2REST binary verified"
            MAVLINK2REST_BINARY_STATE="ready"
            MAVLINK2REST_BINARY_DETAIL="manifest checksum verified"
            return 0
        fi
        log_warn "Existing MAVLink2REST binary failed verification"
        MAVLINK2REST_BINARY_STATE="degraded"
        MAVLINK2REST_BINARY_DETAIL="existing binary failed manifest verification"
        return 1
    fi

    # Prompt user
    echo ""
    echo -e "        ${BLUE}${INFO}${NC}  MAVLink2REST provides REST API access to MAVLink telemetry"

    if ask_yes_no "        Download MAVLink2REST Server now? [Y/n]: " "y"; then
        # Run download script with mavlink2rest flag
        if bash "$download_script" --mavlink2rest; then
            log_success "MAVLink2REST Server downloaded and verified"
            MAVLINK2REST_BINARY_STATE="ready"
            MAVLINK2REST_BINARY_DETAIL="downloaded and checksum verified"
            return 0
        else
            log_warn "MAVLink2REST Server installation failed (non-fatal)"
            log_detail "Download later: bash scripts/setup/download-binaries.sh --mavlink2rest"
            MAVLINK2REST_BINARY_STATE="degraded"
            MAVLINK2REST_BINARY_DETAIL="download or checksum verification failed; retry download-binaries.sh --mavlink2rest"
            return 1
        fi
    else
        log_info "MAVLink2REST Server download skipped"
        log_detail "Download later: bash scripts/setup/download-binaries.sh --mavlink2rest"
        MAVLINK2REST_BINARY_STATE="skipped"
        MAVLINK2REST_BINARY_DETAIL="operator skipped download; run download-binaries.sh --mavlink2rest before telemetry use"
        return 1
    fi
}

# ============================================================================
# Summary Display
# ============================================================================
summary_status_line() {
    local state="$1"
    local label="$2"
    local detail="${3:-}"

    case "$state" in
        ready)
            echo -e "   ${GREEN}${CHECK}${NC} ${label} ${DIM}${detail}${NC}"
            ;;
        skipped)
            echo -e "   ${BLUE}${INFO}${NC} ${label} ${DIM}(skipped: ${detail})${NC}"
            ;;
        degraded)
            echo -e "   ${YELLOW}${WARN}${NC}  ${label} ${DIM}(degraded: ${detail})${NC}"
            ;;
        manual_follow_up)
            echo -e "   ${YELLOW}${WARN}${NC}  ${label} ${DIM}(manual follow-up: ${detail})${NC}"
            ;;
        *)
            echo -e "   ${YELLOW}${WARN}${NC}  ${label} ${DIM}(not verified: ${detail})${NC}"
            ;;
    esac
}

show_summary() {
    local project_cmd_dir
    printf -v project_cmd_dir '%q' "$PIXEAGLE_DIR"
    echo ""
    echo -e "${CYAN}============================================================================${NC}"
    echo -e "                       ${PARTY} ${BOLD}Installation Summary${NC} ${PARTY}"
    echo -e "${CYAN}============================================================================${NC}"
    echo ""
    summary_status_line "ready" "Python ${PYTHON_FULL_VERSION} virtual environment" "created or reused"
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        summary_status_line "ready" "Core Python dependencies" "AI packages skipped by Core profile"
    else
        if [[ "$AI_VERIFY_PASSED" == true ]]; then
            summary_status_line "ready" "Full Python dependencies" "including AI/YOLO"
        else
            summary_status_line "degraded" "Python dependencies" "AI install incomplete; inspect the installer output and rerun"
        fi
        if [[ "$PYTORCH_SETUP_PASSED" == true ]]; then
            summary_status_line "ready" "Automated PyTorch setup" "accelerator profile resolved"
        elif [[ "$PYTORCH_SETUP_FAILED" == true ]]; then
            summary_status_line "degraded" "Automated PyTorch setup" "retry with setup-pytorch.sh"
        elif [[ "$PYTORCH_SETUP_SKIPPED" == true ]]; then
            summary_status_line "skipped" "Automated PyTorch setup" "run setup-pytorch.sh when ready"
        fi
        summary_status_line "$SMART_TRACKER_STATE" "SmartTracker runtime" "$SMART_TRACKER_DETAIL"
    fi
    summary_status_line "$NODE_SETUP_STATE" "Node.js" "$NODE_SETUP_DETAIL"
    summary_status_line "$DASHBOARD_DEPS_STATE" "Dashboard dependencies" "$DASHBOARD_DEPS_DETAIL"
    summary_status_line "$CONFIG_DEFAULTS_STATE" "Configuration defaults" "$CONFIG_DEFAULTS_DETAIL"
    summary_status_line "$DASHBOARD_ENV_STATE" "Dashboard .env" "$DASHBOARD_ENV_DETAIL"
    summary_status_line "$MAVSDK_BINARY_STATE" "MAVSDK Server binary" "$MAVSDK_BINARY_DETAIL"
    summary_status_line "$MAVLINK2REST_BINARY_STATE" "MAVLink2REST binary" "$MAVLINK2REST_BINARY_DETAIL"
    if [[ -n "${OPTIONAL_COMPONENT_SELECTION:-}" ]]; then
        echo ""
        echo -e "   ${CYAN}${BOLD}Selected optional components:${NC}"
        optional_component_selected dlib && \
            summary_status_line "$OPTIONAL_DLIB_STATE" "dlib tracker backend" "$OPTIONAL_DLIB_DETAIL"
        optional_component_selected gstreamer && \
            summary_status_line "$OPTIONAL_GSTREAMER_STATE" "OpenCV GStreamer provider" "$OPTIONAL_GSTREAMER_DETAIL"
        optional_component_selected shell-shortcut && \
            summary_status_line "$OPTIONAL_SHORTCUT_STATE" "Bash pixeagle shortcut" "$OPTIONAL_SHORTCUT_DETAIL"
    fi
    echo ""
    echo -e "   ${CYAN}${BOLD}Next Steps:${NC}"
    if [[ "$DASHBOARD_DEPS_STATE" == "ready" ]] && [[ "$CONFIG_DEFAULTS_STATE" == "ready" ]] && [[ "$DASHBOARD_ENV_STATE" == "ready" ]]; then
        echo -e "      1. Local verification: ${BOLD}cd $project_cmd_dir && make demo${NC} (bundled video; no PX4 commands)"
        echo -e "      2. Manual configured runtime: ${BOLD}cd $project_cmd_dir && make run${NC}"
        echo -e "      3. Manual background runtime: ${BOLD}cd $project_cmd_dir && bash scripts/run.sh --no-attach${NC}"
        echo -e "      4. Optional managed runtime: ${BOLD}sudo bash $project_cmd_dir/scripts/service/install.sh${NC}"
    else
        echo -e "      1. Resolve any ${BOLD}manual follow-up${NC} or ${BOLD}degraded${NC} items above."
        echo -e "      2. Re-run: ${BOLD}cd $project_cmd_dir && make init${NC}"
        echo -e "      3. Start PixEagle only after the required components report ready."
    fi
    echo ""
    echo -e "   ${CYAN}${BOLD}Dashboard Access:${NC}"
    echo -e "      - Fresh default: ${BOLD}http://127.0.0.1:3040${NC} (local-only; no account is created)"
    echo -e "      - Fresh Core setup stays local-only; the explicit browser lab asks for credentials and defaults to ${BOLD}admin/admin${NC} on Enter."
    echo -e "      - Trusted remote lab: ${BOLD}cd $project_cmd_dir && make quick-browser-demo LAN_HOST=<device-ip>${NC}"
    echo -e "        ${DIM}It asks for credentials; Enter keeps admin/admin. Use DEMO_CREDENTIAL_MODE=generated for a one-time password.${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}Add or change optional capabilities later:${NC}"
    echo -e "      - dlib: ${BOLD}bash scripts/setup/install-dlib.sh${NC}"
    echo -e "      - GStreamer: ${BOLD}bash scripts/setup/build-opencv.sh${NC}, then ${BOLD}make check-gstreamer-runtime${NC}"
    echo -e "      - Bash shortcut: ${BOLD}bash scripts/setup/install-shell-shortcut.sh${NC}"
    echo -e "      - Standalone service: ${BOLD}sudo bash scripts/service/install.sh${NC}"
    if [[ "$INSTALL_PROFILE" == "core" ]] || [[ "$AI_VERIFY_PASSED" != "true" ]]; then
        echo -e "      - Full AI: ${BOLD}bash scripts/setup/setup-pytorch.sh --mode auto${NC}, then ${BOLD}bash scripts/setup/install-ai-deps.sh${NC}"
    fi
    echo -e "      - Capability report: ${BOLD}bash scripts/setup/check-ai-runtime.sh${NC}"
    echo ""
    if [[ "$NODE_SETUP_STATE" != "ready" ]]; then
        echo -e "   ${RED}${BOLD}Node.js recovery:${NC}"
        echo -e "      The exact nvm/Node failure is printed above. Correct that condition, then run:"
        echo -e "      ${BOLD}make init${NC}"
        echo -e "      PixEagle will reuse the verified Python environment and resume missing setup."
        echo ""
    fi
    echo -e "${CYAN}============================================================================${NC}"
    echo ""
}

# ============================================================================
# Post-Transaction Service Setup (Linux/systemd)
# ============================================================================
configure_service_autostart() {
    # Linux/systemd-only feature.
    if [[ "$(uname -s)" != "Linux" ]]; then
        return 0
    fi

    if ! command -v systemctl &>/dev/null || [[ ! -d /run/systemd/system ]]; then
        log_info "systemd not detected; skipping auto-start setup prompt"
        return 0
    fi

    # Non-interactive mode: skip service setup entirely.
    # The caller (e.g., ARK-OS, Docker, CI) manages the service lifecycle.
    if [[ "${PIXEAGLE_NONINTERACTIVE:-}" == "1" ]]; then
        log_info "Non-interactive mode: skipping service setup (managed externally)"
        log_detail "To set up standalone service later: sudo bash scripts/service/install.sh"
        return 0
    fi

    # Detect externally-managed user-level service (e.g., ARK-OS).
    # Avoid creating a conflicting system-level service.
    if systemctl --user cat pixeagle.service &>/dev/null 2>&1; then
        log_info "User-level pixeagle.service detected (managed by external system)"
        log_detail "Skipping system-level service setup to avoid conflict"
        log_detail "Manage via: systemctl --user {start|stop|status} pixeagle"
        return 0
    fi

    local installer="$SCRIPTS_DIR/service/install.sh"
    local auto_start_enabled=false
    local login_hint_enabled=false
    if pixeagle_resource_lock_context_present; then
        log_error "Managed-service onboarding cannot run inside a setup transaction"
        log_detail "Finish and release the source/environment lock before starting PixEagle."
        return 1
    fi
    if [[ ! -f "$installer" ]]; then
        log_warn "Service installer not found: $installer"
        return 1
    fi

    echo ""
    echo -e "   ${CYAN}${INFO}${NC}  Deployment-only: configure PixEagle service management"
    echo -e "        ${DIM}This optional path can install service management, enable boot auto-start,${NC}"
    echo -e "        ${DIM}and configure SSH startup guide output. It does not start or reboot here.${NC}"

    if ! ask_yes_no "        Install pixeagle-service command now? [y/N]: " "n"; then
        log_info "Skipped service command installation"
        log_detail "Install later with: sudo bash scripts/service/install.sh"
        return 0
    fi

    if [[ "$EUID" -ne 0 ]] && ! command -v sudo &>/dev/null; then
        log_warn "sudo is not available; cannot install service command automatically"
        log_detail "Run as root later: bash scripts/service/install.sh"
        return 1
    fi

    if [[ "$EUID" -ne 0 ]] && ! sudo -v; then
        log_warn "sudo authentication failed; skipping service setup"
        return 1
    fi

    if ! run_privileged bash "$installer"; then
        log_warn "Service installer failed"
        log_detail "Retry later: sudo bash scripts/service/install.sh"
        return 1
    fi

    log_success "Service command installed"

    if ask_yes_no "        Enable auto-start on every boot now? [y/N]: " "n"; then
        if run_privileged pixeagle-service enable; then
            auto_start_enabled=true
            log_success "Auto-start enabled"
        else
            log_warn "Failed to enable auto-start"
            return 1
        fi
    else
        log_info "Auto-start remains disabled"
        log_detail "Enable later with: sudo pixeagle-service enable"
    fi

    if ask_yes_no "        Show PixEagle status hints on SSH login for all users? [y/N]: " "n"; then
        if run_privileged pixeagle-service login-hint enable --system; then
            login_hint_enabled=true
            log_success "SSH login hint enabled (system-wide)"
            log_detail "Open a new SSH session to view the startup guide banner, URLs, and version metadata"
        else
            log_warn "Could not enable SSH login hint"
            return 1
        fi
    else
        log_info "SSH login hint disabled"
        log_detail "Enable later with: sudo pixeagle-service login-hint enable --system"
    fi

    log_info "Managed service installed without starting a competing runtime"
    log_detail "The one-line installer offers a credentialed browser lab after onboarding."
    log_detail "For configured operation later: sudo pixeagle-service start"

    echo ""
    echo -e "   ${CYAN}${BOLD}Service Onboarding Guide:${NC}"
    if [[ "$auto_start_enabled" == true ]]; then
        echo -e "      - Auto-start enabled: ${BOLD}yes${NC}"
    else
        echo -e "      - Auto-start enabled: ${BOLD}no${NC} (enable with: sudo pixeagle-service enable)"
    fi
    if [[ "$login_hint_enabled" == true ]]; then
        echo -e "      - SSH login hint (all users): ${BOLD}enabled${NC}"
        echo -e "      - SSH hint refresh: ${BOLD}sudo pixeagle-service login-hint disable --system && sudo pixeagle-service login-hint enable --system${NC}"
        echo -e "      - Verify hint: ${BOLD}open a new SSH session${NC}"
    else
        echo -e "      - SSH login hint (all users): ${BOLD}disabled${NC} (enable with: sudo pixeagle-service login-hint enable --system)"
    fi
    echo -e "      - Inspect status: ${BOLD}pixeagle-service status${NC}"
    echo -e "      - Start/stop now: ${BOLD}pixeagle-service start${NC} / ${BOLD}pixeagle-service stop${NC}"
    echo -e "      - View logs: ${BOLD}pixeagle-service logs -f${NC}"
    echo -e "      - Attach tmux: ${BOLD}pixeagle-service attach${NC}"

    if [[ "$auto_start_enabled" == true ]]; then
        if [[ -f /var/run/reboot-required ]]; then
            log_warn "System reports a reboot is recommended by package updates."
        fi
        log_detail "Validate boot auto-start later with: sudo reboot"
        log_detail "After reconnect: pixeagle-service status"
    fi

}

# ============================================================================
# Optional Components (Step 10)
# ============================================================================
optional_component_selected() {
    local component="$1"
    [[ ",${OPTIONAL_COMPONENT_SELECTION:-}," == *",$component,"* ]]
}

normalize_optional_component_selection() {
    local raw="$1"
    local token=""
    local normalized=""
    local -a tokens=()

    raw="${raw,,}"
    raw="${raw//[[:space:]]/}"
    [[ -n "$raw" ]] || {
        OPTIONAL_COMPONENT_SELECTION=""
        return 0
    }
    if [[ ",$raw," == *",none,"* && "$raw" != "none" ]]; then
        log_error "Optional component 'none' cannot be combined with other choices"
        log_detail "Use none by itself, or select one or more numbered components."
        return 1
    fi
    IFS=',' read -r -a tokens <<< "$raw"
    for token in "${tokens[@]}"; do
        case "$token" in
            1|dlib) token="dlib" ;;
            2|gstreamer|opencv-gstreamer) token="gstreamer" ;;
            3|shortcut|shell-shortcut) token="shell-shortcut" ;;
            none) continue ;;
            *)
                log_error "Unknown optional component: $token"
                log_detail "Allowed: dlib,gstreamer,shell-shortcut"
                return 1
                ;;
        esac
        [[ ",$normalized," == *",$token,"* ]] || normalized="${normalized:+$normalized,}$token"
    done
    OPTIONAL_COMPONENT_SELECTION="$normalized"
}

configure_optional_components() {
    log_step 10 "Optional components..."
    local selection="${PIXEAGLE_OPTIONAL_COMPONENTS:-}"
    local optional_status=0

    if [[ -z "$selection" ]] && pixeagle_has_interactive_input; then
        echo -e "   ${BOLD}Core/Full installation is complete.${NC}"
        echo -e "   Optional capabilities can be added or changed later."
        echo ""
        echo -e "      1) dlib tracker backend ${DIM}(source build; not selected by default)${NC}"
        echo -e "      2) OpenCV with GStreamer ${DIM}(large source build; not selected by default)${NC}"
        echo -e "      3) Bash ${BOLD}pixeagle${NC} shortcut ${DIM}[default]${NC}"
        echo ""
        printf "   Select comma-separated options [Enter=3, none=None, example 1,3]: "
        if ! pixeagle_read_user_input selection; then
            echo ""
            log_error "Terminal input closed before optional-component selection"
            return 2
        fi
        [[ -n "${selection//[[:space:]]/}" ]] || selection="3"
    elif [[ -z "$selection" ]]; then
        log_info "No controlling terminal is available; optional components were not changed"
        log_detail "Use PIXEAGLE_OPTIONAL_COMPONENTS=dlib,gstreamer,shell-shortcut with an explicit unattended run."
        log_detail "Install a standalone service explicitly with: sudo bash scripts/service/install.sh"
    fi

    normalize_optional_component_selection "$selection" || return 1
    if [[ -z "$OPTIONAL_COMPONENT_SELECTION" ]]; then
        log_success "No optional components selected"
        return 0
    fi

    if optional_component_selected dlib; then
        OPTIONAL_DLIB_STATE="pending"
        OPTIONAL_DLIB_DETAIL="installation started"
        if bash "$SCRIPTS_DIR/setup/install-dlib.sh" --yes; then
            OPTIONAL_DLIB_STATE="ready"
            OPTIONAL_DLIB_DETAIL="dlib backend installed and verified"
        else
            OPTIONAL_DLIB_STATE="degraded"
            OPTIONAL_DLIB_DETAIL="dlib setup failed; Core/Full installation remains intact"
            optional_status=1
        fi
    fi

    if optional_component_selected gstreamer; then
        OPTIONAL_GSTREAMER_STATE="pending"
        OPTIONAL_GSTREAMER_DETAIL="source build started"
        if bash "$SCRIPTS_DIR/setup/build-opencv.sh" --skip-confirm; then
            OPTIONAL_GSTREAMER_STATE="ready"
            OPTIONAL_GSTREAMER_DETAIL="OpenCV GStreamer provider built and verified"
        else
            OPTIONAL_GSTREAMER_STATE="degraded"
            OPTIONAL_GSTREAMER_DETAIL="GStreamer build failed or was refused; prior OpenCV remains protected"
            optional_status=1
        fi
    fi

    if optional_component_selected shell-shortcut; then
        OPTIONAL_SHORTCUT_STATE="pending"
        OPTIONAL_SHORTCUT_DETAIL="installation started"
        if bash "$SCRIPTS_DIR/setup/install-shell-shortcut.sh" --yes; then
            OPTIONAL_SHORTCUT_STATE="ready"
            OPTIONAL_SHORTCUT_DETAIL="Bash pixeagle directory shortcut installed"
        else
            OPTIONAL_SHORTCUT_STATE="degraded"
            OPTIONAL_SHORTCUT_DETAIL="Bash shortcut installation failed"
            optional_status=1
        fi
    fi

    return "$optional_status"
}

run_post_setup_onboarding() {
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" ]]; then
        return 0
    fi
    pixeagle_has_interactive_input || return 0
    if ! configure_service_autostart; then
        log_warn "Optional service onboarding did not complete"
        log_detail "Core setup remains usable; retry later with: sudo bash scripts/service/install.sh"
    fi
    return 0
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    local final_status=0
    cd "$PIXEAGLE_DIR" || exit 1

    if ! pixeagle_acquire_setup_lock "$VENV_DIR" "full initialization" 30; then
        return 1
    fi

    display_banner

    echo -e "${DIM}Starting PixEagle initialization...${NC}"
    echo ""
    log_info "Install owner: $(id -un) ($(id -u)); project: $PIXEAGLE_DIR"
    if [[ "$EUID" -eq 0 ]]; then
        log_warn "This creates a root-owned runtime under $HOME"
        log_detail "For companion computers, a dedicated non-root service account is recommended."
    fi
    describe_setup_action

    check_supported_platform
    select_installation_profile || return 1
    check_system_requirements
    prepare_model_store || return 1
    install_system_packages
    if ! pixeagle_begin_venv_transaction "$VENV_DIR" "PixEagle initialization"; then
        return 1
    fi
    create_venv
    install_python_deps
    if ! pixeagle_commit_venv_transaction; then
        log_error "Could not commit the verified Python environment"
        return 1
    fi
    if ! pixeagle_finalize_venv_transaction; then
        log_error "Could not finalize the verified Python environment transaction"
        return 1
    fi
    setup_nodejs
    install_dashboard_deps
    setup_configs
    setup_mavsdk_server
    setup_mavlink2rest

    if [[ "$CONFIG_DEFAULTS_STATE" != "ready" ]]; then
        final_status=1
    fi
    if [[ "$NODE_SETUP_STATE" != "ready" ]] || \
       [[ "$DASHBOARD_DEPS_STATE" != "ready" ]] || \
       [[ "$DASHBOARD_ENV_STATE" != "ready" ]]; then
        final_status=1
    fi
    if [[ "$INSTALL_PROFILE" == "full" ]] && [[ "$AI_VERIFY_PASSED" != "true" ]]; then
        final_status=1
    fi

    if [[ "$final_status" -eq 0 ]]; then
        if ! configure_optional_components; then
            final_status=1
        fi
    else
        log_step 10 "Optional components..."
        log_warn "Optional component setup skipped because required installation steps need attention"
        log_detail "Resolve the summary items and rerun make init."
    fi

    show_summary
    return "$final_status"
}

run_initialization_entrypoint() {
    if pixeagle_setup_lock_context_present; then
        main "$@"
        return
    fi

    if ! pixeagle_run_with_setup_lock \
        "$VENV_DIR" "full initialization" 30 bash "${BASH_SOURCE[0]}" "$@"; then
        return 1
    fi
    run_post_setup_onboarding
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    run_initialization_entrypoint "$@"
fi
