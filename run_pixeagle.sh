#!/bin/bash

#########################################
# PixEagle Complete System Launcher
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Date: August 2024
#
# This script manages the execution of the entire PixEagle system,
# including MAVLink2REST, the React Dashboard, and the main Python
# application. Each component runs in its own tmux session for easy
# management, even when using SSH.
#
# Usage:
#   ./run_pixeagle.sh [-m|-d|-p|-h]
#   Flags:
#     -m : Run MAVLink2REST (default: enabled)
#     -d : Run Dashboard (default: enabled)
#     -p : Run Main Python Application (default: enabled)
#     -h : Display help
#
# Example:
#   ./run_pixeagle.sh -m -d
#   Runs MAVLink2REST and Dashboard, skipping the main Python application.
#
#########################################

# Default flag values (all enabled)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true

# Tmux session names
MAVLINK2REST_SESSION="mavlink2rest"
DASHBOARD_SESSION="pixeagle_dashboard"
MAIN_APP_SESSION="pixeagle_main"

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

# Function to run MAVLink2REST in a tmux session
run_mavlink2rest() {
    echo "Starting MAVLink2REST in a new tmux session..."
    tmux new-session -d -s $MAVLINK2REST_SESSION "bash ~/PixEagle/src/tools/mavlink2rest/run_mavlink2rest.sh"
    if [ $? -eq 0 ]; then
        echo "MAVLink2REST is running in tmux session '$MAVLINK2REST_SESSION'."
    else
        echo "Failed to start MAVLink2REST."
        exit 1
    fi
}

# Function to run the PixEagle Dashboard in a tmux session
run_dashboard() {
    echo "Starting PixEagle Dashboard in a new tmux session..."
    tmux new-session -d -s $DASHBOARD_SESSION "bash ~/PixEagle/run_dashboard.sh"
    if [ $? -eq 0 ]; then
        echo "PixEagle Dashboard is running in tmux session '$DASHBOARD_SESSION'."
    else
        echo "Failed to start PixEagle Dashboard."
        exit 1
    fi
}

# Function to run the PixEagle Main Application in a tmux session
run_main_app() {
    echo "Starting PixEagle Main Application in a new tmux session..."
    tmux new-session -d -s $MAIN_APP_SESSION "bash ~/PixEagle/run_main.sh"
    if [ $? -eq 0 ]; then
        echo "PixEagle Main Application is running in tmux session '$MAIN_APP_SESSION'."
    else
        echo "Failed to start PixEagle Main Application."
        exit 1
    fi
}

# Main execution sequence
check_install_tmux

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

echo "------------------------------------------------------------------------------"
echo "All selected components are now running in their respective tmux sessions."
echo "Use the following commands to interact with them:"
echo "  tmux attach-session -t $MAVLINK2REST_SESSION     # For MAVLink2REST"
echo "  tmux attach-session -t $DASHBOARD_SESSION       # For Dashboard"
echo "  tmux attach-session -t $MAIN_APP_SESSION        # For Main Application"
echo "To exit tmux, press 'Ctrl+b', then 'd' to detach from the session."
echo "------------------------------------------------------------------------------"
