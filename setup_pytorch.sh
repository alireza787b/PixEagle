#!/bin/bash

# ============================================================================
# setup_pytorch.sh - PyTorch Setup Script for PixEagle
# ============================================================================
# This script installs PyTorch with GPU support for PixEagle.
#
# Features:
#   - Auto-detects system configuration (OS, architecture, CUDA version)
#   - Uses PixEagle virtual environment
#   - Modern PyTorch versions (2.5.x) with CUDA 12.x support
#   - Validates installation after completion
#   - Consistent UX with init_pixeagle.sh
#
# Supported Platforms:
#   - Linux x86_64 (CUDA 12.4, 12.1, 11.8, or CPU)
#   - Linux ARM64 (Jetson - CUDA, or CPU)
#   - macOS (Apple Silicon MPS, or Intel CPU)
#   - Windows WSL (CUDA or CPU)
#
# Usage: bash setup_pytorch.sh [--cpu]
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=5
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# PyTorch versions (updated December 2025)
PYTORCH_VERSION="2.5.1"
TORCHVISION_VERSION="0.20.1"
TORCHAUDIO_VERSION="2.5.1"

# ============================================================================
# Colors and Formatting (match init_pixeagle.sh)
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

CHECK="✅"
CROSS="❌"
WARN="⚠️"
INFO="ℹ️"
FIRE="🔥"
PARTY="🎉"

# ============================================================================
# Logging Functions
# ============================================================================
log_step() {
    local step=$1
    local message=$2
    echo ""
    echo -e "${CYAN}${BOLD}[${step}/${TOTAL_STEPS}]${NC} ${message}"
}

log_success() {
    echo -e "        ${GREEN}${CHECK}${NC} $1"
}

log_error() {
    echo -e "        ${RED}${CROSS}${NC} $1"
}

log_warn() {
    echo -e "        ${YELLOW}${WARN}${NC}  $1"
}

log_info() {
    echo -e "        ${BLUE}${INFO}${NC}  $1"
}

log_detail() {
    echo -e "        ${DIM}$1${NC}"
}

# ============================================================================
# Banner Display
# ============================================================================
display_banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}   ${FIRE} ${BOLD}PyTorch Setup - GPU Acceleration for PixEagle${NC}                       ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}      ${DIM}Supports CUDA 12.4, 12.1, 11.8, Apple Silicon MPS, and CPU${NC}        ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                                                                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ============================================================================
# System Detection (Step 1)
# ============================================================================
# Global variables for detected configuration
DETECTED_OS=""
DETECTED_ARCH=""
DETECTED_CUDA=""
DETECTED_GPU=""
INSTALL_MODE=""  # gpu, mps, cpu

detect_system() {
    log_step 1 "Detecting system configuration..."

    # Detect OS
    case "$(uname -s)" in
        Linux*)  DETECTED_OS="Linux" ;;
        Darwin*) DETECTED_OS="macOS" ;;
        CYGWIN*|MINGW*|MSYS*) DETECTED_OS="Windows" ;;
        *)       DETECTED_OS="Unknown" ;;
    esac

    # Get OS details
    local os_detail=""
    if [[ "$DETECTED_OS" == "Linux" ]]; then
        if [[ -f /etc/os-release ]]; then
            os_detail=$(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)
        fi
    elif [[ "$DETECTED_OS" == "macOS" ]]; then
        os_detail=$(sw_vers -productVersion 2>/dev/null || echo "Unknown")
    fi
    log_success "OS: ${DETECTED_OS} ${os_detail:+($os_detail)}"

    # Detect architecture
    DETECTED_ARCH=$(uname -m)
    log_success "Architecture: ${DETECTED_ARCH}"

    # Detect CUDA (only on Linux x86_64)
    DETECTED_CUDA="none"
    if [[ "$DETECTED_OS" == "Linux" ]] && [[ "$DETECTED_ARCH" == "x86_64" ]]; then
        # Try nvidia-smi first
        if command -v nvidia-smi &>/dev/null; then
            local cuda_version
            cuda_version=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
            if [[ -n "$cuda_version" ]]; then
                # Get CUDA version from nvidia-smi
                local cuda_full
                cuda_full=$(nvidia-smi 2>/dev/null | grep "CUDA Version" | awk '{print $9}')
                if [[ -n "$cuda_full" ]]; then
                    DETECTED_CUDA="$cuda_full"
                fi
            fi
        fi

        # Fallback to nvcc
        if [[ "$DETECTED_CUDA" == "none" ]] && command -v nvcc &>/dev/null; then
            DETECTED_CUDA=$(nvcc --version 2>/dev/null | grep "release" | awk '{print $6}' | cut -d',' -f1)
        fi

        if [[ "$DETECTED_CUDA" != "none" ]]; then
            log_success "CUDA: ${DETECTED_CUDA} detected"
        else
            log_info "CUDA: Not detected (will use CPU)"
        fi
    fi

    # Detect GPU
    DETECTED_GPU="none"
    if [[ "$DETECTED_OS" == "Linux" ]] && command -v nvidia-smi &>/dev/null; then
        DETECTED_GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        if [[ -n "$DETECTED_GPU" ]]; then
            log_success "GPU: ${DETECTED_GPU}"
        fi
    elif [[ "$DETECTED_OS" == "macOS" ]] && [[ "$DETECTED_ARCH" == "arm64" ]]; then
        DETECTED_GPU="Apple Silicon (MPS)"
        log_success "GPU: ${DETECTED_GPU}"
    fi

    # Determine install mode
    if [[ "$DETECTED_OS" == "macOS" ]] && [[ "$DETECTED_ARCH" == "arm64" ]]; then
        INSTALL_MODE="mps"
    elif [[ "$DETECTED_CUDA" != "none" ]]; then
        INSTALL_MODE="gpu"
    else
        INSTALL_MODE="cpu"
    fi
}

# ============================================================================
# Check PixEagle Environment (Step 2)
# ============================================================================
check_venv() {
    log_step 2 "Checking PixEagle environment..."

    # Check if venv exists
    if [[ ! -d "$VENV_DIR" ]]; then
        log_error "Virtual environment not found at: $VENV_DIR"
        log_detail "Please run 'bash init_pixeagle.sh' first"
        exit 1
    fi

    # Check if activate script exists
    if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
        log_error "Virtual environment is corrupted"
        log_detail "Remove 'venv/' and run 'bash init_pixeagle.sh'"
        exit 1
    fi
    log_success "Virtual environment found"

    # Get Python version
    local python_version
    python_version=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
    log_success "Python ${python_version} detected"

    # Check if PyTorch is already installed
    if "$VENV_DIR/bin/python" -c "import torch; print(torch.__version__)" 2>/dev/null; then
        local existing_version
        existing_version=$("$VENV_DIR/bin/python" -c "import torch; print(torch.__version__)" 2>/dev/null)
        log_warn "PyTorch ${existing_version} already installed"
        echo ""
        echo -en "        Reinstall/upgrade PyTorch? [y/N]: "
        read -r REPLY
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing PyTorch installation"
            # Skip to verification
            verify_installation
            show_summary
            exit 0
        fi
    fi
}

# ============================================================================
# Select PyTorch Configuration (Step 3)
# ============================================================================
PYTORCH_INDEX_URL=""
INSTALL_DESCRIPTION=""

select_pytorch_config() {
    log_step 3 "Selecting PyTorch configuration..."

    # Determine the best PyTorch configuration based on detected system
    case "$INSTALL_MODE" in
        gpu)
            # Determine CUDA version to use
            local cuda_major
            cuda_major=$(echo "$DETECTED_CUDA" | cut -d'.' -f1)
            local cuda_minor
            cuda_minor=$(echo "$DETECTED_CUDA" | cut -d'.' -f2)

            if [[ "$cuda_major" -ge 12 ]]; then
                if [[ "$cuda_minor" -ge 4 ]]; then
                    PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu124"
                    INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} + CUDA 12.4"
                elif [[ "$cuda_minor" -ge 1 ]]; then
                    PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu121"
                    INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} + CUDA 12.1"
                else
                    PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu121"
                    INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} + CUDA 12.1"
                fi
            elif [[ "$cuda_major" -eq 11 ]]; then
                PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cu118"
                INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} + CUDA 11.8"
            else
                # Fallback to CPU
                PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
                INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} (CPU)"
                INSTALL_MODE="cpu"
            fi
            ;;
        mps)
            PYTORCH_INDEX_URL=""  # Default PyPI for macOS
            INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} + MPS (Apple Silicon)"
            ;;
        cpu)
            PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
            INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} (CPU only)"
            ;;
    esac

    log_info "Recommended: ${INSTALL_DESCRIPTION}"
    echo ""

    # Ask user to confirm or change
    if [[ "$INSTALL_MODE" == "gpu" ]]; then
        echo -e "        ${YELLOW}Install PyTorch with GPU support?${NC}"
        echo -en "        [Y/n] or type 'cpu' for CPU-only: "
    elif [[ "$INSTALL_MODE" == "mps" ]]; then
        echo -e "        ${YELLOW}Install PyTorch with MPS (Apple Silicon) support?${NC}"
        echo -en "        [Y/n]: "
    else
        echo -e "        ${YELLOW}Install PyTorch (CPU only)?${NC}"
        echo -en "        [Y/n]: "
    fi

    read -r REPLY
    echo ""

    if [[ "$REPLY" == "cpu" ]]; then
        PYTORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
        INSTALL_DESCRIPTION="PyTorch ${PYTORCH_VERSION} (CPU only)"
        INSTALL_MODE="cpu"
        log_info "Changed to: ${INSTALL_DESCRIPTION}"
    elif [[ $REPLY =~ ^[Nn]$ ]]; then
        log_info "Installation cancelled by user"
        exit 0
    fi

    log_success "Configuration selected: ${INSTALL_DESCRIPTION}"
}

# ============================================================================
# Install PyTorch (Step 4)
# ============================================================================
install_pytorch() {
    log_step 4 "Installing PyTorch..."

    # Activate venv
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"

    # Uninstall existing PyTorch first (clean install)
    log_info "Removing any existing PyTorch packages..."
    "$VENV_DIR/bin/pip" uninstall -y torch torchvision torchaudio 2>/dev/null || true

    # Build pip command
    local pip_cmd=("$VENV_DIR/bin/pip" install)

    if [[ -n "$PYTORCH_INDEX_URL" ]]; then
        pip_cmd+=(--index-url "$PYTORCH_INDEX_URL")
    fi

    pip_cmd+=(torch torchvision torchaudio)

    log_info "Installing packages (this may take a few minutes)..."
    echo -e "        ${DIM}Command: pip install torch torchvision torchaudio${NC}"
    if [[ -n "$PYTORCH_INDEX_URL" ]]; then
        echo -e "        ${DIM}Index: ${PYTORCH_INDEX_URL}${NC}"
    fi
    echo ""

    # Run pip with progress
    echo -e "        ${CYAN}Installing packages:${NC}"
    "${pip_cmd[@]}" 2>&1 | while IFS= read -r line; do
        if [[ "$line" =~ ^Collecting\ (.+) ]]; then
            local pkg="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Collecting: %-55s${NC}" "${pkg:0:55}"
        elif [[ "$line" =~ ^Downloading\ (.+) ]]; then
            printf "\r        ${DIM}→ Downloading: %-53s${NC}" "${BASH_REMATCH[1]:0:53}"
        elif [[ "$line" =~ ^Installing\ collected\ packages ]]; then
            printf "\r        ${GREEN}→ Installing collected packages...                           ${NC}\n"
        elif [[ "$line" =~ Successfully\ installed ]]; then
            printf "\r        ${GREEN}${CHECK} Packages installed successfully                            ${NC}\n"
        fi
    done

    deactivate

    log_success "PyTorch installation completed"
}

# ============================================================================
# Verify Installation (Step 5)
# ============================================================================
TORCH_VERSION_INSTALLED=""
CUDA_AVAILABLE=""
MPS_AVAILABLE=""
GPU_NAME=""

verify_installation() {
    log_step 5 "Verifying installation..."

    # Test PyTorch import
    local test_result
    test_result=$("$VENV_DIR/bin/python" << 'PYEOF'
import sys
try:
    import torch
    print(f"VERSION:{torch.__version__}")
    print(f"CUDA:{torch.cuda.is_available()}")
    print(f"MPS:{torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False}")
    if torch.cuda.is_available():
        print(f"GPU:{torch.cuda.get_device_name(0)}")
    else:
        print("GPU:none")
    sys.exit(0)
except Exception as e:
    print(f"ERROR:{e}")
    sys.exit(1)
PYEOF
2>&1)

    if [[ $? -ne 0 ]]; then
        log_error "PyTorch import failed"
        log_detail "$test_result"
        exit 1
    fi

    # Parse results
    TORCH_VERSION_INSTALLED=$(echo "$test_result" | grep "VERSION:" | cut -d':' -f2)
    CUDA_AVAILABLE=$(echo "$test_result" | grep "CUDA:" | cut -d':' -f2)
    MPS_AVAILABLE=$(echo "$test_result" | grep "MPS:" | cut -d':' -f2)
    GPU_NAME=$(echo "$test_result" | grep "GPU:" | cut -d':' -f2-)

    log_success "PyTorch ${TORCH_VERSION_INSTALLED} imported successfully"

    if [[ "$CUDA_AVAILABLE" == "True" ]]; then
        log_success "CUDA available: Yes"
        if [[ "$GPU_NAME" != "none" ]]; then
            log_success "GPU: ${GPU_NAME}"
        fi
    elif [[ "$MPS_AVAILABLE" == "True" ]]; then
        log_success "MPS (Apple Silicon) available: Yes"
    else
        log_info "GPU acceleration: Not available (CPU mode)"
    fi
}

# ============================================================================
# Summary Display
# ============================================================================
show_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}PyTorch Setup Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} PyTorch ${TORCH_VERSION_INSTALLED} installed"

    if [[ "$CUDA_AVAILABLE" == "True" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} CUDA acceleration enabled"
        if [[ "$GPU_NAME" != "none" ]]; then
            echo -e "   ${GREEN}${CHECK}${NC} GPU: ${GPU_NAME}"
        fi
    elif [[ "$MPS_AVAILABLE" == "True" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} MPS (Apple Silicon) acceleration enabled"
    else
        echo -e "   ${YELLOW}${WARN}${NC}  CPU mode (no GPU acceleration)"
    fi

    echo ""
    echo -e "   ${CYAN}${BOLD}📋 Next Steps:${NC}"
    echo -e "      1. Enable SmartTracker in ${BOLD}configs/config.yaml${NC}:"
    echo -e "         ${DIM}SMART_TRACKER_USE_GPU: true${NC}"
    echo -e "      2. Run PixEagle: ${BOLD}bash run_pixeagle.sh${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}💡 Test GPU acceleration:${NC}"
    echo -e "      ${DIM}source venv/bin/activate${NC}"
    echo -e "      ${DIM}python -c \"import torch; print('CUDA:', torch.cuda.is_available())\"${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    # Parse arguments
    FORCE_CPU=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cpu|-c)
                FORCE_CPU=true
                shift
                ;;
            --help|-h)
                echo "Usage: bash setup_pytorch.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --cpu, -c    Force CPU-only installation (no GPU)"
                echo "  --help, -h   Show this help message"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    display_banner

    echo -e "${DIM}Starting PyTorch setup...${NC}"

    detect_system

    # Override to CPU if requested
    if [[ "$FORCE_CPU" == true ]]; then
        INSTALL_MODE="cpu"
        log_info "Forced CPU mode via --cpu flag"
    fi

    check_venv
    select_pytorch_config
    install_pytorch
    verify_installation
    show_summary
}

main "$@"
