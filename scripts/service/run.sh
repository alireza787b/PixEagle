#!/bin/bash

# ============================================================================
# scripts/service/run.sh - PixEagle Service-Optimized Launcher
# ============================================================================
# This script is optimized for running PixEagle as a system service.
# It provides enhanced error handling, logging, and headless operation
# while maintaining compatibility with the tmux-based architecture.
#
# Key Features:
# - Headless operation suitable for systemd services
# - Enhanced error handling and recovery
# - Comprehensive logging for service monitoring
# - Graceful shutdown handling
# - Network dependency checking
# - Resource cleanup on exit
#
# This script is automatically called by the systemd service but can
# also be run manually for testing service operation.
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Service configuration
SERVICE_MODE=true
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/pixeagle_service.log"
PID_FILE="$PROJECT_ROOT/pixeagle_service.pid"

# Store PID for service management
echo $$ > "$PID_FILE"

# Logging function for service mode
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Enhanced error handling
set -e
trap 'handle_error $? $LINENO' ERR
trap 'cleanup_on_exit' EXIT

handle_error() {
    local exit_code=$1
    local line_number=$2
    log_message "ERROR" "Script failed with exit code $exit_code at line $line_number"
    cleanup_on_exit
    exit $exit_code
}

cleanup_on_exit() {
    log_message "INFO" "Performing cleanup on exit"
    rm -f "$PID_FILE"
}

# Function to check network connectivity
wait_for_network() {
    log_message "INFO" "Checking network connectivity..."

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if ping -c 1 8.8.8.8 &>/dev/null || ping -c 1 google.com &>/dev/null; then
            log_message "INFO" "Network connectivity confirmed"
            return 0
        fi

        log_message "WARN" "Network not ready, attempt $attempt/$max_attempts"
        sleep 2
        ((attempt++))
    done

    log_message "WARN" "Network connectivity timeout, proceeding anyway"
    return 0
}

# Function to check prerequisites
check_service_prerequisites() {
    log_message "INFO" "Checking service prerequisites..."

    # Check required commands
    local missing_deps=()
    for cmd in tmux python3 node npm; do
        if ! command -v "$cmd" &>/dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_message "ERROR" "Missing dependencies: ${missing_deps[*]}"
        return 1
    fi

    # Check PixEagle files
    if [ ! -f "$PROJECT_ROOT/scripts/run.sh" ]; then
        log_message "ERROR" "PixEagle launcher script not found: $PROJECT_ROOT/scripts/run.sh"
        return 1
    fi

    # Check Python virtual environment
    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        log_message "WARN" "Python virtual environment not found at $PROJECT_ROOT/venv"
        log_message "INFO" "Attempting to create virtual environment..."
        if ! python3 -m venv "$PROJECT_ROOT/venv"; then
            log_message "ERROR" "Failed to create virtual environment"
            return 1
        fi
    fi

    # Check if dashboard dependencies are installed
    if [ -d "$PROJECT_ROOT/dashboard" ] && [ ! -d "$PROJECT_ROOT/dashboard/node_modules" ]; then
        log_message "WARN" "Dashboard dependencies not installed"
        log_message "INFO" "This may cause dashboard startup delays"
    fi

    log_message "INFO" "Prerequisites check completed"
    return 0
}

# Function to setup environment for service
setup_service_environment() {
    log_message "INFO" "Setting up service environment..."

    # Set environment variables for headless operation
    export DISPLAY=""
    export XDG_RUNTIME_DIR=""
    export DBUS_SESSION_BUS_ADDRESS=""

    # Ensure proper working directory
    cd "$PROJECT_ROOT" || {
        log_message "ERROR" "Failed to change to PixEagle directory: $PROJECT_ROOT"
        exit 1
    }

    # Set Python path if virtual environment exists
    if [ -d "venv" ]; then
        export PATH="$PROJECT_ROOT/venv/bin:$PATH"
        export VIRTUAL_ENV="$PROJECT_ROOT/venv"
    fi

    log_message "INFO" "Service environment configured"
}

# Function to start PixEagle with service optimizations
start_pixeagle_service() {
    log_message "INFO" "Starting PixEagle in service mode..."

    # Check if tmux session already exists
    if tmux has-session -t PixEagle 2>/dev/null; then
        log_message "WARN" "PixEagle tmux session already exists, killing it"
        tmux kill-session -t PixEagle 2>/dev/null || true
        sleep 2
    fi

    # Clean up any processes on PixEagle ports
    for port in 8088 5077 3000; do
        if lsof -ti ":$port" &>/dev/null; then
            log_message "INFO" "Cleaning up process on port $port"
            lsof -ti ":$port" | xargs -r kill -9 2>/dev/null || true
        fi
    done

    # Start PixEagle using the new launcher but in detached mode
    log_message "INFO" "Launching PixEagle components in tmux session..."

    # Create tmux session in detached mode
    tmux new-session -d -s PixEagle -c "$PROJECT_ROOT"

    # Set tmux session environment
    tmux send-keys -t PixEagle "export HOME=$HOME" C-m
    tmux send-keys -t PixEagle "export USER=$USER" C-m
    tmux send-keys -t PixEagle "cd $PROJECT_ROOT" C-m

    # Execute the PixEagle launcher within tmux
    tmux send-keys -t PixEagle "bash scripts/run.sh" C-m

    # Wait for components to start
    log_message "INFO" "Waiting for components to initialize..."
    sleep 10

    # Verify components are running
    local startup_success=true
    local component_checks=(
        "8088:MAVLink2REST"
        "5077:Main Python App"
        "3000:Dashboard"
    )

    for check in "${component_checks[@]}"; do
        local port="${check%:*}"
        local name="${check#*:}"

        local attempts=0
        local max_attempts=12  # 1 minute total

        while [ $attempts -lt $max_attempts ]; do
            if lsof -i ":$port" &>/dev/null; then
                log_message "INFO" "$name started successfully on port $port"
                break
            fi

            sleep 5
            ((attempts++))
        done

        if [ $attempts -eq $max_attempts ]; then
            log_message "WARN" "$name did not start on port $port within timeout"
            startup_success=false
        fi
    done

    if [ "$startup_success" = "true" ]; then
        log_message "INFO" "PixEagle service started successfully"
        log_message "INFO" "Dashboard available at: http://localhost:3000"
        log_message "INFO" "Tmux session 'PixEagle' is running in detached mode"
    else
        log_message "WARN" "PixEagle started with some components not responding"
        log_message "INFO" "Check individual component logs for details"
    fi

    return 0
}

# Function to monitor service health
monitor_service_health() {
    log_message "INFO" "Starting service health monitoring..."

    while true; do
        # Check if tmux session is still alive
        if ! tmux has-session -t PixEagle 2>/dev/null; then
            log_message "ERROR" "PixEagle tmux session died unexpectedly"
            return 1
        fi

        # Basic health check every 30 seconds
        sleep 30

        # Check if main components are still responsive
        local health_ok=true
        for port in 5077 3000; do  # Skip MAVLink2REST as it might be optional
            if ! lsof -i ":$port" &>/dev/null; then
                log_message "WARN" "Component on port $port is not responding"
                health_ok=false
            fi
        done

        if [ "$health_ok" = "true" ]; then
            log_message "DEBUG" "Health check passed"
        fi
    done
}

# Main execution
main() {
    log_message "INFO" "PixEagle Service Launcher starting..."

    # Wait for network if needed
    wait_for_network

    # Check prerequisites
    if ! check_service_prerequisites; then
        log_message "ERROR" "Prerequisites check failed"
        exit 1
    fi

    # Setup environment
    setup_service_environment

    # Start PixEagle
    if ! start_pixeagle_service; then
        log_message "ERROR" "Failed to start PixEagle service"
        exit 1
    fi

    # Monitor health (this will run indefinitely)
    monitor_service_health
}

# Handle service signals
handle_signal() {
    local signal="$1"
    log_message "INFO" "Received signal: $signal"

    case "$signal" in
        "TERM"|"INT")
            log_message "INFO" "Gracefully shutting down PixEagle service..."

            # Kill tmux session gracefully
            if tmux has-session -t PixEagle 2>/dev/null; then
                tmux send-keys -t PixEagle C-c 2>/dev/null || true
                sleep 3
                tmux kill-session -t PixEagle 2>/dev/null || true
            fi

            log_message "INFO" "PixEagle service shutdown complete"
            exit 0
            ;;
        "HUP")
            log_message "INFO" "Reloading PixEagle configuration..."
            # Could implement config reload here
            ;;
    esac
}

# Set up signal handlers
trap 'handle_signal TERM' TERM
trap 'handle_signal INT' INT
trap 'handle_signal HUP' HUP

# Execute main function
main "$@"
