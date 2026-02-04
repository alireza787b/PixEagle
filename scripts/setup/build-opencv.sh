#!/usr/bin/env bash

# ============================================================================
# scripts/setup/build-opencv.sh - Build OpenCV with GStreamer Support
# ============================================================================
# This script builds OpenCV from source with GStreamer, Qt, and OpenGL support.
#
# Features:
#   - Professional UX with progress indicators and colors
#   - Pre-flight checks (disk space, RAM, dependencies)
#   - GStreamer and Qt support for video streaming
#   - Installs into PixEagle virtual environment
#   - Verifies GStreamer support after build
#
# Requirements:
#   - Debian-based Linux (Ubuntu, Raspberry Pi OS)
#   - 10GB+ free disk space
#   - 4GB+ RAM (8GB recommended for parallel build)
#   - 1-2 hours build time (depends on CPU cores)
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
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
VENV_DIR="$PIXEAGLE_DIR/venv"
OPENCV_VERSION="4.9.0"
REQUIRED_DISK_GB=10
REQUIRED_RAM_GB=4
VERSION="2.1.0"

# Fix CRLF line endings
[[ -f "$SCRIPTS_DIR/lib/common.sh" ]] && grep -q $'\r' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && \
    sed -i.bak 's/\r$//' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && rm -f "$SCRIPTS_DIR/lib/common.sh.bak"

# Source shared functions with fallback
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    # Symbols
    CHECK="[✓]"; CROSS="[✗]"; WARN="[!]"; INFO="[i]"; VIDEO="[Video]"; PARTY=""
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

cleanup() {
    stop_spinner
}
trap cleanup EXIT

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    display_pixeagle_banner "${VIDEO} OpenCV Build with GStreamer" \
        "Builds OpenCV ${OPENCV_VERSION} with GStreamer, Qt, and OpenGL support"

    # Warning about build time
    echo -e "   ${YELLOW}${WARN}${NC}  ${BOLD}This build takes 1-2 hours.${NC} Ensure you have:"
    echo -e "       • ${REQUIRED_DISK_GB}GB+ free disk space"
    echo -e "       • ${REQUIRED_RAM_GB}GB+ RAM (8GB recommended)"
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
LOW_RAM_MODE=false

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

    # Check RAM
    local total_ram_gb
    total_ram_gb=$(free -g 2>/dev/null | awk '/^Mem:/ {print $2}')
    local total_ram_mb
    total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')

    # Check swap
    local swap_mb
    swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')

    if [[ -n "$total_ram_gb" ]] && [[ "$total_ram_gb" -lt "$REQUIRED_RAM_GB" ]]; then
        log_warn "Low RAM: ${total_ram_mb}MB (${REQUIRED_RAM_GB}GB+ recommended)"
        LOW_RAM_MODE=true

        # Check if we have enough swap
        local total_memory_mb=$((total_ram_mb + swap_mb))
        if [[ $total_memory_mb -lt 3000 ]]; then
            log_warn "Total memory (RAM+Swap): ${total_memory_mb}MB"
            log_detail "Will use single-threaded build (-j1) to prevent OOM"
            log_detail "Consider adding swap: sudo dphys-swapfile swapoff && sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile && sudo dphys-swapfile setup && sudo dphys-swapfile swapon"
        else
            log_info "Swap available: ${swap_mb}MB (total: ${total_memory_mb}MB)"
            log_detail "Will use limited parallelism (-j2) for build"
        fi
    else
        log_success "RAM: ${total_ram_gb}GB available"
        LOW_RAM_MODE=false
    fi

    # Check PixEagle venv
    if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_DIR/bin/activate" ]]; then
        log_error "PixEagle virtual environment not found"
        log_detail "Run 'bash init_pixeagle.sh' first"
        errors=$((errors + 1))
    else
        log_success "PixEagle venv found"
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
        gstreamer1.0-plugins-good
        gstreamer1.0-plugins-bad
        gstreamer1.0-plugins-ugly
    )

    # Optional GStreamer packages (may not exist on all distros)
    local optional_gstreamer=(
        gstreamer1.0-gl
        gstreamer1.0-gtk3
    )

    # Video/Image libraries
    local media_packages=(
        libavcodec-dev
        libavformat-dev
        libswscale-dev
        libv4l-dev
        libjpeg-dev
        libpng-dev
        libtiff-dev
    )

    # Optional media packages (may not exist on all distros)
    local optional_media=(
        libxvidcore-dev
        libx264-dev
    )

    # GUI packages
    local gui_packages=(
        libgtk2.0-dev
    )

    # Math packages
    local math_packages=(
        libatlas-base-dev
        gfortran
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

    # Install GUI packages
    log_info "Installing GUI packages..."
    sudo apt-get install -y "${gui_packages[@]}" >/dev/null 2>&1 || log_warn "GUI packages may be missing"

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

    export PKG_CONFIG_PATH=/usr/lib/pkgconfig
    export GST_PLUGIN_PATH=/usr/lib/gstreamer-1.0

    # Verify GStreamer is available
    if pkg-config --exists gstreamer-1.0 2>/dev/null; then
        local gst_version
        gst_version=$(pkg-config --modversion gstreamer-1.0 2>/dev/null)
        log_success "GStreamer ${gst_version} found"
    else
        log_warn "GStreamer not detected by pkg-config"
    fi

    log_success "Environment variables configured"
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

    # Uninstall ALL pip opencv packages to avoid conflicts
    log_info "Removing any existing OpenCV installations..."
    "$VENV_DIR/bin/pip" uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true

    # Remove any leftover cv2 directories in site-packages (thorough cleanup)
    local site_packages
    site_packages=$("$VENV_DIR/bin/python" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "$VENV_DIR/lib/python3/site-packages")

    if [[ -d "$site_packages/cv2" ]]; then
        log_info "Removing leftover cv2 directory..."
        rm -rf "$site_packages/cv2"
    fi

    # Also check for opencv*.dist-info directories
    rm -rf "$site_packages"/opencv*.dist-info 2>/dev/null || true
    rm -rf "$site_packages"/opencv*.egg-info 2>/dev/null || true

    log_success "Cleaned up old OpenCV installations"

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

    local cmake_args=(
        -D CMAKE_BUILD_TYPE=Release
        -D CMAKE_INSTALL_PREFIX="$VENV_DIR"
        -D OPENCV_EXTRA_MODULES_PATH="$SCRIPT_DIR/opencv_contrib/modules"
        -D WITH_GSTREAMER=ON
        -D WITH_QT=ON
        -D WITH_OPENGL=ON
        -D BUILD_EXAMPLES=OFF
        -D BUILD_TESTS=OFF
        -D BUILD_PERF_TESTS=OFF
        -D BUILD_DOCS=OFF
        -D PYTHON3_EXECUTABLE="$VENV_DIR/bin/python"
        -D PYTHON3_INCLUDE_DIR="$("$VENV_DIR/bin/python" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
        -D PYTHON3_LIBRARY="$("$VENV_DIR/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))' 2>/dev/null || echo "")"
        -D Python3_FIND_REGISTRY=NEVER
        -D Python3_FIND_IMPLEMENTATIONS=CPython
        -D Python3_FIND_STRATEGY=LOCATION
    )

    start_spinner "Running CMake configuration..."
    if cmake .. "${cmake_args[@]}" > cmake_output.log 2>&1; then
        stop_spinner
        log_success "CMake configuration complete"
    else
        stop_spinner
        log_error "CMake configuration failed"
        log_detail "Check opencv/build/cmake_output.log for details"
        exit 1
    fi

    # Verify GStreamer is enabled
    if grep -q "GStreamer:.*YES" cmake_output.log 2>/dev/null; then
        log_success "GStreamer support enabled in build"
    else
        log_warn "GStreamer may not be enabled - check cmake_output.log"
    fi
}

# ============================================================================
# Compile OpenCV (Step 8)
# ============================================================================
compile_opencv() {
    log_step 8 "Compiling OpenCV... ${CLOCK} (this takes 1-2 hours)"

    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "1")

    # Adjust parallelism for low RAM systems
    local make_jobs
    if [[ "$LOW_RAM_MODE" == true ]]; then
        local total_ram_mb
        total_ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
        local swap_mb
        swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/ {print $2}')
        local total_memory_mb=$((total_ram_mb + swap_mb))

        if [[ $total_memory_mb -lt 3000 ]]; then
            make_jobs=1
            log_warn "Using single-threaded build (-j1) due to low memory"
            log_info "This will be SLOW but should complete without OOM errors"
        else
            make_jobs=2
            log_info "Using limited parallelism (-j2) for low RAM system"
        fi
    else
        make_jobs="$cpu_cores"
        log_info "Using ${make_jobs} CPU cores for parallel build"
    fi

    log_info "Go grab a coffee... ${VIDEO}"
    echo ""

    # Run make with progress
    local start_time
    start_time=$(date +%s)

    echo -e "        ${CYAN}Build progress:${NC}"

    # Compile with appropriate parallelism
    if make -j"$make_jobs" 2>&1 | while IFS= read -r line; do
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
        log_detail "Check build output for errors"
        log_detail "If OOM killed, try adding more swap or use -j1"
        exit 1
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    log_info "Build time: ${minutes} minutes"

    # Install
    start_spinner "Installing to virtual environment..."
    if make install >/dev/null 2>&1; then
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
    log_step 9 "Verifying GStreamer support..."

    # Test OpenCV import
    local test_result
    test_result=$("$VENV_DIR/bin/python" << 'PYEOF'
try:
    import cv2
    build_info = cv2.getBuildInformation()
    version = cv2.__version__
    gstreamer = "YES" in build_info.split("GStreamer:")[1].split("\n")[0] if "GStreamer:" in build_info else False
    print(f"VERSION:{version}")
    print(f"GSTREAMER:{gstreamer}")
except Exception as e:
    print(f"ERROR:{e}")
PYEOF
2>&1)

    local cv_version
    cv_version=$(echo "$test_result" | grep "VERSION:" | cut -d':' -f2)
    local gstreamer_enabled
    gstreamer_enabled=$(echo "$test_result" | grep "GSTREAMER:" | cut -d':' -f2)

    if [[ -n "$cv_version" ]]; then
        log_success "OpenCV ${cv_version} imported successfully"
    else
        log_error "OpenCV import failed"
        log_detail "$test_result"
        exit 1
    fi

    if [[ "$gstreamer_enabled" == "True" ]]; then
        log_success "GStreamer support ENABLED"
    else
        log_error "GStreamer support NOT enabled"
        log_detail "Check CMake configuration logs"
        exit 1
    fi
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
    echo -e "      1. Enable GStreamer in ${BOLD}configs/config.yaml${NC}:"
    echo -e "         ${DIM}USE_GSTREAMER: true${NC}"
    echo -e "      2. Configure your video source (RTSP, CSI, etc.)"
    echo -e "      3. Run PixEagle: ${BOLD}bash run_pixeagle.sh${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}💡 Test GStreamer support:${NC}"
    echo -e "      ${DIM}source venv/bin/activate${NC}"
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
    display_banner
    check_prerequisites
    install_dependencies
    setup_gstreamer_env
    clone_opencv
    setup_python_env
    prepare_build
    configure_cmake
    compile_opencv
    verify_installation
    show_summary
}

main "$@"
