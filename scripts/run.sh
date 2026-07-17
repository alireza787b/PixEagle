#!/bin/bash

# ============================================================================
# scripts/run.sh - PixEagle System Launcher
# ============================================================================
# The main entry point for running the PixEagle system.
#
# Features:
#   - Combined tmux view (4-pane grid) as default
#   - Comprehensive pre-flight checks
#   - Service health monitoring with port readiness
#   - Clear progress steps with status indicators
#   - Graceful cleanup on interrupt (SIGINT/SIGTERM)
#
# Components:
#   - MAVLink2REST: MAVLink to REST API bridge
#   - Dashboard: React-based web interface
#   - Main App: Python computer vision backend
#   - MAVSDK Server: MAVLink communication server
#
# Usage:
#   make run                     (recommended)
#   bash scripts/run.sh          (direct)
#   bash scripts/run.sh --dev    (development mode)
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
TOTAL_STEPS=6

# Source shared functions (colors, logging, banner)
# shellcheck source=scripts/lib/common.sh
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    echo "Warning: Could not source common.sh"
fi

# Source shared port helpers (optional fallback below).
# shellcheck source=/dev/null
if ! source "$SCRIPTS_DIR/lib/ports.sh" 2>/dev/null; then
    echo "Warning: Could not source ports.sh"
fi

# Ownership checks are mandatory because launcher cleanup can signal processes.
# shellcheck source=scripts/lib/runtime_ownership.sh
if ! source "$SCRIPTS_DIR/lib/runtime_ownership.sh" 2>/dev/null; then
    echo "Error: Could not source runtime_ownership.sh" >&2
    exit 1
fi

# Resource locking is mandatory. Lifecycle transactions are serialized and
# every runtime component holds shared source/venv access for its full lifetime.
# shellcheck source=scripts/lib/setup_lock.sh
if ! source "$SCRIPTS_DIR/lib/setup_lock.sh" 2>/dev/null; then
    echo "Error: Could not source setup_lock.sh" >&2
    exit 1
fi

LIFECYCLE_RESOURCE="$(pixeagle_lifecycle_resource "$PIXEAGLE_DIR")" || {
    echo "Error: Could not resolve the lifecycle resource" >&2
    exit 1
}

# Fallback definitions if common.sh failed
if ! declare -f log_info &>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    CHECK="✓"; CROSS="✗"; WARN="!"
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[${CHECK}]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[${WARN}]${NC} $1"; }
    log_error() { echo -e "   ${RED}[${CROSS}]${NC} $1"; }
    log_step() { echo -e "\n${CYAN}━━━ Step $1/${TOTAL_STEPS}: $2 ━━━${NC}"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}═══ PixEagle System Launcher ═══${NC}\n"
    }
fi

# Default flag values (all components enabled by default)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true
RUN_MAVSDK_SERVER=true
COMBINED_VIEW=true
NO_ATTACH=false

# Development and build flags
DEVELOPMENT_MODE=false
FORCE_REBUILD=false

# Runtime identity. Manual and systemd launches use separate tmux servers, so
# neither lifecycle can adopt or stop the other one.
SESSION_NAME="pixeagle"
PIXEAGLE_RUNTIME_MODE="${PIXEAGLE_RUNTIME_MODE:-manual}"
if ! pixeagle_runtime_mode_is_valid "$PIXEAGLE_RUNTIME_MODE"; then
    echo "Error: PIXEAGLE_RUNTIME_MODE must be manual or service" >&2
    exit 2
fi
TMUX_SOCKET_NAME="$(pixeagle_tmux_socket_name "$PIXEAGLE_DIR" "$PIXEAGLE_RUNTIME_MODE")" || exit 1

# Default ports (resolved from shared defaults + config when available)
MAVLINK2REST_PORT="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"
BACKEND_PORT="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
DASHBOARD_PORT="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
WEBSOCKET_PORT="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"
MAVSDK_SERVER_ADDRESS="127.0.0.1"
MAVSDK_SERVER_PORT="50051"
PX4_SYSTEM_ADDRESS="udp://127.0.0.1:14540"
EXTERNAL_MAVSDK_SERVER="true"
BACKEND_HOST="127.0.0.1"
API_EXPOSURE_MODE="local_only"
API_AUTH_MODE="local_compat"
DASHBOARD_HOST="${PIXEAGLE_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_EXPOSURE_MODE="${PIXEAGLE_DASHBOARD_EXPOSURE_MODE:-local_only}"
if [[ -z "${PIXEAGLE_RUN_ID:-}" ]]; then
    PIXEAGLE_RUN_ID="$(pixeagle_generate_run_id "pixeagle_${PIXEAGLE_RUNTIME_MODE}")" || {
        echo "Error: could not generate a collision-resistant PixEagle run ID" >&2
        exit 1
    }
fi
if ! pixeagle_run_id_is_valid "$PIXEAGLE_RUN_ID"; then
    echo "Error: PIXEAGLE_RUN_ID is not a valid bounded runtime identity" >&2
    exit 2
fi
PIXEAGLE_RUNTIME_LOG_DIR="${PIXEAGLE_RUNTIME_LOG_DIR:-$PIXEAGLE_DIR/logs/runtime}"
PIXEAGLE_PROJECT_ROOT="$(pixeagle_canonical_root "$PIXEAGLE_DIR")"
PIXEAGLE_SESSION_NAME="$SESSION_NAME"
PIXEAGLE_TMUX_SOCKET_NAME="$TMUX_SOCKET_NAME"
export PIXEAGLE_RUN_ID PIXEAGLE_RUNTIME_LOG_DIR PIXEAGLE_PROJECT_ROOT
export PIXEAGLE_SESSION_NAME PIXEAGLE_RUNTIME_MODE PIXEAGLE_TMUX_SOCKET_NAME

tmux_runtime() {
    pixeagle_tmux "$TMUX_SOCKET_NAME" "$@"
}

# ============================================================================
# Helper: Read port from config.yaml
# ============================================================================
get_config_value() {
    local section="$1"
    local key="$2"
    local default="$3"
    local source_config="$CONFIG_FILE"

    if [[ ! -f "$source_config" && -f "$DEFAULT_CONFIG_FILE" ]]; then
        source_config="$DEFAULT_CONFIG_FILE"
    fi

    if [[ -f "$source_config" && -x "$VENV_DIR/bin/python" ]]; then
        "$VENV_DIR/bin/python" - "$source_config" "$section" "$key" "$default" <<'PY' 2>/dev/null || printf '%s\n' "$default"
import sys

import yaml

source_path, section, key, default = sys.argv[1:]
try:
    with open(source_path, "r", encoding="utf-8") as source_file:
        config = yaml.safe_load(source_file) or {}
    section_data = config.get(section, {}) if isinstance(config, dict) else {}
    value = section_data.get(key, default) if isinstance(section_data, dict) else default
    if isinstance(value, bool):
        print("true" if value else "false")
    elif value is None:
        print("")
    else:
        print(value)
except (OSError, UnicodeError, yaml.YAMLError):
    print(default)
PY
    else
        echo "$default"
    fi
}

is_loopback_host() {
    case "$1" in
        127.*|localhost|"::1"|"[::1]") return 0 ;;
        *) return 1 ;;
    esac
}

resolve_venv_dir() {
    if declare -f resolve_pixeagle_venv_dir >/dev/null 2>&1; then
        resolve_pixeagle_venv_dir "$PIXEAGLE_DIR"
    elif [[ -x "$PIXEAGLE_DIR/.venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/.venv"
    elif [[ -x "$PIXEAGLE_DIR/venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/venv"
    else
        echo "$PIXEAGLE_DIR/.venv"
    fi
}

# Paths to component scripts
VENV_DIR="$(resolve_venv_dir)"
CONFIG_FILE="$PIXEAGLE_DIR/configs/config.yaml"
DEFAULT_CONFIG_FILE="$PIXEAGLE_DIR/configs/config_default.yaml"
MAVLINK2REST_SCRIPT="$SCRIPTS_DIR/components/mavlink2rest.sh"
DASHBOARD_SCRIPT="$SCRIPTS_DIR/components/dashboard.sh"
MAIN_APP_SCRIPT="$SCRIPTS_DIR/components/main.sh"
RUNTIME_LOG_PIPE_TOOL="$PIXEAGLE_DIR/tools/runtime_log_pipe.py"
RUNTIME_LOG_EXEC_TOOL="$PIXEAGLE_DIR/tools/runtime_log_exec.sh"

# Resolve dashboard port from dashboard/.env (or env_default.yaml fallback).
if declare -f resolve_dashboard_port >/dev/null 2>&1; then
    DASHBOARD_PORT="$(resolve_dashboard_port "$PIXEAGLE_DIR/dashboard" 2>/dev/null || echo "$DASHBOARD_PORT")"
fi

# Binary locations (check bin/ first, then root for backwards compatibility)
if [[ -f "$PIXEAGLE_DIR/bin/mavsdk_server_bin" ]]; then
    MAVSDK_SERVER_BINARY="$PIXEAGLE_DIR/bin/mavsdk_server_bin"
else
    MAVSDK_SERVER_BINARY="$PIXEAGLE_DIR/mavsdk_server_bin"
fi
MAVSDK_SERVER_DOWNLOAD_SCRIPT="$SCRIPTS_DIR/setup/download-binaries.sh"

# Tracking variables
CLEANUP_IN_PROGRESS=false

# ============================================================================
# SIGINT/SIGTERM Handler
# ============================================================================
cleanup_on_interrupt() {
    # Prevent multiple cleanup calls
    if [[ "$CLEANUP_IN_PROGRESS" == "true" ]]; then
        return
    fi
    CLEANUP_IN_PROGRESS=true

    echo ""
    log_warn "Interrupt received"
    echo -en "        Stop the existing manual runtime? [Y/n]: "
    read -r -t 5 REPLY || REPLY="y"
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Stopping services..."
        if bash "$SCRIPTS_DIR/stop.sh" --mode "$PIXEAGLE_RUNTIME_MODE"; then
            log_success "This PixEagle run stopped"
        else
            log_warn "Stop was incomplete; run 'make stop' and review retained processes"
        fi
    else
        log_info "Services left running in background"
        log_detail "Re-attach with: make attach"
    fi

    exit 0
}

trap cleanup_on_interrupt SIGINT SIGTERM

# ============================================================================
# Help Display
# ============================================================================
show_help() {
    display_pixeagle_banner "Help" "Usage information for run.sh"

    echo ""
    echo -e "   ${BOLD}USAGE:${NC}"
    echo -e "      make run               (recommended)"
    echo -e "      bash scripts/run.sh [OPTIONS]"
    echo ""
    echo -e "   ${BOLD}OPTIONS:${NC}"
    echo -e "      ${GREEN}--dev, -d${NC}"
    echo -e "          Development mode with hot-reload and auto-restart"
    echo ""
    echo -e "      ${GREEN}--rebuild, -r${NC}"
    echo -e "          Force rebuild of dashboard before starting (npm build)"
    echo ""
    echo -e "      ${GREEN}--separate, -s${NC}"
    echo -e "          Use separate tmux windows instead of combined grid"
    echo ""
    echo -e "      ${GREEN}--no-attach, -n${NC}"
    echo -e "          Start services without attaching to tmux"
    echo ""
    echo -e "      ${GREEN}--no-dashboard${NC}"
    echo -e "          Do NOT run the React dashboard"
    echo ""
    echo -e "      ${GREEN}-m${NC}  Do NOT run MAVLink2REST"
    echo -e "      ${GREEN}-p${NC}  Do NOT run Main Python Application"
    echo -e "      ${GREEN}-k${NC}  Do NOT run MAVSDK Server"
    echo ""
    echo -e "      ${GREEN}--help, -h${NC}"
    echo -e "          Show this help message"
    echo ""
    echo -e "   ${BOLD}EXAMPLES:${NC}"
    echo -e "      ${DIM}make run${NC}"
    echo -e "          Start normally with combined 4-pane view"
    echo ""
    echo -e "      ${DIM}make dev${NC}"
    echo -e "          Start in development mode with hot-reload"
    echo ""
    echo -e "      ${DIM}bash scripts/run.sh --dev --rebuild${NC}"
    echo -e "          Rebuild dashboard and start in development mode"
    echo ""
    echo -e "      ${DIM}bash scripts/run.sh --no-attach${NC}"
    echo -e "          Start services in background (don't attach to tmux)"
    echo ""
    echo -e "   ${BOLD}TMUX SHORTCUTS:${NC}"
    echo -e "      ${GREEN}Ctrl+B z${NC}       Toggle full-screen on current pane"
    echo -e "      ${GREEN}Ctrl+B arrows${NC}  Navigate between panes"
    echo -e "      ${GREEN}Ctrl+B d${NC}       Detach from session (keeps running)"
    echo -e "      ${DIM}Use 'make stop' to close the supervised runtime${NC}"
    echo ""
    exit 0
}

# ============================================================================
# Banner with Version Info
# ============================================================================
display_startup_banner() {
    display_pixeagle_banner "System Launcher" "Starting all PixEagle components"

    # Version info from git
    local branch commit_short commit_date
    branch=$(git -C "$PIXEAGLE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    commit_short=$(git -C "$PIXEAGLE_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    commit_date=$(git -C "$PIXEAGLE_DIR" log -1 --format="%cr" 2>/dev/null || echo "unknown")

    echo ""
    echo -e "   ${DIM}Branch: ${NC}${CYAN}${branch}${NC}  ${DIM}Commit: ${NC}${commit_short}${DIM} (${commit_date})${NC}"

    if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
        echo -e "   ${YELLOW}${BOLD}Development Mode${NC}${DIM} - Hot-reload enabled${NC}"
    fi
    echo ""
}

# ============================================================================
# Step 1: Pre-flight Checks
# ============================================================================
preflight_checks() {
    log_step 1 "Pre-flight Checks"

    # 1. Virtual environment
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        log_error "Virtual environment not found"
        log_detail "Run: make init (or bash scripts/init.sh)"
        exit 1
    fi
    log_success "Virtual environment found: $VENV_DIR"

    # 2. Configuration file
    if [[ ! -f "$CONFIG_FILE" ]]; then
        if [[ -f "$DEFAULT_CONFIG_FILE" ]]; then
            log_warn "Runtime configuration file not found: $CONFIG_FILE"
            log_detail "Using checked-in defaults from: $DEFAULT_CONFIG_FILE"
            log_detail "Use setup profiles for local overrides: docs/setup/setup-profiles.md"
        else
            log_error "Configuration defaults not found: $DEFAULT_CONFIG_FILE"
            log_detail "Run: make init (or bash scripts/init.sh)"
            exit 1
        fi
    else
        log_success "Configuration file found"
    fi

    # 3. Core Python dependencies (advisory sanity check). Component startup
    # below is authoritative and runs under shared source/venv locks; this
    # probe must not request a nested venv lock from the lifecycle transaction.
    if ! "$VENV_DIR/bin/python" -c "import cv2, numpy" 2>/dev/null; then
        log_warn "Some Python dependencies may be missing"
        log_detail "Run: make init (or bash scripts/init.sh) to reinstall"
    else
        log_success "Core Python dependencies available"
    fi

    # 4. tmux availability
    if ! command -v tmux &>/dev/null; then
        log_error "tmux is not installed"
        log_detail "Install with: sudo apt install tmux"
        exit 1
    fi
    log_success "tmux available"

    # 5. lsof availability (required for ownership-aware port checks)
    if ! command -v lsof &>/dev/null; then
        log_error "lsof is required for ownership-aware port checks"
        log_detail "Install with: sudo apt install lsof"
        exit 1
    fi
    log_success "lsof available"

    # 6. The external lock supervisor owns non-inheritable lifecycle/resource locks.
    if ! _pixeagle_require_lock_supervisor; then
        log_error "Secure lifecycle/resource lock support is unavailable"
        log_detail "Install Python 3 and restore scripts/lib/setup_lock_supervisor.py"
        exit 1
    fi
    log_success "Supervised lifecycle/resource locking available"

    # 7. Check MAVSDK Server if needed
    if [[ "$RUN_MAVSDK_SERVER" == "true" ]]; then
        if [[ ! -f "$MAVSDK_SERVER_BINARY" ]]; then
            log_warn "MAVSDK Server binary not found"
            log_detail "Will attempt to download during startup"
        else
            log_success "MAVSDK Server binary found"
        fi
    fi
}

# ============================================================================
# Step 3: Cleanup Previous Sessions
# ============================================================================
port_listener_pids() {
    local port="$1"
    command -v lsof >/dev/null 2>&1 || return 0
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
}

describe_pid() {
    local pid="$1"
    ps -p "$pid" -o comm= 2>/dev/null || echo "unknown"
}

is_pixeagle_owned_pid() {
    local pid="$1"
    pixeagle_pid_is_owned \
        "$pid" "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$PIXEAGLE_RUN_ID"
}

is_pixeagle_mode_owned_pid() {
    local pid="$1"
    pixeagle_pid_is_owned \
        "$pid" "$PIXEAGLE_DIR" "$(id -u)" "$PIXEAGLE_RUNTIME_MODE"
}

terminate_owned_pid() {
    local pid="$1"
    local expected_run_id="${2:-}"
    local start_token
    start_token="$(pixeagle_pid_start_token "$pid" 2>/dev/null || true)"
    if [[ -z "$start_token" ]]; then
        kill -0 "$pid" 2>/dev/null && return 1
        return 0
    fi
    if ! pixeagle_pid_is_owned \
        "$pid" "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id"; then
        kill -0 "$pid" 2>/dev/null && return 1
        return 0
    fi

    pixeagle_terminate_owned_pid \
        "$pid" "$start_token" "$PIXEAGLE_DIR" "$(id -u)" \
        "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id"
}

cleanup_owned_processes() {
    local expected_run_id="$1"
    local pid cleanup_failed=false

    pixeagle_run_id_is_valid "$expected_run_id" || return 1
    while IFS= read -r pid; do
        [[ -n "$pid" && "$pid" != "$$" && "$pid" != "$PPID" ]] || continue
        terminate_owned_pid "$pid" "$expected_run_id" || cleanup_failed=true
    done < <(pixeagle_owned_pids \
        "$PIXEAGLE_DIR" "$(id -u)" "$PIXEAGLE_RUNTIME_MODE" "$expected_run_id")
    [[ "$cleanup_failed" != "true" ]]
}

check_and_kill_port() {
    local port="$1"
    local service_name="${2:-Service}"
    local cleanup_run_id="${3:-}"

    local pids
    pids=$(port_listener_pids "$port")

    if [[ -n "$pids" ]]; then
        local pid process_name blocked=false

        for pid in $pids; do
            process_name=$(describe_pid "$pid")

            if [[ -n "$cleanup_run_id" ]] && pixeagle_pid_is_owned \
                "$pid" "$PIXEAGLE_DIR" "$(id -u)" \
                "$PIXEAGLE_RUNTIME_MODE" "$cleanup_run_id"; then
                if terminate_owned_pid "$pid" "$cleanup_run_id"; then
                    log_success "Killed exact prior-run $process_name on port $port ($service_name)"
                else
                    log_warn "Could not kill exact prior-run process on port $port"
                    blocked=true
                fi
                continue
            fi

            if is_pixeagle_mode_owned_pid "$pid"; then
                log_error "Port $port is held by a marked PixEagle process outside the exact prior run ($process_name, pid $pid)"
                log_detail "Stop and verify the orphaned $PIXEAGLE_RUNTIME_MODE runtime before launching a replacement"
                blocked=true
                continue
            else
                log_error "Port $port is already in use by a non-PixEagle process ($process_name, pid $pid)"
                log_detail "Stop that process or change the configured $service_name port before running PixEagle"
                blocked=true
                continue
            fi
        done

        [[ "$blocked" != "true" ]]
    else
        log_success "Port $port already free ($service_name)"
    fi
}

cleanup_previous_sessions() {
    log_step 3 "Cleaning Up Previous Runtime"
    local previous_run_id="" orphan_pids=""
    local -a orphan_pid_list=()

    if pixeagle_tmux_session_exists "$TMUX_SOCKET_NAME" "$SESSION_NAME"; then
        if ! pixeagle_tmux_session_is_owned \
            "$TMUX_SOCKET_NAME" "$SESSION_NAME" "$PIXEAGLE_DIR" \
            "$PIXEAGLE_RUNTIME_MODE"; then
            log_error "Tmux session '$SESSION_NAME' exists but is not owned by this PixEagle checkout"
            log_detail "Rename or stop it explicitly after verifying its owner; launcher cleanup refused it."
            exit 1
        fi
        previous_run_id="$(pixeagle_tmux_environment_value \
            "$TMUX_SOCKET_NAME" "$SESSION_NAME" PIXEAGLE_RUN_ID 2>/dev/null || true)"
        if [[ -z "$previous_run_id" ]] || \
           ! pixeagle_tmux_session_is_owned \
                "$TMUX_SOCKET_NAME" "$SESSION_NAME" "$PIXEAGLE_DIR" \
                "$PIXEAGLE_RUNTIME_MODE" "$previous_run_id"; then
            log_error "Existing tmux session has no valid exact run identity"
            log_detail "Refusing to replace an incomplete supervision contract."
            exit 1
        fi
        if [[ "$previous_run_id" == "$PIXEAGLE_RUN_ID" ]]; then
            log_error "Replacement runtime must use a fresh exact run identity"
            log_detail "Unset PIXEAGLE_RUN_ID or provide a new collision-resistant ID."
            exit 1
        fi
        tmux_runtime list-panes -t "=$SESSION_NAME" -F "#{session_name}:#{window_index}.#{pane_index}" 2>/dev/null | \
        while read -r pane; do
            tmux_runtime send-keys -t "$pane" C-c 2>/dev/null || true
        done
        sleep 1

        tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null
        log_success "Terminated existing tmux session"
    else
        log_success "No existing tmux session"
        mapfile -t orphan_pid_list < <(pixeagle_owned_pids \
            "$PIXEAGLE_DIR" "$(id -u)" "$PIXEAGLE_RUNTIME_MODE")
        if (( ${#orphan_pid_list[@]} > 0 )); then
            local IFS=,
            orphan_pids="${orphan_pid_list[*]}"
        fi
        if [[ -n "$orphan_pids" ]]; then
            log_error "Marked $PIXEAGLE_RUNTIME_MODE processes exist without an exact tmux run: $orphan_pids"
            log_detail "Launcher cleanup refused a mode-wide signal operation."
            exit 1
        fi
    fi

    if [[ -n "$previous_run_id" ]]; then
        cleanup_owned_processes "$previous_run_id" || {
            log_error "Could not stop all exact prior-run processes from the previous $PIXEAGLE_RUNTIME_MODE runtime"
            exit 1
        }
    fi

    # Clean up marked listeners; unrelated or differently supervised listeners
    # block startup rather than being signalled.
    local blocked_ports=false
    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        check_and_kill_port "$MAVLINK2REST_PORT" "MAVLink2REST" "$previous_run_id" || blocked_ports=true
    fi

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        check_and_kill_port "$BACKEND_PORT" "Backend" "$previous_run_id" || blocked_ports=true
        check_and_kill_port "$WEBSOCKET_PORT" "Legacy telemetry WebSocket" "$previous_run_id" || blocked_ports=true
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        check_and_kill_port "$DASHBOARD_PORT" "Dashboard" "$previous_run_id" || blocked_ports=true
    fi

    if [[ "$RUN_MAVSDK_SERVER" == "true" ]]; then
        check_and_kill_port "$MAVSDK_SERVER_PORT" "MAVSDK Server" "$previous_run_id" || blocked_ports=true
    fi

    if [[ "$blocked_ports" == "true" ]]; then
        log_error "Startup blocked by non-PixEagle process on a required port"
        exit 1
    fi
}

# ============================================================================
# Step 2: Load Configuration
# ============================================================================
load_configuration() {
    log_step 2 "Loading Configuration"

    # Read ports from config.yaml (with defaults)
    BACKEND_PORT=$(get_config_value "Streaming" "HTTP_STREAM_PORT" "$BACKEND_PORT")
    BACKEND_HOST=$(get_config_value "Streaming" "HTTP_STREAM_HOST" "$BACKEND_HOST")
    API_EXPOSURE_MODE=$(get_config_value "Streaming" "API_EXPOSURE_MODE" "$API_EXPOSURE_MODE")
    API_AUTH_MODE=$(get_config_value "Streaming" "API_AUTH_MODE" "$API_AUTH_MODE")
    WEBSOCKET_PORT=$(get_config_value "Telemetry" "WEBSOCK_PORT" "$WEBSOCKET_PORT")
    EXTERNAL_MAVSDK_SERVER=$(get_config_value "PX4" "EXTERNAL_MAVSDK_SERVER" "$EXTERNAL_MAVSDK_SERVER")
    MAVSDK_SERVER_ADDRESS=$(get_config_value "PX4" "MAVSDK_SERVER_ADDRESS" "$MAVSDK_SERVER_ADDRESS")
    MAVSDK_SERVER_PORT=$(get_config_value "PX4" "MAVSDK_SERVER_PORT" "$MAVSDK_SERVER_PORT")
    PX4_SYSTEM_ADDRESS=$(get_config_value "PX4" "SYSTEM_ADDRESS" "$PX4_SYSTEM_ADDRESS")
    if ! is_valid_port "$BACKEND_PORT"; then
        log_error "Streaming.HTTP_STREAM_PORT must be an integer from 1 to 65535"
        exit 1
    fi
    if ! is_valid_port "$WEBSOCKET_PORT"; then
        log_error "Telemetry.WEBSOCK_PORT must be an integer from 1 to 65535"
        exit 1
    fi
    if ! is_valid_port "$MAVSDK_SERVER_PORT"; then
        log_error "PX4.MAVSDK_SERVER_PORT must be an integer from 1 to 65535"
        exit 1
    fi
    if [[ "$EXTERNAL_MAVSDK_SERVER" != "true" ]]; then
        RUN_MAVSDK_SERVER=false
    elif ! is_loopback_host "$MAVSDK_SERVER_ADDRESS"; then
        RUN_MAVSDK_SERVER=false
        log_info "Using remote MAVSDK server at ${MAVSDK_SERVER_ADDRESS}:${MAVSDK_SERVER_PORT}"
    fi
    if [[ "$API_EXPOSURE_MODE" == "local_only" ]] && ! is_loopback_host "$BACKEND_HOST"; then
        log_warn "Legacy/non-loopback backend bind '$BACKEND_HOST' is displayed as 127.0.0.1 under local_only"
        BACKEND_HOST="127.0.0.1"
    fi
    if [[ -z "${PIXEAGLE_DASHBOARD_HOST:-}" ]] && [[ "$API_EXPOSURE_MODE" == "trusted_lan_legacy" ]] && [[ "$API_AUTH_MODE" == "browser_session" ]] && ! is_loopback_host "$BACKEND_HOST"; then
        DASHBOARD_HOST="0.0.0.0"
        DASHBOARD_EXPOSURE_MODE="trusted_lan_legacy"
    fi
    if declare -f resolve_dashboard_port >/dev/null 2>&1; then
        DASHBOARD_PORT="$(resolve_dashboard_port "$PIXEAGLE_DIR/dashboard" 2>/dev/null || echo "$DASHBOARD_PORT")"
    fi

    # Display configured local-first service URLs.
    log_info "MAVLink2REST: http://localhost:${MAVLINK2REST_PORT} (local-only by default)"
    log_info "Backend API:  http://${BACKEND_HOST}:${BACKEND_PORT} (${API_EXPOSURE_MODE})"
    log_info "Dashboard:    http://${DASHBOARD_HOST}:${DASHBOARD_PORT}"
    if [[ "$DASHBOARD_PORT" != "3040" ]]; then
        log_warn "Custom dashboard port requires matching Streaming.API_CORS_ALLOWED_ORIGINS entries"
    fi
    if [[ "$API_EXPOSURE_MODE" == "trusted_lan_legacy" ]]; then
        log_warn "trusted_lan_legacy backend exposure requires scoped API auth for non-loopback clients"
    fi
    if [[ "$DASHBOARD_EXPOSURE_MODE" == "trusted_lan_legacy" ]]; then
        log_warn "Dashboard static server is reachable on the LAN; backend actions still require browser-session auth"
    elif [[ "$API_EXPOSURE_MODE" == "trusted_lan_legacy" ]] && [[ "$API_AUTH_MODE" == "browser_session" ]] && is_loopback_host "$BACKEND_HOST"; then
        log_detail "Dashboard remains loopback for reverse-proxy/tunnel browser-session profiles"
    fi

    # Check component scripts exist
    if [[ "$RUN_MAIN_APP" == "true" ]] && [[ ! -f "$MAIN_APP_SCRIPT" ]]; then
        log_error "Main app script not found: $MAIN_APP_SCRIPT"
        exit 1
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]] && [[ ! -f "$DASHBOARD_SCRIPT" ]]; then
        log_error "Dashboard script not found: $DASHBOARD_SCRIPT"
        exit 1
    fi

    if [[ "$RUN_MAVLINK2REST" == "true" ]] && [[ ! -f "$MAVLINK2REST_SCRIPT" ]]; then
        log_error "MAVLink2REST script not found: $MAVLINK2REST_SCRIPT"
        exit 1
    fi
}

# ============================================================================
# Step 4: Start Services
# ============================================================================
prepare_mavsdk_server() {
    if [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
        return 0
    fi

    log_warn "MAVSDK Server binary not found"
    log_detail "Location: $MAVSDK_SERVER_BINARY"
    echo ""
    echo -en "        Download now? [Y/n]: "
    read -r REPLY
    echo ""

    if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ -f "$MAVSDK_SERVER_DOWNLOAD_SCRIPT" ]]; then
            log_info "Running download script..."
            if bash "$MAVSDK_SERVER_DOWNLOAD_SCRIPT" --mavsdk; then
                # Update binary path after download
                if [[ -f "$PIXEAGLE_DIR/bin/mavsdk_server_bin" ]]; then
                    MAVSDK_SERVER_BINARY="$PIXEAGLE_DIR/bin/mavsdk_server_bin"
                fi
                log_success "MAVSDK Server installed"
                return 0
            else
                log_error "MAVSDK Server download failed"
                log_detail "Try manually: bash scripts/setup/download-binaries.sh --mavsdk"
                return 1
            fi
        else
            log_error "Download script not found: $MAVSDK_SERVER_DOWNLOAD_SCRIPT"
            log_detail "Manual download: https://github.com/mavlink/MAVSDK/releases/"
            return 1
        fi
    else
        log_warn "MAVSDK Server download skipped"
        log_detail "MAVSDK Server will not be started"
        return 1
    fi
}

prepare_runtime_component_logs() {
    if [[ ! -f "$RUNTIME_LOG_PIPE_TOOL" ]] || [[ ! -x "$VENV_DIR/bin/python" ]]; then
        return 0
    fi

    local -a runtime_log_components=("backend" "$@")
    # Startup already owns the lifecycle lock, and the preparation helper uses
    # only the Python standard library. Avoid a nested venv-lock acquisition;
    # component processes acquire normal shared source/venv locks below.
    if env PIXEAGLE_RUN_ID="$PIXEAGLE_RUN_ID" \
       PIXEAGLE_RUNTIME_LOG_DIR="$PIXEAGLE_RUNTIME_LOG_DIR" \
       PYTHONDONTWRITEBYTECODE=1 \
       PYTHONPATH="$PIXEAGLE_DIR/src" \
       python3 "$RUNTIME_LOG_PIPE_TOOL" \
       --prepare-components "${runtime_log_components[@]}" 2>/dev/null; then
        log_detail "Runtime component logs prepared: ${runtime_log_components[*]}"
    else
        log_warn "Runtime component log preparation failed; continuing with tmux output only"
    fi
}

component_wrapped_command() {
    local component="$1"
    local command="$2"
    local component_arg command_arg exec_tool_arg python_arg run_id_arg runtime_log_dir_arg
    local lock_supervisor_arg source_resource_arg venv_resource_arg lock_operation_arg

    printf -v component_arg "%q" "$component"
    printf -v command_arg "%q" "$command"
    printf -v exec_tool_arg "%q" "$RUNTIME_LOG_EXEC_TOOL"
    printf -v python_arg "%q" "$VENV_DIR/bin/python"
    printf -v run_id_arg "%q" "$PIXEAGLE_RUN_ID"
    printf -v runtime_log_dir_arg "%q" "$PIXEAGLE_RUNTIME_LOG_DIR"
    printf -v lock_supervisor_arg "%q" "$PIXEAGLE_SETUP_LOCK_SUPERVISOR"
    printf -v source_resource_arg "%q" "$PIXEAGLE_PROJECT_ROOT"
    printf -v venv_resource_arg "%q" "$VENV_DIR"
    printf -v lock_operation_arg "%q" "runtime-$component"

    # Clear every systemd-owned runtime channel in the pane shell before exec.
    # The indirect expansion covers current and future WATCHDOG_* variables.
    echo "unset NOTIFY_SOCKET; unset \"\${!WATCHDOG_@}\"; exec env PIXEAGLE_RUN_ID=$run_id_arg PIXEAGLE_RUNTIME_LOG_DIR=$runtime_log_dir_arg PIXEAGLE_PROJECT_ROOT=$(printf '%q' "$PIXEAGLE_PROJECT_ROOT") PIXEAGLE_SESSION_NAME=$(printf '%q' "$SESSION_NAME") PIXEAGLE_RUNTIME_MODE=$(printf '%q' "$PIXEAGLE_RUNTIME_MODE") PIXEAGLE_TMUX_SOCKET_NAME=$(printf '%q' "$TMUX_SOCKET_NAME") PIXEAGLE_RUNTIME_LOG_PIPE_PYTHON=$python_arg python3 $lock_supervisor_arg run --mode shared --resource-path $source_resource_arg --resource-path $venv_resource_arg --operation $lock_operation_arg --timeout 30 --descendant-policy terminate -- bash $exec_tool_arg $component_arg -- bash -lc $command_arg"
}

strip_tmux_systemd_runtime_channels() {
    local marker key
    local -a keys=(NOTIFY_SOCKET)

    while IFS= read -r marker; do
        [[ "$marker" == *=* ]] || continue
        key="${marker%%=*}"
        case "$key" in
            WATCHDOG_*) keys+=("$key") ;;
        esac
    done < <(
        tmux_runtime show-environment -g 2>/dev/null || true
        tmux_runtime show-environment -t "=$SESSION_NAME" 2>/dev/null || true
    )

    for key in "${keys[@]}"; do
        tmux_runtime set-environment -g -u "$key" || return 1
        tmux_runtime set-environment -t "=$SESSION_NAME" -u "$key" || return 1
    done
}

start_services() {
    log_step 4 "Starting Services"

    # Prepare MAVSDK Server if needed
    if [[ "$RUN_MAVSDK_SERVER" == "true" ]]; then
        if ! prepare_mavsdk_server; then
            log_error "MAVSDK Server is enabled but could not be prepared"
            log_detail "Install it first, or explicitly launch with -k when another server is managed separately"
            return 1
        fi
    fi

    # Create new tmux session
    if ! tmux_runtime new-session -d -s "$SESSION_NAME"; then
        log_error "Could not create tmux session '$SESSION_NAME'"
        return 1
    fi
    if ! strip_tmux_systemd_runtime_channels ||
       ! tmux_runtime set-environment -t "=$SESSION_NAME" PIXEAGLE_PROJECT_ROOT "$PIXEAGLE_PROJECT_ROOT" ||
       ! tmux_runtime set-environment -t "=$SESSION_NAME" PIXEAGLE_RUN_ID "$PIXEAGLE_RUN_ID" ||
       ! tmux_runtime set-environment -t "=$SESSION_NAME" PIXEAGLE_RUNTIME_MODE "$PIXEAGLE_RUNTIME_MODE" ||
       ! tmux_runtime set-environment -t "=$SESSION_NAME" PIXEAGLE_READY "0" ||
       ! tmux_runtime set-window-option -t "=$SESSION_NAME:0" remain-on-exit on >/dev/null; then
        tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null || true
        log_error "Could not publish the tmux ownership/supervision contract"
        return 1
    fi

    # Build component array
    declare -A components
    declare -A component_log_names
    local component_count=0
    local run_id_arg runtime_log_dir_arg runtime_env_prefix
    printf -v run_id_arg "%q" "$PIXEAGLE_RUN_ID"
    printf -v runtime_log_dir_arg "%q" "$PIXEAGLE_RUNTIME_LOG_DIR"
    local project_root_arg session_name_arg runtime_mode_arg tmux_socket_arg
    printf -v project_root_arg "%q" "$PIXEAGLE_PROJECT_ROOT"
    printf -v session_name_arg "%q" "$SESSION_NAME"
    printf -v runtime_mode_arg "%q" "$PIXEAGLE_RUNTIME_MODE"
    printf -v tmux_socket_arg "%q" "$TMUX_SOCKET_NAME"
    runtime_env_prefix="PIXEAGLE_RUN_ID=$run_id_arg PIXEAGLE_RUNTIME_LOG_DIR=$runtime_log_dir_arg PIXEAGLE_PROJECT_ROOT=$project_root_arg PIXEAGLE_SESSION_NAME=$session_name_arg PIXEAGLE_RUNTIME_MODE=$runtime_mode_arg PIXEAGLE_TMUX_SOCKET_NAME=$tmux_socket_arg"

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        local python_arg main_script_arg
        printf -v python_arg "%q" "$VENV_DIR/bin/python"
        printf -v main_script_arg "%q" "$MAIN_APP_SCRIPT"
        local main_cmd="$runtime_env_prefix bash $main_script_arg $python_arg"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            main_cmd="$runtime_env_prefix bash $main_script_arg --dev $python_arg"
        fi
        components["MainApp"]="$main_cmd"
        component_log_names["MainApp"]="main_app"
        ((component_count++))
        printf "\r        ${DIM}-> Starting Main App... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        local mavlink2rest_script_arg
        printf -v mavlink2rest_script_arg "%q" "$MAVLINK2REST_SCRIPT"
        components["MAVLink2REST"]="$runtime_env_prefix bash $mavlink2rest_script_arg"
        component_log_names["MAVLink2REST"]="mavlink2rest"
        ((component_count++))
        printf "\r        ${DIM}-> Starting MAVLink2REST... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        # Ensure nvm is loaded in the tmux pane (needed if node installed via nvm)
        # shellcheck disable=SC2016  # Expand HOME/NVM_DIR inside the tmux pane.
        local nvm_setup='export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh";'
        local dashboard_host_arg dashboard_exposure_arg dashboard_script_arg
        printf -v dashboard_host_arg "%q" "$DASHBOARD_HOST"
        printf -v dashboard_exposure_arg "%q" "$DASHBOARD_EXPOSURE_MODE"
        printf -v dashboard_script_arg "%q" "$DASHBOARD_SCRIPT"
        local dashboard_cmd="$runtime_env_prefix PIXEAGLE_DASHBOARD_HOST=$dashboard_host_arg PIXEAGLE_DASHBOARD_EXPOSURE_MODE=$dashboard_exposure_arg bash $dashboard_script_arg"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -d"
        fi
        if [[ "$FORCE_REBUILD" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -f"
        fi
        dashboard_cmd="$dashboard_cmd $DASHBOARD_PORT"
        components["Dashboard"]="${nvm_setup} ${dashboard_cmd}"
        component_log_names["Dashboard"]="dashboard"
        ((component_count++))
        printf "\r        ${DIM}-> Starting Dashboard... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_MAVSDK_SERVER" == "true" ]] && [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
        local quoted_mavsdk_binary quoted_mavsdk_link
        printf -v quoted_mavsdk_binary '%q' "$MAVSDK_SERVER_BINARY"
        printf -v quoted_mavsdk_link '%q' "$PX4_SYSTEM_ADDRESS"
        components["MAVSDKServer"]="cd $project_root_arg; $runtime_env_prefix $quoted_mavsdk_binary -p $MAVSDK_SERVER_PORT $quoted_mavsdk_link"
        component_log_names["MAVSDKServer"]="mavsdk_server"
        ((component_count++))
        printf "\r        ${DIM}-> Starting MAVSDK Server... (%d/4)${NC}" $component_count
    fi

    echo ""

    if [[ "$component_count" -eq 0 ]]; then
        tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null || true
        log_error "No runtime components were selected"
        return 1
    fi

    local expected_components
    expected_components="$(printf '%s\n' "${!components[@]}" | LC_ALL=C sort | paste -sd, -)"
    if ! tmux_runtime set-environment -t "=$SESSION_NAME" \
        PIXEAGLE_EXPECTED_COMPONENTS "$expected_components"; then
        tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null || true
        log_error "Could not publish expected component identities"
        return 1
    fi

    local runtime_components=()
    local runtime_component_name
    for runtime_component_name in "${component_log_names[@]}"; do
        runtime_components+=("$runtime_component_name")
    done
    prepare_runtime_component_logs "${runtime_components[@]}"

    # Create tmux layout
    if [[ "$COMBINED_VIEW" == "true" ]]; then
        # Combined view with split panes
        tmux_runtime rename-window -t "$SESSION_NAME:0" "CombinedView"
        local pane_index=0

        for component_name in "${!components[@]}"; do
            if [[ $pane_index -eq 0 ]]; then
                tmux_runtime send-keys -t "$SESSION_NAME:CombinedView.$pane_index" \
                    "clear; $(component_wrapped_command "${component_log_names[$component_name]}" "${components[$component_name]}")" C-m
                tmux_runtime select-pane -t "$SESSION_NAME:CombinedView.$pane_index" -T "$component_name"
                tmux_runtime set-option -p -t "$SESSION_NAME:CombinedView.$pane_index" @pixeagle_component "$component_name"
            else
                tmux_runtime split-window -t "$SESSION_NAME:CombinedView" -h
                tmux_runtime select-pane -t "$SESSION_NAME:CombinedView.$pane_index"
                tmux_runtime send-keys -t "$SESSION_NAME:CombinedView.$pane_index" \
                    "clear; $(component_wrapped_command "${component_log_names[$component_name]}" "${components[$component_name]}")" C-m
                tmux_runtime select-pane -t "$SESSION_NAME:CombinedView.$pane_index" -T "$component_name"
                tmux_runtime set-option -p -t "$SESSION_NAME:CombinedView.$pane_index" @pixeagle_component "$component_name"
            fi
            ((pane_index++))
        done

        if [[ $pane_index -gt 1 ]]; then
            tmux_runtime select-layout -t "$SESSION_NAME:CombinedView" tiled
        fi
    else
        # Separate windows
        local window_index=0
        for component_name in "${!components[@]}"; do
            if [[ $window_index -eq 0 ]]; then
                tmux_runtime rename-window -t "$SESSION_NAME:0" "$component_name"
                tmux_runtime send-keys -t "$SESSION_NAME:$component_name" \
                    "clear; $(component_wrapped_command "${component_log_names[$component_name]}" "${components[$component_name]}")" C-m
                tmux_runtime select-pane -t "$SESSION_NAME:$component_name" -T "$component_name"
                tmux_runtime set-option -p -t "$SESSION_NAME:$component_name" @pixeagle_component "$component_name"
            else
                tmux_runtime new-window -t "$SESSION_NAME" -n "$component_name"
                tmux_runtime send-keys -t "$SESSION_NAME:$component_name" \
                    "clear; $(component_wrapped_command "${component_log_names[$component_name]}" "${components[$component_name]}")" C-m
                tmux_runtime select-pane -t "$SESSION_NAME:$component_name" -T "$component_name"
                tmux_runtime set-option -p -t "$SESSION_NAME:$component_name" @pixeagle_component "$component_name"
            fi
            ((window_index++))
        done
    fi

    log_success "All services started ($component_count components)"
}

# ============================================================================
# Step 5: Wait for Services
# ============================================================================
check_port_ready() {
    local port=$1
    if command -v nc >/dev/null 2>&1; then
        nc -z localhost "$port" 2>/dev/null || return 1
    else
        python3 - "$port" <<'PYEOF' >/dev/null 2>&1 || return 1
import socket
import sys

port = int(sys.argv[1])
with socket.create_connection(("127.0.0.1", port), timeout=0.5):
    pass
PYEOF
    fi

    local pids pid found=false
    pids="$(port_listener_pids "$port")"
    [[ -n "$pids" ]] || return 1
    for pid in $pids; do
        is_pixeagle_owned_pid "$pid" || return 1
        found=true
    done
    [[ "$found" == "true" ]]
}

tmux_has_dead_component() {
    tmux_runtime list-panes -t "=$SESSION_NAME" -s -F '#{pane_dead}' 2>/dev/null |
        grep -qx '1'
}

positive_integer_or_default() {
    local value="$1"
    local default="$2"

    if [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
        echo "$value"
    else
        echo "$default"
    fi
}

service_ready_retries() {
    local name="$1"

    case "$name" in
        Dashboard)
            positive_integer_or_default "${PIXEAGLE_DASHBOARD_READY_RETRIES:-120}" 120
            ;;
        Backend)
            positive_integer_or_default "${PIXEAGLE_BACKEND_READY_RETRIES:-30}" 30
            ;;
        MAVLink2REST)
            positive_integer_or_default "${PIXEAGLE_MAVLINK2REST_READY_RETRIES:-30}" 30
            ;;
        *)
            positive_integer_or_default "${PIXEAGLE_SERVICE_READY_RETRIES:-15}" 15
            ;;
    esac
}

wait_for_services() {
    log_step 5 "Waiting for Services"

    local services=()

    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        services+=("MAVLink2REST:$MAVLINK2REST_PORT")
    fi

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        services+=("Backend:$BACKEND_PORT")
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        services+=("Dashboard:$DASHBOARD_PORT")
    fi

    if [[ "$RUN_MAVSDK_SERVER" == "true" ]] && [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
        services+=("MAVSDKServer:$MAVSDK_SERVER_PORT")
    fi

    local failed=false

    for service_info in "${services[@]}"; do
        local name="${service_info%%:*}"
        local port="${service_info##*:}"
        local retries
        retries="$(service_ready_retries "$name")"
        local ready=false

        printf '        %b-> Waiting for %s (port %s)...%b' \
            "$DIM" "$name" "$port" "$NC"

        for ((i=1; i<=retries; i++)); do
            if tmux_has_dead_component; then
                break
            fi
            if check_port_ready "$port"; then
                ready=true
                break
            fi
            sleep 1
        done

        if $ready; then
            printf '\r        %b%s%b %s ready (port %s)                    \n' \
                "$GREEN" "$CHECK" "$NC" "$name" "$port"
        else
            printf '\r        %b%s%b %s failed readiness (port %s)         \n' \
                "$RED" "$CROSS" "$NC" "$name" "$port"
            failed=true
        fi
    done

    [[ "$failed" != "true" ]]
}

cleanup_failed_startup() {
    log_error "Startup readiness failed; stopping only this checkout's marked runtime"
    if pixeagle_tmux_session_is_owned \
       "$TMUX_SOCKET_NAME" "$SESSION_NAME" "$PIXEAGLE_DIR" \
       "$PIXEAGLE_RUNTIME_MODE" "$PIXEAGLE_RUN_ID"; then
        tmux_runtime kill-session -t "=$SESSION_NAME" 2>/dev/null || true
    fi
    cleanup_owned_processes "$PIXEAGLE_RUN_ID" || true
}

# ============================================================================
# Step 6: Launch Tmux Interface
# ============================================================================
launch_tmux_interface() {
    log_step 6 "Launching Tmux Interface"

    log_success "Tmux session '$SESSION_NAME' created"

    if [[ "$NO_ATTACH" == "true" ]]; then
        log_info "Running in background (--no-attach)"
        log_detail "Attach with: make attach"
    else
        log_info "Attaching to combined view..."
    fi
}

# ============================================================================
# Final Summary
# ============================================================================
show_final_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                          ${PARTY} ${BOLD}PixEagle Running!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${BOLD}Configured Service URLs:${NC}"
    echo -e "      Dashboard:     ${CYAN}http://${DASHBOARD_HOST}:${DASHBOARD_PORT}${NC}"
    echo -e "      Backend API:   ${CYAN}http://${BACKEND_HOST}:${BACKEND_PORT}${NC} ${DIM}(${API_EXPOSURE_MODE})${NC}"
    echo -e "      MAVLink2REST:  ${CYAN}http://localhost:${MAVLINK2REST_PORT}${NC} ${DIM}(local-only default)${NC}"
    echo -e "      Runtime logs:  ${CYAN}${PIXEAGLE_RUNTIME_LOG_DIR}/${PIXEAGLE_RUN_ID}${NC}"
    echo ""
    echo -e "   ${BOLD}Tmux Keyboard Shortcuts:${NC}"
    echo -e "      ${GREEN}Ctrl+B z${NC}       Toggle full-screen on current pane"
    echo -e "      ${GREEN}Ctrl+B arrows${NC}  Navigate between panes"
    echo -e "      ${GREEN}Ctrl+B d${NC}       Detach from session (keeps running)"
    echo ""
    echo -e "   ${BOLD}Management Commands:${NC}"
    echo -e "      ${DIM}make attach${NC}                       Re-attach to session"
    echo -e "      ${DIM}make stop${NC}                         Stop the manual runtime"
    echo -e "      ${DIM}bash scripts/run.sh --help${NC}        Show all options"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Argument Parsing
# ============================================================================
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev|-d)
                DEVELOPMENT_MODE=true
                shift
                ;;
            --rebuild|-r)
                FORCE_REBUILD=true
                shift
                ;;
            -m)
                RUN_MAVLINK2REST=false
                shift
                ;;
            -p)
                RUN_MAIN_APP=false
                shift
                ;;
            -k)
                RUN_MAVSDK_SERVER=false
                shift
                ;;
            --separate|-s)
                COMBINED_VIEW=false
                shift
                ;;
            --no-attach|-n)
                NO_ATTACH=true
                shift
                ;;
            --no-dashboard)
                RUN_DASHBOARD=false
                shift
                ;;
            -h|--help)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                echo ""
                echo "Use --help to see available options"
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# Main Execution
# ============================================================================
main_startup() {
    # Change to PixEagle directory
    cd "$PIXEAGLE_DIR" || exit 1

    # Parse command line arguments
    parse_arguments "$@"

    # Display banner
    display_startup_banner

    # Execute startup sequence
    preflight_checks
    load_configuration
    cleanup_previous_sessions
    start_services || exit 1
    if ! wait_for_services; then
        cleanup_failed_startup
        exit 1
    fi
    if ! tmux_runtime set-environment -t "=$SESSION_NAME" PIXEAGLE_READY "1"; then
        log_error "Could not publish runtime readiness"
        cleanup_failed_startup
        exit 1
    fi
    launch_tmux_interface

    # Show summary
    show_final_summary
}

launch_runtime() {
    # Parse once in the caller so help/invalid options do not enter a lock
    # transaction and so attachment happens only after startup serialization.
    parse_arguments "$@"

    if ! pixeagle_run_with_resource_lock_preserving_descendants \
        exclusive "$LIFECYCLE_RESOURCE" \
        "start $PIXEAGLE_RUNTIME_MODE runtime" 30 \
        bash "$SCRIPTS_DIR/run.sh" --internal-lifecycle-start "$@"; then
        log_error "Runtime startup transaction failed"
        return 1
    fi

    # Attachment is deliberately outside the transaction so another shell can
    # stop or update the verified runtime while this terminal is attached.
    if [[ "$NO_ATTACH" != "true" ]]; then
        tmux_runtime attach-session -t "=$SESSION_NAME"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    if [[ "${1:-}" == "--internal-lifecycle-start" ]]; then
        shift
        if ! pixeagle_validate_resource_lock_context \
            exclusive "$LIFECYCLE_RESOURCE"; then
            log_error "Runtime startup is outside the supervised lifecycle transaction"
            exit 73
        fi
        main_startup "$@"
    else
        launch_runtime "$@"
    fi
fi
