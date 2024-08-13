#!/bin/bash

#########################################
# PixEagle Complete System Launcher with Tmux Split Panes
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Date: August 2024
#
# This script manages the execution of the entire PixEagle system,
# including MAVLink2REST, the React Dashboard, and the main Python
# application. Each component runs in its own tmux pane for easy
# management during SSH sessions.
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
    echo "  - Switch between panes: Arrow keys (e.g., Ctrl+B, then →)"
    echo "  - Detach from session: Ctrl+B, then D"
    echo "  - Reattach to session: tmux attach -t $SESSION_NAME"
    echo "  - Close pane/window: Type 'exit' or press Ctrl+D"
    echo "==============================================="
    echo ""
}

# Function to create a new tmux session with the main app as the larger pane
create_tmux_session() {
    echo "Creating tmux session '$SESSION_NAME' with split panes..."

    # Create the session with the main app taking up the left side (larger pane)
    tmux new-session -d -s $SESSION_NAME -n "MainApp" "clear; $MAIN_APP_COMMAND; bash"
    tmux split-window -h -p 30 "clear; $MAVLINK2REST_COMMAND; bash"  # Split horizontally, 30% of screen width for MAVLink2REST
    tmux split-window -v "clear; $DASHBOARD_COMMAND; bash"           # Split the right pane vertically for the dashboard
    tmux select-pane -t 0                                             # Start with the main app pane selected
}

# Function to run the PixEagle system components
run_pixeagle_components() {
    echo "Starting PixEagle components in tmux panes..."

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

    create_tmux_session

    # Display tmux instructions
    show_tmux_instructions

    # Attach to the tmux session so the user can see the split panes
    tmux attach-session -t $SESSION_NAME
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
