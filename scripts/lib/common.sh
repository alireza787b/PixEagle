#!/bin/bash
# shellcheck disable=SC2034  # Symbols/colors are an API for scripts that source this file.

# Shared shell presentation helpers for PixEagle scripts.
# Keep this file dependency-free: it is sourced before venv/npm setup exists.

if [[ -n "${PIXEAGLE_COMMON_SH_LOADED:-}" ]]; then
    # shellcheck disable=SC2317  # This file supports both sourcing and direct execution.
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
    local common_dir banner_file

    common_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    banner_file="$common_dir/../banner.txt"

    echo ""
    echo -e "${CYAN}${BOLD}"
    if [[ -f "$banner_file" ]]; then
        cat -- "$banner_file"
    else
        cat <<'ASCIIART'
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
    echo -e "  ${BOLD}${title}${NC}"
    if [[ -n "$subtitle" ]]; then
        echo -e "  ${DIM}${subtitle}${NC}"
    fi
    echo ""
}

# A /dev/tty device node can exist even when the process has no controlling
# terminal. Probe the open operation itself so curl-piped and automation runs
# never emit a misleading /dev/tty error or wait for input that cannot arrive.
pixeagle_has_interactive_input() {
    [[ "${PIXEAGLE_NONINTERACTIVE:-0}" != "1" ]] || return 1
    [[ -t 0 ]] && return 0
    ( : </dev/tty ) 2>/dev/null
}

pixeagle_read_user_input() {
    local __pixeagle_destination="$1"
    local __pixeagle_read_value=""

    [[ "$__pixeagle_destination" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || return 2
    if [[ -t 0 ]]; then
        IFS= read -r __pixeagle_read_value || return 1
    elif ( : </dev/tty ) 2>/dev/null; then
        IFS= read -r __pixeagle_read_value </dev/tty || return 1
    else
        return 1
    fi
    # Bash functions use dynamic scoping. Keep the internal value name distinct
    # from normal caller variables such as reply, choice, and selection so the
    # assignment reaches the caller instead of a same-named local here.
    printf -v "$__pixeagle_destination" '%s' "$__pixeagle_read_value"
}

pixeagle_running_as_root() {
    [[ "$EUID" -eq 0 ]]
}

# Privileged setup commands can be reached through a curl pipe whose stdin is
# already closed. Authenticate sudo against the verified controlling terminal
# instead of inheriting that pipe. The password remains inside sudo.
PIXEAGLE_SUDO_FAILURE_REASON=""

pixeagle_sudo_validate() {
    PIXEAGLE_SUDO_FAILURE_REASON=""

    if pixeagle_running_as_root; then
        return 0
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        PIXEAGLE_SUDO_FAILURE_REASON="sudo_missing"
        return 1
    fi
    if sudo -n -v 2>/dev/null; then
        return 0
    fi
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" ]]; then
        PIXEAGLE_SUDO_FAILURE_REASON="authentication_required_noninteractive"
        return 1
    fi
    if [[ -t 0 ]]; then
        if sudo -S -v; then
            return 0
        fi
    elif ( : </dev/tty ) 2>/dev/null; then
        # shellcheck disable=SC2024  # The redirect intentionally feeds sudo -S itself.
        if sudo -S -v </dev/tty; then
            return 0
        fi
    else
        PIXEAGLE_SUDO_FAILURE_REASON="terminal_unavailable"
        return 1
    fi

    PIXEAGLE_SUDO_FAILURE_REASON="authentication_failed"
    return 1
}

pixeagle_sudo_failure_message() {
    case "${PIXEAGLE_SUDO_FAILURE_REASON:-unknown}" in
        sudo_missing)
            printf '%s\n' "Administrator access is required, but sudo is not installed."
            ;;
        authentication_required_noninteractive)
            printf '%s\n' "Administrator authentication is required in non-interactive setup."
            ;;
        terminal_unavailable)
            printf '%s\n' "Administrator authentication requires an interactive terminal."
            ;;
        authentication_failed)
            printf '%s\n' "sudo authentication failed; no privileged setup command was started."
            ;;
        *)
            printf '%s\n' "Administrator access could not be validated."
            ;;
    esac
}

pixeagle_sudo_run() {
    PIXEAGLE_SUDO_FAILURE_REASON=""

    if pixeagle_running_as_root; then
        "$@"
        return
    fi
    if ! pixeagle_sudo_validate; then
        return 1
    fi

    # Use the same verified terminal for each privileged operation. This also
    # recovers cleanly when sudo credentials expire during a long source build.
    if [[ "${PIXEAGLE_NONINTERACTIVE:-0}" == "1" ]]; then
        sudo -n "$@"
    elif [[ -t 0 ]]; then
        sudo -S "$@"
    elif ( : </dev/tty ) 2>/dev/null; then
        # shellcheck disable=SC2024  # The redirect intentionally feeds sudo -S itself.
        sudo -S "$@" </dev/tty
    else
        PIXEAGLE_SUDO_FAILURE_REASON="terminal_unavailable"
        return 1
    fi
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
    # shellcheck disable=SC1003  # A trailing backslash is a spinner glyph.
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

    printf '%s\n' "$project_root/.venv"
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
