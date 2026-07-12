#!/usr/bin/env bash

# ============================================================================
# scripts/setup/build-opencv.sh - Build OpenCV with GStreamer Support
# ============================================================================
# This script builds OpenCV from source with GStreamer support.
#
# Features:
#   - Professional UX with progress indicators and colors
#   - Pre-flight checks (disk space, RAM, dependencies)
#   - Automatic temporary swap creation on low-memory systems (cleaned up after build)
#   - Memory-aware parallelism (2-2.5GB per job based on RAM, CUDA-aware)
#   - Platform auto-detection: Jetson (CUDA), Raspberry Pi (NEON), ARM, x86
#   - GStreamer support for video input and QGC/GCS output
#   - Headless companion build by default; optional GTK/OpenGL with OPENCV_GUI=1
#   - Deferred replacement and automatic rollback of the active OpenCV runtime
#   - Installs into PixEagle virtual environment
#   - Verifies GStreamer support after build
#
# Requirements:
#   - Debian-based Linux (Ubuntu, Raspberry Pi OS, Jetson)
#   - 10GB+ free disk space
#   - 2GB+ RAM (script auto-creates swap if needed; 8GB+ recommended)
#   - 1-2 hours build time (depends on CPU cores and memory)
#
# Usage: bash scripts/setup/build-opencv.sh [-h|--help] [-v|--version]
#
# Author: Alireza Ghaderi
# Version: 2.0.0
# License: MIT
# ============================================================================

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=9
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
OPENCV_VERSION="4.13.0"
REQUIRED_DISK_GB=10
REQUIRED_RAM_GB=2
VERSION="2.4.0"
OPENCV_GUI="${OPENCV_GUI:-0}"

# Source shared functions with fallback
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    # Symbols
    CHECK="[✓]"; WARN="[!]"; VIDEO="[Video]"; CLOCK="[time]"; PARTY=""
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[✓]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[!]${NC} $1"; }
    log_error() { echo -e "   ${RED}[✗]${NC} $1"; }
    log_step() { echo -e "\n${CYAN}━━━ Step $1/${TOTAL_STEPS}: $2 ━━━${NC}"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}"
        [[ -n "${1:-}" ]] && echo -e "  ${BOLD}$1${NC}"
        [[ -n "${2:-}" ]] && echo -e "  ${DIM}$2${NC}"
        echo ""
    }
fi

if declare -F resolve_pixeagle_venv_dir >/dev/null 2>&1; then
    VENV_DIR="$(resolve_pixeagle_venv_dir "$PIXEAGLE_DIR")"
else
    VENV_DIR="${PIXEAGLE_VENV_DIR:-$PIXEAGLE_DIR/venv}"
fi

# ============================================================================
# Spinner for Long Operations
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
        wait "$spinner_pid" 2>/dev/null || true
        spinner_pid=""
        printf "\r        \033[K"
    fi
}

TEMP_SWAP_FILE=""
OPENCV_BACKUP_DIR=""
OPENCV_STAGE_DIR=""
OPENCV_REPLACEMENT_STARTED=false
OPENCV_REPLACEMENT_COMMITTED=false

is_safe_relative_install_path() {
    local relative_path="$1"
    [[ -n "$relative_path" && "$relative_path" != /* && "$relative_path" != */ ]] || return 1
    [[ "$relative_path" != *//* ]] || return 1

    local component
    local -a components=()
    IFS='/' read -r -a components <<< "$relative_path"
    for component in "${components[@]}"; do
        [[ -n "$component" && "$component" != "." && "$component" != ".." ]] || return 1
    done
}

assert_venv_destination_path() {
    local destination="$1"
    local relative_path
    case "$destination" in
        "$VENV_DIR"/*)
            relative_path="${destination#"$VENV_DIR"/}"
            ;;
        *)
            log_error "OpenCV destination is outside the selected venv: $destination"
            return 1
            ;;
    esac
    if ! is_safe_relative_install_path "$relative_path"; then
        log_error "OpenCV destination contains an unsafe venv-relative path: $destination"
        return 1
    fi

    local probe="$destination"
    local parent
    while [[ ! -e "$probe" && ! -L "$probe" ]]; do
        parent=$(dirname "$probe")
        if [[ "$parent" == "$probe" ]]; then
            log_error "Could not resolve an existing ancestor for OpenCV destination: $destination"
            return 1
        fi
        probe="$parent"
    done

    local canonical_probe
    canonical_probe=$(realpath -e -- "$probe" 2>/dev/null || true)
    case "$canonical_probe" in
        "$VENV_DIR"|"$VENV_DIR"/*) return 0 ;;
        *)
            log_error "OpenCV destination resolves outside the selected venv: $destination"
            return 1
            ;;
    esac
}

remove_existing_opencv_artifacts() {
    local site_packages="$1"
    local removal_failed=false
    local path
    local -a paths=()

    shopt -s nullglob
    paths=(
        "$site_packages/cv2"
        "$site_packages"/cv2*.so
        "$site_packages"/opencv*.dist-info
        "$site_packages"/opencv*.egg-info
        "$site_packages"/opencv*.libs
        "$VENV_DIR/include/opencv4"
        "$VENV_DIR/share/opencv4"
        "$VENV_DIR/share/OpenCV"
        "$VENV_DIR/share/licenses/opencv4"
        "$VENV_DIR/lib/cmake/opencv4"
        "$VENV_DIR/lib/pkgconfig/opencv4.pc"
        "$VENV_DIR/lib"/libopencv*
        "$VENV_DIR/bin"/opencv_*
    )
    shopt -u nullglob

    for path in "${paths[@]}"; do
        if ! assert_venv_destination_path "$path"; then
            removal_failed=true
            continue
        fi
        if ! rm -rf -- "$path" 2>/dev/null; then
            log_error "Could not remove the previous OpenCV artifact: $path"
            removal_failed=true
            continue
        fi
        if [[ -e "$path" || -L "$path" ]]; then
            log_error "Previous OpenCV artifact remains after removal: $path"
            removal_failed=true
        fi
    done

    [[ "$removal_failed" == false ]]
}

restore_previous_opencv() {
    [[ "$OPENCV_REPLACEMENT_STARTED" == true ]] || return 0
    [[ "$OPENCV_REPLACEMENT_COMMITTED" == false ]] || return 0
    [[ -n "$OPENCV_BACKUP_DIR" && -d "$OPENCV_BACKUP_DIR" ]] || return 0

    log_warn "Restoring the previous OpenCV runtime after an incomplete replacement..."
    local site_packages
    site_packages=$("$VENV_DIR/bin/python" -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
    site_packages=$(realpath -e -- "$site_packages" 2>/dev/null || true)
    if [[ -z "$site_packages" ]] || ! assert_venv_destination_path "$site_packages"; then
        log_error "Could not resolve site-packages for OpenCV rollback"
        return 1
    fi

    local restore_failed=false
    local install_targets="$OPENCV_BACKUP_DIR/install-targets.txt"
    if [[ -f "$install_targets" ]]; then
        while IFS= read -r installed_path; do
            case "$installed_path" in
                "$VENV_DIR"/*)
                    if ! assert_venv_destination_path "$installed_path"; then
                        restore_failed=true
                        continue
                    fi
                    if [[ -d "$installed_path" && ! -L "$installed_path" ]]; then
                        if ! rmdir -- "$installed_path" 2>/dev/null; then
                            log_error "Could not remove replacement directory during rollback: $installed_path"
                            restore_failed=true
                        fi
                    elif ! rm -f -- "$installed_path" 2>/dev/null; then
                        log_error "Could not remove replacement path during rollback: $installed_path"
                        restore_failed=true
                    fi
                    ;;
            esac
        done < "$install_targets"
    fi

    local path
    shopt -s nullglob
    for path in "$site_packages/cv2" "$site_packages"/cv2*.so \
        "$site_packages"/opencv*.dist-info "$site_packages"/opencv*.egg-info \
        "$site_packages"/opencv*.libs; do
        if ! rm -rf -- "$path" 2>/dev/null; then
            log_error "Could not remove replacement OpenCV artifact during rollback: $path"
            restore_failed=true
        fi
    done
    for path in "$VENV_DIR/lib"/libopencv*; do
        if ! rm -f -- "$path" 2>/dev/null; then
            log_error "Could not remove replacement OpenCV library during rollback: $path"
            restore_failed=true
        fi
    done
    shopt -u nullglob

    if [[ -d "$OPENCV_BACKUP_DIR/site-packages" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/site-packages/." "$site_packages/"; then
            log_error "Could not restore backed-up OpenCV site-packages artifacts"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/lib" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/lib/." "$VENV_DIR/lib/"; then
            log_error "Could not restore backed-up OpenCV libraries"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/manifest" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/manifest/." "$VENV_DIR/"; then
            log_error "Could not restore pre-existing OpenCV install-manifest targets"
            restore_failed=true
        fi
    fi
    if [[ -d "$OPENCV_BACKUP_DIR/venv-layout" ]]; then
        if ! cp -a "$OPENCV_BACKUP_DIR/venv-layout/." "$VENV_DIR/"; then
            log_error "Could not restore the previous native OpenCV venv layout"
            restore_failed=true
        fi
    fi
    if [[ "$restore_failed" == true ]]; then
        log_error "OpenCV rollback was incomplete; preserving backup at $OPENCV_BACKUP_DIR"
        return 1
    fi
    log_success "Previous OpenCV runtime restored"
}

cleanup() {
    stop_spinner
    local rollback_succeeded=true
    if ! restore_previous_opencv; then
        rollback_succeeded=false
    fi
    if [[ -n "$OPENCV_BACKUP_DIR" && -d "$OPENCV_BACKUP_DIR" ]]; then
        if [[ "$OPENCV_REPLACEMENT_COMMITTED" == true || "$rollback_succeeded" == true ]]; then
            rm -rf "$OPENCV_BACKUP_DIR"
            OPENCV_BACKUP_DIR=""
        else
            log_error "Retained OpenCV recovery backup: $OPENCV_BACKUP_DIR"
        fi
    fi
    if [[ -n "$OPENCV_STAGE_DIR" && -d "$OPENCV_STAGE_DIR" ]]; then
        rm -rf "$OPENCV_STAGE_DIR"
        OPENCV_STAGE_DIR=""
    fi
    # Remove temporary swap if we created one
    if [[ -n "$TEMP_SWAP_FILE" ]] && [[ -f "$TEMP_SWAP_FILE" ]]; then
        log_info "Cleaning up temporary swap file..."
        sudo swapoff "$TEMP_SWAP_FILE" 2>/dev/null || true
        sudo rm -f "$TEMP_SWAP_FILE" 2>/dev/null || true
        TEMP_SWAP_FILE=""
        log_success "Temporary swap removed"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    display_pixeagle_banner "${VIDEO} OpenCV Build with GStreamer" \
        "Builds OpenCV ${OPENCV_VERSION} with GStreamer support"

    # Warning about build time
    echo -e "   ${YELLOW}${WARN}${NC}  ${BOLD}This build takes 1-2 hours.${NC} Ensure you have:"
    echo -e "       • ${REQUIRED_DISK_GB}GB+ free disk space"
    echo -e "       • ${REQUIRED_RAM_GB}GB+ RAM (swap auto-created if needed; 8GB+ recommended)"
    echo -e "       • Stable internet connection"
    echo -e "       • Power supply (for laptops)"
    echo ""
}

# ============================================================================
# Parse Arguments
# ============================================================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                echo "Usage: bash scripts/setup/build-opencv.sh [OPTIONS]"
                echo ""
                echo "Build OpenCV ${OPENCV_VERSION} with GStreamer support for PixEagle."
                echo ""
                echo "Options:"
                echo "  -h, --help      Show this help message"
                echo "  -v, --version   Show script version"
                echo "  --skip-confirm  Skip confirmation prompts"
                echo ""
                echo "Environment:"
                echo "  OPENCV_GUI=1    Also build GTK/OpenGL desktop display support"
                echo ""
                echo "Requirements:"
                echo "  - ${REQUIRED_DISK_GB}GB+ free disk space"
                echo "  - ${REQUIRED_RAM_GB}GB+ RAM"
                echo "  - 1-2 hours build time"
                exit 0
                ;;
            -v|--version)
                echo "build-opencv.sh version $VERSION"
                exit 0
                ;;
            --skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

SKIP_CONFIRM=false

# ============================================================================
# Automatic Swap Management
# ============================================================================
# Creates a temporary swap file if total memory (RAM+swap) is below 6GB.
# The swap is a safety net against OOM-kill, NOT a performance tool — actual
# build parallelism is calculated from RAM only (see compile_opencv).
# Cleaned up automatically on exit (success, failure, Ctrl-C) via trap.
#
# Design decisions:
#   - Never touches existing swap — only adds when needed
#   - Swap size calculated dynamically (target: 6GB total RAM+swap)
#   - Uses /var/tmp so the file persists if the script is interrupted
#   - Requires sudo (already acquired for apt-get earlier in the flow)
ensure_build_memory() {
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local existing_swap_mb
    existing_swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
    local total_mb=$((total_ram_mb + existing_swap_mb))

    # Target: RAM + swap should be at least 6GB total.  This ensures the OOM
    # killer stays away even if a few GCC processes spike simultaneously.
    # The actual parallelism is capped by RAM (see compile_opencv), so this
    # swap is a safety net, not a performance boost.
    local target_mb=6000

    if [[ $total_mb -ge $target_mb ]]; then
        return 0  # Already enough memory
    fi

    local needed_mb=$((target_mb - total_mb))
    # Round up to nearest 512MB for filesystem alignment
    needed_mb=$(( ((needed_mb + 511) / 512) * 512 ))

    log_warn "Only ${total_mb}MB usable memory (${total_ram_mb}MB RAM + ${existing_swap_mb}MB swap)"
    log_info "Creating ${needed_mb}MB temporary swap to prevent OOM during build..."

    TEMP_SWAP_FILE="/var/tmp/.opencv_build_swap_$$"

    # fallocate is fast and preferred; dd is the fallback for older kernels/fs
    if sudo fallocate -l "${needed_mb}M" "$TEMP_SWAP_FILE" 2>/dev/null; then
        : # success
    elif sudo dd if=/dev/zero of="$TEMP_SWAP_FILE" bs=1M count="$needed_mb" status=none 2>/dev/null; then
        : # success via dd
    else
        log_warn "Could not create swap file — build will proceed without extra swap"
        TEMP_SWAP_FILE=""
        return 0
    fi

    sudo chmod 600 "$TEMP_SWAP_FILE"
    if sudo mkswap "$TEMP_SWAP_FILE" >/dev/null 2>&1 && sudo swapon "$TEMP_SWAP_FILE" 2>/dev/null; then
        local new_swap_mb
        new_swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
        local new_total=$((total_ram_mb + new_swap_mb))
        log_success "Temporary swap active — now ${new_total}MB usable (will be removed after build)"
    else
        log_warn "Could not activate swap file — build will proceed without extra swap"
        sudo rm -f "$TEMP_SWAP_FILE" 2>/dev/null || true
        TEMP_SWAP_FILE=""
    fi
}

# ============================================================================
# Platform Detection
# ============================================================================
# Detect Jetson, Raspberry Pi, or generic ARM vs x86
detect_platform() {
    PLATFORM="generic"
    ARCH="$(uname -m)"
    HAS_CUDA=false
    IS_JETSON=false
    IS_RPI=false

    # Detect NVIDIA Jetson (Nano, TX2, Xavier, Orin)
    if [[ -f /etc/nv_tegra_release ]] || [[ -d /usr/local/cuda ]] && [[ "$ARCH" == "aarch64" ]]; then
        IS_JETSON=true
        HAS_CUDA=true
        PLATFORM="jetson"
        # Detect Jetson model for CUDA arch
        CUDA_ARCH=""
        if grep -qi "nano" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="5.3"      # Maxwell (Nano)
        elif grep -qi "tx2" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="6.2"      # Pascal (TX2)
        elif grep -qi "xavier" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="7.2"      # Volta (Xavier NX/AGX)
        elif grep -qi "orin" /proc/device-tree/model 2>/dev/null; then
            CUDA_ARCH="8.7"      # Ampere (Orin)
        else
            CUDA_ARCH="5.3"      # Safe default for unknown Jetson
        fi
    # Detect Raspberry Pi
    elif grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
        IS_RPI=true
        PLATFORM="rpi"
    # Detect generic ARM
    elif [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "armv7l" ]]; then
        PLATFORM="arm"
    fi
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

    if ! sudo -v; then
        log_error "Failed to authenticate. Please try again."
        exit 1
    fi
    echo ""
}

# ============================================================================
# Pre-flight Checks (Step 1)
# ============================================================================
check_prerequisites() {
    log_step 1 "Checking prerequisites..."
    local errors=0

    # Check OS
    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "This script only supports Linux"
        errors=$((errors + 1))
    else
        local os_name=""
        if [[ -f /etc/os-release ]]; then
            os_name=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
        fi
        log_success "OS: Linux ${os_name:+($os_name)}"
    fi

    # Check disk space
    local available_gb
    available_gb=$(df -BG . 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
    if [[ -n "$available_gb" ]] && [[ "$available_gb" -lt "$REQUIRED_DISK_GB" ]]; then
        log_error "Insufficient disk space: ${available_gb}GB available, ${REQUIRED_DISK_GB}GB required"
        errors=$((errors + 1))
    else
        log_success "Disk space: ${available_gb}GB available"
    fi

    # Detect platform FIRST — needed for CUDA-aware memory budget below
    detect_platform
    log_info "Platform: ${PLATFORM} (${ARCH})"
    if [[ "$IS_JETSON" == true ]]; then
        log_info "NVIDIA Jetson detected — CUDA ${CUDA_ARCH}, NEON enabled"
    elif [[ "$IS_RPI" == true ]]; then
        log_info "Raspberry Pi detected — NEON + VFPv3 enabled"
    fi

    # Check RAM and calculate safe parallel jobs.
    # Parallelism is based on RAM only (swap is too slow for parallel GCC).
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local swap_mb
    swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
    # Budget per job from RAM (not swap), reserving 1GB for OS.
    # CUDA builds (nvcc) use more memory than pure GCC builds.
    local available_ram_mb=$((total_ram_mb - 1024))
    [[ $available_ram_mb -lt 1500 ]] && available_ram_mb=1500
    local mem_per_job_mb=2000
    [[ "$HAS_CUDA" == true ]] && mem_per_job_mb=2500
    local safe_jobs=$((available_ram_mb / mem_per_job_mb))
    [[ $safe_jobs -lt 1 ]] && safe_jobs=1

    if [[ $total_ram_mb -lt 6000 ]]; then
        log_warn "Limited RAM: ${total_ram_mb}MB RAM + ${swap_mb}MB swap"
        log_detail "Parallel jobs limited to -j${safe_jobs} (based on RAM, not swap)"
        log_detail "Temporary swap will be created automatically if needed"
    else
        log_success "RAM: ${total_ram_mb}MB + ${swap_mb}MB swap"
    fi

    # Check PixEagle venv
    if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_DIR/bin/activate" ]]; then
        log_error "PixEagle virtual environment not found"
        log_detail "Run 'make init' (or 'bash scripts/init.sh') first"
        errors=$((errors + 1))
    else
        local canonical_venv
        canonical_venv=$(realpath -e -- "$VENV_DIR" 2>/dev/null || true)
        if [[ -z "$canonical_venv" || ! -d "$canonical_venv" || ! -x "$canonical_venv/bin/python" ]]; then
            log_error "PixEagle virtual environment could not be resolved safely"
            errors=$((errors + 1))
        else
            VENV_DIR="$canonical_venv"
            log_success "PixEagle venv found: $VENV_DIR"
        fi
    fi

    # Check required commands
    for cmd in git cmake make pkg-config; do
        if ! command -v "$cmd" &>/dev/null; then
            log_warn "Missing command: $cmd (will be installed)"
        fi
    done

    # Check Python version
    if [[ -f "$VENV_DIR/bin/python" ]]; then
        local python_version
        python_version=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
        log_success "Python: ${python_version}"
    fi

    # Estimate build time
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "1")
    log_info "CPU cores: ${cpu_cores} (will use all for parallel build)"

    if [[ $errors -gt 0 ]]; then
        echo ""
        log_error "Prerequisites check failed with $errors error(s)"
        exit 1
    fi

    # Confirm with user
    if [[ "$SKIP_CONFIRM" != true ]]; then
        echo ""
        echo -e "        ${YELLOW}Ready to build OpenCV ${OPENCV_VERSION} with GStreamer.${NC}"
        if [[ "$OPENCV_GUI" == "1" ]]; then
            log_detail "Desktop GTK/OpenGL support: enabled"
        else
            log_detail "Desktop GTK/OpenGL support: disabled (headless companion default)"
        fi
        echo -e "        ${DIM}This will take approximately 1-2 hours.${NC}"
        echo -en "        Continue? [Y/n]: "
        read -r REPLY
        echo ""
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            log_info "Build cancelled by user"
            exit 0
        fi
    fi
}

# ============================================================================
# Install System Dependencies (Step 2)
# ============================================================================
install_dependencies() {
    log_step 2 "Installing system dependencies..."

    prompt_sudo

    start_spinner "Updating package lists..."
    if sudo apt-get update -qq 2>&1; then
        stop_spinner
        log_success "Package lists updated"
    else
        stop_spinner
        log_warn "apt update had warnings (continuing)"
    fi

    # Core build packages (always needed)
    local core_packages=(
        build-essential
        cmake
        git
        pkg-config
        python3-dev
    )

    # GStreamer packages
    local gstreamer_packages=(
        libgstreamer1.0-dev
        libgstreamer-plugins-base1.0-dev
        gstreamer1.0-tools
        gstreamer1.0-libav
        gstreamer1.0-plugins-base
        gstreamer1.0-plugins-good
        gstreamer1.0-plugins-bad
        gstreamer1.0-plugins-ugly
    )

    # Optional GStreamer packages (may not exist on all distros)
    local optional_gstreamer=(
        gstreamer1.0-gl
        gstreamer1.0-gtk3
        gstreamer1.0-rtsp
        libgstrtspserver-1.0-dev
    )

    # Video/Image libraries
    local media_packages=(
        libavcodec-dev
        libavformat-dev
        libavutil-dev
        libswscale-dev
        libswresample-dev
        libv4l-dev
        v4l-utils
        libjpeg-dev
        libpng-dev
        libtiff-dev
        libwebp-dev
    )

    # Optional media packages (may not exist on all distros)
    local optional_media=(
        libxvidcore-dev
        libx264-dev
    )

    # GUI + OpenGL packages are optional on companion/headless systems.
    local gui_packages=(
        libgtk-3-dev
        libgtk2.0-dev
        libgl1-mesa-dev
        libglu1-mesa-dev
    )

    # Math / linear algebra packages
    local math_packages=(
        libatlas-base-dev
        gfortran
        libtbb-dev
        libeigen3-dev
    )

    # Install core packages first (required)
    log_info "Installing core build packages..."
    if ! sudo apt-get install -y "${core_packages[@]}" 2>&1 | tail -5; then
        log_error "Failed to install core packages"
        exit 1
    fi
    log_success "Core packages installed"

    # Install GStreamer packages (required for our use case)
    log_info "Installing GStreamer packages..."
    if ! sudo apt-get install -y "${gstreamer_packages[@]}" 2>&1 | tail -5; then
        log_error "Failed to install GStreamer packages"
        exit 1
    fi
    log_success "GStreamer packages installed"

    # Install optional GStreamer (ignore errors)
    log_info "Installing optional GStreamer packages..."
    for pkg in "${optional_gstreamer[@]}"; do
        sudo apt-get install -y "$pkg" >/dev/null 2>&1 || log_warn "Optional package $pkg not available (OK)"
    done

    # Install media packages
    log_info "Installing media/video packages..."
    if ! sudo apt-get install -y "${media_packages[@]}" 2>&1 | tail -5; then
        log_warn "Some media packages failed (continuing)"
    fi

    # Install optional media (ignore errors)
    for pkg in "${optional_media[@]}"; do
        sudo apt-get install -y "$pkg" >/dev/null 2>&1 || log_warn "Optional package $pkg not available (OK)"
    done

    if [[ "$OPENCV_GUI" == "1" ]]; then
        log_info "Installing optional GUI packages..."
        if ! sudo apt-get install -y "${gui_packages[@]}" >/dev/null 2>&1; then
            log_error "OPENCV_GUI=1 was requested but GUI dependencies could not be installed"
            exit 1
        fi
    else
        log_info "Skipping GTK/OpenGL packages for the headless companion build"
    fi

    # Install math packages
    log_info "Installing math packages..."
    sudo apt-get install -y "${math_packages[@]}" >/dev/null 2>&1 || log_warn "Math packages may be missing"

    log_success "System dependencies installed"
}

# ============================================================================
# Configure GStreamer Environment (Step 3)
# ============================================================================
setup_gstreamer_env() {
    log_step 3 "Configuring GStreamer environment..."

    # Verify GStreamer is available
    if pkg-config --exists gstreamer-1.0 2>/dev/null; then
        local gst_version
        gst_version=$(pkg-config --modversion gstreamer-1.0 2>/dev/null)
        log_success "GStreamer ${gst_version} found"
    else
        log_error "GStreamer development metadata is unavailable to pkg-config"
        log_detail "Install the GStreamer development packages before building OpenCV"
        exit 1
    fi

    if command -v gst-inspect-1.0 >/dev/null 2>&1; then
        log_success "GStreamer plugin discovery is available"
    else
        log_error "gst-inspect-1.0 is unavailable after dependency installation"
        exit 1
    fi
}

# ============================================================================
# Clone OpenCV Repositories (Step 4)
# ============================================================================
clone_opencv() {
    log_step 4 "Cloning OpenCV ${OPENCV_VERSION} repositories..."

    local opencv_dir="$SCRIPT_DIR/opencv"
    local contrib_dir="$SCRIPT_DIR/opencv_contrib"

    # Clone or update opencv
    if [[ ! -d "$opencv_dir" ]]; then
        start_spinner "Cloning opencv..."
        if git clone https://github.com/opencv/opencv.git "$opencv_dir" >/dev/null 2>&1; then
            stop_spinner
            log_success "Cloned opencv repository"
        else
            stop_spinner
            log_error "Failed to clone opencv"
            exit 1
        fi
    else
        start_spinner "Updating opencv..."
        git -C "$opencv_dir" fetch --all >/dev/null 2>&1
        stop_spinner
        log_info "opencv repository exists - updating"
    fi

    # Clone or update opencv_contrib
    if [[ ! -d "$contrib_dir" ]]; then
        start_spinner "Cloning opencv_contrib..."
        if git clone https://github.com/opencv/opencv_contrib.git "$contrib_dir" >/dev/null 2>&1; then
            stop_spinner
            log_success "Cloned opencv_contrib repository"
        else
            stop_spinner
            log_error "Failed to clone opencv_contrib"
            exit 1
        fi
    else
        start_spinner "Updating opencv_contrib..."
        git -C "$contrib_dir" fetch --all >/dev/null 2>&1
        stop_spinner
        log_info "opencv_contrib repository exists - updating"
    fi

    # Checkout specific version
    start_spinner "Checking out version ${OPENCV_VERSION}..."
    git -C "$opencv_dir" checkout "$OPENCV_VERSION" >/dev/null 2>&1
    git -C "$contrib_dir" checkout "$OPENCV_VERSION" >/dev/null 2>&1
    stop_spinner
    log_success "Checked out OpenCV ${OPENCV_VERSION}"
}

# ============================================================================
# Setup Python Environment (Step 5)
# ============================================================================
setup_python_env() {
    log_step 5 "Setting up Python environment..."

    # Activate PixEagle venv
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    log_success "Activated PixEagle virtual environment"

    log_info "Keeping the active OpenCV runtime in place until compilation succeeds"

    # Install numpy if needed
    if ! "$VENV_DIR/bin/python" -c "import numpy" 2>/dev/null; then
        start_spinner "Installing numpy..."
        "$VENV_DIR/bin/pip" install numpy -q
        stop_spinner
        log_success "Installed numpy"
    else
        log_success "numpy already installed"
    fi
}

prepare_opencv_replacement() {
    local site_packages
    site_packages=$("$VENV_DIR/bin/python" -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
    site_packages=$(realpath -e -- "$site_packages" 2>/dev/null || true)
    if [[ -z "$site_packages" || ! -d "$site_packages" ]] \
        || ! assert_venv_destination_path "$site_packages"; then
        log_error "Could not resolve the PixEagle venv site-packages directory"
        exit 1
    fi

    local install_manifest="$SCRIPT_DIR/opencv/build/install_manifest.txt"
    local staged_prefix="${OPENCV_STAGE_DIR}${VENV_DIR}"
    if [[ -z "$OPENCV_STAGE_DIR" || ! -d "$staged_prefix" || ! -s "$install_manifest" ]]; then
        log_error "Staged OpenCV installation or install manifest is unavailable"
        exit 1
    fi

    OPENCV_BACKUP_DIR=$(mktemp -d "/var/tmp/pixeagle-opencv-backup.XXXXXX")
    mkdir -p \
        "$OPENCV_BACKUP_DIR/site-packages" \
        "$OPENCV_BACKUP_DIR/lib" \
        "$OPENCV_BACKUP_DIR/manifest" \
        "$OPENCV_BACKUP_DIR/venv-layout"

    local installed_path
    local relative_path
    local target_path
    while IFS= read -r installed_path; do
        case "$installed_path" in
            "$staged_prefix"/*)
                relative_path="${installed_path#"$staged_prefix"/}"
                ;;
            "$VENV_DIR"/*)
                relative_path="${installed_path#"$VENV_DIR"/}"
                ;;
            *)
                log_error "OpenCV install manifest contains a path outside the PixEagle venv: $installed_path"
                exit 1
                ;;
        esac
        if ! is_safe_relative_install_path "$relative_path"; then
            log_error "OpenCV install manifest contains an unsafe relative path: $installed_path"
            exit 1
        fi
        target_path="$VENV_DIR/$relative_path"
        if ! assert_venv_destination_path "$target_path"; then
            exit 1
        fi
        printf '%s\n' "$target_path" >> "$OPENCV_BACKUP_DIR/install-targets.txt"
        if [[ -e "$target_path" || -L "$target_path" ]]; then
            mkdir -p "$OPENCV_BACKUP_DIR/manifest/$(dirname "$relative_path")"
            cp -a -- "$target_path" "$OPENCV_BACKUP_DIR/manifest/$relative_path"
        fi
    done < "$install_manifest"

    if [[ ! -s "$OPENCV_BACKUP_DIR/install-targets.txt" ]]; then
        log_error "OpenCV staged install produced an empty target manifest"
        exit 1
    fi

    local path
    shopt -s nullglob
    for path in "$site_packages/cv2" "$site_packages"/cv2*.so \
        "$site_packages"/opencv*.dist-info "$site_packages"/opencv*.egg-info \
        "$site_packages"/opencv*.libs; do
        cp -a "$path" "$OPENCV_BACKUP_DIR/site-packages/"
    done
    for path in "$VENV_DIR/lib"/libopencv*; do
        cp -a "$path" "$OPENCV_BACKUP_DIR/lib/"
    done
    for path in \
        "$VENV_DIR/include/opencv4" \
        "$VENV_DIR/share/opencv4" \
        "$VENV_DIR/share/OpenCV" \
        "$VENV_DIR/share/licenses/opencv4" \
        "$VENV_DIR/lib/cmake/opencv4" \
        "$VENV_DIR/lib/pkgconfig/opencv4.pc" \
        "$VENV_DIR/lib"/libopencv* \
        "$VENV_DIR/bin"/opencv_*; do
        if ! assert_venv_destination_path "$path"; then
            exit 1
        fi
        if [[ -e "$path" || -L "$path" ]]; then
            relative_path="${path#"$VENV_DIR"/}"
            mkdir -p "$OPENCV_BACKUP_DIR/venv-layout/$(dirname "$relative_path")"
            cp -a -- "$path" "$OPENCV_BACKUP_DIR/venv-layout/$relative_path"
        fi
    done
    shopt -u nullglob

    OPENCV_REPLACEMENT_STARTED=true
    log_info "Compiled successfully; replacing the active OpenCV runtime with rollback protection..."
    if ! "$VENV_DIR/bin/python" -m pip uninstall -y \
        opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless \
        >/dev/null 2>&1; then
        log_error "Could not uninstall the previous OpenCV wheel packages"
        exit 1
    fi
    if ! remove_existing_opencv_artifacts "$site_packages"; then
        log_error "Previous OpenCV cleanup was incomplete; staged files were not installed"
        exit 1
    fi
}

stage_opencv_installation() {
    OPENCV_STAGE_DIR=$(mktemp -d "/var/tmp/pixeagle-opencv-stage.XXXXXX")
    start_spinner "Staging compiled OpenCV installation..."
    if DESTDIR="$OPENCV_STAGE_DIR" make install >/dev/null 2>&1; then
        stop_spinner
    else
        stop_spinner
        log_error "Could not stage the compiled OpenCV installation"
        exit 1
    fi

    if [[ ! -d "${OPENCV_STAGE_DIR}${VENV_DIR}" ]] \
        || [[ ! -s "$SCRIPT_DIR/opencv/build/install_manifest.txt" ]]; then
        log_error "Staged OpenCV installation is incomplete"
        exit 1
    fi
    log_success "Compiled OpenCV staged without changing the active runtime"
}

# ============================================================================
# Create Build Directory (Step 6)
# ============================================================================
prepare_build() {
    log_step 6 "Preparing build directory..."

    local build_dir="$SCRIPT_DIR/opencv/build"

    # Remove old build if exists
    if [[ -d "$build_dir" ]]; then
        log_info "Removing old build directory..."
        rm -rf "$build_dir"
    fi

    mkdir -p "$build_dir"
    cd "$build_dir"

    log_success "Build directory ready: $build_dir"
}

# ============================================================================
# Configure CMake (Step 7)
# ============================================================================
configure_cmake() {
    log_step 7 "Configuring CMake build..."

    log_info "This may take a few minutes..."

    local gui_backend="OFF"
    if [[ "$OPENCV_GUI" == "1" ]]; then
        gui_backend="ON"
    fi

    local cmake_args=(
        -D CMAKE_BUILD_TYPE=Release
        -D CMAKE_INSTALL_PREFIX="$VENV_DIR"
        -D OPENCV_EXTRA_MODULES_PATH="$SCRIPT_DIR/opencv_contrib/modules"
        -D WITH_GSTREAMER=ON
        -D WITH_GTK="$gui_backend"
        -D WITH_OPENGL="$gui_backend"
        -D WITH_FFMPEG=ON
        -D WITH_V4L=ON
        -D WITH_TBB=ON
        -D BUILD_EXAMPLES=OFF
        -D BUILD_TESTS=OFF
        -D BUILD_PERF_TESTS=OFF
        -D BUILD_DOCS=OFF
        -D PYTHON3_EXECUTABLE="$VENV_DIR/bin/python"
        -D PYTHON3_INCLUDE_DIR="$("$VENV_DIR/bin/python" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
        -D PYTHON3_LIBRARY="$("$VENV_DIR/bin/python" -c 'import os, sysconfig; print(os.path.join(sysconfig.get_config_var("LIBDIR"), sysconfig.get_config_var("LDLIBRARY")))' 2>/dev/null || echo "")"
        -D Python3_FIND_REGISTRY=NEVER
        -D Python3_FIND_IMPLEMENTATIONS=CPython
        -D Python3_FIND_STRATEGY=LOCATION
    )

    # Platform-specific CMake flags
    if [[ "$IS_JETSON" == true ]]; then
        # CUDA is opt-in because:
        #   - This script's purpose is GStreamer support, not CUDA
        #   - CUDA compilation adds 30-60 min and needs 2-3x more RAM per job
        #   - PixEagle uses PyTorch (ultralytics) for inference, not OpenCV CUDA
        #   - OpenCV CUDA is for cv2.cuda functions (resize, threshold, etc.)
        # Enable with: OPENCV_CUDA=1 bash scripts/setup/build-opencv.sh
        if [[ "${OPENCV_CUDA:-0}" == "1" ]]; then
            log_info "Adding Jetson CUDA flags (CUDA arch ${CUDA_ARCH}) — opt-in via OPENCV_CUDA=1"
            cmake_args+=(
                -D WITH_CUDA=ON
                -D CUDA_ARCH_BIN="${CUDA_ARCH}"
                -D CUDA_ARCH_PTX=""
                -D WITH_CUDNN=ON
                -D CUDA_FAST_MATH=ON
                -D WITH_CUBLAS=ON
            )
            # DNN CUDA is a further opt-in (extremely memory-heavy)
            if [[ "${OPENCV_DNN_CUDA:-0}" == "1" ]]; then
                log_info "OPENCV_DNN_CUDA enabled — expect 3-5GB/job peak memory"
                cmake_args+=( -D OPENCV_DNN_CUDA=ON )
            else
                cmake_args+=( -D OPENCV_DNN_CUDA=OFF )
            fi
        else
            log_info "Jetson detected but CUDA disabled (not needed for GStreamer)"
            log_detail "To enable: OPENCV_CUDA=1 bash scripts/setup/build-opencv.sh"
            HAS_CUDA=false  # Override so memory budget uses GCC values
        fi
        # Always enable NEON on Jetson (ARM optimization, no extra memory cost)
        cmake_args+=( -D ENABLE_NEON=ON )
    elif [[ "$ARCH" == "aarch64" ]]; then
        log_info "Adding ARM64 NEON optimization flags"
        cmake_args+=( -D ENABLE_NEON=ON )
    elif [[ "$ARCH" == "armv7l" ]]; then
        log_info "Adding ARM32 NEON + VFPv3 optimization flags"
        cmake_args+=(
            -D ENABLE_NEON=ON
            -D ENABLE_VFPV3=ON
            -D CPU_BASELINE=NEON
        )
    fi

    start_spinner "Running CMake configuration..."
    if cmake .. "${cmake_args[@]}" > cmake_output.log 2>&1; then
        stop_spinner
        log_success "CMake configuration complete"
    else
        stop_spinner
        log_error "CMake configuration failed"
        log_detail "Check scripts/setup/opencv/build/cmake_output.log for details"
        exit 1
    fi

    # Verify GStreamer is enabled
    if grep -q "GStreamer:.*YES" cmake_output.log 2>/dev/null; then
        log_success "GStreamer support enabled in build"
    else
        log_error "CMake completed without enabling the required GStreamer backend"
        log_detail "Check scripts/setup/opencv/build/cmake_output.log before retrying"
        exit 1
    fi
}

# ============================================================================
# Compile OpenCV (Step 8)
# ============================================================================
compile_opencv() {
    log_step 8 "Compiling OpenCV... ${CLOCK} (this takes 1-2 hours)"

    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "1")

    # Calculate safe parallelism based on PHYSICAL RAM only.
    # Swap prevents OOM-kill but is ~100x slower than RAM — running many
    # parallel GCC jobs backed by swap causes thrashing and eventual failure.
    local make_jobs
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    local swap_mb
    swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')

    # Reserve ~1GB for the OS and other processes
    local available_ram_mb=$((total_ram_mb - 1024))
    [[ $available_ram_mb -lt 1500 ]] && available_ram_mb=1500

    # nvcc (CUDA compiler) uses 2-3GB per compilation unit vs ~1.5-2GB for gcc.
    # Budget accordingly based on whether CUDA is enabled.
    local mem_per_job_mb=2000
    if [[ "$HAS_CUDA" == true ]]; then
        mem_per_job_mb=2500
        log_info "CUDA build detected — using ${mem_per_job_mb}MB/job budget (nvcc is memory-heavy)"
    fi

    local mem_safe_jobs=$((available_ram_mb / mem_per_job_mb))
    [[ $mem_safe_jobs -lt 1 ]] && mem_safe_jobs=1

    # Use the lesser of CPU cores and memory-safe jobs
    if [[ $mem_safe_jobs -lt $cpu_cores ]]; then
        make_jobs=$mem_safe_jobs
        log_warn "Memory-limited build: -j${make_jobs} (${total_ram_mb}MB RAM, ${swap_mb}MB swap, ~${mem_per_job_mb}MB/job)"
        if [[ $make_jobs -eq 1 ]]; then
            log_info "This will be SLOW (~2-3 hours) but should complete without OOM"
        fi
    else
        make_jobs="$cpu_cores"
        log_info "Using ${make_jobs} parallel jobs (${total_ram_mb}MB RAM available)"
    fi

    log_info "Go grab a coffee... ${VIDEO}"
    echo ""

    # Run make with progress
    local start_time
    start_time=$(date +%s)

    echo -e "        ${CYAN}Build progress:${NC}"

    # Save full build output for diagnostics on failure
    local build_log="build_output.log"

    # Compile with appropriate parallelism
    if make -j"$make_jobs" 2>&1 | tee "$build_log" | while IFS= read -r line; do
        # Parse make output for progress
        if [[ "$line" =~ ^\[\ *([0-9]+)%\] ]]; then
            local percent="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Building: [%3d%%]${NC}" "$percent"
        fi
    done; then
        echo ""
        log_success "Compilation complete"
    else
        echo ""
        log_error "Compilation failed"
        # Check if OOM killer was involved
        if dmesg 2>/dev/null | tail -20 | grep -qi "out of memory\|oom-kill\|killed process"; then
            log_error "OOM killer detected — not enough RAM for -j${make_jobs}"
            log_detail "Your system ran out of memory during compilation."
            if [[ "$HAS_CUDA" == true ]] && [[ "${OPENCV_DNN_CUDA:-0}" == "1" ]]; then
                log_detail "Try without DNN CUDA: unset OPENCV_DNN_CUDA and re-run"
            fi
        fi
        # Show last few error lines from the build log
        if [[ -f "$build_log" ]]; then
            log_detail "Last lines of build output:"
            tail -10 "$build_log" | while IFS= read -r errline; do
                log_detail "  $errline"
            done
            log_detail "Full log: $(pwd)/$build_log"
        fi
        exit 1
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    log_info "Build time: ${minutes} minutes"

    # Stage first so the complete destination manifest is known before any live
    # venv path is changed. The EXIT trap restores every overwritten target.
    stage_opencv_installation
    prepare_opencv_replacement

    start_spinner "Installing staged OpenCV into the virtual environment..."
    if cp -a "${OPENCV_STAGE_DIR}${VENV_DIR}/." "$VENV_DIR/"; then
        stop_spinner
        log_success "Installed to $VENV_DIR"
    else
        stop_spinner
        log_error "Installation failed"
        exit 1
    fi
}

# ============================================================================
# Verify Installation (Step 9)
# ============================================================================
verify_installation() {
    log_step 9 "Verifying the replacement OpenCV runtime..."

    local test_result
    if ! test_result=$(PIXEAGLE_EXPECTED_OPENCV_VERSION="$OPENCV_VERSION" \
        PIXEAGLE_EXPECTED_VENV="$VENV_DIR" \
        timeout 30s "$VENV_DIR/bin/python" 2>&1 << 'PYEOF'
try:
    import os
    import re
    from pathlib import Path
    from tempfile import TemporaryDirectory

    import cv2
    import numpy as np

    build_info = cv2.getBuildInformation()
    version = cv2.__version__
    module_path = Path(cv2.__file__).resolve()
    expected_venv = Path(os.environ["PIXEAGLE_EXPECTED_VENV"]).resolve()

    def build_feature_enabled(name):
        return re.search(
            rf"^\s*{re.escape(name)}\s*:\s*YES\b",
            build_info,
            flags=re.IGNORECASE | re.MULTILINE,
        ) is not None

    legacy = getattr(cv2, "legacy", None)

    def instantiate_tracker(name):
        factory = getattr(cv2, name, None)
        if not callable(factory):
            factory = getattr(legacy, name, None)
        return callable(factory) and factory() is not None

    csrt = instantiate_tracker("TrackerCSRT_create")
    kcf = instantiate_tracker("TrackerKCF_create")

    with TemporaryDirectory(prefix="pixeagle-opencv-verify-") as temp_dir:
        sink_path = Path(temp_dir) / "frame.raw"
        escaped_sink = str(sink_path).replace("\\", "\\\\").replace('"', '\\"')
        writer = cv2.VideoWriter(
            f'appsrc ! videoconvert ! filesink location="{escaped_sink}" sync=false',
            cv2.CAP_GSTREAMER,
            0,
            5.0,
            (16, 16),
            True,
        )
        writer_opened = writer.isOpened()
        try:
            if writer_opened:
                writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
        finally:
            writer.release()
        sink_observed = writer_opened and sink_path.is_file() and sink_path.stat().st_size > 0

    print(f"VERSION:{version}")
    print(f"MODULE_PATH:{module_path}")
    print(f"PATH_IN_VENV:{module_path.is_relative_to(expected_venv)}")
    print(f"VERSION_MATCH:{version == os.environ['PIXEAGLE_EXPECTED_OPENCV_VERSION']}")
    print(f"GSTREAMER:{build_feature_enabled('GStreamer')}")
    print(f"FFMPEG:{build_feature_enabled('FFMPEG')}")
    print(f"TRACKER_CSRT_INSTANTIATED:{csrt}")
    print(f"TRACKER_KCF_INSTANTIATED:{kcf}")
    print(f"GSTREAMER_SINK_OBSERVED:{sink_observed}")
except Exception as e:
    print(f"ERROR:{type(e).__name__}:{e}")
PYEOF
    ); then
        log_error "OpenCV verification timed out or could not start"
        exit 1
    fi

    local cv_version
    cv_version=$(echo "$test_result" | grep "VERSION:" | cut -d':' -f2 || true)
    local module_path
    module_path=$(echo "$test_result" | grep "MODULE_PATH:" | cut -d':' -f2- || true)

    if [[ -n "$cv_version" ]]; then
        log_success "OpenCV ${cv_version} imported from ${module_path}"
    else
        log_error "OpenCV import failed"
        log_detail "$test_result"
        exit 1
    fi

    local check
    for check in PATH_IN_VENV VERSION_MATCH GSTREAMER FFMPEG \
        TRACKER_CSRT_INSTANTIATED TRACKER_KCF_INSTANTIATED GSTREAMER_SINK_OBSERVED; do
        if ! grep -q "^${check}:True$" <<<"$test_result"; then
            log_error "OpenCV replacement verification failed: ${check}"
            log_detail "$test_result"
            exit 1
        fi
    done

    log_success "Verified venv path, exact version, instantiated trackers, FFmpeg, and an observed GStreamer sink"

    OPENCV_REPLACEMENT_COMMITTED=true
}

# ============================================================================
# Summary Display
# ============================================================================
show_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}OpenCV Build Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} OpenCV ${OPENCV_VERSION} built from source"
    echo -e "   ${GREEN}${CHECK}${NC} GStreamer support enabled"
    echo -e "   ${GREEN}${CHECK}${NC} Installed to PixEagle venv"
    echo ""
    echo -e "   ${CYAN}${BOLD}📋 Next Steps:${NC}"
    echo -e "      1. If needed, create/apply a local override and set:"
    echo -e "         ${DIM}VideoSource.USE_GSTREAMER: true${NC}"
    echo -e "      2. Configure your video source through the dashboard or local override"
    echo -e "      3. Run PixEagle: ${BOLD}bash scripts/run.sh${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}💡 Test GStreamer support:${NC}"
    echo -e "      ${DIM}source ${VENV_DIR#"$PIXEAGLE_DIR"/}/bin/activate${NC}"
    echo -e "      ${DIM}python -c \"import cv2; print(cv2.getBuildInformation())\" | grep GStreamer${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    parse_args "$@"
    if [[ "$OPENCV_GUI" != "0" && "$OPENCV_GUI" != "1" ]]; then
        log_error "OPENCV_GUI must be 0 or 1"
        exit 2
    fi
    display_banner
    check_prerequisites
    install_dependencies
    setup_gstreamer_env
    clone_opencv
    setup_python_env
    prepare_build
    configure_cmake
    # Ensure enough memory before the heavy compilation step.
    # This creates temporary swap if RAM+swap is below the safe threshold.
    # The swap is automatically removed on exit (see cleanup trap).
    ensure_build_memory
    compile_opencv
    verify_installation
    show_summary
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
