#!/bin/bash

#########################################
# PixEagle Complete System Launcher with Tmux Windows and Split Panes
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Date: August 2024
#
# This script manages the execution of the entire PixEagle system,
# including MAVLink2REST, the React Dashboard, and the main Python
# application. Components are run in separate tmux windows, and
# also combined in a single window with split panes.
#
# Usage:
#   ./run_pixeagle.sh [-m|-d|-p|-h]
#   Flags:
#     -m : Run MAVLink2REST (default: enabled)
#     -d : Run Dashboard (default: enabled)
#     -p : Run Main Python Application (default: enabled)
#     -h : Display help
#
#########################################

# Default flag values (all enabled)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true

# Tmux session name
SESSION_NAME="PixEagle"

# Function to display usage instructions
display_usage() {
    echo "Usage: $0 [-m|-d|-p|-h]"
    echo "Flags:"
    echo "  -m : Run MAVLink2REST (default: enabled)"
    echo "  -d : Run Dashboard (default: enabled)"
    echo "  -p : Run Main Python Application (default: enabled)"
    echo "  -h : Display this help message"
    echo "Example: $0 -m -d (Runs MAVLink2REST and Dashboard, skips the main Python application)"
}

# Parse command-line options
while getopts "mdph" opt; do
  case ${opt} in
    m) RUN_MAVLINK2REST=true ;;
    d) RUN_DASHBOARD=true ;;
    p) RUN_MAIN_APP=true ;;
    h)
      display_usage
      exit 0
      ;;
    *)
      display_usage
      exit 1
      ;;
  esac
done

# Function to check if tmux is installed and install it if not
check_tmux_installed() {
    if ! command -v tmux &> /dev/null; then
        echo "tmux could not be found. Installing tmux..."
        sudo apt-get update
        sudo apt-get install -y tmux
    else
        echo "tmux is already installed."
    fi
}

# Function to display tmux instructions
show_tmux_instructions() {
    echo "==============================================="
    echo "  Quick tmux Guide:"
    echo "==============================================="
    echo "Prefix key (Ctrl+B), then:"
    echo "  - Switch between windows: Number keys (e.g., Ctrl+B, then 1, 2, 3)"
    echo "  - Switch between panes: Arrow keys (e.g., Ctrl+B, then →)"
    echo "  - Detach from session: Ctrl+B, then D"
    echo "  - Reattach to session: tmux attach -t $SESSION_NAME"
    echo "  - Close pane/window: Type 'exit' or press Ctrl+D"
    echo "==============================================="
    echo ""
}

# Function to start a process in a new tmux window
start_process_tmux() {
    local session="$1"
    local window_name="$2"
    local command="$3"
    
    tmux new-window -t "$session" -n "$window_name" "clear; $command"
    sleep 2
}

# Function to create a tmux session with both windows and split panes
start_services_in_tmux() {
    local session="$SESSION_NAME"

    echo "Creating tmux session '$session'..."
    tmux new-session -d -s "$session" -n "MainApp" "clear; show_tmux_instructions; $MAIN_APP_COMMAND"

    # Start the MAVLink2REST service in a new window
    if [ "$RUN_MAVLINK2REST" = true ]; then
        echo "Starting MAVLink2REST in tmux..."
        start_process_tmux "$session" "MAVLink2REST" "$MAVLINK2REST_COMMAND"
    fi

    # Start the Dashboard service in a new window
    if [ "$RUN_DASHBOARD" = true ]; then
        echo "Starting Dashboard in tmux..."
        start_process_tmux "$session" "Dashboard" "$DASHBOARD_COMMAND"
    fi

    # Create a window with split panes for a combined view
    tmux new-window -t "$session" -n "CombinedView"
    tmux split-window -h -t "$session:3" "clear; $MAIN_APP_COMMAND; bash"
    tmux split-window -v -t "$session:3.0" "clear; $MAVLINK2REST_COMMAND; bash"
    tmux split-window -v -t "$session:3.1" "clear; $DASHBOARD_COMMAND; bash"
    tmux select-layout -t "$session:3" tiled

    # Attach to the tmux session and display instructions
    tmux attach-session -t "$session"
    show_tmux_instructions
}

# Function to run the PixEagle system components
run_pixeagle_components() {
    echo "Starting PixEagle components in tmux windows and split panes..."

    if [ "$RUN_MAVLINK2REST" = true ]; then
        MAVLINK2REST_COMMAND="bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh"
    else
        MAVLINK2REST_COMMAND="echo 'MAVLink2REST is disabled'; bash"
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        DASHBOARD_COMMAND="bash ~/PixEagle/run_dashboard.sh"
    else
        DASHBOARD_COMMAND="echo 'Dashboard is disabled'; bash"
    fi

    if [ "$RUN_MAIN_APP" = true ]; then
        MAIN_APP_COMMAND="bash ~/PixEagle/run_main.sh"
    else
        MAIN_APP_COMMAND="echo 'Main Application is disabled'; bash"
    fi

    start_services_in_tmux
}

# Main execution sequence
check_tmux_installed
run_pixeagle_components

echo ""
echo "==============================================="
echo "  PixEagle System Startup Complete!"
echo "==============================================="
echo ""
echo "All selected components are now running in tmux."
echo "Use 'tmux attach -t $SESSION_NAME' to reattach to the session."
echo ""
