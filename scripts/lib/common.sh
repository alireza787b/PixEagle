#!/bin/bash

# Shared shell presentation helpers for PixEagle scripts.
# Keep this file dependency-free: it is sourced before venv/npm setup exists.

if [[ -n "${PIXEAGLE_COMMON_SH_LOADED:-}" ]]; then
    return 0 2>/dev/null || exit 0
fi
PIXEAGLE_COMMON_SH_LOADED=1

# Colors. NO_COLOR disables ANSI output for logs that need plain text.
if [[ -n "${NO_COLOR:-}" ]]; then
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    CYAN=""
    BOLD=""
    DIM=""
    NC=""
else
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    DIM='\033[2m'
    NC='\033[0m'
fi

# Symbols are ASCII so logs remain portable across minimal terminals.
CHECK="[OK]"
CROSS="[X]"
WARN="[!]"
INFO="[i]"
PARTY="*"
PACKAGE="[pkg]"
VIDEO="[video]"
CLOCK="[time]"

display_pixeagle_banner() {
    local title="${1:-Vision-Based Drone Tracking System}"
    local subtitle="${2:-}"

    echo ""
    echo -e "${CYAN}${BOLD}PixEagle${NC}"
    echo -e "  ${BOLD}${title}${NC}"
    if [[ -n "$subtitle" ]]; then
        echo -e "  ${DIM}${subtitle}${NC}"
    fi
    echo ""
}

get_version_info() {
    local script_version="${1:-unknown}"
    local root="${PIXEAGLE_DIR:-}"

    if [[ -z "$root" ]]; then
        root="$(pwd)"
    fi

    if [[ -d "$root/.git" ]]; then
        local git_tag=""
        local git_commit="unknown"
        git_tag="$(git -C "$root" describe --tags --abbrev=0 2>/dev/null || true)"
        git_commit="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
        if [[ -n "$git_tag" ]]; then
            echo -e "  ${DIM}Version: ${git_tag} (${git_commit}) | Script: v${script_version}${NC}"
        else
            echo -e "  ${DIM}Commit: ${git_commit} | Script: v${script_version}${NC}"
        fi
    else
        echo -e "  ${DIM}Script: v${script_version}${NC}"
    fi
}

log_info() {
    echo -e "   ${CYAN}[*]${NC} $1"
}

log_success() {
    echo -e "   ${GREEN}${CHECK}${NC} $1"
}

log_warn() {
    echo -e "   ${YELLOW}${WARN}${NC} $1"
}

log_warning() {
    log_warn "$1"
}

log_error() {
    echo -e "   ${RED}${CROSS}${NC} $1"
}

log_detail() {
    echo -e "      ${DIM}$1${NC}"
}

log_step() {
    local step="${1:-?}"
    local msg="${2:-}"
    local total="${TOTAL_STEPS:-?}"

    echo ""
    echo -e "${CYAN}----------------------------------------------------------------${NC}"
    echo -e "   ${BOLD}Step ${step}/${total}:${NC} ${msg}"
    echo -e "${CYAN}----------------------------------------------------------------${NC}"
}

log_section() {
    local msg="${1:-}"
    echo ""
    echo -e "${CYAN}----------------------------------------------------------------${NC}"
    echo -e "${CYAN}${BOLD}${msg}${NC}"
    echo -e "${CYAN}----------------------------------------------------------------${NC}"
    echo ""
}

PIXEAGLE_COMMON_SPINNER_PID=""

start_spinner() {
    local msg="${1:-Working...}"
    local chars='|/-\'

    (
        while true; do
            local i
            for ((i = 0; i < ${#chars}; i++)); do
                printf "\r        ${CYAN}%s${NC} %s" "${chars:$i:1}" "$msg"
                sleep 0.1
            done
        done
    ) &
    PIXEAGLE_COMMON_SPINNER_PID=$!
}

stop_spinner() {
    if [[ -n "${PIXEAGLE_COMMON_SPINNER_PID:-}" ]]; then
        kill "$PIXEAGLE_COMMON_SPINNER_PID" 2>/dev/null || true
        wait "$PIXEAGLE_COMMON_SPINNER_PID" 2>/dev/null || true
        PIXEAGLE_COMMON_SPINNER_PID=""
        printf "\r        \033[K"
    fi
}

resolve_pixeagle_venv_dir() {
    local project_root="${1:-${PIXEAGLE_DIR:-$(pwd)}}"

    if [[ -n "${PIXEAGLE_VENV_DIR:-}" ]]; then
        case "$PIXEAGLE_VENV_DIR" in
            /*) printf '%s\n' "$PIXEAGLE_VENV_DIR" ;;
            *) printf '%s\n' "$project_root/$PIXEAGLE_VENV_DIR" ;;
        esac
        return 0
    fi

    if [[ -x "$project_root/.venv/bin/python" ]]; then
        printf '%s\n' "$project_root/.venv"
        return 0
    fi

    if [[ -x "$project_root/venv/bin/python" ]]; then
        printf '%s\n' "$project_root/venv"
        return 0
    fi

    if [[ -d "$project_root/.venv" ]]; then
        printf '%s\n' "$project_root/.venv"
        return 0
    fi

    printf '%s\n' "$project_root/venv"
}

resolve_pixeagle_venv_python() {
    local project_root="${1:-${PIXEAGLE_DIR:-$(pwd)}}"
    local venv_dir
    venv_dir="$(resolve_pixeagle_venv_dir "$project_root")"
    printf '%s\n' "$venv_dir/bin/python"
}

resolve_pixeagle_venv_pip() {
    local project_root="${1:-${PIXEAGLE_DIR:-$(pwd)}}"
    local venv_dir
    venv_dir="$(resolve_pixeagle_venv_dir "$project_root")"
    printf '%s\n' "$venv_dir/bin/pip"
}
