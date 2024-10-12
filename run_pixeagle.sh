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
# application. Components are run either in separate tmux windows,
# or combined in a single window with split panes, based on user preference.
#
# Usage:
#   ./run_pixeagle.sh [-m|-d|-p|-s|-h]
#   Flags:
#     -m : Do NOT run MAVLink2REST (default: enabled)
#     -d : Do NOT run Dashboard (default: enabled)
#     -p : Do NOT run Main Python Application (default: enabled)
#     -s : Run components in Separate windows (default: Combined view)
#     -h : Display help
#
# Example:
#   ./run_pixeagle.sh -p -s
#   (Runs MAVLink2REST and Dashboard in separate windows, skips the main Python application)
#
# Note:
#   This script assumes all configurations and initializations are complete.
#   If not, please refer to the GitHub repository and documentation:
#   https://github.com/alireza787b/PixEagle
#
#########################################

# Default flag values (all components enabled by default)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true
COMBINED_VIEW=true  # Default is combined view

# Tmux session name
SESSION_NAME="PixEagle"

# Default ports used by the components
MAVLINK2REST_PORT=8088
BACKEND_PORT=5077
DASHBOARD_PORT=3001

# Paths to component scripts (modify these paths if your directory structure is different)
BASE_DIR="$HOME/PixEagle"
MAVLINK2REST_SCRIPT="$BASE_DIR/src/tools/mavlink2rest/run_mavlink2rest.sh"
DASHBOARD_SCRIPT="$BASE_DIR/run_dashboard.sh"
MAIN_APP_SCRIPT="$BASE_DIR/run_main.sh"

# Function to display usage instructions
display_usage() {
    echo "Usage: $0 [-m|-d|-p|-s|-h]"
    echo "Flags:"
    echo "  -m : Do NOT run MAVLink2REST (default: enabled)"
    echo "  -d : Do NOT run Dashboard (default: enabled)"
    echo "  -p : Do NOT run Main Python Application (default: enabled)"
    echo "  -s : Run components in Separate windows (default: Combined view)"
    echo "  -h : Display this help message"
    echo "Example: $0 -p -s (Runs MAVLink2REST and Dashboard in separate windows, skips the main Python application)"
}

# Parse command-line options
while getopts "mdpsh" opt; do
  case ${opt} in
    m) RUN_MAVLINK2REST=false ;;
    d) RUN_DASHBOARD=false ;;
    p) RUN_MAIN_APP=false ;;
    s) COMBINED_VIEW=false ;;
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

# Function to check if a command is installed and install it if not
check_command_installed() {
    local cmd="$1"
    local pkg="$2"
    if ! command -v "$cmd" &> /dev/null; then
        echo "⚠️  $cmd could not be found. Installing $pkg..."
        sudo apt-get update
        sudo apt-get install -y "$pkg"
    else
        echo "✅ $cmd is already installed."
    fi
}

# Function to check if a port is in use and kill the process using it
check_and_kill_port() {
    local port="$1"
    # Ensure lsof is installed
    check_command_installed "lsof" "lsof"
    # Find the process ID (PID) using the port
    pid=$(lsof -t -i :"$port")
    if [ -n "$pid" ]; then
        echo "⚠️  Port $port is in use by process $pid."
        # Get the process name
        process_name=$(ps -p "$pid" -o comm=)
        echo "Process using port $port: $process_name (PID: $pid)"
        # Kill the process
        echo "Killing process $pid..."
        kill -9 "$pid"
        echo "✅ Process $pid killed."
    else
        echo "✅ Port $port is free."
    fi
}

# Function to check if tmux is installed and install it if not
check_tmux_installed() {
    check_command_installed "tmux" "tmux"
}

# Function to display tmux instructions
show_tmux_instructions() {
    echo ""
    echo "==============================================="
    echo "  Quick tmux Guide:"
    echo "==============================================="
    echo "Prefix key (Ctrl+B), then:"
    if [ "$COMBINED_VIEW" = true ]; then
        echo "  - Switch between panes: Arrow keys (e.g., Ctrl+B, then →)"
        echo "  - Resize panes: Hold Ctrl+B, then press and hold an arrow key"
    else
        echo "  - Switch between windows: Number keys (e.g., Ctrl+B, then 1, 2, 3)"
    fi
    echo "  - Detach from session: Ctrl+B, then D"
    echo "  - Reattach to session: tmux attach -t $SESSION_NAME"
    echo "  - Close pane/window: Type 'exit' or press Ctrl+D"
    echo "==============================================="
    echo ""
}

# Function to start services in tmux
start_services_in_tmux() {
    local session="$SESSION_NAME"

    # Kill existing session if it exists
    if tmux has-session -t "$session" 2>/dev/null; then
        echo "⚠️  Killing existing tmux session '$session'..."
        tmux kill-session -t "$session"
    fi

    echo "Creating tmux session '$session'..."
    tmux new-session -d -s "$session"

    # Create an associative array to hold enabled components
    declare -A components
    local index=0

    # Add components to the components array
    if [ "$RUN_MAIN_APP" = true ]; then
        components["MainApp"]="bash $MAIN_APP_SCRIPT; bash"
        index=$((index + 1))
    fi

    if [ "$RUN_MAVLINK2REST" = true ]; then
        components["MAVLink2REST"]="bash $MAVLINK2REST_SCRIPT; bash"
        index=$((index + 1))
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        components["Dashboard"]="bash $DASHBOARD_SCRIPT; bash"
        index=$((index + 1))
    fi

    if [ "$COMBINED_VIEW" = true ]; then
        # Create a window with split panes for a combined view
        tmux rename-window -t "$session:0" "CombinedView"
        local pane_index=0
        for component_name in "${!components[@]}"; do
            if [ $pane_index -eq 0 ]; then
                tmux send-keys -t "$session:CombinedView.$pane_index" "clear; ${components[$component_name]}" C-m
            else
                tmux split-window -t "$session:CombinedView" -h
                tmux select-pane -t "$session:CombinedView.$pane_index"
                tmux send-keys -t "$session:CombinedView.$pane_index" "clear; ${components[$component_name]}" C-m
            fi
            pane_index=$((pane_index + 1))
        done

        if [ $pane_index -gt 1 ]; then
            tmux select-layout -t "$session:CombinedView" tiled
        fi
    else
        # Start components in separate windows
        local window_index=0
        for component_name in "${!components[@]}"; do
            if [ $window_index -eq 0 ]; then
                # Rename the first window (created by default)
                tmux rename-window -t "$session:0" "$component_name"
                tmux send-keys -t "$session:$component_name" "clear; ${components[$component_name]}" C-m
            else
                tmux new-window -t "$session" -n "$component_name"
                tmux send-keys -t "$session:$component_name" "clear; ${components[$component_name]}" C-m
            fi
            window_index=$((window_index + 1))
        done
    fi

    # Display tmux instructions before attaching
    show_tmux_instructions

    # Attach to the tmux session
    tmux attach-session -t "$session"
}

# Main execution sequence

echo "==============================================="
echo "  Initializing PixEagle System..."
echo "==============================================="
echo ""
echo "Note: This script assumes all configurations and initializations are complete."
echo "If not, please refer to the GitHub repository and documentation:"
echo "👉 https://github.com/alireza787b/PixEagle"
echo ""

# Check if required commands are installed
check_tmux_installed
check_command_installed "lsof" "lsof"

# Check and kill processes using default ports
echo "-----------------------------------------------"
echo "Checking and freeing up default ports..."
echo "-----------------------------------------------"
if [ "$RUN_MAVLINK2REST" = true ]; then
    check_and_kill_port "$MAVLINK2REST_PORT"
fi

if [ "$RUN_MAIN_APP" = true ]; then
    check_and_kill_port "$BACKEND_PORT"
fi

if [ "$RUN_DASHBOARD" = true ]; then
    check_and_kill_port "$DASHBOARD_PORT"
fi

# Function to run the PixEagle components
run_pixeagle_components() {
    echo ""
    echo "-----------------------------------------------"
    echo "Starting PixEagle components in tmux..."
    echo "-----------------------------------------------"

    if [ "$RUN_MAVLINK2REST" = true ]; then
        echo "✅ MAVLink2REST will be started."
    else
        echo "❌ MAVLink2REST is disabled."
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        echo "✅ Dashboard will be started."
    else
        echo "❌ Dashboard is disabled."
    fi

    if [ "$RUN_MAIN_APP" = true ]; then
        echo "✅ Main Python Application will be started."
    else
        echo "❌ Main Python Application is disabled."
    fi

    if [ "$COMBINED_VIEW" = true ]; then
        echo "Components will be started in a combined view (split panes)."
    else
        echo "Components will be started in separate tmux windows."
    fi

    start_services_in_tmux
}

# Run the components
run_pixeagle_components

echo ""
echo "==============================================="
echo "  PixEagle System Startup Complete!"
echo "==============================================="
echo ""
echo "All selected components are now running in tmux."
echo "You can detach from the session without stopping the services."
echo "Use 'tmux attach -t $SESSION_NAME' to reattach to the session."
echo ""
echo "To kill the tmux session and stop all components, run:"
echo "👉 tmux kill-session -t $SESSION_NAME"
echo ""
echo "To kill all tmux sessions (caution: this will kill all tmux sessions on the system), run:"
echo "👉 tmux kill-server"
echo ""
