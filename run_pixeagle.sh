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
#     -m : Do NOT run MAVLink2REST (default: enabled)
#     -d : Do NOT run Dashboard (default: enabled)
#     -p : Do NOT run Main Python Application (default: enabled)
#     -h : Display help
#
# Example:
#   ./run_pixeagle.sh -p
#   (Runs MAVLink2REST and Dashboard, skips the main Python application)
#
# Note:
#   This script assumes all configurations and initializations are complete.
#   If not, please refer to the GitHub repository and documentation:
#   https://github.com/alireza787b/PixEagle
#
#########################################

# Default flag values (all enabled)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true

# Tmux session name
SESSION_NAME="PixEagle"

# Paths to component scripts (modify if needed)
BASE_DIR="$HOME/PixEagle"
MAVLINK2REST_SCRIPT="$BASE_DIR/src/tools/mavlink2rest/run_mavlink2rest.sh"
DASHBOARD_SCRIPT="$BASE_DIR/run_dashboard.sh"
MAIN_APP_SCRIPT="$BASE_DIR/run_main.sh"

# Function to display usage instructions
display_usage() {
    echo "Usage: $0 [-m|-d|-p|-h]"
    echo "Flags:"
    echo "  -m : Do NOT run MAVLink2REST (default: enabled)"
    echo "  -d : Do NOT run Dashboard (default: enabled)"
    echo "  -p : Do NOT run Main Python Application (default: enabled)"
    echo "  -h : Display this help message"
    echo "Example: $0 -p (Runs MAVLink2REST and Dashboard, skips the main Python application)"
}

# Parse command-line options
while getopts "mdph" opt; do
  case ${opt} in
    m) RUN_MAVLINK2REST=false ;;
    d) RUN_DASHBOARD=false ;;
    p) RUN_MAIN_APP=false ;;
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
    echo ""
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
    tmux new-window -t "$session" -n "$window_name"
    tmux send-keys -t "$session:$window_name" "clear; $command" C-m
}

# Function to create a tmux session with both windows and split panes
start_services_in_tmux() {
    local session="$SESSION_NAME"

    # Kill existing session if it exists
    if tmux has-session -t "$session" 2>/dev/null; then
        tmux kill-session -t "$session"
    fi

    echo "Creating tmux session '$session'..."
    tmux new-session -d -s "$session"

    # Create an array to hold enabled components
    declare -A components
    local index=1

    # Start components in separate windows
    if [ "$RUN_MAIN_APP" = true ]; then
        tmux rename-window -t "$session:0" "MainApp"
        tmux send-keys -t "$session:0" "clear; bash $MAIN_APP_SCRIPT" C-m
        components["MainApp"]="bash $MAIN_APP_SCRIPT"
    else
        tmux rename-window -t "$session:0" "MainApp"
        tmux send-keys -t "$session:0" "echo 'Main Application is disabled'; bash" C-m
    fi

    if [ "$RUN_MAVLINK2REST" = true ]; then
        start_process_tmux "$session" "MAVLink2REST" "bash $MAVLINK2REST_SCRIPT"
        components["MAVLink2REST"]="bash $MAVLINK2REST_SCRIPT"
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        start_process_tmux "$session" "Dashboard" "bash $DASHBOARD_SCRIPT"
        components["Dashboard"]="bash $DASHBOARD_SCRIPT"
    fi

    # Create a window with split panes for a combined view
    tmux new-window -t "$session" -n "CombinedView"
    local pane_index=0
    for component_name in "${!components[@]}"; do
        if [ $pane_index -eq 0 ]; then
            tmux send-keys -t "$session:CombinedView.$pane_index" "clear; ${components[$component_name]}; bash" C-m
        else
            tmux split-window -t "$session:CombinedView" -h
            tmux select-pane -t "$session:CombinedView.$pane_index"
            tmux send-keys -t "$session:CombinedView.$pane_index" "clear; ${components[$component_name]}; bash" C-m
        fi
        pane_index=$((pane_index + 1))
    done

    if [ $pane_index -gt 1 ]; then
        tmux select-layout -t "$session:CombinedView" tiled
    fi

    # Attach to the tmux session
    tmux attach-session -t "$session"

    # Display tmux instructions
    show_tmux_instructions
}

# Main execution sequence
echo "Initializing PixEagle System..."
echo "Note: This script assumes all configurations and initializations are complete."
echo "If not, please refer to the GitHub repository and documentation:"
echo "👉 https://github.com/alireza787b/PixEagle"
echo ""

check_tmux_installed
run_pixeagle_components() {
    echo "Starting PixEagle components in tmux windows and split panes..."

    if [ "$RUN_MAVLINK2REST" = true ]; then
        echo "MAVLink2REST will be started."
    else
        echo "MAVLink2REST is disabled."
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        echo "Dashboard will be started."
    else
        echo "Dashboard is disabled."
    fi

    if [ "$RUN_MAIN_APP" = true ]; then
        echo "Main Python Application will be started."
    else
        echo "Main Python Application is disabled."
    fi

    start_services_in_tmux
}

run_pixeagle_components

echo ""
echo "==============================================="
echo "  PixEagle System Startup Complete!"
echo "==============================================="
echo ""
echo "All selected components are now running in tmux."
echo "Use 'tmux attach -t $SESSION_NAME' to reattach to the session."
echo ""
