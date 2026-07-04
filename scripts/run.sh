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
# CRLF Line Ending Fix (Windows compatibility)
# ============================================================================
fix_line_endings() {
    local file="$1"
    if [[ -f "$file" ]] && grep -q $'\r' "$file" 2>/dev/null; then
        if command -v sed &>/dev/null; then
            sed -i.bak 's/\r$//' "$file" 2>/dev/null && rm -f "${file}.bak" 2>/dev/null
        elif command -v tr &>/dev/null; then
            tr -d '\r' < "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
        fi
    fi
}

# ============================================================================
# Configuration
# ============================================================================
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
TOTAL_STEPS=6

# Fix line endings before sourcing
fix_line_endings "$SCRIPTS_DIR/lib/common.sh"
fix_line_endings "$SCRIPTS_DIR/lib/ports.sh"

# Source shared functions (colors, logging, banner)
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    echo "Warning: Could not source common.sh"
fi

# Source shared port helpers (optional fallback below).
if ! source "$SCRIPTS_DIR/lib/ports.sh" 2>/dev/null; then
    echo "Warning: Could not source ports.sh"
fi

# Fallback definitions if common.sh failed
if ! declare -f log_info &>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    CHECK="✓"; CROSS="✗"; WARN="!"; INFO="i"
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

# Tmux session name
SESSION_NAME="pixeagle"

# Default ports (resolved from shared defaults + config when available)
MAVLINK2REST_PORT="${PIXEAGLE_DEFAULT_MAVLINK2REST_PORT:-8088}"
BACKEND_PORT="${PIXEAGLE_DEFAULT_BACKEND_PORT:-5077}"
DASHBOARD_PORT="${PIXEAGLE_DEFAULT_DASHBOARD_PORT:-3040}"
WEBSOCKET_PORT="${PIXEAGLE_DEFAULT_WEBSOCKET_PORT:-5551}"
BACKEND_HOST="127.0.0.1"
API_EXPOSURE_MODE="local_only"
API_AUTH_MODE="local_compat"
DASHBOARD_HOST="${PIXEAGLE_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_EXPOSURE_MODE="${PIXEAGLE_DASHBOARD_EXPOSURE_MODE:-local_only}"
PIXEAGLE_RUN_ID="${PIXEAGLE_RUN_ID:-pixeagle_$(date -u '+%Y%m%dT%H%M%SZ')_$$}"
PIXEAGLE_RUNTIME_LOG_DIR="${PIXEAGLE_RUNTIME_LOG_DIR:-$PIXEAGLE_DIR/logs/runtime}"
export PIXEAGLE_RUN_ID PIXEAGLE_RUNTIME_LOG_DIR

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

    if [[ -f "$source_config" ]] && command -v python3 &>/dev/null; then
        python3 -c "
import yaml
try:
    with open('$source_config', 'r') as f:
        config = yaml.safe_load(f)
    print(config.get('$section', {}).get('$key', '$default'))
except:
    print('$default')
" 2>/dev/null || echo "$default"
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
    if [[ -x "$PIXEAGLE_DIR/.venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/.venv"
    elif [[ -x "$PIXEAGLE_DIR/venv/bin/python" ]]; then
        echo "$PIXEAGLE_DIR/venv"
    else
        echo "$PIXEAGLE_DIR/venv"
    fi
}

# Paths to component scripts
VENV_DIR="$(resolve_venv_dir)"
CONFIG_FILE="$PIXEAGLE_DIR/configs/config.yaml"
DEFAULT_CONFIG_FILE="$PIXEAGLE_DIR/configs/config_default.yaml"
MAVLINK2REST_SCRIPT="$SCRIPTS_DIR/components/mavlink2rest.sh"
DASHBOARD_SCRIPT="$SCRIPTS_DIR/components/dashboard.sh"
MAIN_APP_SCRIPT="$SCRIPTS_DIR/components/main.sh"

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
    echo -en "        Stop all services? [Y/n]: "
    read -r -t 5 REPLY || REPLY="y"
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Stopping services..."
        tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
        cleanup_ports_silent
        log_success "All services stopped"
    else
        log_info "Services left running in background"
        log_detail "Re-attach with: tmux attach -t $SESSION_NAME"
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
    echo -e "      ${GREEN}Ctrl+B x${NC}       Close current pane"
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

    # 3. Core Python dependencies (quick sanity check)
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

    # 5. lsof availability (needed for port checking)
    if ! command -v lsof &>/dev/null; then
        log_warn "lsof not installed (needed for port cleanup)"
        log_detail "Install with: sudo apt install lsof"
    fi

    # 6. Check MAVSDK Server if needed
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
# Step 2: Cleanup Previous Sessions
# ============================================================================
cleanup_ports_silent() {
    # Silent PixEagle-owned port cleanup for interrupt handler.
    for port in $MAVLINK2REST_PORT $BACKEND_PORT $DASHBOARD_PORT $WEBSOCKET_PORT; do
        local pids pid
        pids=$(port_listener_pids "$port")
        for pid in $pids; do
            is_pixeagle_owned_pid "$pid" || continue
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        done
    done
}

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
    local cwd cmd

    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
    if [[ -n "$cwd" && "$cwd" == "$PIXEAGLE_DIR"* ]]; then
        return 0
    fi

    cmd=$(ps -p "$pid" -o args= 2>/dev/null || true)
    case "$cmd" in
        *"$PIXEAGLE_DIR"*) return 0 ;;
        *) return 1 ;;
    esac
}

check_and_kill_port() {
    local port="$1"
    local service_name="${2:-Service}"

    local pids
    pids=$(port_listener_pids "$port")

    if [[ -n "$pids" ]]; then
        local pid process_name blocked=false

        for pid in $pids; do
            process_name=$(describe_pid "$pid")

            if ! is_pixeagle_owned_pid "$pid"; then
                log_error "Port $port is already in use by a non-PixEagle process ($process_name, pid $pid)"
                log_detail "Stop that process or change the configured $service_name port before running PixEagle"
                blocked=true
                continue
            fi

            # Try graceful termination first
            kill -TERM "$pid" 2>/dev/null
            sleep 1

            # Check if process is still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
                sleep 0.5
            fi

            # Verify the process was killed
            if ! kill -0 "$pid" 2>/dev/null; then
                log_success "Killed PixEagle-owned $process_name on port $port ($service_name)"
            else
                log_warn "Could not kill PixEagle-owned process on port $port"
                blocked=true
            fi
        done

        [[ "$blocked" != "true" ]]
    else
        log_success "Port $port already free ($service_name)"
    fi
}

cleanup_previous_sessions() {
    log_step 2 "Cleaning Up Previous Sessions"

    # Kill existing tmux session
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        # Send interrupt to all panes first (graceful)
        tmux list-panes -t "$SESSION_NAME" -F "#{session_name}:#{window_index}.#{pane_index}" 2>/dev/null | \
        while read -r pane; do
            tmux send-keys -t "$pane" C-c 2>/dev/null || true
        done
        sleep 1

        tmux kill-session -t "$SESSION_NAME" 2>/dev/null
        log_success "Terminated existing tmux session"
    else
        log_success "No existing tmux session"
    fi

    # Clean up PixEagle-owned ports; unrelated port occupants block startup.
    local blocked_ports=false
    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        check_and_kill_port "$MAVLINK2REST_PORT" "MAVLink2REST" || blocked_ports=true
    fi

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        check_and_kill_port "$BACKEND_PORT" "Backend" || blocked_ports=true
        check_and_kill_port "$WEBSOCKET_PORT" "Legacy telemetry WebSocket" || blocked_ports=true
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        check_and_kill_port "$DASHBOARD_PORT" "Dashboard" || blocked_ports=true
    fi

    if [[ "$blocked_ports" == "true" ]]; then
        log_error "Startup blocked by non-PixEagle process on a required port"
        exit 1
    fi
}

# ============================================================================
# Step 3: Load Configuration
# ============================================================================
load_configuration() {
    log_step 3 "Loading Configuration"

    # Read ports from config.yaml (with defaults)
    BACKEND_PORT=$(get_config_value "Streaming" "HTTP_STREAM_PORT" "$BACKEND_PORT")
    BACKEND_HOST=$(get_config_value "Streaming" "HTTP_STREAM_HOST" "$BACKEND_HOST")
    API_EXPOSURE_MODE=$(get_config_value "Streaming" "API_EXPOSURE_MODE" "$API_EXPOSURE_MODE")
    API_AUTH_MODE=$(get_config_value "Streaming" "API_AUTH_MODE" "$API_AUTH_MODE")
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

start_services() {
    log_step 4 "Starting Services"

    # Prepare MAVSDK Server if needed
    if [[ "$RUN_MAVSDK_SERVER" == "true" ]]; then
        prepare_mavsdk_server
    fi

    # Create new tmux session
    tmux new-session -d -s "$SESSION_NAME"

    # Build component array
    declare -A components
    local component_count=0

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        local python_arg
        printf -v python_arg "%q" "$VENV_DIR/bin/python"
        local run_id_arg runtime_log_dir_arg
        printf -v run_id_arg "%q" "$PIXEAGLE_RUN_ID"
        printf -v runtime_log_dir_arg "%q" "$PIXEAGLE_RUNTIME_LOG_DIR"
        local main_cmd="PIXEAGLE_RUN_ID=$run_id_arg PIXEAGLE_RUNTIME_LOG_DIR=$runtime_log_dir_arg bash $MAIN_APP_SCRIPT $python_arg"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            main_cmd="PIXEAGLE_RUN_ID=$run_id_arg PIXEAGLE_RUNTIME_LOG_DIR=$runtime_log_dir_arg bash $MAIN_APP_SCRIPT --dev $python_arg"
        fi
        components["MainApp"]="$main_cmd; bash"
        ((component_count++))
        printf "\r        ${DIM}-> Starting Main App... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        components["MAVLink2REST"]="bash $MAVLINK2REST_SCRIPT; bash"
        ((component_count++))
        printf "\r        ${DIM}-> Starting MAVLink2REST... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        # Ensure nvm is loaded in the tmux pane (needed if node installed via nvm)
        local nvm_setup='export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh";'
        local dashboard_host_arg dashboard_exposure_arg dashboard_script_arg
        printf -v dashboard_host_arg "%q" "$DASHBOARD_HOST"
        printf -v dashboard_exposure_arg "%q" "$DASHBOARD_EXPOSURE_MODE"
        printf -v dashboard_script_arg "%q" "$DASHBOARD_SCRIPT"
        local dashboard_cmd="PIXEAGLE_DASHBOARD_HOST=$dashboard_host_arg PIXEAGLE_DASHBOARD_EXPOSURE_MODE=$dashboard_exposure_arg bash $dashboard_script_arg"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -d"
        fi
        if [[ "$FORCE_REBUILD" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -f"
        fi
        dashboard_cmd="$dashboard_cmd $DASHBOARD_PORT"
        components["Dashboard"]="${nvm_setup} ${dashboard_cmd}; bash"
        ((component_count++))
        printf "\r        ${DIM}-> Starting Dashboard... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_MAVSDK_SERVER" == "true" ]] && [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
        components["MAVSDKServer"]="cd $PIXEAGLE_DIR; $MAVSDK_SERVER_BINARY; bash"
        ((component_count++))
        printf "\r        ${DIM}-> Starting MAVSDK Server... (%d/4)${NC}" $component_count
    fi

    echo ""

    # Create tmux layout
    if [[ "$COMBINED_VIEW" == "true" ]]; then
        # Combined view with split panes
        tmux rename-window -t "$SESSION_NAME:0" "CombinedView"
        local pane_index=0

        for component_name in "${!components[@]}"; do
            if [[ $pane_index -eq 0 ]]; then
                tmux send-keys -t "$SESSION_NAME:CombinedView.$pane_index" "clear; ${components[$component_name]}" C-m
            else
                tmux split-window -t "$SESSION_NAME:CombinedView" -h
                tmux select-pane -t "$SESSION_NAME:CombinedView.$pane_index"
                tmux send-keys -t "$SESSION_NAME:CombinedView.$pane_index" "clear; ${components[$component_name]}" C-m
            fi
            ((pane_index++))
        done

        if [[ $pane_index -gt 1 ]]; then
            tmux select-layout -t "$SESSION_NAME:CombinedView" tiled
        fi
    else
        # Separate windows
        local window_index=0
        for component_name in "${!components[@]}"; do
            if [[ $window_index -eq 0 ]]; then
                tmux rename-window -t "$SESSION_NAME:0" "$component_name"
                tmux send-keys -t "$SESSION_NAME:$component_name" "clear; ${components[$component_name]}" C-m
            else
                tmux new-window -t "$SESSION_NAME" -n "$component_name"
                tmux send-keys -t "$SESSION_NAME:$component_name" "clear; ${components[$component_name]}" C-m
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
        nc -z localhost "$port" 2>/dev/null
        return $?
    fi

    python3 - "$port" <<'PYEOF' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
with socket.create_connection(("127.0.0.1", port), timeout=0.5):
    pass
PYEOF
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

    for service_info in "${services[@]}"; do
        local name="${service_info%%:*}"
        local port="${service_info##*:}"
        local retries
        retries="$(service_ready_retries "$name")"
        local ready=false

        printf "        ${DIM}-> Waiting for ${name} (port ${port})...${NC}"

        for ((i=1; i<=retries; i++)); do
            if check_port_ready "$port"; then
                ready=true
                break
            fi
            sleep 1
        done

        if $ready; then
            printf "\r        ${GREEN}${CHECK}${NC} ${name} ready (port ${port})                    \n"
        else
            printf "\r        ${YELLOW}${WARN}${NC}  ${name} may not be ready (port ${port})        \n"
        fi
    done
}

# ============================================================================
# Step 6: Launch Tmux Interface
# ============================================================================
launch_tmux_interface() {
    log_step 6 "Launching Tmux Interface"

    log_success "Tmux session '$SESSION_NAME' created"

    if [[ "$NO_ATTACH" == "true" ]]; then
        log_info "Running in background (--no-attach)"
        log_detail "Attach with: tmux attach -t $SESSION_NAME"
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
    echo -e "      ${GREEN}Ctrl+B x${NC}       Close current pane"
    echo ""
    echo -e "   ${BOLD}Management Commands:${NC}"
    echo -e "      ${DIM}tmux attach -t $SESSION_NAME${NC}       Re-attach to session"
    echo -e "      ${DIM}tmux kill-session -t $SESSION_NAME${NC}  Stop all services"
    echo -e "      ${DIM}make stop${NC}                         Stop all services"
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
main() {
    # Change to PixEagle directory
    cd "$PIXEAGLE_DIR" || exit 1

    # Parse command line arguments
    parse_arguments "$@"

    # Display banner
    display_startup_banner

    # Execute startup sequence
    preflight_checks
    cleanup_previous_sessions
    load_configuration
    start_services
    wait_for_services
    launch_tmux_interface

    # Show summary
    show_final_summary

    # Attach to tmux session (unless --no-attach)
    if [[ "$NO_ATTACH" != "true" ]]; then
        tmux attach-session -t "$SESSION_NAME"
    fi
}

main "$@"
