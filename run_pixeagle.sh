#!/bin/bash

#########################################
# PixEagle Complete System Launcher with Tmux 
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
#   ./run_pixeagle_split.sh [-m|-d|-p|-h]
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
check_install_tmux() {
    if ! command -v tmux &> /dev/null; then
        echo "Tmux not found. Installing tmux..."
        sudo apt-get update && sudo apt-get install -y tmux
        if [ $? -ne 0 ]; then
            echo "Failed to install tmux. Please install it manually and re-run the script."
            exit 1
        fi
        echo "Tmux installed successfully."
    else
        echo "Tmux is already installed."
    fi
}

# Function to create a new tmux session with a split layout
create_tmux_session() {
    echo "Creating tmux session '$SESSION_NAME' with split panes..."
    tmux new-session -d -s $SESSION_NAME
    tmux split-window -v  # Split horizontally
    tmux split-window -h  # Split the new pane vertically, so you have 3 panes
    tmux select-pane -t 0
}

# Function to run MAVLink2REST in a tmux pane
run_mavlink2rest() {
    echo "Running MAVLink2REST in tmux pane 0..."
    tmux send-keys -t $SESSION_NAME:0.0 "bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh" C-m
}

# Function to run the PixEagle Dashboard in a tmux pane
run_dashboard() {
    echo "Running PixEagle Dashboard in tmux pane 1..."
    tmux send-keys -t $SESSION_NAME:0.1 "bash ~/PixEagle/run_dashboard.sh" C-m
}

# Function to run the PixEagle Main Application in a tmux pane
run_main_app() {
    echo "Running PixEagle Main Application in tmux pane 2..."
    tmux send-keys -t $SESSION_NAME:0.2 "bash ~/PixEagle/run_main.sh" C-m
}

# Main execution sequence
check_install_tmux
create_tmux_session

if [ "$RUN_MAVLINK2REST" = true ]; then
    run_mavlink2rest
else
    echo "Skipping MAVLink2REST as per user request."
fi

if [ "$RUN_DASHBOARD" = true ]; then
    run_dashboard
else
    echo "Skipping Dashboard as per user request."
fi

if [ "$RUN_MAIN_APP" = true ]; then
    run_main_app
else
    echo "Skipping Main Application as per user request."
fi

# Attach to the tmux session so the user can see the split panes
tmux attach-session -t $SESSION_NAME
