#!/bin/bash
# ============================================================================
# common.sh - Shared Functions for PixEagle Scripts
# ============================================================================
# This file provides consistent colors, logging, and banner display
# across all PixEagle shell scripts.
#
# Usage: source "$(dirname "$0")/scripts/common.sh"
#    or: source "$SCRIPT_DIR/scripts/common.sh"
#
# Variables provided:
#   Colors: RED, GREEN, YELLOW, BLUE, CYAN, MAGENTA, BOLD, DIM, NC
#   Symbols: CHECK, CROSS, WARN, INFO, ROCKET, PACKAGE, GEAR, PARTY
#
# Functions provided:
#   display_pixeagle_banner [subtitle] [description]
#   log_step <step_num> <message>       # Requires TOTAL_STEPS to be set
#   log_success <message>
#   log_error <message>
#   log_warn <message>
#   log_info <message>
# ============================================================================

# Prevent multiple sourcing
if [[ -n "${_PIXEAGLE_COMMON_SOURCED:-}" ]]; then
    return 0
fi
_PIXEAGLE_COMMON_SOURCED=1

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
FIRE="🔥"
VIDEO="🎥"
CLOCK="⏱️"

# ============================================================================
# Banner Display
# ============================================================================
# Displays the PixEagle ASCII banner with optional subtitle and description
#
# Usage:
#   display_pixeagle_banner                           # Just the banner
#   display_pixeagle_banner "My Script"               # With subtitle
#   display_pixeagle_banner "My Script" "Description" # With both
#
display_pixeagle_banner() {
    local subtitle="${1:-}"
    local description="${2:-}"

    # Find the banner file relative to this script
    local common_dir
    common_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local banner_file="$common_dir/banner.txt"

    echo ""
    echo -e "${CYAN}"

    if [[ -f "$banner_file" ]]; then
        cat "$banner_file"
    else
        # Fallback if banner.txt is missing
        cat << 'ASCIIART'
 _____ _      ______            _
 |  __ (_)    |  ____|          | |
 | |__) |__  _| |__   __ _  __ _| | ___
 |  ___/ \ \/ /  __| / _` |/ _` | |/ _ \
 | |   | |>  <| |___| (_| | (_| | |  __/
 |_|   |_/_/\_\______\__,_|\__, |_|\___|
                            __/ |
                           |___/
ASCIIART
    fi

    echo -e "${NC}"

    # Display subtitle if provided
    if [[ -n "$subtitle" ]]; then
        echo -e "  ${BOLD}${subtitle}${NC}"
    fi

    # Display description if provided
    if [[ -n "$description" ]]; then
        echo -e "  ${DIM}${description}${NC}"
    fi

    echo ""
}

# ============================================================================
# Logging Functions
# ============================================================================
# Note: log_step requires TOTAL_STEPS variable to be set in the calling script

log_step() {
    local step=$1
    local message=$2
    echo ""
    echo -e "${CYAN}${BOLD}[${step}/${TOTAL_STEPS:-?}]${NC} ${message}"
}

log_success() {
    echo -e "        ${GREEN}${CHECK}${NC} $1"
}

log_error() {
    echo -e "        ${RED}${CROSS}${NC} $1" >&2
}

log_warn() {
    echo -e "        ${YELLOW}${WARN}${NC}  $1"
}

log_info() {
    echo -e "        ${BLUE}${INFO}${NC}  $1"
}

# Simple logging without indentation
log() {
    echo -e "$1"
}

# Section header for visual separation
log_section() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}${BOLD}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ============================================================================
# Utility Functions
# ============================================================================

# Check if running in PixEagle directory
check_pixeagle_dir() {
    if [[ ! -f "requirements.txt" ]] || [[ ! -d "src" ]]; then
        log_error "This script must be run from the PixEagle root directory"
        exit 1
    fi
}

# Check if virtual environment exists
check_venv() {
    local venv_dir="${1:-venv}"
    if [[ ! -d "$venv_dir" ]] || [[ ! -f "$venv_dir/bin/activate" ]]; then
        return 1
    fi
    return 0
}

# Get git version info
get_version_info() {
    local version="${1:-}"
    local commit_hash
    local commit_date

    commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    commit_date=$(git log -1 --format=%cd --date=short 2>/dev/null || echo "unknown")

    if [[ -n "$version" ]]; then
        echo -e "  ${BOLD}Version:${NC} ${version}  ${DIM}|${NC}  ${BOLD}Commit:${NC} ${commit_hash} (${commit_date})"
    else
        echo -e "  ${BOLD}Commit:${NC} ${commit_hash} (${commit_date})"
    fi
}
