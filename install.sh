#!/bin/bash

# ============================================================================
# install.sh - PixEagle Bootstrap Installer (Linux/macOS)
# ============================================================================
# One-liner installation for PixEagle vision-based drone tracking system.
#
# Usage (curl):
#   curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
#
# Usage (wget):
#   wget -qO- https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
#
# What this script does:
#   1. Checks system prerequisites (git, python3, curl)
#   2. Clones PixEagle repository (or updates if exists)
#   3. Runs the initialization script (scripts/init.sh)
#   4. Displays next steps
#
# Environment variables:
#   PIXEAGLE_HOME    - Installation directory (default: ~/PixEagle)
#   PIXEAGLE_BRANCH  - Git branch to clone (default: main)
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -e

# ============================================================================
# Configuration
# ============================================================================
REPO_URL="https://github.com/alireza787b/PixEagle.git"
DEFAULT_BRANCH="main"
DEFAULT_HOME="$HOME/PixEagle"

# Use environment variables if set, otherwise use defaults
INSTALL_DIR="${PIXEAGLE_HOME:-$DEFAULT_HOME}"
BRANCH="${PIXEAGLE_BRANCH:-$DEFAULT_BRANCH}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ============================================================================
# Functions
# ============================================================================

print_banner() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  _____ _      ______            _       ${NC}"
    echo -e "${CYAN} |  __ (_)    |  ____|          | |      ${NC}"
    echo -e "${CYAN} | |__) |__  _| |__   __ _  __ _| | ___  ${NC}"
    echo -e "${CYAN} |  ___/ \\ \\/ /  __| / _\` |/ _\` | |/ _ \\ ${NC}"
    echo -e "${CYAN} | |   | |>  <| |___| (_| | (_| | |  __/ ${NC}"
    echo -e "${CYAN} |_|   |_/_/\\_\\______\\__,_|\\__, |_|\\___| ${NC}"
    echo -e "${CYAN}                           __/ |        ${NC}"
    echo -e "${CYAN}                          |___/         ${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "          ${BOLD}PixEagle Bootstrap Installer${NC}"
    echo -e "          Vision-Based Drone Tracking System"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

log_info() {
    echo -e "   ${CYAN}[*]${NC} $1"
}

log_success() {
    echo -e "   ${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "   ${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "   ${YELLOW}[!]${NC} $1"
}

check_os() {
    log_info "Detecting operating system..."

    case "$(uname -s)" in
        Linux*)
            OS="Linux"
            if [[ -f /etc/os-release ]]; then
                . /etc/os-release
                DISTRO="$NAME"
            else
                DISTRO="Unknown Linux"
            fi
            log_success "Detected: $DISTRO"
            ;;
        Darwin*)
            OS="macOS"
            MACOS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "Unknown")
            log_success "Detected: macOS $MACOS_VERSION"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            log_error "Windows detected - please use install.ps1 instead"
            echo ""
            echo "   For Windows PowerShell:"
            echo "   irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex"
            echo ""
            exit 1
            ;;
        *)
            log_error "Unsupported operating system: $(uname -s)"
            exit 1
            ;;
    esac
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    local missing=()

    # Check git
    if ! command -v git &>/dev/null; then
        missing+=("git")
    else
        log_success "git $(git --version | awk '{print $3}')"
    fi

    # Check Python 3
    if ! command -v python3 &>/dev/null; then
        missing+=("python3")
    else
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        log_success "python3 $PYTHON_VERSION"
    fi

    # Check curl or wget
    if command -v curl &>/dev/null; then
        log_success "curl available"
    elif command -v wget &>/dev/null; then
        log_success "wget available"
    else
        missing+=("curl or wget")
    fi

    # Report missing prerequisites
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo ""
        log_error "Missing prerequisites: ${missing[*]}"
        echo ""

        if [[ "$OS" == "Linux" ]]; then
            echo "   Install on Debian/Ubuntu:"
            echo "   ${CYAN}sudo apt install ${missing[*]}${NC}"
            echo ""
            echo "   Install on Fedora/RHEL:"
            echo "   ${CYAN}sudo dnf install ${missing[*]}${NC}"
        elif [[ "$OS" == "macOS" ]]; then
            echo "   Install with Homebrew:"
            echo "   ${CYAN}brew install ${missing[*]}${NC}"
        fi
        echo ""
        exit 1
    fi
}

clone_or_update() {
    log_info "Installing to: $INSTALL_DIR"

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        # Existing installation - update
        log_warn "Existing installation found"
        echo ""
        echo -en "   Update existing installation? [Y/n]: "
        read -r REPLY

        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Updating repository..."
            cd "$INSTALL_DIR"

            # Save any local changes
            if ! git diff --quiet 2>/dev/null; then
                log_warn "Stashing local changes..."
                git stash push -m "Pre-update stash $(date +%Y%m%d_%H%M%S)"
            fi

            git fetch origin
            git checkout "$BRANCH"
            git pull origin "$BRANCH"
            log_success "Repository updated"
        else
            log_info "Skipping update"
        fi
    else
        # Fresh installation
        if [[ -d "$INSTALL_DIR" ]]; then
            log_error "Directory exists but is not a git repository: $INSTALL_DIR"
            echo ""
            echo "   Please remove or rename the existing directory:"
            echo "   ${CYAN}rm -rf $INSTALL_DIR${NC}"
            echo ""
            exit 1
        fi

        log_info "Cloning repository (branch: $BRANCH)..."

        # Create parent directory if needed
        mkdir -p "$(dirname "$INSTALL_DIR")"

        # Clone with shallow depth for faster download
        git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

        log_success "Repository cloned"
    fi
}

run_init() {
    log_info "Running initialization script..."
    echo ""

    cd "$INSTALL_DIR"

    if [[ -f "scripts/init.sh" ]]; then
        bash scripts/init.sh
    elif [[ -f "init_pixeagle.sh" ]]; then
        # Fallback to old location
        bash init_pixeagle.sh
    else
        log_error "Initialization script not found"
        exit 1
    fi
}

show_success() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                    ${GREEN}✓${NC} ${BOLD}Installation Complete!${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   PixEagle has been installed to: ${CYAN}$INSTALL_DIR${NC}"
    echo ""
    echo -e "   ${BOLD}Next Steps:${NC}"
    echo -e "   1. ${CYAN}cd $INSTALL_DIR${NC}"
    echo -e "   2. Edit ${CYAN}configs/config.yaml${NC} for your setup"
    echo -e "   3. ${CYAN}make run${NC} to start all services"
    echo ""
    echo -e "   ${BOLD}Quick Commands:${NC}"
    echo -e "   ${CYAN}make help${NC}    - Show all available commands"
    echo -e "   ${CYAN}make run${NC}     - Run all services"
    echo -e "   ${CYAN}make dev${NC}     - Run in development mode"
    echo -e "   ${CYAN}make stop${NC}    - Stop all services"
    echo ""
    echo -e "   ${BOLD}Documentation:${NC}"
    echo -e "   ${CYAN}https://github.com/alireza787b/PixEagle${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main
# ============================================================================

main() {
    print_banner

    echo -e "${BOLD}Starting PixEagle installation...${NC}"
    echo ""

    check_os
    check_prerequisites
    clone_or_update
    run_init
    show_success
}

main "$@"
