#!/bin/bash

#########################################
# PixEagle Service Stop Script
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script gracefully stops the PixEagle service by terminating
# the tmux session and cleaning up running processes.
# It's designed to be called by systemd when stopping the service.
#
#########################################

# Load service utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_UTILS="$SCRIPT_DIR/service_utils.sh"

if [ -f "$SERVICE_UTILS" ]; then
    source "$SERVICE_UTILS"
else
    echo "Error: service_utils.sh not found"
    exit 1
fi

# Main stop function
stop_service() {
    # Detect user and session
    if ! detect_service_user; then
        exit 1
    fi

    # Check if tmux session exists
    if is_tmux_session_active; then
        print_status "process" "Stopping PixEagle tmux session..."

        # Send interrupt signal to all processes in the session
        tmux send-keys -t "$TMUX_SESSION_NAME" C-c 2>/dev/null || true
        sleep 3

        # Kill the session
        tmux kill-session -t "$TMUX_SESSION_NAME" 2>/dev/null || true
        sleep 1

        print_status "success" "PixEagle tmux session stopped"
    fi

    # Clean up any remaining processes on PixEagle ports
    for port in 8088 5077 3000; do
        if lsof -ti ":$port" &>/dev/null; then
            print_status "process" "Cleaning up process on port $port"
            lsof -ti ":$port" | xargs -r kill -TERM 2>/dev/null || true
            sleep 1
            # Force kill if still running
            lsof -ti ":$port" | xargs -r kill -9 2>/dev/null || true
        fi
    done

    print_status "success" "PixEagle service stopped successfully"
}

# Execute stop function
stop_service