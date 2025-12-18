#!/bin/bash

# ============================================================================
# run_pixeagle.sh - PixEagle System Launcher
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
# Usage: bash run_pixeagle.sh [OPTIONS]
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOTAL_STEPS=6

# Source shared functions (colors, logging, banner)
source "$SCRIPT_DIR/scripts/common.sh"

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

# Default ports used by the components
MAVLINK2REST_PORT=8088
BACKEND_PORT=5077
DASHBOARD_PORT=3000
WEBSOCKET_PORT=5551

# Paths to component scripts
BASE_DIR="$SCRIPT_DIR"
VENV_DIR="$BASE_DIR/venv"
CONFIG_FILE="$BASE_DIR/configs/config.yaml"
MAVLINK2REST_SCRIPT="$BASE_DIR/src/tools/mavlink2rest/run_mavlink2rest.sh"
DASHBOARD_SCRIPT="$BASE_DIR/run_dashboard.sh"
MAIN_APP_SCRIPT="$BASE_DIR/run_main.sh"
MAVSDK_SERVER_BINARY="$BASE_DIR/mavsdk_server_bin"
MAVSDK_SERVER_DOWNLOAD_SCRIPT="$BASE_DIR/src/tools/download_mavsdk_server.sh"

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
    display_pixeagle_banner "Help" "Usage information for run_pixeagle.sh"

    echo ""
    echo -e "   ${BOLD}USAGE:${NC}"
    echo -e "      bash run_pixeagle.sh [OPTIONS]"
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
    echo -e "      ${GREEN}-m${NC}  Do NOT run MAVLink2REST"
    echo -e "      ${GREEN}-p${NC}  Do NOT run Main Python Application"
    echo -e "      ${GREEN}-k${NC}  Do NOT run MAVSDK Server"
    echo ""
    echo -e "      ${GREEN}--help, -h${NC}"
    echo -e "          Show this help message"
    echo ""
    echo -e "   ${BOLD}EXAMPLES:${NC}"
    echo -e "      ${DIM}bash run_pixeagle.sh${NC}"
    echo -e "          Start normally with combined 4-pane view"
    echo ""
    echo -e "      ${DIM}bash run_pixeagle.sh --dev${NC}"
    echo -e "          Start in development mode with hot-reload"
    echo ""
    echo -e "      ${DIM}bash run_pixeagle.sh --dev --rebuild${NC}"
    echo -e "          Rebuild dashboard and start in development mode"
    echo ""
    echo -e "      ${DIM}bash run_pixeagle.sh --no-attach${NC}"
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
    branch=$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    commit_short=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    commit_date=$(git -C "$SCRIPT_DIR" log -1 --format="%cr" 2>/dev/null || echo "unknown")

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
    log_step 1 $TOTAL_STEPS "Pre-flight Checks"

    # 1. Virtual environment
    if [[ ! -d "$VENV_DIR" ]]; then
        log_error "Virtual environment not found"
        log_detail "Run: bash init_pixeagle.sh"
        exit 1
    fi
    log_success "Virtual environment found"

    # 2. Configuration file
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "Configuration file not found: $CONFIG_FILE"
        log_detail "Run: bash init_pixeagle.sh"
        exit 1
    fi
    log_success "Configuration file found"

    # 3. Core Python dependencies (quick sanity check)
    if ! "$VENV_DIR/bin/python" -c "import cv2, numpy" 2>/dev/null; then
        log_warn "Some Python dependencies may be missing"
        log_detail "Run: bash init_pixeagle.sh to reinstall"
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
    # Silent port cleanup for interrupt handler
    for port in $MAVLINK2REST_PORT $BACKEND_PORT $DASHBOARD_PORT $WEBSOCKET_PORT; do
        local pid
        pid=$(lsof -t -i :"$port" 2>/dev/null)
        if [[ -n "$pid" ]]; then
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
}

check_and_kill_port() {
    local port="$1"
    local service_name="${2:-Service}"

    local pid
    pid=$(lsof -t -i :"$port" 2>/dev/null)

    if [[ -n "$pid" ]]; then
        local process_name
        process_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")

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
            log_success "Killed $process_name on port $port ($service_name)"
        else
            log_warn "Could not kill process on port $port"
        fi
    else
        log_success "Port $port already free ($service_name)"
    fi
}

cleanup_previous_sessions() {
    log_step 2 $TOTAL_STEPS "Cleaning Up Previous Sessions"

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

    # Clean up ports
    if [[ "$RUN_MAVLINK2REST" == "true" ]]; then
        check_and_kill_port "$MAVLINK2REST_PORT" "MAVLink2REST"
    fi

    if [[ "$RUN_MAIN_APP" == "true" ]]; then
        check_and_kill_port "$BACKEND_PORT" "Backend"
        check_and_kill_port "$WEBSOCKET_PORT" "WebSocket"
    fi

    if [[ "$RUN_DASHBOARD" == "true" ]]; then
        check_and_kill_port "$DASHBOARD_PORT" "Dashboard"
    fi
}

# ============================================================================
# Step 3: Load Configuration
# ============================================================================
load_configuration() {
    log_step 3 $TOTAL_STEPS "Loading Configuration"

    # Display configured ports
    log_info "MAVLink2REST: http://localhost:${MAVLINK2REST_PORT}"
    log_info "Backend API:  http://localhost:${BACKEND_PORT}"
    log_info "Dashboard:    http://localhost:${DASHBOARD_PORT}"
    log_info "WebSocket:    ws://localhost:${WEBSOCKET_PORT}"

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

    log_info "MAVSDK Server binary not found, downloading..."

    if [[ -f "$MAVSDK_SERVER_DOWNLOAD_SCRIPT" ]]; then
        bash "$MAVSDK_SERVER_DOWNLOAD_SCRIPT"
        if [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
            chmod +x "$MAVSDK_SERVER_BINARY"
            log_success "MAVSDK Server downloaded"
            return 0
        fi
    fi

    log_warn "Could not download MAVSDK Server"
    log_detail "Download manually from: https://github.com/mavlink/MAVSDK/releases/"
    return 1
}

start_services() {
    log_step 4 $TOTAL_STEPS "Starting Services"

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
        local main_cmd="bash $MAIN_APP_SCRIPT"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            main_cmd="bash $MAIN_APP_SCRIPT --dev"
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
        local dashboard_cmd="bash $DASHBOARD_SCRIPT"
        if [[ "$DEVELOPMENT_MODE" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -d"
        fi
        if [[ "$FORCE_REBUILD" == "true" ]]; then
            dashboard_cmd="$dashboard_cmd -f"
        fi
        components["Dashboard"]="$dashboard_cmd; bash"
        ((component_count++))
        printf "\r        ${DIM}-> Starting Dashboard... (%d/4)${NC}" $component_count
    fi

    if [[ "$RUN_MAVSDK_SERVER" == "true" ]] && [[ -f "$MAVSDK_SERVER_BINARY" ]]; then
        components["MAVSDKServer"]="cd $BASE_DIR; ./mavsdk_server_bin; bash"
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
    nc -z localhost "$port" 2>/dev/null
    return $?
}

wait_for_services() {
    log_step 5 $TOTAL_STEPS "Waiting for Services"

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
        local retries=15
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
    log_step 6 $TOTAL_STEPS "Launching Tmux Interface"

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
    echo -e "   ${BOLD}Service URLs:${NC}"
    echo -e "      Dashboard:     ${CYAN}http://localhost:${DASHBOARD_PORT}${NC}"
    echo -e "      Backend API:   ${CYAN}http://localhost:${BACKEND_PORT}${NC}"
    echo -e "      MAVLink2REST:  ${CYAN}http://localhost:${MAVLINK2REST_PORT}${NC}"
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
    echo -e "      ${DIM}bash run_pixeagle.sh --help${NC}      Show all options"
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
