#!/bin/bash

# scripts/install_dlib.sh
# Robust dlib installation script for PixEagle
# Handles low-memory systems (Raspberry Pi) with intelligent swap management
#
# Features:
#   - Automatic memory detection and adaptive swap sizing
#   - Handles CONF_MAXSWAP for >2GB swap on Raspberry Pi
#   - Pre-flight checks (disk space, sudo, dependencies)
#   - Graceful cleanup on Ctrl+C (SIGINT trap)
#   - USB drive swap option to preserve SD card
#   - Single-threaded compilation for reduced memory peaks
#   - Estimated compilation time display
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# Date: December 2025
# Author: Alireza Ghaderi

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=7
MANUAL_SWAP_FILE="/var/pixeagle_swap"  # Not /tmp (may be tmpfs)
MIN_DISK_SPACE_GB=3
LOW_MEMORY_THRESHOLD_MB=3000

# State variables
SWAP_MODIFIED=false
SWAP_METHOD=""
SWAP_MODE=""
ORIGINAL_SWAP_CONFIG=""
LOW_MEMORY=false
TOTAL_RAM=0
AVAILABLE_DISK_GB=0
CALCULATED_SWAP_MB=0

# Get script directory for sourcing common functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

# Fix CRLF line endings
[[ -f "$SCRIPTS_DIR/lib/common.sh" ]] && grep -q $'\r' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && \
    sed -i.bak 's/\r$//' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && rm -f "$SCRIPTS_DIR/lib/common.sh.bak"

# Source shared functions with fallback
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BLUE='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    # Symbols
    CHECK="[✓]"; CROSS="[✗]"; WARN="[!]"; INFO="[i]"; PACKAGE="[pkg]"; PARTY=""
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[✓]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[!]${NC} $1"; }
    log_warning() { log_warn "$1"; }
    log_error() { echo -e "   ${RED}[✗]${NC} $1"; }
    log_step() { echo -e "\n${CYAN}━━━ Step $1/${TOTAL_STEPS}: $2 ━━━${NC}"; }
    log_section() {
        echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}${BOLD}$1${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}"
        [[ -n "${1:-}" ]] && echo -e "  ${BOLD}$1${NC}"
        [[ -n "${2:-}" ]] && echo -e "  ${DIM}$2${NC}"
        echo ""
    }
fi

# ============================================================================
# Trap Handler for Graceful Cleanup
# ============================================================================
cleanup_on_exit() {
    local exit_code=$?

    if [[ "$SWAP_MODIFIED" == "true" ]]; then
        echo ""
        log_warning "Cleaning up swap configuration..."
        restore_swap_silent
    fi

    # Deactivate venv if active
    if [[ -n "$VIRTUAL_ENV" ]]; then
        deactivate 2>/dev/null || true
    fi

    exit $exit_code
}

trap cleanup_on_exit EXIT SIGINT SIGTERM

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    display_pixeagle_banner "${PACKAGE} dlib Installation" \
        "GitHub: https://github.com/alireza787b/PixEagle"
}

# ============================================================================
# Script-specific Logging (non-indented style)
# ============================================================================
log_info() {
    echo -e "${BLUE}${INFO}${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}${WARN}${NC} $1"
}

log_detail() {
    echo -e "    ${DIM}$1${NC}"
}

# ============================================================================
# Pre-flight Checks
# ============================================================================
preflight_checks() {
    log_section "Step 1: Pre-flight Checks"

    local checks_passed=true

    # 1. Check sudo privileges
    echo -e "${DIM}Checking sudo privileges...${NC}"
    if ! sudo -n true 2>/dev/null; then
        log_warning "This script requires sudo privileges for swap modifications"
        echo ""
        sudo -v || {
            log_error "Failed to obtain sudo privileges"
            exit 1
        }
    fi
    log_success "Sudo privileges available"

    # 2. Check available disk space
    echo -e "${DIM}Checking disk space...${NC}"
    AVAILABLE_DISK_GB=$(df -BG "$PIXEAGLE_DIR" | awk 'NR==2 {print $4}' | tr -d 'G')

    if [[ "$AVAILABLE_DISK_GB" -lt "$MIN_DISK_SPACE_GB" ]]; then
        log_error "Insufficient disk space: ${AVAILABLE_DISK_GB}GB available, need at least ${MIN_DISK_SPACE_GB}GB"
        log_info "Free up disk space or use external storage for swap"
        exit 1
    fi
    log_success "Disk space: ${AVAILABLE_DISK_GB}GB available"

    # 3. Check build dependencies
    echo -e "${DIM}Checking build dependencies...${NC}"
    local missing_deps=()

    command -v cmake >/dev/null 2>&1 || missing_deps+=("cmake")
    command -v g++ >/dev/null 2>&1 || missing_deps+=("g++")
    command -v make >/dev/null 2>&1 || missing_deps+=("make")

    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_warning "Missing build dependencies: ${missing_deps[*]}"
        log_info "Installing required packages..."

        if command -v apt >/dev/null 2>&1; then
            sudo apt update -qq && sudo apt install -y cmake build-essential || {
                log_error "Failed to install dependencies"
                exit 1
            }
            log_success "Build dependencies installed"
        else
            log_error "Cannot auto-install dependencies (apt not found)"
            log_info "Please install manually: cmake build-essential"
            exit 1
        fi
    else
        log_success "Build dependencies available (cmake, g++, make)"
    fi

    # 4. Check Python development headers
    echo -e "${DIM}Checking Python development headers...${NC}"

    # Detect Python version
    local python_version
    python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)

    # Try to find Python.h
    if ! find /usr/include -name "Python.h" 2>/dev/null | grep -q .; then
        log_warning "Python development headers not found (Python.h missing)"
        log_info "Installing python3-dev package..."

        if command -v apt >/dev/null 2>&1; then
            # Try version-specific first, fallback to generic
            if ! sudo apt install -y "python${python_version}-dev" 2>/dev/null; then
                sudo apt update -qq && sudo apt install -y python3-dev || {
                    log_error "Failed to install Python development headers"
                    log_info "Please install manually: sudo apt install python3-dev"
                    exit 1
                }
            fi
            log_success "Python development headers installed"
        else
            log_error "Cannot auto-install python3-dev (apt not found)"
            log_info "Please install manually: python3-dev or python${python_version}-dev"
            exit 1
        fi
    else
        log_success "Python development headers available (Python.h found)"
    fi

    # 5. Check if /tmp is tmpfs (RAM-based)
    echo -e "${DIM}Checking filesystem configuration...${NC}"
    if mount | grep -q "tmpfs on /tmp"; then
        log_warning "/tmp is RAM-based (tmpfs), will use /var for manual swap"
    else
        log_success "Filesystem configuration OK"
    fi

    # 6. Check virtual environment
    echo -e "${DIM}Checking Python virtual environment...${NC}"
    if [[ ! -d "$PIXEAGLE_DIR/venv" ]]; then
        log_error "Virtual environment not found!"
        log_info "Please run 'make init' (or 'bash scripts/init.sh') first to set up PixEagle."
        exit 1
    fi
    log_success "Virtual environment found"
}

# ============================================================================
# Check Existing Installation
# ============================================================================
check_existing_dlib() {
    log_section "Step 2: Checking Existing Installation"

    cd "$PIXEAGLE_DIR"
    source venv/bin/activate

    if python -c "import dlib" 2>/dev/null; then
        local dlib_version
        dlib_version=$(python -c "import dlib; print(dlib.__version__ if hasattr(dlib, '__version__') else 'unknown')")
        log_success "dlib is already installed (version: $dlib_version)"
        echo ""
        echo -e "${GREEN}No installation needed. You're ready to use the dlib tracker!${NC}"
        echo ""
        deactivate
        exit 0
    fi

    log_info "dlib not found - proceeding with installation"
    deactivate
}

# ============================================================================
# System Analysis
# ============================================================================
analyze_system() {
    log_section "Step 3: System Analysis"

    # Detect RAM
    if command -v free &> /dev/null; then
        TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
    else
        log_warning "Cannot detect memory automatically, assuming 4GB"
        TOTAL_RAM=4000
    fi

    log_info "Total system RAM: ${TOTAL_RAM}MB"

    # Detect CPU for time estimation
    local cpu_model=""
    local cpu_cores=1

    if [[ -f /proc/cpuinfo ]]; then
        cpu_model=$(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Unknown")
        cpu_cores=$(nproc 2>/dev/null || echo 1)
    fi

    log_info "CPU: $cpu_model ($cpu_cores cores)"

    # Estimate compilation time
    if [[ "$cpu_model" == *"Cortex"* ]] || [[ "$cpu_model" == *"BCM"* ]] || [[ "$cpu_model" == *"ARM"* ]]; then
        log_warning "Estimated compilation time: 45-90 minutes (ARM/Raspberry Pi)"
    elif [[ "$cpu_model" == *"Intel"* ]] || [[ "$cpu_model" == *"AMD"* ]]; then
        log_info "Estimated compilation time: 5-15 minutes (x86 desktop)"
    else
        log_info "Estimated compilation time: 15-45 minutes"
    fi

    # Determine if low memory system
    if [[ "$TOTAL_RAM" -lt "$LOW_MEMORY_THRESHOLD_MB" ]]; then
        LOW_MEMORY=true
        log_warning "Low memory system detected (< ${LOW_MEMORY_THRESHOLD_MB}MB)"
    else
        LOW_MEMORY=false
        log_success "Sufficient memory detected (>= ${LOW_MEMORY_THRESHOLD_MB}MB)"
    fi
}

# ============================================================================
# Calculate Adaptive Swap Size
# ============================================================================
calculate_swap_size() {
    # Rule: 2x RAM or at least 2GB, capped by available disk space (max 4GB)
    local ideal_swap_mb=$((TOTAL_RAM * 2))

    # Minimum 2GB
    [[ $ideal_swap_mb -lt 2048 ]] && ideal_swap_mb=2048

    # Maximum 4GB (diminishing returns beyond this)
    [[ $ideal_swap_mb -gt 4096 ]] && ideal_swap_mb=4096

    # Cap by available disk (leave 1GB buffer)
    local max_swap_mb=$(( (AVAILABLE_DISK_GB - 1) * 1024 ))
    [[ $max_swap_mb -lt $ideal_swap_mb ]] && ideal_swap_mb=$max_swap_mb

    # Absolute minimum 1GB
    [[ $ideal_swap_mb -lt 1024 ]] && ideal_swap_mb=1024

    CALCULATED_SWAP_MB=$ideal_swap_mb
}

# ============================================================================
# Ask User for Swap Preference
# ============================================================================
ask_swap_preference() {
    log_section "Step 4: Swap Configuration"

    if [[ "$LOW_MEMORY" != "true" ]]; then
        log_info "Sufficient memory available - swap modification optional"
        log_info "dlib will use single-threaded compilation to reduce memory usage"
        echo ""
        read -p "Skip swap modification? [Y/n]: " skip_choice
        skip_choice=${skip_choice:-Y}

        case "$skip_choice" in
            n|N|no|No)
                log_info "Proceeding with swap configuration..."
                ;;
            *)
                SWAP_MODE="none"
                log_info "Skipping swap modification"
                return
                ;;
        esac
    fi

    # Calculate recommended swap size
    calculate_swap_size

    echo ""
    echo -e "${YELLOW}${WARN}${NC} dlib compilation requires 2-4GB of memory"
    echo -e "    Your system has ${BOLD}${TOTAL_RAM}MB RAM${NC}"
    echo -e "    Recommended swap: ${BOLD}${CALCULATED_SWAP_MB}MB${NC}"
    echo ""
    echo -e "    ${BOLD}Options:${NC}"
    echo -e "    ${CYAN}1)${NC} Use SD card/disk swap ${DIM}(recommended, slight disk wear)${NC}"
    echo -e "    ${CYAN}2)${NC} Use USB drive for swap ${DIM}(recommended if USB available)${NC}"
    echo -e "    ${CYAN}3)${NC} Skip swap modification ${DIM}(may fail on low-memory systems)${NC}"
    echo ""

    read -p "    Select option [1]: " choice
    choice=${choice:-1}

    case $choice in
        1)
            SWAP_MODE="disk"
            log_info "Using disk-based swap (${CALCULATED_SWAP_MB}MB)"
            ;;
        2)
            echo ""
            read -p "    Enter USB mount point (e.g., /media/usb): " usb_mount
            if [[ -d "$usb_mount" ]] && [[ -w "$usb_mount" ]]; then
                SWAP_MODE="usb"
                MANUAL_SWAP_FILE="$usb_mount/pixeagle_swap"
                log_success "Using USB drive at $usb_mount"
            else
                log_error "Mount point not found or not writable: $usb_mount"
                log_info "Falling back to disk-based swap"
                SWAP_MODE="disk"
            fi
            ;;
        3)
            SWAP_MODE="none"
            log_warning "Skipping swap - compilation may fail on low-memory systems"
            ;;
        *)
            SWAP_MODE="disk"
            log_info "Using disk-based swap (${CALCULATED_SWAP_MB}MB)"
            ;;
    esac
}

# ============================================================================
# Detect Swap Method
# ============================================================================
detect_swap_method() {
    if [[ -f "/etc/dphys-swapfile" ]]; then
        SWAP_METHOD="dphys"
    elif [[ -f "/etc/default/swapfile" ]]; then
        SWAP_METHOD="swapfile"
    else
        SWAP_METHOD="manual"
    fi
}

# ============================================================================
# Setup dphys-swapfile (Raspberry Pi)
# ============================================================================
setup_dphys_swap() {
    local swap_size_mb=$1

    log_info "Configuring swap using dphys-swapfile..."

    # Backup original config
    sudo cp /etc/dphys-swapfile /etc/dphys-swapfile.pixeagle.bak
    ORIGINAL_SWAP_CONFIG="/etc/dphys-swapfile.pixeagle.bak"

    # Turn off current swap
    sudo dphys-swapfile swapoff 2>/dev/null || true

    # Set CONF_SWAPSIZE
    if grep -q "^CONF_SWAPSIZE=" /etc/dphys-swapfile; then
        sudo sed -i "s/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=$swap_size_mb/" /etc/dphys-swapfile
    else
        echo "CONF_SWAPSIZE=$swap_size_mb" | sudo tee -a /etc/dphys-swapfile > /dev/null
    fi
    log_detail "Set CONF_SWAPSIZE=$swap_size_mb"

    # Handle CONF_MAXSWAP if swap > 2GB (critical for Raspberry Pi!)
    if [[ $swap_size_mb -gt 2048 ]]; then
        if grep -q "^#.*CONF_MAXSWAP" /etc/dphys-swapfile; then
            # Uncomment and set
            sudo sed -i "s/^#.*CONF_MAXSWAP=.*/CONF_MAXSWAP=$swap_size_mb/" /etc/dphys-swapfile
        elif grep -q "^CONF_MAXSWAP" /etc/dphys-swapfile; then
            # Already uncommented, update value
            sudo sed -i "s/^CONF_MAXSWAP=.*/CONF_MAXSWAP=$swap_size_mb/" /etc/dphys-swapfile
        else
            # Add new line
            echo "CONF_MAXSWAP=$swap_size_mb" | sudo tee -a /etc/dphys-swapfile > /dev/null
        fi
        log_detail "Set CONF_MAXSWAP=$swap_size_mb (required for >2GB swap)"
    fi

    # Recreate and enable swap
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon

    SWAP_MODIFIED=true
    log_success "Swap configured: ${swap_size_mb}MB"
}

# ============================================================================
# Setup Generic Swapfile
# ============================================================================
setup_generic_swap() {
    local swap_size_mb=$1

    log_info "Configuring swap using swapfile service..."

    sudo cp /etc/default/swapfile /etc/default/swapfile.pixeagle.bak
    ORIGINAL_SWAP_CONFIG="/etc/default/swapfile.pixeagle.bak"

    sudo sed -i "s/^SWAPSIZE=.*/SWAPSIZE=$swap_size_mb/" /etc/default/swapfile
    sudo service swapfile restart

    SWAP_MODIFIED=true
    log_success "Swap configured: ${swap_size_mb}MB"
}

# ============================================================================
# Create Manual Swap File
# ============================================================================
create_manual_swap() {
    local swap_size_mb=$1

    log_info "Creating manual swap file at $MANUAL_SWAP_FILE..."

    # Remove existing swap file if present
    if [[ -f "$MANUAL_SWAP_FILE" ]]; then
        sudo swapoff "$MANUAL_SWAP_FILE" 2>/dev/null || true
        sudo rm -f "$MANUAL_SWAP_FILE"
    fi

    # Create swap file with progress
    log_detail "Allocating ${swap_size_mb}MB (this may take a minute)..."
    sudo dd if=/dev/zero of="$MANUAL_SWAP_FILE" bs=1M count=$swap_size_mb status=progress 2>&1 | \
        while IFS= read -r line; do
            echo -e "    ${DIM}$line${NC}"
        done

    sudo chmod 600 "$MANUAL_SWAP_FILE"
    sudo mkswap "$MANUAL_SWAP_FILE" > /dev/null
    sudo swapon "$MANUAL_SWAP_FILE"

    SWAP_MODIFIED=true
    SWAP_METHOD="manual"
    log_success "Manual swap created: ${swap_size_mb}MB"
}

# ============================================================================
# Configure Swap
# ============================================================================
configure_swap() {
    if [[ "$SWAP_MODE" == "none" ]]; then
        log_info "Swap modification skipped by user"
        return
    fi

    detect_swap_method

    log_info "Detected swap method: $SWAP_METHOD"

    case "$SWAP_METHOD" in
        dphys)
            setup_dphys_swap "$CALCULATED_SWAP_MB"
            ;;
        swapfile)
            setup_generic_swap "$CALCULATED_SWAP_MB"
            ;;
        manual)
            create_manual_swap "$CALCULATED_SWAP_MB"
            ;;
    esac

    # Verify swap is active
    local current_swap
    current_swap=$(free -m | awk '/^Swap:/{print $2}')
    log_success "Current swap space: ${current_swap}MB"
}

# ============================================================================
# Restore Swap (Silent version for trap handler)
# ============================================================================
restore_swap_silent() {
    case "$SWAP_METHOD" in
        dphys)
            if [[ -f "/etc/dphys-swapfile.pixeagle.bak" ]]; then
                sudo dphys-swapfile swapoff 2>/dev/null || true
                sudo cp /etc/dphys-swapfile.pixeagle.bak /etc/dphys-swapfile
                sudo dphys-swapfile setup 2>/dev/null || true
                sudo dphys-swapfile swapon 2>/dev/null || true
                sudo rm -f /etc/dphys-swapfile.pixeagle.bak
            fi
            ;;
        swapfile)
            if [[ -f "/etc/default/swapfile.pixeagle.bak" ]]; then
                sudo cp /etc/default/swapfile.pixeagle.bak /etc/default/swapfile
                sudo service swapfile restart 2>/dev/null || true
                sudo rm -f /etc/default/swapfile.pixeagle.bak
            fi
            ;;
        manual)
            if [[ -f "$MANUAL_SWAP_FILE" ]]; then
                sudo swapoff "$MANUAL_SWAP_FILE" 2>/dev/null || true
                sudo rm -f "$MANUAL_SWAP_FILE"
            fi
            ;;
    esac

    SWAP_MODIFIED=false
}

# ============================================================================
# Restore Swap (Verbose version for normal flow)
# ============================================================================
restore_swap() {
    log_section "Step 6: Restoring Original Swap Configuration"

    if [[ "$SWAP_MODIFIED" != "true" ]]; then
        log_info "Swap was not modified - nothing to restore"
        return
    fi

    case "$SWAP_METHOD" in
        dphys)
            log_info "Restoring dphys-swapfile configuration..."
            if [[ -f "/etc/dphys-swapfile.pixeagle.bak" ]]; then
                sudo dphys-swapfile swapoff 2>/dev/null || true
                sudo cp /etc/dphys-swapfile.pixeagle.bak /etc/dphys-swapfile
                sudo dphys-swapfile setup
                sudo dphys-swapfile swapon
                sudo rm -f /etc/dphys-swapfile.pixeagle.bak
                log_success "Original dphys-swapfile configuration restored"
            else
                log_warning "Backup not found - swap may need manual restoration"
            fi
            ;;
        swapfile)
            log_info "Restoring swapfile configuration..."
            if [[ -f "/etc/default/swapfile.pixeagle.bak" ]]; then
                sudo cp /etc/default/swapfile.pixeagle.bak /etc/default/swapfile
                sudo service swapfile restart
                sudo rm -f /etc/default/swapfile.pixeagle.bak
                log_success "Original swapfile configuration restored"
            else
                log_warning "Backup not found - swap may need manual restoration"
            fi
            ;;
        manual)
            log_info "Removing temporary swap file..."
            if [[ -f "$MANUAL_SWAP_FILE" ]]; then
                sudo swapoff "$MANUAL_SWAP_FILE" 2>/dev/null || true
                sudo rm -f "$MANUAL_SWAP_FILE"
                log_success "Temporary swap file removed"
            fi
            ;;
    esac

    SWAP_MODIFIED=false

    # Show final swap status
    local final_swap
    final_swap=$(free -m | awk '/^Swap:/{print $2}')
    log_info "Final swap space: ${final_swap}MB"
}

# ============================================================================
# Install dlib with Memory Optimization
# ============================================================================
install_dlib() {
    log_section "Step 5: Installing dlib"

    cd "$PIXEAGLE_DIR"
    source venv/bin/activate

    # Force single-threaded compilation to reduce memory peaks
    export CMAKE_BUILD_PARALLEL_LEVEL=1
    log_info "Using single-threaded compilation (CMAKE_BUILD_PARALLEL_LEVEL=1)"

    # Upgrade pip first
    log_info "Upgrading pip..."
    pip install --upgrade pip -q

    echo ""
    log_warning "Starting dlib compilation - this may take a while..."
    log_info "On Raspberry Pi: 45-90 minutes | On desktop: 5-15 minutes"
    log_info "Press Ctrl+C to cancel (swap will be restored automatically)"
    echo ""

    # Install dlib with verbose output, filtering for progress
    pip install dlib --verbose 2>&1 | while IFS= read -r line; do
        # Show compilation progress and errors
        if [[ "$line" == *"Building"* ]] || [[ "$line" == *"%"* ]] || [[ "$line" == *"Collecting"* ]] || [[ "$line" == *"Installing"* ]]; then
            echo -e "    ${DIM}${line:0:100}${NC}"
        elif [[ "$line" == *"error:"* ]] || [[ "$line" == *"fatal error:"* ]] || [[ "$line" == *"ERROR:"* ]]; then
            echo -e "    ${RED}${line}${NC}"
        fi
    done

    # Check pip exit status using PIPESTATUS (index 0 is pip command)
    if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
        echo ""
        log_success "dlib installation completed successfully"
    else
        echo ""
        log_error "dlib installation failed"
        log_info "Common causes:"
        log_info "  - Missing Python development headers (install: sudo apt install python3-dev)"
        log_info "  - Insufficient memory/swap space"
        log_info "  - Missing build dependencies"
        log_info "Run with --verbose flag or check output above for specific error"
        deactivate
        exit 1
    fi

    deactivate
}

# ============================================================================
# Verify Installation
# ============================================================================
verify_installation() {
    log_section "Step 7: Verifying Installation"

    cd "$PIXEAGLE_DIR"
    source venv/bin/activate

    if python -c "import dlib" 2>/dev/null; then
        local dlib_version
        dlib_version=$(python -c "import dlib; print(dlib.__version__ if hasattr(dlib, '__version__') else 'installed')")
        log_success "dlib successfully installed and verified!"
        log_info "Version: $dlib_version"
    else
        log_error "Installation verification failed"
        log_error "dlib was installed but cannot be imported"
        deactivate
        exit 1
    fi

    deactivate
}

# ============================================================================
# Show Usage Instructions
# ============================================================================
show_usage_instructions() {
    log_section "Installation Complete!"

    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  dlib tracker is now ready to use!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    echo -e "${BLUE}To enable dlib tracker:${NC}"
    echo ""
    echo -e "1. Edit your configuration:"
    echo -e "   ${YELLOW}nano configs/config.yaml${NC}"
    echo ""
    echo -e "2. Set the tracking algorithm:"
    echo -e "   ${YELLOW}DEFAULT_TRACKING_ALGORITHM: dlib${NC}"
    echo ""
    echo -e "3. Configure performance mode (optional):"
    echo -e "   ${YELLOW}DLIB_Tracker:${NC}"
    echo -e "   ${YELLOW}  performance_mode: balanced  # fast | balanced | robust${NC}"
    echo ""
    echo -e "${BLUE}Then start PixEagle:${NC}"
    echo -e "   ${YELLOW}bash run_pixeagle.sh${NC}"
    echo ""
    echo -e "${DIM}See configs/config_default.yaml for all dlib parameters${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    display_banner

    # Change to PixEagle directory
    cd "$PIXEAGLE_DIR"
    log_info "Working directory: $PIXEAGLE_DIR"

    # Run installation steps
    preflight_checks
    check_existing_dlib
    analyze_system
    ask_swap_preference

    # Configure swap if needed
    configure_swap

    # Install dlib
    install_dlib

    # Restore swap if modified
    restore_swap

    # Verify and show instructions
    verify_installation
    show_usage_instructions

    log_success "All done! Happy flying!"
}

# Run main function
main "$@"
