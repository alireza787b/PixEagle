#!/bin/bash

# ============================================================================
# install.sh - PixEagle Bootstrap Installer (Linux)
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
#   4. Displays wrapper next steps; scripts/init.sh prints component status
#      for ready, skipped, degraded, and manual-follow-up items
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
STAGED_CONFIG_RELATIVE="configs/.config_default_preupdate.yaml"

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

validate_staged_defaults_content() {
    local staged_path="$1"
    local candidate
    local validation_python=""
    local configured_venv="${PIXEAGLE_VENV_DIR:-}"

    if [[ -n "$configured_venv" && "$configured_venv" != /* ]]; then
        configured_venv="$INSTALL_DIR/$configured_venv"
    fi
    for candidate in \
        "${configured_venv:+$configured_venv/bin/python}" \
        "$INSTALL_DIR/.venv/bin/python" \
        "$INSTALL_DIR/venv/bin/python" \
        "$(command -v python3 2>/dev/null || true)"; do
        if [[ -n "$candidate" && -x "$candidate" ]] &&
           "$candidate" -c "import yaml" >/dev/null 2>&1; then
            validation_python="$candidate"
            break
        fi
    done
    if [[ -z "$validation_python" ]]; then
        log_error "Cannot validate pre-update defaults: Python with PyYAML is unavailable"
        return 1
    fi
    "$validation_python" - "$staged_path" <<'PY'
import pathlib
import sys

import yaml

source = pathlib.Path(sys.argv[1]).read_bytes()
value = yaml.safe_load(source)
if not isinstance(value, dict) or not value:
    raise SystemExit("staged defaults must contain a non-empty YAML mapping")
PY
}

stage_preupdate_defaults() {
    local source_path="$INSTALL_DIR/configs/config_default.yaml"
    local staged_path="$INSTALL_DIR/$STAGED_CONFIG_RELATIVE"

    if [[ ! -f "$source_path" || -L "$source_path" || ! -s "$source_path" ]]; then
        log_error "Cannot preserve pre-update defaults: configs/config_default.yaml is not a regular file"
        return 1
    fi

    if [[ -e "$staged_path" || -L "$staged_path" ]]; then
        if [[ ! -f "$staged_path" || -L "$staged_path" || ! -O "$staged_path" ]]; then
            log_error "Pending pre-update defaults are not an owner-controlled regular file"
            return 1
        fi
        if ! chmod 600 "$staged_path"; then
            log_error "Could not restrict pending pre-update defaults to the current user"
            return 1
        fi
        if ! validate_staged_defaults_content "$staged_path"; then
            log_error "Pending pre-update defaults failed integrity validation"
            return 1
        fi
        log_info "Keeping the pending pre-update defaults baseline"
        return 0
    fi

    local previous_umask
    local temp_path
    previous_umask="$(umask)"
    umask 077
    if ! temp_path="$(mktemp "${staged_path}.tmp.XXXXXX")"; then
        umask "$previous_umask"
        log_error "Could not create the private pre-update defaults staging file"
        return 1
    fi
    umask "$previous_umask"

    if ! cp -- "$source_path" "$temp_path" ||
       ! chmod 600 "$temp_path" ||
       ! cmp -s -- "$source_path" "$temp_path"; then
        rm -f -- "$temp_path"
        log_error "Could not copy and verify the pre-update defaults baseline"
        return 1
    fi
    if ! validate_staged_defaults_content "$temp_path"; then
        rm -f -- "$temp_path"
        log_error "Pre-update defaults failed integrity validation"
        return 1
    fi
    if ! ln -- "$temp_path" "$staged_path"; then
        rm -f -- "$temp_path"
        log_error "Could not atomically publish the pre-update defaults baseline"
        return 1
    fi
    rm -f -- "$temp_path"
    log_success "Pre-update config defaults preserved"
}

check_os() {
    log_info "Detecting operating system..."

    case "$(uname -s)" in
        Linux*)
            OS="Linux"
            if [[ -f /etc/os-release ]]; then
                # shellcheck source=/dev/null
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
            log_error "PixEagle guided bootstrap currently supports Linux only"
            echo ""
            echo "   macOS is not a maintained one-command install path because"
            echo "   scripts/init.sh installs Debian/Ubuntu apt packages."
            echo "   Use a Linux host/VM for the guided setup, or follow the docs"
            echo "   only after adding a reviewed macOS bootstrap path."
            echo ""
            exit 1
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
        cd "$INSTALL_DIR"

        # Get current version info
        local current_commit
        local current_branch
        current_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")

        echo ""
        log_warn "Existing installation found"
        echo -e "      Current: ${CYAN}$current_branch${NC} @ ${CYAN}$current_commit${NC}"
        echo ""

        # Check for local changes (staged + unstaged + untracked).
        local raw_status
        local status
        if ! raw_status="$(git status --porcelain --untracked-files=all 2>/dev/null)"; then
            log_error "Cannot inspect the existing checkout; refusing automatic update"
            echo ""
            echo "   Repair repository ownership/integrity and confirm ${CYAN}git status${NC} succeeds."
            echo ""
            exit 1
        fi
        status="$(
            printf '%s\n' "$raw_status" |
                awk -v staged="$STAGED_CONFIG_RELATIVE" '$0 != "?? " staged'
        )"
        if [[ -n "$status" ]]; then
            log_warn "Local changes detected:"
            git status --short
            echo ""
        fi

        # Check if running interactively (has TTY) or via pipe
        if [[ -t 0 ]]; then
            # Interactive - ask user
            echo -en "   Update to latest version? [Y/n]: "
            read -r REPLY
        else
            # Running via pipe (curl | bash) - default to yes
            log_info "Running non-interactively, auto-updating..."
            REPLY="y"
        fi

        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Updating repository..."

            if [[ -n "$status" ]]; then
                log_error "Existing checkout has local changes; refusing automatic update"
                echo ""
                echo "   Commit or stash manually, then rerun the installer or use:"
                echo "   ${CYAN}cd $INSTALL_DIR && make sync${NC}"
                echo ""
                exit 1
            fi

            if [[ "$current_branch" != "$BRANCH" ]]; then
                log_error "Current branch '$current_branch' does not match requested branch '$BRANCH'"
                echo ""
                echo "   Checkout the target branch manually, then rerun:"
                echo "   ${CYAN}cd $INSTALL_DIR && git checkout $BRANCH && make sync${NC}"
                echo ""
                exit 1
            fi

            log_info "Preserving the current config defaults before update..."
            if ! stage_preupdate_defaults; then
                log_error "Update stopped before changing the source checkout"
                exit 1
            fi

            # Fetch latest
            log_info "Fetching latest changes..."
            if ! git fetch --prune origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"; then
                log_error "Fetch failed for origin/$BRANCH; no update was attempted"
                exit 1
            fi
            if ! git rev-parse --verify "origin/$BRANCH^{commit}" >/dev/null 2>&1; then
                log_error "Fetched ref is not available: origin/$BRANCH"
                exit 1
            fi

            # Get remote version info
            local remote_commit
            remote_commit=$(git rev-parse --short "origin/$BRANCH" 2>/dev/null || echo "unknown")

            if [[ "$current_commit" == "$remote_commit" ]]; then
                log_success "Already up to date ($current_commit)"
            else
                echo -e "      Updating: ${CYAN}$current_commit${NC} → ${CYAN}$remote_commit${NC}"

                if ! git merge --ff-only "origin/$BRANCH"; then
                    log_error "Fast-forward update was not possible; no merge or reset was attempted"
                    echo ""
                    echo "   Inspect and resolve manually:"
                    echo "   ${CYAN}cd $INSTALL_DIR && git log --oneline --graph --decorate HEAD origin/$BRANCH${NC}"
                    echo ""
                    exit 1
                fi

                log_success "Repository updated to $remote_commit"
            fi
        else
            log_info "Skipping update - using existing version"
        fi
    else
        # Fresh installation
        if [[ -d "$INSTALL_DIR" ]]; then
            log_error "Directory exists but is not a git repository: $INSTALL_DIR"
            echo ""
            echo "   Options:"
            echo "   1. Remove it:  ${CYAN}rm -rf $INSTALL_DIR${NC}"
            echo "   2. Rename it:  ${CYAN}mv $INSTALL_DIR ${INSTALL_DIR}.backup${NC}"
            echo ""
            exit 1
        fi

        log_info "Cloning repository (branch: $BRANCH)..."

        # Create parent directory if needed
        mkdir -p "$(dirname "$INSTALL_DIR")"

        # Clone with shallow depth for faster download
        git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

        cd "$INSTALL_DIR"
        local new_commit
        new_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        log_success "Repository cloned ($new_commit)"
    fi
}

fix_line_endings() {
    # Fix CRLF line endings in shell scripts (Windows compatibility)
    local dir="$1"
    log_info "Normalizing shell script line endings..."

    # Find all .sh files and fix CRLF endings
    if command -v find &>/dev/null && command -v sed &>/dev/null; then
        find "$dir" -name "*.sh" -type f 2>/dev/null | while read -r file; do
            if grep -q $'\r' "$file" 2>/dev/null; then
                sed -i.bak 's/\r$//' "$file" 2>/dev/null && rm -f "${file}.bak" 2>/dev/null
            fi
        done
        log_success "Line endings normalized"
    fi
}

run_init() {
    log_info "Running initialization script..."
    echo ""

    cd "$INSTALL_DIR"

    # Fix any CRLF line endings before running scripts
    fix_line_endings "$INSTALL_DIR"

    if [[ -f "scripts/init.sh" ]]; then
        bash scripts/init.sh
    elif [[ -f "init_pixeagle.sh" ]]; then
        # Fallback to old location
        bash init_pixeagle.sh
    else
        log_error "Initialization script not found"
        exit 1
    fi

    if [[ -e "$INSTALL_DIR/$STAGED_CONFIG_RELATIVE" || -L "$INSTALL_DIR/$STAGED_CONFIG_RELATIVE" ]]; then
        log_error "Configuration update baseline is still pending after initialization"
        echo "   Re-run ${CYAN}make init${NC}; the preserved baseline was not deleted."
        exit 1
    fi
}

show_success() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                    ${GREEN}✓${NC} ${BOLD}Bootstrap Finished${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   PixEagle checkout is at: ${CYAN}$INSTALL_DIR${NC}"
    echo -e "   Review the init summary above before starting services."
    echo -e "   Resolve any degraded or manual-follow-up items, then re-run ${CYAN}make init${NC}."
    echo ""
    echo -e "   ${BOLD}Next Steps:${NC}"
    echo -e "   1. ${CYAN}cd $INSTALL_DIR${NC}"
    echo -e "   2. ${CYAN}make run${NC} only after the init summary is ready for your use case"
    echo -e "   3. Optional QGC field video: ${CYAN}make qgc-video-profile GCS_HOST=<gcs-ip>${NC}"
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
