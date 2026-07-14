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
#   PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init  (deployment service prompts)
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
TOTAL_STEPS=9
NVM_VERSION="v0.40.3"
NODE_VERSION="22"  # LTS version for stability
MIN_PYTHON_VERSION="3.9"
MAX_TESTED_PYTHON_MINOR="12"
REQUIRED_DISK_MB=500

# Installation profile: "core" (no AI) or "full" (with AI/torch)
INSTALL_PROFILE="full"
# Python dependency installation status (used in final summary)
AI_VERIFY_PASSED=false
AI_ROLLBACK_APPLIED=false
AI_KEEP_FAILED=false
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
# Platform detection
DETECTED_ARCH=""
IS_ARM_PLATFORM=false

# Get the scripts directory and PixEagle root
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# Fix line endings on critical files before sourcing
fix_line_endings "$SCRIPTS_DIR/lib/common.sh"
fix_line_endings "$0"  # Fix this script too

# Source shared functions (colors, logging, banner)
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    echo "Warning: Could not source common.sh, using fallback definitions"
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

# Read user input - works both interactively and when piped
# Usage: ask_yes_no "prompt" [default]
# Returns 0 for yes, 1 for no
ask_yes_no() {
    local prompt="$1"
    local default="${2:-y}"  # Default to yes
    local reply=""

    # Non-interactive mode: always use default (for automated installs, e.g., ARK-OS)
    if [[ "${PIXEAGLE_NONINTERACTIVE:-}" == "1" ]]; then
        printf "%b (auto: %s)\n" "$prompt" "$default"
        [[ "$default" =~ ^[Yy] ]] && return 0 || return 1
    fi

    # Print prompt (use %b so color escape sequences render correctly)
    printf "%b" "$prompt"

    # Try to read user input
    # Priority: /dev/tty (works when stdin is piped) > stdin (interactive)
    if [[ -r /dev/tty ]] && [[ -w /dev/tty ]]; then
        # /dev/tty available - best option for piped scenarios
        reply=$(bash -c 'read -r line </dev/tty && echo "$line"' 2>/dev/null) || reply=""
    elif [[ -t 0 ]]; then
        # stdin is a terminal
        read -r reply || reply=""
    else
        # No interactive input possible - use default
        printf " (auto: %s)\n" "$default"
        reply="$default"
    fi

    # Empty reply uses default
    [[ -z "$reply" ]] && reply="$default"

    # Debug: uncomment to see what was read
    # echo "[DEBUG] reply='$reply' default='$default'" >&2

    # Return 0 for yes, 1 for no
    case "$reply" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        [Nn]|[Nn][Oo]) return 1 ;;
        *) [[ "$default" =~ ^[Yy] ]] && return 0 || return 1 ;;
    esac
}

# ============================================================================
# Spinner for Long-Running Operations
# ============================================================================
spinner_pid=""

start_spinner() {
    local msg="$1"
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
        kill "$spinner_pid" 2>/dev/null
        wait "$spinner_pid" 2>/dev/null
        spinner_pid=""
        printf "\r        \033[K"  # Clear line
    fi
}

# Cleanup on exit
cleanup() {
    stop_spinner
}
trap cleanup EXIT

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    clear
    display_pixeagle_banner
    get_version_info "3.2"
    echo -e "  ${DIM}Professional Vision-Based Drone Tracking System${NC}"
    echo -e "  ${DIM}GitHub: https://github.com/alireza787b/PixEagle${NC}"
    echo ""
}

# ============================================================================
# Sudo Password Prompt
# ============================================================================
prompt_sudo() {
    # Non-interactive mode: skip the fancy prompt, just validate sudo
    if [[ "${PIXEAGLE_NONINTERACTIVE:-}" == "1" ]]; then
        if ! sudo -v 2>/dev/null; then
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
                log_warn "Unknown PIXEAGLE_INSTALL_PROFILE='$PIXEAGLE_INSTALL_PROFILE', falling through to interactive"
                ;;
        esac
    fi

    echo ""
    echo -e "${CYAN}+==========================================================================+${NC}"
    echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
    echo -e "${CYAN}|${NC}   ${BOLD}INSTALLATION PROFILE${NC}                                                   ${CYAN}|${NC}"
    echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"

    if [[ "$IS_ARM_PLATFORM" == true ]]; then
        echo -e "${CYAN}|${NC}   ${YELLOW}WARNING: ARM platform detected ($DETECTED_ARCH)${NC}                         ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}   ${BOLD}1) Core${NC} - Essential features (recommended for ARM)                    ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Drone control, tracking, dashboard                               ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - OpenCV-based detection and tracking                              ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Works reliably on all ARM devices                                ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}   ${BOLD}2) Full${NC} - All features including AI/YOLO                              ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Includes PyTorch and Ultralytics                                 ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Includes guided PyTorch setup (Jetson/NVIDIA aware)             ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      ${YELLOW}- Some ARM boards may still need CPU mode/manual override${NC}            ${CYAN}|${NC}"
    else
        echo -e "${CYAN}|${NC}   ${GREEN}OK x86_64 platform detected${NC} - Full compatibility                      ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}   ${BOLD}1) Core${NC} - Essential features only                                     ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Drone control, tracking, dashboard                               ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Lighter installation, faster setup                               ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}   ${BOLD}2) Full${NC} - All features including AI/YOLO (recommended)                ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - YOLO object detection                                            ${CYAN}|${NC}"
        echo -e "${CYAN}|${NC}      - Advanced AI-based tracking                                       ${CYAN}|${NC}"
    fi

    echo -e "${CYAN}|${NC}                                                                          ${CYAN}|${NC}"
    echo -e "${CYAN}+==========================================================================+${NC}"
    echo ""

    local read_from_tty=false
    if [[ -r /dev/tty ]] && [[ -w /dev/tty ]]; then
        read_from_tty=true
    elif [[ ! -t 0 ]]; then
        log_error "No interactive input available for installation profile selection."
        log_detail "Run interactively so the installer can ask and wait for your 1/2 choice."
        exit 1
    fi

    while true; do
        if [[ "$IS_ARM_PLATFORM" == true ]]; then
            echo -en "   Select profile [1=Core (recommended), 2=Full]: "
        else
            echo -en "   Select profile [1=Core, 2=Full (recommended)]: "
        fi

        if [[ "$read_from_tty" == true ]]; then
            read -r choice </dev/tty || choice=""
        else
            read -r choice || choice=""
        fi
        choice="${choice//[[:space:]]/}"
        if [[ -z "$choice" ]]; then
            echo -e "   ${YELLOW}Please enter 1 or 2 (no automatic default).${NC}"
            continue
        fi

        case "$choice" in
            1)
                INSTALL_PROFILE="core"
                echo ""
                log_success "Selected: Core installation (no AI packages)"
                break
                ;;
            2)
                INSTALL_PROFILE="full"
                echo ""
                if [[ "$IS_ARM_PLATFORM" == true ]]; then
                    log_warn "Selected: Full installation with AI packages"
                    log_detail "If torch fails, you can reinstall with: make init (choose Core)"
                    log_detail "Recommended recovery: bash scripts/setup/setup-pytorch.sh --mode auto"
                    log_detail "Manual wheel override is available via --torch-wheel/--torchvision-wheel"
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

# ============================================================================
# Pre-flight Checks (Step 1)
# ============================================================================
check_system_requirements() {
    log_step 1 "Checking system requirements..."
    local errors=0

    # Check Python
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 not installed"
        log_detail "Install with: sudo apt install python3"
        errors=$((errors + 1))
    else
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

        if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 9 ]]; then
            log_error "Python ${MIN_PYTHON_VERSION}+ required (found ${PYTHON_VERSION})"
            errors=$((errors + 1))
        else
            log_success "Python ${PYTHON_VERSION} detected"
            if [[ $PYTHON_MAJOR -gt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -gt $MAX_TESTED_PYTHON_MINOR ]]; then
                log_warn "Python ${PYTHON_VERSION} is newer than tested range (3.9-3.${MAX_TESTED_PYTHON_MINOR})"
                log_detail "If installation fails, use Python 3.10-3.12 for best compatibility"
            fi
        fi
    fi

    # Check disk space
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
        if sudo apt install -y "$pkg" >/dev/null 2>&1; then
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
        "python${PYTHON_VERSION}-venv|python3-venv"      # Python venv
        "python${PYTHON_VERSION}-dev|python3-dev"        # Python headers (for compilation)
        "libgl1|libgl1-mesa-glx"                         # OpenGL library
        "curl"                                            # HTTP client
        "lsof"                                            # List open files
        "make"                                            # Project task entry point
        "tmux"                                            # Terminal multiplexer
    )

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
            start_spinner "Running apt update..."
            sudo apt update -qq 2>&1 || true
            stop_spinner

            log_info "Installing required packages..."
            # Run apt install directly (pipe loses exit code)
            if sudo apt install -y "${MISSING_PKGS[@]}"; then
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
                if sudo apt install -y "$pkg" >/dev/null 2>&1; then
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
    if python3 -m venv "$VENV_DIR" 2>&1; then
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

# Check if OpenCV has GStreamer support (custom build)
check_opencv_gstreamer() {
    if "$VENV_PYTHON" -c "import cv2; print(cv2.getBuildInformation())" 2>/dev/null | grep -q "GStreamer:.*YES"; then
        return 0  # Has GStreamer
    fi
    return 1  # No GStreamer or no cv2
}

install_python_deps() {
    log_step 4 "Installing Python dependencies..."

    cd "$PIXEAGLE_DIR" || exit 1

    # Source the virtual environment
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"

    # Reset status flags for this run
    AI_VERIFY_PASSED=false
    AI_ROLLBACK_APPLIED=false
    AI_KEEP_FAILED=false
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

    # Check for existing custom OpenCV with GStreamer before pip install
    local SKIP_OPENCV=false
    if check_opencv_gstreamer; then
        echo ""
        log_warn "Custom OpenCV with GStreamer support detected!"
        log_detail "pip install will OVERWRITE this with standard opencv-python (no GStreamer)"
        log_detail "You'll lose RTSP/GStreamer camera support if you proceed"
        echo ""
        if ask_yes_no "        ${YELLOW}Overwrite custom OpenCV? [y/N]:${NC} " "n"; then
            log_info "Will install pip opencv (GStreamer support will be lost)"
        else
            log_info "Preserving custom OpenCV build (skipping opencv packages)"
            SKIP_OPENCV=true
        fi
        echo ""
    fi

    # Upgrade pip first
    echo -e "        ${DIM}Upgrading pip...${NC}"
    "$VENV_PIP" install --upgrade pip -q 2>&1 || true

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

    if ! "$VENV_PIP" install -r "$core_req_file"; then
        [[ "$core_req_temp" == true ]] && rm -f "$core_req_file"
        log_error "Core dependency installation failed"
        log_detail "Retry with: make init"
        log_detail "For manual setup, use the core-first dependency flow in docs/INSTALLATION.md"
        deactivate
        exit 1
    fi
    [[ "$core_req_temp" == true ]] && rm -f "$core_req_file"

    # Verify core dependencies
    if "$VENV_PYTHON" -c "import cv2; import numpy" 2>/dev/null; then
        if [[ "$SKIP_OPENCV" == true ]]; then
            log_success "Core packages installed (preserved custom OpenCV with GStreamer)"
        else
            log_success "Core packages installed successfully"
        fi
    else
        log_error "Core packages (opencv, numpy) not installed correctly"
        log_detail "Retry with: make init"
        log_detail "For manual setup, use the core-first dependency flow in docs/INSTALLATION.md"
        deactivate
        exit 1
    fi

    # pip consistency check (warning only)
    if ! "$VENV_PIP" check >/dev/null 2>&1; then
        log_warn "Some dependency warnings detected (usually not critical)"
    fi

    # Core profile ends here
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        log_detail "To add AI features later:"
        log_detail "bash scripts/setup/setup-pytorch.sh --mode auto"
        log_detail "bash scripts/setup/install-ai-deps.sh"
        log_detail "bash scripts/setup/check-ai-runtime.sh"
        deactivate
        return 0
    fi

    # -------------------------------
    # Phase B: Install AI packages
    # -------------------------------
    local pytorch_setup_script="$PIXEAGLE_DIR/scripts/setup/setup-pytorch.sh"
    local run_pytorch_setup_default="n"
    local is_jetson=false
    if [[ -f /proc/device-tree/model ]] && tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi "jetson"; then
        is_jetson=true
    elif command -v dpkg-query &>/dev/null && dpkg-query -W -f='${Status}' nvidia-l4t-core 2>/dev/null | grep -q "install ok installed"; then
        is_jetson=true
    fi

    if [[ "$is_jetson" == true ]] || command -v nvidia-smi &>/dev/null; then
        run_pytorch_setup_default="y"
    fi

    if [[ -f "$pytorch_setup_script" ]]; then
        echo ""
        log_info "Optional accelerator setup (recommended for NVIDIA GPU/Jetson)"
        if ask_yes_no "        Run automated PyTorch setup now? [Y/n]: " "$run_pytorch_setup_default"; then
            if bash "$pytorch_setup_script" --mode auto; then
                PYTORCH_SETUP_PASSED=true
                log_success "Automated PyTorch setup completed"
            else
                PYTORCH_SETUP_FAILED=true
                log_warn "Automated PyTorch setup failed"
                log_detail "Continuing with AI package installation; you can retry later:"
                log_detail "bash scripts/setup/setup-pytorch.sh --mode auto"
            fi
        else
            PYTORCH_SETUP_SKIPPED=true
            log_info "Skipped automated PyTorch setup"
            log_detail "You can run it later: bash scripts/setup/setup-pytorch.sh --mode auto"
        fi
    else
        PYTORCH_SETUP_SKIPPED=true
        log_warn "PyTorch setup script not found: scripts/setup/setup-pytorch.sh"
    fi

    echo ""
    log_info "Phase B/2: Installing AI packages (ultralytics, lap, ncnn, pnnx optional)"
    log_warn "Using safe AI installer to preserve core runtime (numpy/opencv/torch) versions"

    local ai_setup_script="$PIXEAGLE_DIR/scripts/setup/install-ai-deps.sh"
    local ai_verify_failed=false
    if [[ -f "$ai_setup_script" ]]; then
        if bash "$ai_setup_script"; then
            AI_VERIFY_PASSED=true
            log_success "Full AI dependencies installed and verified (ultralytics + lap)"
        else
            ai_verify_failed=true
            log_warn "AI setup helper failed"
        fi
    else
        log_warn "AI setup helper not found; using legacy pip fallback"
        if [[ -f "$PIXEAGLE_DIR/requirements-ai.txt" ]]; then
            if ! "$VENV_PIP" install --prefer-binary -r "$PIXEAGLE_DIR/requirements-ai.txt"; then
                log_warn "AI package install command reported errors; verifying imports next"
            fi
        elif ! "$VENV_PIP" install --prefer-binary ultralytics lap ncnn; then
            log_warn "AI package install command reported errors; verifying imports next"
        fi
        if ! "$VENV_PIP" install --prefer-binary pnnx; then
            log_warn "Optional package install failed: pnnx (NCNN auto-export may be unavailable)"
        fi
        if ! "$VENV_PYTHON" -c "from ultralytics import YOLO; print('ok')" 2>/dev/null | grep -q "ok"; then
            ai_verify_failed=true
            log_warn "AI verify failed: ultralytics could not be imported"
        fi
        if ! "$VENV_PYTHON" -c "import lap; print('ok')" 2>/dev/null | grep -q "ok"; then
            ai_verify_failed=true
            log_warn "AI verify failed: lap could not be imported"
        fi
        if ! "$VENV_PYTHON" -c "import ncnn; print('ok')" 2>/dev/null | grep -q "ok"; then
            log_warn "Optional package check: ncnn import failed (SmartTracker may still work)"
        fi
        if [[ "$ai_verify_failed" == false ]]; then
            AI_VERIFY_PASSED=true
            log_success "Full AI dependencies installed and verified (ultralytics + lap)"
        fi
    fi

    if [[ "$AI_VERIFY_PASSED" != true ]]; then
        echo ""
        log_warn "AI packages are not fully usable yet."
        log_info "Manual recovery commands:"
        log_detail "bash scripts/setup/setup-pytorch.sh --mode auto"
        log_detail "bash scripts/setup/install-ai-deps.sh"
        log_detail "bash scripts/setup/check-ai-runtime.sh"
        echo ""

        if ask_yes_no "        Roll back to Core-safe mode now? [Y/n]: " "y"; then
            log_info "Rolling back AI packages for stable Core mode..."
            "$VENV_PIP" uninstall -y ultralytics torch torchvision torchaudio lap ncnn pnnx 2>/dev/null || true
            AI_ROLLBACK_APPLIED=true
            log_warn "AI rollback applied. Core mode remains fully functional."
        else
            AI_KEEP_FAILED=true
            log_warn "Keeping current AI package state. SmartTracker may fail until fixed manually."
        fi
    fi

    deactivate
}

# ============================================================================
# Node.js Setup via nvm (Step 5)
# ============================================================================
setup_nodejs() {
    log_step 5 "Setting up Node.js via nvm..."
    NODE_SETUP_STATE="pending"
    NODE_SETUP_DETAIL="Node.js setup started"

    # Set up NVM_DIR
    export NVM_DIR="$HOME/.nvm"

    # Check if nvm already installed
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        # shellcheck source=/dev/null
        source "$NVM_DIR/nvm.sh"
        log_info "nvm already installed ($(nvm --version))"
    else
        # Install nvm
        log_info "Installing nvm ${NVM_VERSION}..."
        start_spinner "Downloading nvm..."

        if curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" 2>/dev/null | bash >/dev/null 2>&1; then
            stop_spinner

            # Load nvm
            export NVM_DIR="$HOME/.nvm"
            # shellcheck source=/dev/null
            [[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh"

            if command -v nvm &>/dev/null; then
                log_success "nvm installed successfully"
            else
                stop_spinner
                log_error "nvm installation failed"
                log_detail "Manual install: https://github.com/nvm-sh/nvm"
                log_detail "Then re-run this script"
                NODE_SETUP_STATE="manual_follow_up"
                NODE_SETUP_DETAIL="nvm install completed but nvm was not loadable; install Node.js manually"
                return 1
            fi
        else
            stop_spinner
            log_error "nvm download failed"
            log_detail "Manual install: https://github.com/nvm-sh/nvm"
            NODE_SETUP_STATE="manual_follow_up"
            NODE_SETUP_DETAIL="nvm download failed; install Node.js manually"
            return 1
        fi
    fi

    # Check if Node.js is already installed
    if command -v node &>/dev/null; then
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

    if nvm install "$NODE_VERSION" >/dev/null 2>&1; then
        stop_spinner
        nvm use "$NODE_VERSION" >/dev/null 2>&1
        log_success "Node.js $(node -v) installed"
        NODE_SETUP_STATE="ready"
        NODE_SETUP_DETAIL="Node.js $(node -v)"
    else
        stop_spinner
        log_error "Node.js installation failed"
        log_detail "Manual install: https://nodejs.org/en/download"
        NODE_SETUP_STATE="manual_follow_up"
        NODE_SETUP_DETAIL="Node.js ${NODE_VERSION} installation failed; install Node.js manually"
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

    # Ensure nvm/node is loaded
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh"

    if ! command -v npm &>/dev/null; then
        log_warn "npm not available - skipping dashboard setup"
        log_detail "Install Node.js first, then run: cd dashboard && npm install"
        DASHBOARD_DEPS_STATE="manual_follow_up"
        DASHBOARD_DEPS_DETAIL="npm unavailable; install Node.js/npm, then run cd dashboard && npm install"
        return 1
    fi

    if ! cd dashboard; then
        DASHBOARD_DEPS_STATE="degraded"
        DASHBOARD_DEPS_DETAIL="could not enter dashboard directory"
        return 1
    fi

    if [[ -d "node_modules" ]]; then
        log_info "node_modules exists - checking for updates"
    fi

    start_spinner "Installing npm packages..."
    if npm ci --silent --no-audit --no-fund 2>&1 || npm install --silent --no-audit --no-fund 2>&1; then
        stop_spinner
        log_success "Dashboard dependencies installed"
        if command -v sha256sum >/dev/null 2>&1 && [[ -f package.json && -f package-lock.json ]]; then
            mkdir -p .pixeagle_cache
            local package_hash lock_hash
            package_hash="$(sha256sum package.json | cut -d' ' -f1)"
            lock_hash="$(sha256sum package-lock.json | cut -d' ' -f1)"
            echo "${package_hash}_${lock_hash}" > .pixeagle_cache/deps_hash
        fi
        DASHBOARD_DEPS_STATE="ready"
        DASHBOARD_DEPS_DETAIL="npm dependencies installed"
    else
        stop_spinner
        log_warn "npm install had issues"
        log_detail "Try manually: cd dashboard && npm install"
        DASHBOARD_DEPS_STATE="degraded"
        DASHBOARD_DEPS_DETAIL="npm install failed; run cd dashboard && npm install manually"
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
    echo ""
    echo -e "${CYAN}============================================================================${NC}"
    echo -e "                          ${PARTY} ${BOLD}Setup Summary${NC} ${PARTY}"
    echo -e "${CYAN}============================================================================${NC}"
    echo ""
    summary_status_line "ready" "Python ${PYTHON_VERSION} virtual environment" "created or reused"
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        summary_status_line "ready" "Core Python dependencies" "AI packages skipped by Core profile"
    else
        if [[ "$AI_VERIFY_PASSED" == true ]]; then
            summary_status_line "ready" "Full Python dependencies" "including AI/YOLO"
        elif [[ "$AI_ROLLBACK_APPLIED" == true ]]; then
            summary_status_line "degraded" "Python dependencies" "AI rollback applied after verify failure; Core runtime remains usable"
        elif [[ "$AI_KEEP_FAILED" == true ]]; then
            summary_status_line "manual_follow_up" "Python dependencies" "AI install incomplete; SmartTracker may fail until fixed"
        else
            summary_status_line "manual_follow_up" "Python dependencies" "AI status unknown; verify manually"
        fi
        if [[ "$PYTORCH_SETUP_PASSED" == true ]]; then
            summary_status_line "ready" "Automated PyTorch setup" "accelerator profile resolved"
        elif [[ "$PYTORCH_SETUP_FAILED" == true ]]; then
            summary_status_line "degraded" "Automated PyTorch setup" "retry with setup-pytorch.sh"
        elif [[ "$PYTORCH_SETUP_SKIPPED" == true ]]; then
            summary_status_line "skipped" "Automated PyTorch setup" "run setup-pytorch.sh when ready"
        fi
    fi
    summary_status_line "$NODE_SETUP_STATE" "Node.js" "$NODE_SETUP_DETAIL"
    summary_status_line "$DASHBOARD_DEPS_STATE" "Dashboard dependencies" "$DASHBOARD_DEPS_DETAIL"
    summary_status_line "$CONFIG_DEFAULTS_STATE" "Configuration defaults" "$CONFIG_DEFAULTS_DETAIL"
    summary_status_line "$DASHBOARD_ENV_STATE" "Dashboard .env" "$DASHBOARD_ENV_DETAIL"
    summary_status_line "$MAVSDK_BINARY_STATE" "MAVSDK Server binary" "$MAVSDK_BINARY_DETAIL"
    summary_status_line "$MAVLINK2REST_BINARY_STATE" "MAVLink2REST binary" "$MAVLINK2REST_BINARY_DETAIL"
    echo ""
    echo -e "   ${CYAN}${BOLD}Next Steps:${NC}"
    if [[ "$DASHBOARD_DEPS_STATE" == "ready" ]] && [[ "$CONFIG_DEFAULTS_STATE" == "ready" ]] && [[ "$DASHBOARD_ENV_STATE" == "ready" ]]; then
        echo -e "      1. Run: ${BOLD}make run${NC} (or ${BOLD}bash scripts/run.sh${NC})"
        echo -e "      2. Optional QGC field video: ${BOLD}make qgc-video-profile GCS_HOST=<gcs-ip>${NC}"
        echo -e "      3. Guarded QGC HTTPS/WSS media: ${BOLD}make qgc-direct-media-profile PUBLIC_HOST=<tls-host>${NC}"
        echo -e "      4. Deployment only: ${BOLD}sudo bash scripts/service/install.sh${NC} for boot auto-start"
    else
        echo -e "      1. Resolve any ${BOLD}manual follow-up${NC} or ${BOLD}degraded${NC} items above."
        echo -e "      2. Re-run: ${BOLD}make init${NC}"
        echo -e "      3. Then run: ${BOLD}make run${NC} (or ${BOLD}bash scripts/run.sh${NC})"
    fi
    echo ""
    echo -e "   ${YELLOW}${BOLD}Optional (better performance):${NC}"
    echo -e "      - ${BOLD}bash scripts/setup/install-dlib.sh${NC}    (faster tracking)"
    echo -e "      - ${BOLD}bash scripts/setup/setup-pytorch.sh --mode auto${NC}   (auto accelerator profile)"
    if [[ "$INSTALL_PROFILE" == "core" ]] || [[ "$AI_VERIFY_PASSED" != "true" ]]; then
        echo -e "      - ${BOLD}bash scripts/setup/install-ai-deps.sh${NC}         (safe AI deps install)"
    fi
    echo -e "      - ${BOLD}bash scripts/setup/check-ai-runtime.sh${NC}        (verify runtime/backends)"
    echo -e "      - ${BOLD}bash scripts/setup/build-opencv.sh${NC}    (optional OpenCV GStreamer build)"
    echo -e "        then ${BOLD}make check-gstreamer-runtime${NC}     (capability check; not receiver proof)"
    if [[ "$MAVSDK_BINARY_STATE" != "ready" ]] || [[ "$MAVLINK2REST_BINARY_STATE" != "ready" ]]; then
        echo -e "      - ${BOLD}bash scripts/setup/download-binaries.sh${NC}  (download binaries)"
    fi
    echo -e "      - ${BOLD}python add_yolo_model.py${NC}              (add YOLO models)"
    echo ""
    if [[ "$NODE_SETUP_STATE" != "ready" ]]; then
        echo -e "   ${RED}${BOLD}WARNING: Node.js Installation:${NC}"
        echo -e "      If nvm installation failed, install manually:"
        echo -e "      ${DIM}https://nodejs.org/en/download${NC}"
        echo -e "      Then run: ${BOLD}cd dashboard && npm install${NC}"
        echo ""
    fi
    echo -e "${CYAN}============================================================================${NC}"
    echo ""
}

# ============================================================================
# Optional Service Setup (Linux/systemd)
# ============================================================================
configure_service_autostart() {
    # Linux/systemd-only feature.
    if [[ "$(uname -s)" != "Linux" ]]; then
        return 0
    fi

    if ! command -v systemctl &>/dev/null; then
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
    local service_cmd_installed=false
    local auto_start_enabled=false
    local login_hint_enabled=false
    if [[ ! -f "$installer" ]]; then
        log_warn "Service installer not found: $installer"
        return 0
    fi

    echo ""
    echo -e "   ${CYAN}${INFO}${NC}  Deployment-only: configure PixEagle service management"
    echo -e "        ${DIM}This optional path can install service management, enable boot auto-start,${NC}"
    echo -e "        ${DIM}configure SSH startup guide output, and optionally reboot for validation.${NC}"

    if ! ask_yes_no "        Install pixeagle-service command now? [y/N]: " "n"; then
        log_info "Skipped service command installation"
        log_detail "Install later with: sudo bash scripts/service/install.sh"
        return 0
    fi

    if ! command -v sudo &>/dev/null; then
        log_warn "sudo is not available; cannot install service command automatically"
        log_detail "Run as root later: bash scripts/service/install.sh"
        return 0
    fi

    if ! sudo -v; then
        log_warn "sudo authentication failed; skipping service setup"
        return 0
    fi

    if ! sudo bash "$installer"; then
        log_warn "Service installer failed"
        log_detail "Retry later: sudo bash scripts/service/install.sh"
        return 0
    fi

    service_cmd_installed=true
    log_success "Service command installed"

    if ask_yes_no "        Enable auto-start on every boot now? [y/N]: " "n"; then
        if sudo pixeagle-service enable; then
            auto_start_enabled=true
            log_success "Auto-start enabled"
        else
            log_warn "Failed to enable auto-start"
        fi
    else
        log_info "Auto-start remains disabled"
        log_detail "Enable later with: sudo pixeagle-service enable"
    fi

    if ask_yes_no "        Show PixEagle status hints on SSH login for all users? [y/N]: " "n"; then
        if sudo pixeagle-service login-hint enable --system; then
            login_hint_enabled=true
            log_success "SSH login hint enabled (system-wide)"
            log_detail "Open a new SSH session to view the startup guide banner, URLs, and version metadata"
        else
            log_warn "Could not enable SSH login hint"
        fi
    else
        log_info "SSH login hint disabled"
        log_detail "Enable later with: sudo pixeagle-service login-hint enable --system"
    fi

    # Optional immediate start for first-time onboarding.
    if [[ "$service_cmd_installed" == true ]]; then
        if ask_yes_no "        Start PixEagle service now? [y/N]: " "n"; then
            if sudo pixeagle-service start; then
                log_success "PixEagle service started"
            else
                log_warn "Could not start PixEagle service"
            fi
            echo ""
            log_info "Current service status:"
            pixeagle-service status || true
        else
            log_info "Service start skipped"
            log_detail "Start later with: sudo pixeagle-service start"
        fi
    fi

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
    echo -e "      - View logs: ${BOLD}pixeagle-service logs -f${NC}"
    echo -e "      - Attach tmux: ${BOLD}pixeagle-service attach${NC}"

    # Offer reboot validation for boot auto-start; default is No to avoid surprises.
    if [[ "$auto_start_enabled" == true ]]; then
        if [[ -f /var/run/reboot-required ]]; then
            log_warn "System reports a reboot is recommended by package updates."
        fi
        if ask_yes_no "        Reboot now to validate boot auto-start? [y/N]: " "n"; then
            log_info "Rebooting now. After reconnect, verify with: pixeagle-service status"
            sudo reboot
        else
            log_info "Reboot skipped"
            log_detail "Recommended validation later: sudo reboot"
            log_detail "After reconnect: pixeagle-service status"
        fi
    fi
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    local final_status=0
    cd "$PIXEAGLE_DIR" || exit 1

    display_banner

    echo -e "${DIM}Starting PixEagle initialization...${NC}"
    echo ""

    check_system_requirements
    select_installation_profile
    install_system_packages
    create_venv
    install_python_deps
    setup_nodejs
    install_dashboard_deps
    setup_configs
    setup_mavsdk_server
    setup_mavlink2rest

    show_summary
    if [[ "${PIXEAGLE_ENABLE_SERVICE_SETUP:-0}" == "1" ]]; then
        configure_service_autostart
    else
        log_info "Deployment service setup skipped"
        log_detail "Run explicitly when needed: sudo bash scripts/service/install.sh"
        log_detail "Or enable guided prompts with: PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init"
    fi

    if [[ "$CONFIG_DEFAULTS_STATE" != "ready" ]]; then
        final_status=1
    fi
    return "$final_status"
}

# Run main function
main "$@"
