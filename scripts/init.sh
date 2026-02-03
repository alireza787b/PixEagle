#!/bin/bash

# ============================================================================
# scripts/init.sh - Professional Initialization Script for PixEagle
# ============================================================================
# This script sets up the complete PixEagle environment:
#   - Python virtual environment with all dependencies
#   - Node.js via nvm for the dashboard
#   - Configuration files
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
TOTAL_STEPS=9
NVM_VERSION="v0.40.3"
NODE_VERSION="22"  # LTS version for stability
MIN_PYTHON_VERSION="3.9"
REQUIRED_DISK_MB=500

# Installation profile: "core" (no AI) or "full" (with AI/torch)
INSTALL_PROFILE="full"
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
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    echo "Warning: Could not source common.sh, using fallback definitions"
fi

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
    CHECK="✓"
    CROSS="✗"
    WARN="!"
    INFO="i"
    PARTY="🎉"

    display_pixeagle_banner() {
        echo ""
        echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║${NC}              ${BOLD}PixEagle${NC}                                       ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}       Vision-Based Drone Tracking System                     ${CYAN}║${NC}"
        echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
        echo ""
    }

    get_version_info() {
        local script_version="${1:-unknown}"
        if [[ -d "$PIXEAGLE_DIR/.git" ]]; then
            local git_tag=$(git -C "$PIXEAGLE_DIR" describe --tags --abbrev=0 2>/dev/null || echo "")
            local git_commit=$(git -C "$PIXEAGLE_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
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
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "   ${BOLD}Step ${step}/${TOTAL_STEPS}:${NC} ${msg}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
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

    # Print prompt (use printf for reliability)
    printf "%s" "$prompt"

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
    local chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
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
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   ${BOLD}🔐 SUDO PASSWORD REQUIRED${NC}                                              ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   System packages need to be installed. Please enter your password       ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}   when prompted below.                                                   ${YELLOW}║${NC}"
    echo -e "${YELLOW}║${NC}                                                                          ${YELLOW}║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
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

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${BOLD}📦 INSTALLATION PROFILE${NC}                                                ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"

    if [[ "$IS_ARM_PLATFORM" == true ]]; then
        echo -e "${CYAN}║${NC}   ${YELLOW}⚠ ARM platform detected ($DETECTED_ARCH)${NC}                                  ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}   ${BOLD}1) Core${NC} - Essential features (recommended for ARM)                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Drone control, tracking, dashboard                               ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • OpenCV-based detection and tracking                              ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Works reliably on all ARM devices                                ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}   ${BOLD}2) Full${NC} - All features including AI/YOLO                              ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Includes PyTorch and Ultralytics                                 ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      ${YELLOW}• May require manual torch installation on ARM${NC}                      ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      ${YELLOW}• Can cause 'Illegal instruction' on some ARM devices${NC}              ${CYAN}║${NC}"
    else
        echo -e "${CYAN}║${NC}   ${GREEN}✓ x86_64 platform detected${NC} - Full compatibility                      ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}   ${BOLD}1) Core${NC} - Essential features only                                     ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Drone control, tracking, dashboard                               ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Lighter installation, faster setup                               ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}   ${BOLD}2) Full${NC} - All features including AI/YOLO (recommended)                ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • YOLO object detection                                            ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}      • Advanced AI-based tracking                                       ${CYAN}║${NC}"
    fi

    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Set default based on platform
    local default_choice="2"
    [[ "$IS_ARM_PLATFORM" == true ]] && default_choice="1"

    while true; do
        if [[ "$IS_ARM_PLATFORM" == true ]]; then
            echo -en "   Select profile [1=Core (recommended), 2=Full]: "
        else
            echo -en "   Select profile [1=Core, 2=Full (recommended)]: "
        fi
        read -r choice

        # Use default if empty
        [[ -z "$choice" ]] && choice="$default_choice"

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
                    log_detail "Or manually install ARM torch from pytorch.org"
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
    local ARCH=$(uname -m)
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

    for spec in "${REQUIRED_SPECS[@]}"; do
        # Split spec by | to get alternatives
        IFS='|' read -ra alternatives <<< "$spec"

        # Check if any alternative is installed
        if ! any_pkg_installed "${alternatives[@]}"; then
            # Find first available alternative
            local pkg_to_install=$(find_available_pkg "${alternatives[@]}")
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
                local pkg_to_install=$(find_available_pkg "${alternatives[@]}")
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

    if [[ -d "venv" ]] && [[ -f "venv/bin/activate" ]]; then
        log_info "Existing venv found - reusing"
        log_success "Virtual environment ready"
        return 0
    fi

    # Remove corrupted venv if exists
    if [[ -d "venv" ]]; then
        log_warn "Removing corrupted venv directory..."
        rm -rf venv
    fi

    start_spinner "Creating venv..."
    if python3 -m venv venv 2>&1; then
        stop_spinner
    else
        stop_spinner
        log_error "Failed to create virtual environment"
        log_detail "Try: sudo apt install python${PYTHON_VERSION}-venv"
        exit 1
    fi

    # Validate venv was created correctly
    if [[ ! -f "venv/bin/activate" ]]; then
        log_error "Virtual environment creation failed (activate script missing)"
        log_detail "Remove 'venv/' directory and re-run"
        exit 1
    fi

    log_success "Virtual environment created"
}

# ============================================================================
# Python Dependencies (Step 4)
# ============================================================================

# Check if OpenCV has GStreamer support (custom build)
check_opencv_gstreamer() {
    if venv/bin/python -c "import cv2; print(cv2.getBuildInformation())" 2>/dev/null | grep -q "GStreamer:.*YES"; then
        return 0  # Has GStreamer
    fi
    return 1  # No GStreamer or no cv2
}

install_python_deps() {
    log_step 4 "Installing Python dependencies..."

    cd "$PIXEAGLE_DIR" || exit 1

    # Source the virtual environment
    # shellcheck source=/dev/null
    source venv/bin/activate

    # Count packages (excluding comments and empty lines)
    local total_packages
    total_packages=$(grep -c -E '^[^#[:space:]]' requirements.txt 2>/dev/null || echo "0")
    log_info "Installing packages from requirements.txt"

    # Show what will be installed based on profile
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        log_info "Profile: Core (skipping AI packages: ultralytics, ncnn, lap)"
    else
        log_info "Profile: Full (all packages including AI)"
        log_warn "Large packages (ultralytics, torch, opencv) may take several minutes"
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
    venv/bin/pip install --upgrade pip -q 2>&1 || true

    # Install with visible progress - parse pip output in real-time
    echo -e "        ${CYAN}Installing packages:${NC}"
    local install_failed=0

    # Prepare requirements file based on profile and options
    local req_file="requirements.txt"
    local using_temp_file=false

    # Build exclusion pattern
    local exclude_pattern=""
    if [[ "$SKIP_OPENCV" == true ]]; then
        exclude_pattern="opencv"
    fi
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        # Skip AI packages: ultralytics, ncnn, lap (torch is a dependency of ultralytics)
        if [[ -n "$exclude_pattern" ]]; then
            exclude_pattern="${exclude_pattern}|ultralytics|ncnn|lap"
        else
            exclude_pattern="ultralytics|ncnn|lap"
        fi
    fi

    # Create filtered requirements file if needed
    if [[ -n "$exclude_pattern" ]]; then
        req_file=$(mktemp)
        using_temp_file=true
        grep -v -iE "$exclude_pattern" requirements.txt > "$req_file"
        local filtered_count
        filtered_count=$(grep -c -E '^[^#[:space:]]' "$req_file" 2>/dev/null || echo "0")
        log_info "Installing ${filtered_count} packages (filtered from ${total_packages})"
    fi

    # Create a temp file to capture pip output for error checking
    local pip_log=$(mktemp)
    local pip_exit_code=0

    # Run pip with visible output for errors
    log_info "Running pip install (this may take a while on ARM)..."
    echo ""

    # Run pip and capture output, showing progress
    if venv/bin/pip install -r "$req_file" 2>&1 | tee "$pip_log" | while IFS= read -r line; do
        # Parse pip output for package names
        if [[ "$line" =~ ^Collecting\ (.+) ]]; then
            local pkg="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Collecting: %-55s${NC}" "${pkg:0:55}"
        elif [[ "$line" =~ ^Downloading\ (.+) ]]; then
            local file="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Downloading: %-53s${NC}" "${file:0:53}"
        elif [[ "$line" =~ ^Building\ wheel ]]; then
            printf "\r        ${YELLOW}→ Building wheel (may take several minutes)...              ${NC}"
        elif [[ "$line" =~ ^Installing\ collected\ packages ]]; then
            printf "\r        ${GREEN}→ Installing collected packages...                           ${NC}\n"
        elif [[ "$line" =~ ^Successfully\ installed ]]; then
            printf "\r        ${GREEN}✅ Packages installed successfully                            ${NC}\n"
        elif [[ "$line" =~ ^ERROR:|^error:|failed|Error: ]]; then
            printf "\n        ${RED}❌ %s${NC}\n" "$line"
        fi
    done; then
        pip_exit_code=0
    else
        pip_exit_code=${PIPESTATUS[0]}
    fi
    printf "\n"

    # Check for errors in pip log
    if grep -qi "error\|failed\|could not" "$pip_log" 2>/dev/null; then
        log_warn "pip encountered issues. Check above for details."
        # Show last few error lines
        grep -i "error\|failed" "$pip_log" | tail -5 | while read -r err; do
            log_detail "$err"
        done
    fi
    rm -f "$pip_log"

    # Clean up temp file if created
    if [[ "$using_temp_file" == true ]]; then
        rm -f "$req_file"
    fi

    # Check if pip succeeded
    # Re-run pip in check mode to verify installation
    if ! venv/bin/pip check >/dev/null 2>&1; then
        # Some dependency issues but not necessarily fatal
        log_warn "Some dependency warnings detected (usually not critical)"
    fi

    # Verify key packages are installed
    if venv/bin/python -c "import cv2; import numpy" 2>/dev/null; then
        if [[ "$INSTALL_PROFILE" == "core" ]]; then
            log_success "Core packages installed successfully (AI packages skipped)"
            log_detail "To add AI features later: pip install ultralytics"
        elif [[ "$SKIP_OPENCV" == true ]]; then
            log_success "Packages installed (preserved custom OpenCV with GStreamer)"
        else
            # Full profile - verify AI packages work
            local ai_status="unknown"
            if venv/bin/python -c "from ultralytics import YOLO; print('ok')" 2>/dev/null | grep -q "ok"; then
                ai_status="ok"
                log_success "All packages installed successfully (including AI/YOLO)"
            else
                ai_status="failed"
                log_warn "Core packages OK, but AI packages (ultralytics/torch) failed to load"

                # Uninstall broken AI packages to prevent app crashes
                log_info "Removing incompatible AI packages to ensure app stability..."
                venv/bin/pip uninstall -y ultralytics torch torchvision torchaudio 2>/dev/null || true

                if [[ "$IS_ARM_PLATFORM" == true ]]; then
                    log_detail "This is common on ARM - standard PyTorch is not compatible"
                    log_detail "The app will work with all features except AI/YOLO tracking"
                    echo ""
                    log_info "To add AI support on ARM later, try:"
                    log_detail "1. pip install torch --index-url https://download.pytorch.org/whl/cpu"
                    log_detail "2. pip install ultralytics"
                    log_detail "3. Test with: python -c \"from ultralytics import YOLO\""
                else
                    log_detail "Unexpected failure on x86 platform"
                    log_detail "Try manually: pip install ultralytics"
                fi
                # Update profile to reflect reality
                INSTALL_PROFILE="core"
            fi
        fi
    else
        if [[ "$SKIP_OPENCV" == true ]]; then
            log_error "numpy not installed correctly"
            log_detail "Custom OpenCV should still be available"
        else
            log_error "Core packages (opencv, numpy) not installed correctly"
            log_detail "Try manually: source venv/bin/activate && pip install -r requirements.txt"
        fi
        deactivate
        exit 1
    fi

    deactivate
}

# ============================================================================
# Node.js Setup via nvm (Step 5)
# ============================================================================
setup_nodejs() {
    log_step 5 "Setting up Node.js via nvm..."

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
                return 1
            fi
        else
            stop_spinner
            log_error "nvm download failed"
            log_detail "Manual install: https://github.com/nvm-sh/nvm"
            return 1
        fi
    fi

    # Check if Node.js is already installed
    if command -v node &>/dev/null; then
        local current_version
        current_version=$(node -v)
        log_info "Node.js ${current_version} already installed"
        log_success "Node.js ready"
        return 0
    fi

    # Install Node.js
    log_info "Installing Node.js ${NODE_VERSION}..."
    start_spinner "Installing Node.js..."

    if nvm install "$NODE_VERSION" >/dev/null 2>&1; then
        stop_spinner
        nvm use "$NODE_VERSION" >/dev/null 2>&1
        log_success "Node.js $(node -v) installed"
    else
        stop_spinner
        log_error "Node.js installation failed"
        log_detail "Manual install: https://nodejs.org/en/download"
        return 1
    fi
}

# ============================================================================
# Dashboard Dependencies (Step 6)
# ============================================================================
install_dashboard_deps() {
    log_step 6 "Installing dashboard dependencies..."

    cd "$PIXEAGLE_DIR" || exit 1

    if [[ ! -d "dashboard" ]]; then
        log_warn "Dashboard directory not found - skipping"
        return 0
    fi

    # Ensure nvm/node is loaded
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [[ -s "$NVM_DIR/nvm.sh" ]] && source "$NVM_DIR/nvm.sh"

    if ! command -v npm &>/dev/null; then
        log_warn "npm not available - skipping dashboard setup"
        log_detail "Install Node.js first, then run: cd dashboard && npm install"
        return 1
    fi

    cd dashboard || return 1

    if [[ -d "node_modules" ]]; then
        log_info "node_modules exists - checking for updates"
    fi

    start_spinner "Installing npm packages..."
    if npm install --silent 2>&1; then
        stop_spinner
        log_success "Dashboard dependencies installed"
    else
        stop_spinner
        log_warn "npm install had issues"
        log_detail "Try manually: cd dashboard && npm install"
    fi

    cd "$PIXEAGLE_DIR"
}

# ============================================================================
# Configuration Files (Step 7)
# ============================================================================
generate_env_from_yaml() {
    local yaml_file="$1"
    local env_file="$2"

    cd "$PIXEAGLE_DIR" || exit 1

    # shellcheck source=/dev/null
    source venv/bin/activate
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
    deactivate
}

setup_configs() {
    log_step 7 "Generating configuration files..."

    local CONFIG_DIR="$PIXEAGLE_DIR/configs"
    local DEFAULT_CONFIG="$CONFIG_DIR/config_default.yaml"
    local USER_CONFIG="$CONFIG_DIR/config.yaml"
    local DASHBOARD_DIR="$PIXEAGLE_DIR/dashboard"
    local DASHBOARD_DEFAULT_CONFIG="$DASHBOARD_DIR/env_default.yaml"
    local DASHBOARD_ENV_FILE="$DASHBOARD_DIR/.env"

    # Create configs directory if needed
    if [[ ! -d "$CONFIG_DIR" ]]; then
        mkdir -p "$CONFIG_DIR"
        log_info "Created configs directory"
    fi

    # Main config
    if [[ ! -f "$DEFAULT_CONFIG" ]]; then
        log_error "Default config not found: $DEFAULT_CONFIG"
        return 1
    fi

    if [[ -f "$USER_CONFIG" ]]; then
        # Existing config found - ask user what to do
        echo ""
        echo -e "        ${YELLOW}⚠️  Existing configs/config.yaml found${NC}"
        echo -e "        ${DIM}New releases may include new configuration options.${NC}"

        if ask_yes_no "        Replace with latest default? [y/N]: " "n"; then
            # Backup existing config
            local backup_name="${USER_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$USER_CONFIG" "$backup_name"
            cp "$DEFAULT_CONFIG" "$USER_CONFIG"
            log_success "Replaced configs/config.yaml (backup: ${backup_name##*/})"
        else
            log_info "Keeping existing configs/config.yaml"
        fi
    else
        cp "$DEFAULT_CONFIG" "$USER_CONFIG"
        log_success "Created configs/config.yaml"
    fi

    # Dashboard .env
    if [[ -f "$DASHBOARD_DEFAULT_CONFIG" ]]; then
        if [[ -f "$DASHBOARD_ENV_FILE" ]]; then
            # Existing .env found - ask user what to do
            echo ""
            echo -e "        ${YELLOW}⚠️  Existing dashboard/.env found${NC}"
            echo -e "        ${DIM}New releases may include new dashboard settings.${NC}"

            if ask_yes_no "        Replace with latest default? [y/N]: " "n"; then
                # Backup existing .env
                local backup_name="${DASHBOARD_ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
                cp "$DASHBOARD_ENV_FILE" "$backup_name"
                generate_env_from_yaml "$DASHBOARD_DEFAULT_CONFIG" "$DASHBOARD_ENV_FILE"
                log_success "Replaced dashboard/.env (backup: ${backup_name##*/})"
            else
                log_info "Keeping existing dashboard/.env"
            fi
        else
            # No existing .env - create new one
            generate_env_from_yaml "$DASHBOARD_DEFAULT_CONFIG" "$DASHBOARD_ENV_FILE"
            log_success "Created dashboard/.env"
        fi
    else
        log_warn "Dashboard env_default.yaml not found"
    fi
}

# ============================================================================
# MAVSDK Server Setup (Step 8)
# ============================================================================
setup_mavsdk_server() {
    log_step 8 "Setting up MAVSDK Server..."

    # Check bin/ first, then root for backwards compatibility
    local mavsdk_binary="$PIXEAGLE_DIR/bin/mavsdk_server_bin"
    local mavsdk_binary_legacy="$PIXEAGLE_DIR/mavsdk_server_bin"
    local download_script="$SCRIPTS_DIR/setup/download-binaries.sh"

    # Check if binary already exists (either location)
    if [[ -f "$mavsdk_binary" ]] && [[ -x "$mavsdk_binary" ]]; then
        log_success "MAVSDK Server binary already installed"
        return 0
    fi
    if [[ -f "$mavsdk_binary_legacy" ]] && [[ -x "$mavsdk_binary_legacy" ]]; then
        log_success "MAVSDK Server binary already installed (legacy location)"
        return 0
    fi

    # Check if download script exists
    if [[ ! -f "$download_script" ]]; then
        log_warn "Binary download script not found"
        log_detail "Skipping MAVSDK Server setup"
        return 1
    fi

    # Prompt user
    echo ""
    echo -e "        ${BLUE}${INFO}${NC}  MAVSDK Server is required for drone communication"

    if ask_yes_no "        Download MAVSDK Server now? [Y/n]: " "y"; then
        # Run download script with mavsdk flag
        if bash "$download_script" --mavsdk; then
            log_success "MAVSDK Server installed successfully"
            return 0
        else
            log_warn "MAVSDK Server installation failed (non-fatal)"
            log_detail "Download later: bash scripts/setup/download-binaries.sh --mavsdk"
            return 1
        fi
    else
        log_info "MAVSDK Server download skipped"
        log_detail "Download later: bash scripts/setup/download-binaries.sh --mavsdk"
        return 1
    fi
}

# ============================================================================
# MAVLink2REST Server Setup (Step 9)
# ============================================================================
setup_mavlink2rest() {
    log_step 9 "Setting up MAVLink2REST Server..."

    # Check bin/ first, then root for backwards compatibility
    local mavlink2rest_binary="$PIXEAGLE_DIR/bin/mavlink2rest"
    local mavlink2rest_binary_legacy="$PIXEAGLE_DIR/mavlink2rest"
    local download_script="$SCRIPTS_DIR/setup/download-binaries.sh"

    # Check if binary already exists (either location)
    if [[ -f "$mavlink2rest_binary" ]] && [[ -x "$mavlink2rest_binary" ]]; then
        log_success "MAVLink2REST Server binary already installed"
        return 0
    fi
    if [[ -f "$mavlink2rest_binary_legacy" ]] && [[ -x "$mavlink2rest_binary_legacy" ]]; then
        log_success "MAVLink2REST Server binary already installed (legacy location)"
        return 0
    fi

    # Check if download script exists
    if [[ ! -f "$download_script" ]]; then
        log_warn "Binary download script not found"
        log_detail "Skipping MAVLink2REST Server setup"
        return 1
    fi

    # Prompt user
    echo ""
    echo -e "        ${BLUE}${INFO}${NC}  MAVLink2REST provides REST API access to MAVLink telemetry"

    if ask_yes_no "        Download MAVLink2REST Server now? [Y/n]: " "y"; then
        # Run download script with mavlink2rest flag
        if bash "$download_script" --mavlink2rest; then
            log_success "MAVLink2REST Server installed successfully"
            return 0
        else
            log_warn "MAVLink2REST Server installation failed (non-fatal)"
            log_detail "Download later: bash scripts/setup/download-binaries.sh --mavlink2rest"
            return 1
        fi
    else
        log_info "MAVLink2REST Server download skipped"
        log_detail "Download later: bash scripts/setup/download-binaries.sh --mavlink2rest"
        return 1
    fi
}

# ============================================================================
# Summary Display
# ============================================================================
show_summary() {
    local node_version
    node_version=$(node -v 2>/dev/null || echo "not installed")

    # Check MAVSDK Server status (check both locations)
    local mavsdk_status="${RED}Not installed${NC}"
    if [[ -f "$PIXEAGLE_DIR/bin/mavsdk_server_bin" ]] || [[ -f "$PIXEAGLE_DIR/mavsdk_server_bin" ]]; then
        mavsdk_status="${GREEN}Installed${NC}"
    fi

    # Check MAVLink2REST Server status (check both locations)
    local mavlink2rest_status="${RED}Not installed${NC}"
    if [[ -f "$PIXEAGLE_DIR/bin/mavlink2rest" ]] || [[ -f "$PIXEAGLE_DIR/mavlink2rest" ]]; then
        mavlink2rest_status="${GREEN}Installed${NC}"
    fi

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}Setup Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} Python ${PYTHON_VERSION} virtual environment created"
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} Core Python dependencies installed ${DIM}(AI packages skipped)${NC}"
    else
        echo -e "   ${GREEN}${CHECK}${NC} Full Python dependencies installed ${DIM}(including AI/YOLO)${NC}"
    fi
    if [[ "$node_version" != "not installed" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} Node.js ${node_version} ready"
        echo -e "   ${GREEN}${CHECK}${NC} Dashboard dependencies installed"
    else
        echo -e "   ${YELLOW}${WARN}${NC}  Node.js needs manual setup"
    fi
    echo -e "   ${GREEN}${CHECK}${NC} Configuration files generated"
    echo -e "   MAVSDK Server:    $mavsdk_status"
    echo -e "   MAVLink2REST:     $mavlink2rest_status"
    echo ""
    echo -e "   ${CYAN}${BOLD}📋 Next Steps:${NC}"
    echo -e "      1. Edit ${BOLD}configs/config.yaml${NC} for your setup"
    echo -e "      2. Run: ${BOLD}make run${NC} (or ${BOLD}bash scripts/run.sh${NC})"
    echo ""
    echo -e "   ${YELLOW}${BOLD}⚡ Optional (better performance):${NC}"
    echo -e "      • ${BOLD}bash scripts/setup/install-dlib.sh${NC}    (faster tracking)"
    if [[ "$INSTALL_PROFILE" == "core" ]]; then
        echo -e "      • ${BOLD}pip install ultralytics${NC}              (add AI/YOLO support)"
    fi
    echo -e "      • ${BOLD}bash scripts/setup/setup-pytorch.sh${NC}   (GPU acceleration)"
    echo -e "      • ${BOLD}bash scripts/setup/build-opencv.sh${NC}    (GStreamer support)"
    if [[ "$mavsdk_status" == *"Not installed"* ]] || [[ "$mavlink2rest_status" == *"Not installed"* ]]; then
        echo -e "      • ${BOLD}bash scripts/setup/download-binaries.sh${NC}  (download binaries)"
    fi
    echo -e "      • ${BOLD}source venv/bin/activate${NC}"
    echo -e "        ${BOLD}python tools/add_yolo_model.py${NC}        (add YOLO models)"
    echo ""
    if [[ "$node_version" == "not installed" ]]; then
        echo -e "   ${RED}${BOLD}⚠️  Node.js Installation:${NC}"
        echo -e "      If nvm installation failed, install manually:"
        echo -e "      ${DIM}https://nodejs.org/en/download${NC}"
        echo -e "      Then run: ${BOLD}cd dashboard && npm install${NC}"
        echo ""
    fi
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
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
}

# Run main function
main "$@"
