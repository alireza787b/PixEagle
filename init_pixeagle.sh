#!/bin/bash

# ============================================================================
# init_pixeagle.sh - Professional Initialization Script for PixEagle
# ============================================================================
# This script sets up the complete PixEagle environment:
#   - Python virtual environment with all dependencies
#   - Node.js via nvm for the dashboard
#   - Configuration files
#
# Features:
#   - Auto-detection and installation of missing packages
#   - Progress indicators and professional UX
#   - Robust error handling with clear recovery instructions
#
# Usage: bash init_pixeagle.sh
# ============================================================================

set -o pipefail  # Catch pipe failures

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=7
NVM_VERSION="v0.40.3"
NODE_VERSION="22"  # LTS version for stability
MIN_PYTHON_VERSION="3.9"
REQUIRED_DISK_MB=500

# ============================================================================
# Colors and Formatting
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'  # No Color

# Unicode symbols
CHECK="✅"
CROSS="❌"
WARN="⚠️"
INFO="ℹ️"
ROCKET="🚀"
PACKAGE="📦"
FOLDER="📁"
GEAR="⚙️"
PARTY="🎉"
EAGLE="🦅"

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
    echo ""
    echo -e "${CYAN}"
    cat << 'ASCIIART'
PPPPPPPPPPPPPPPPP     iiii                      EEEEEEEEEEEEEEEEEEEEEE                                    lllllll
P::::::::::::::::P   i::::i                     E::::::::::::::::::::E                                    l:::::l
P::::::PPPPPP:::::P   iiii                      E::::::::::::::::::::E                                    l:::::l
PP:::::P     P:::::P                            EE::::::EEEEEEEEE::::E                                    l:::::l
  P::::P     P:::::Piiiiiii xxxxxxx      xxxxxxx  E:::::E       EEEEEE  aaaaaaaaaaaaa     ggggggggg   gggggl::::l     eeeeeeeeeeee
  P::::P     P:::::Pi:::::i  x:::::x    x:::::x   E:::::E               a::::::::::::a   g:::::::::ggg::::gl::::l   ee::::::::::::ee
  P::::PPPPPP:::::P  i::::i   x:::::x  x:::::x    E::::::EEEEEEEEEE     aaaaaaaaa:::::a g:::::::::::::::::gl::::l  e::::::eeeee:::::ee
  P:::::::::::::PP   i::::i    x:::::xx:::::x     E:::::::::::::::E              a::::ag::::::ggggg::::::ggl::::l e::::::e     e:::::e
  P::::PPPPPPPPP     i::::i     x::::::::::x      E:::::::::::::::E       aaaaaaa:::::ag:::::g     g:::::g l::::l e:::::::eeeee::::::e
  P::::P             i::::i      x::::::::x       E::::::EEEEEEEEEE     aa::::::::::::ag:::::g     g:::::g l::::l e:::::::::::::::::e
  P::::P             i::::i      x::::::::x       E:::::E              a::::aaaa::::::ag:::::g     g:::::g l::::l e::::::eeeeeeeeeee
  P::::P             i::::i     x::::::::::x      E:::::E       EEEEEEa::::a    a:::::ag::::::g    g:::::g l::::l e:::::::e
PP::::::PP          i::::::i   x:::::xx:::::x   EE::::::EEEEEEEE:::::Ea::::a    a:::::ag:::::::ggggg:::::gl::::::le::::::::e
P::::::::P          i::::::i  x:::::x  x:::::x  E::::::::::::::::::::Ea:::::aaaa::::::a g::::::::::::::::gl::::::l e::::::::eeeeeeee
P::::::::P          i::::::i x:::::x    x:::::x E::::::::::::::::::::E a::::::::::aa:::a gg::::::::::::::gl::::::l  ee:::::::::::::e
PPPPPPPPPP          iiiiiiiixxxxxxx      xxxxxxxEEEEEEEEEEEEEEEEEEEEEE  aaaaaaaaaa  aaaa   gggggggg::::::gllllllll    eeeeeeeeeeeeee
                                                                                                   g:::::g
                                                                                       gggggg      g:::::g
                                                                                       g:::::gg   gg:::::g
                                                                                        g::::::ggg:::::::g
                                                                                         gg:::::::::::::g
                                                                                           ggg::::::ggg
                                                                                              gggggg
ASCIIART
    echo -e "${NC}"

    # Get version and commit info
    local version="3.2"
    local commit_hash
    commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local commit_date
    commit_date=$(git log -1 --format=%cd --date=short 2>/dev/null || echo "unknown")

    echo -e "  ${BOLD}Version:${NC} ${version}  ${DIM}|${NC}  ${BOLD}Commit:${NC} ${commit_hash} (${commit_date})"
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
    if [[ ! -f "requirements.txt" ]]; then
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
install_system_packages() {
    log_step 2 "Installing system packages..."

    local MISSING_PKGS=()
    local PYTHON_VENV_PKG="python${PYTHON_VERSION}-venv"

    # Check each required package
    if ! dpkg -s "$PYTHON_VENV_PKG" &>/dev/null 2>&1; then
        MISSING_PKGS+=("$PYTHON_VENV_PKG")
    fi
    if ! dpkg -s "libgl1" &>/dev/null 2>&1; then
        MISSING_PKGS+=("libgl1")
    fi
    if ! command -v curl &>/dev/null; then
        MISSING_PKGS+=("curl")
    fi
    if ! command -v lsof &>/dev/null; then
        MISSING_PKGS+=("lsof")
    fi
    if ! command -v tmux &>/dev/null; then
        MISSING_PKGS+=("tmux")
    fi

    if [[ ${#MISSING_PKGS[@]} -eq 0 ]]; then
        log_success "All system packages already installed"
        return 0
    fi

    log_info "Missing packages: ${MISSING_PKGS[*]}"
    echo -en "        Install automatically? [Y/n]: "
    read -r REPLY
    echo ""

    if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
        # Show prominent sudo prompt
        prompt_sudo

        log_info "Updating package lists..."
        start_spinner "Running apt update..."
        if sudo apt update -qq 2>&1; then
            stop_spinner
        else
            stop_spinner
            log_warn "apt update had warnings (continuing anyway)"
        fi

        start_spinner "Installing packages..."
        if sudo apt install -y "${MISSING_PKGS[@]}" >/dev/null 2>&1; then
            stop_spinner
            log_success "System packages installed: ${MISSING_PKGS[*]}"
        else
            stop_spinner
            log_error "Package installation failed"
            log_detail "Try manually: sudo apt install ${MISSING_PKGS[*]}"
            exit 1
        fi
    else
        log_error "Required packages not installed"
        log_detail "Please install manually: sudo apt install ${MISSING_PKGS[*]}"
        exit 1
    fi
}

# ============================================================================
# Python Virtual Environment (Step 3)
# ============================================================================
create_venv() {
    log_step 3 "Creating Python virtual environment..."

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
install_python_deps() {
    log_step 4 "Installing Python dependencies..."

    # Source the virtual environment
    # shellcheck source=/dev/null
    source venv/bin/activate

    # Count packages (excluding comments and empty lines)
    local total_packages
    total_packages=$(grep -c -E '^[^#[:space:]]' requirements.txt 2>/dev/null || echo "0")
    log_info "Installing ${total_packages} packages from requirements.txt"
    log_warn "Large packages (ultralytics, torch, opencv) may take several minutes"
    echo ""

    # Upgrade pip first
    echo -e "        ${DIM}Upgrading pip...${NC}"
    venv/bin/pip install --upgrade pip -q 2>&1 || true

    # Install with visible progress - parse pip output in real-time
    echo -e "        ${CYAN}Installing packages:${NC}"
    local install_failed=0

    # Run pip and parse output line by line
    venv/bin/pip install -r requirements.txt 2>&1 | while IFS= read -r line; do
        # Parse pip output for package names
        if [[ "$line" =~ ^Collecting\ (.+) ]]; then
            local pkg="${BASH_REMATCH[1]}"
            # Truncate long package names
            printf "\r        ${DIM}→ Collecting: %-55s${NC}" "${pkg:0:55}"
        elif [[ "$line" =~ ^Downloading\ (.+) ]]; then
            local file="${BASH_REMATCH[1]}"
            printf "\r        ${DIM}→ Downloading: %-53s${NC}" "${file:0:53}"
        elif [[ "$line" =~ ^Installing\ collected\ packages ]]; then
            printf "\r        ${GREEN}→ Installing collected packages...                           ${NC}\n"
        elif [[ "$line" =~ ^Successfully\ installed ]]; then
            printf "\r        ${GREEN}✅ Packages installed successfully                            ${NC}\n"
        elif [[ "$line" =~ ^ERROR: ]]; then
            printf "\r        ${RED}❌ Error: %s${NC}\n" "${line:7}"
        fi
    done

    # Check if pip succeeded
    # Re-run pip in check mode to verify installation
    if ! venv/bin/pip check >/dev/null 2>&1; then
        # Some dependency issues but not necessarily fatal
        log_warn "Some dependency warnings detected (usually not critical)"
    fi

    # Verify key packages are installed
    if venv/bin/python -c "import cv2; import numpy" 2>/dev/null; then
        log_success "${total_packages} packages installed successfully"
    else
        log_error "Core packages (opencv, numpy) not installed correctly"
        log_detail "Try manually: source venv/bin/activate && pip install -r requirements.txt"
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

    cd ..
}

# ============================================================================
# Configuration Files (Step 7)
# ============================================================================
generate_env_from_yaml() {
    local yaml_file="$1"
    local env_file="$2"

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

    local BASE_DIR
    BASE_DIR="$(pwd)"
    local CONFIG_DIR="$BASE_DIR/configs"
    local DEFAULT_CONFIG="$CONFIG_DIR/config_default.yaml"
    local USER_CONFIG="$CONFIG_DIR/config.yaml"
    local DASHBOARD_DIR="$BASE_DIR/dashboard"
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
        echo -en "        Replace with latest default? [y/N]: "
        read -r REPLY
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
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
            echo -en "        Replace with latest default? [y/N]: "
            read -r REPLY
            echo ""

            if [[ $REPLY =~ ^[Yy]$ ]]; then
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
# Summary Display
# ============================================================================
show_summary() {
    local node_version
    node_version=$(node -v 2>/dev/null || echo "not installed")

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}Setup Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} Python ${PYTHON_VERSION} virtual environment created"
    echo -e "   ${GREEN}${CHECK}${NC} Python dependencies installed"
    if [[ "$node_version" != "not installed" ]]; then
        echo -e "   ${GREEN}${CHECK}${NC} Node.js ${node_version} ready"
        echo -e "   ${GREEN}${CHECK}${NC} Dashboard dependencies installed"
    else
        echo -e "   ${YELLOW}${WARN}${NC}  Node.js needs manual setup"
    fi
    echo -e "   ${GREEN}${CHECK}${NC} Configuration files generated"
    echo ""
    echo -e "   ${CYAN}${BOLD}📋 Next Steps:${NC}"
    echo -e "      1. Edit ${BOLD}configs/config.yaml${NC} for your setup"
    echo -e "      2. Run: ${BOLD}bash run_pixeagle.sh${NC}"
    echo ""
    echo -e "   ${YELLOW}${BOLD}⚡ Optional (better performance):${NC}"
    echo -e "      • ${BOLD}bash scripts/install_dlib.sh${NC}     (faster tracking)"
    echo -e "      • ${BOLD}bash setup_pytorch.sh${NC}            (GPU acceleration)"
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
    display_banner

    echo -e "${DIM}Starting PixEagle initialization...${NC}"
    echo ""

    check_system_requirements
    install_system_packages
    create_venv
    install_python_deps
    setup_nodejs
    install_dashboard_deps
    setup_configs

    show_summary
}

# Run main function
main "$@"
