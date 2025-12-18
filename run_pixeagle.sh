#!/bin/bash

#########################################
# PixEagle Complete System Launcher with Tmux Windows and Split Panes
#
# Project: PixEagle
# Author: Alireza Ghaderi
# Date: August 2024
#
# This script manages the execution of the entire PixEagle system,
# including MAVLink2REST, the React Dashboard, the main Python
# application, and the MAVSDK Server. Components are run either in
# separate tmux windows or combined in a single window with split panes,
# based on user preference.
#
# Usage:
#   ./run_pixeagle.sh [-m|-d|-p|-k|-s|-h]
#   Flags:
#     -m : Do NOT run MAVLink2REST (default: enabled)
#     -d : Do NOT run Dashboard (default: enabled)
#     -p : Do NOT run Main Python Application (default: enabled)
#     -k : Do NOT run MAVSDK Server (default: enabled)
#     -s : Run components in Separate windows (default: Combined view)
#     -h : Display help
#
# Example:
#   ./run_pixeagle.sh -p -s
#   (Runs MAVLink2REST, Dashboard, and MAVSDK Server in separate windows, skips the main Python application)
#
# Note:
#   This script assumes all configurations and initializations are complete.
#   If not, please refer to the GitHub repository and documentation:
#   https://github.com/alireza787b/PixEagle
#
#########################################

# Get script directory for sourcing common functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source shared functions (colors, logging, banner)
source "$SCRIPT_DIR/scripts/common.sh"

# Default flag values (all components enabled by default)
RUN_MAVLINK2REST=true
RUN_DASHBOARD=true
RUN_MAIN_APP=true
RUN_MAVSDK_SERVER=true
COMBINED_VIEW=true  # Default is combined view

# Development and build flags
DEVELOPMENT_MODE=false
FORCE_REBUILD=false

# Tmux session name
SESSION_NAME="PixEagle"

# Default ports used by the components
MAVLINK2REST_PORT=8088
BACKEND_PORT=5077
DASHBOARD_PORT=3000

# Paths to component scripts (modify these paths if your directory structure is different)
BASE_DIR="$HOME/PixEagle"
MAVLINK2REST_SCRIPT="$BASE_DIR/src/tools/mavlink2rest/run_mavlink2rest.sh"
DASHBOARD_SCRIPT="$BASE_DIR/run_dashboard.sh"
MAIN_APP_SCRIPT="$BASE_DIR/run_main.sh"
MAVSDK_SERVER_BINARY="$BASE_DIR/mavsdk_server_bin"
MAVSDK_SERVER_DOWNLOAD_SCRIPT="$BASE_DIR/src/tools/download_mavsdk_server.sh"

# Function to display usage instructions
display_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "🚀 MAIN OPTIONS:"
    echo "  --dev              Run in development mode (dashboard dev server + backend reload)"
    echo "  --rebuild          Force rebuild of all components (dashboard + backend)"
    echo ""
    echo "🔧 COMPONENT CONTROL:"
    echo "  -m                 Do NOT run MAVLink2REST (default: enabled)"
    echo "  -d                 Do NOT run Dashboard (default: enabled)"
    echo "  -p                 Do NOT run Main Python Application (default: enabled)"
    echo "  -k                 Do NOT run MAVSDK Server (default: enabled)"
    echo "  -s                 Run components in Separate tmux windows (default: Combined view)"
    echo "  -h, --help         Display this help message"
    echo ""
    echo "📖 EXAMPLES:"
    echo "  $0                 # Standard production mode"
    echo "  $0 --dev           # Development mode with hot-reload"
    echo "  $0 --rebuild       # Force rebuild everything in production mode"
    echo "  $0 --dev --rebuild # Development mode with force rebuild"
    echo "  $0 -p -s           # Skip Python app, separate windows"
    echo ""
    echo "💡 Development mode provides:"
    echo "   • Dashboard hot-reload with live changes"
    echo "   • Backend auto-restart on file changes (if supported)"
    echo "   • Enhanced debugging and error reporting"
    echo ""
    echo "🔨 Rebuild mode forces:"
    echo "   • Complete npm rebuild for dashboard"
    echo "   • Fresh dependency installation"
    echo "   • Clean build artifacts"
}

display_banner() {
    display_pixeagle_banner "${ROCKET} PixEagle System Launcher" \
        "For documentation: https://github.com/alireza787b/PixEagle"
    sleep 1  # Wait for 1 second
}


# Parse command-line options (support both short and long options)
while [[ $# -gt 0 ]]; do
  case $1 in
    --dev)
      DEVELOPMENT_MODE=true
      shift
      ;;
    --rebuild)
      FORCE_REBUILD=true
      shift
      ;;
    -m)
      RUN_MAVLINK2REST=false
      shift
      ;;
    -d)
      RUN_DASHBOARD=false
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
    -s)
      COMBINED_VIEW=false
      shift
      ;;
    -h|--help)
      display_usage
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1"
      echo ""
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
    local service_name="${2:-Service}"

    # Ensure lsof is installed
    check_command_installed "lsof" "lsof"

    # Find the process ID (PID) using the port
    pid=$(lsof -t -i :"$port" 2>/dev/null)

    if [ -n "$pid" ]; then
        # Get the process name and command
        process_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        process_cmd=$(ps -p "$pid" -o args= 2>/dev/null | head -c 50 || echo "unknown command")

        echo "⚠️  Port $port is occupied by $service_name"
        echo "   Process: $process_name (PID: $pid)"
        echo "   Command: $process_cmd"

        # Try graceful termination first
        echo "🔄 Attempting graceful shutdown..."
        kill -TERM "$pid" 2>/dev/null
        sleep 2

        # Check if process is still running
        if kill -0 "$pid" 2>/dev/null; then
            echo "🔄 Process still running, force killing..."
            kill -9 "$pid" 2>/dev/null
            sleep 1
        fi

        # Verify the process was killed
        if kill -0 "$pid" 2>/dev/null; then
            echo "❌ Failed to kill process $pid on port $port"
            echo "⚠️  Manual intervention may be required"
        else
            echo "✅ $service_name on port $port stopped successfully"
        fi
    else
        echo "✅ Port $port is free for $service_name"
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

# Function to check and prepare the MAVSDK Server binary
prepare_mavsdk_server() {
    if [ -f "$MAVSDK_SERVER_BINARY" ]; then
        echo "✅ MAVSDK Server binary found."
    else
        echo "⚠️  MAVSDK Server binary not found at '$MAVSDK_SERVER_BINARY'."
        echo ""
        echo "You can:"
        echo "1. Manually download the MAVSDK Server binary from:"
        echo "   👉 https://github.com/mavlink/MAVSDK/releases/"
        echo "   Then rename it to 'mavsdk_server_bin' and place it in the project root directory."
        echo "2. Automatically download it using the provided script."
        echo ""
        read -p "Press Enter to automatically download or Ctrl+C to cancel and download manually..."

        # Check if the download script exists
        if [ -f "$MAVSDK_SERVER_DOWNLOAD_SCRIPT" ]; then
            echo "Downloading MAVSDK Server binary..."
            bash "$MAVSDK_SERVER_DOWNLOAD_SCRIPT"
            if [ -f "$MAVSDK_SERVER_BINARY" ]; then
                echo "✅ MAVSDK Server binary downloaded successfully."
                chmod +x "$MAVSDK_SERVER_BINARY"
            else
                echo "❌ Failed to download MAVSDK Server binary. Please download it manually."
                exit 1
            fi
        else
            echo "❌ Download script not found at '$MAVSDK_SERVER_DOWNLOAD_SCRIPT'. Please download the binary manually."
            exit 1
        fi
    fi
}

# Function to perform comprehensive cleanup before starting
perform_comprehensive_cleanup() {
    echo ""
    echo "==============================================="
    echo "🧹 Performing Comprehensive System Cleanup"
    echo "==============================================="

    # 1. Check for any PixEagle-related processes
    echo "🔍 Scanning for running PixEagle processes..."
    local pixeagle_processes=$(ps aux | grep -i pixeagle | grep -v grep | wc -l)
    if [ "$pixeagle_processes" -gt 0 ]; then
        echo "⚠️  Found $pixeagle_processes PixEagle-related process(es)"
        ps aux | grep -i pixeagle | grep -v grep | head -5
        echo "🔄 These will be cleaned up by port and session cleanup"
    else
        echo "✅ No stray PixEagle processes detected"
    fi

    # 2. Check for Python processes on our ports (more targeted)
    echo ""
    echo "🔍 Checking for Python processes on PixEagle ports..."
    local python_on_ports=0
    for port in $MAVLINK2REST_PORT $BACKEND_PORT $DASHBOARD_PORT; do
        if lsof -i ":$port" 2>/dev/null | grep -q python; then
            python_on_ports=$((python_on_ports + 1))
        fi
    done

    if [ "$python_on_ports" -gt 0 ]; then
        echo "⚠️  Found Python processes on $python_on_ports PixEagle port(s)"
    else
        echo "✅ No Python processes blocking PixEagle ports"
    fi

    # 3. Check for any orphaned tmux servers
    echo ""
    echo "🔍 Checking tmux server status..."
    if tmux list-sessions 2>/dev/null | grep -q .; then
        local session_count=$(tmux list-sessions 2>/dev/null | wc -l)
        echo "ℹ️  Found $session_count existing tmux session(s)"
        tmux list-sessions 2>/dev/null | head -3
    else
        echo "✅ No existing tmux sessions found"
    fi

    echo ""
    echo "✅ System cleanup scan completed"
    echo "==============================================="
}

# Function to start services in tmux
start_services_in_tmux() {
    local session="$SESSION_NAME"

    # Enhanced tmux session cleanup
    if tmux has-session -t "$session" 2>/dev/null; then
        echo "⚠️  Existing PixEagle tmux session found"
        echo "🔄 Performing clean shutdown of previous session..."

        # Get session info before killing
        local session_windows=$(tmux list-windows -t "$session" 2>/dev/null | wc -l)
        echo "   Previous session had $session_windows window(s)"

        # Send interrupt to all panes first (graceful)
        tmux list-panes -t "$session" -F "#{session_name}:#{window_index}.#{pane_index}" 2>/dev/null | \
        while read pane; do
            tmux send-keys -t "$pane" C-c 2>/dev/null || true
        done

        # Wait a moment for graceful shutdown
        sleep 2

        # Kill the session
        tmux kill-session -t "$session" 2>/dev/null
        sleep 1

        # Verify session was killed
        if tmux has-session -t "$session" 2>/dev/null; then
            echo "⚠️  Session still exists, forcing tmux server restart..."
            tmux kill-server 2>/dev/null || true
            sleep 2
        fi

        echo "✅ Previous PixEagle session cleaned up successfully"
    fi

    echo "Creating tmux session '$session'..."
    tmux new-session -d -s "$session"

    # Create an associative array to hold enabled components
    declare -A components
    local index=0

    # Add components to the components array with development/rebuild flags
    if [ "$RUN_MAIN_APP" = true ]; then
        local main_cmd="bash $MAIN_APP_SCRIPT"
        # Add development mode flag for Python backend if supported
        if [ "$DEVELOPMENT_MODE" = true ]; then
            main_cmd="bash $MAIN_APP_SCRIPT --dev"
        fi
        components["MainApp"]="$main_cmd; bash"
        index=$((index + 1))
    fi

    if [ "$RUN_MAVLINK2REST" = true ]; then
        components["MAVLink2REST"]="bash $MAVLINK2REST_SCRIPT; bash"
        index=$((index + 1))
    fi

    if [ "$RUN_DASHBOARD" = true ]; then
        local dashboard_cmd="bash $DASHBOARD_SCRIPT"

        # Add development mode flag
        if [ "$DEVELOPMENT_MODE" = true ]; then
            dashboard_cmd="$dashboard_cmd -d"
        fi

        # Add force rebuild flag
        if [ "$FORCE_REBUILD" = true ]; then
            dashboard_cmd="$dashboard_cmd -f"
        fi

        components["Dashboard"]="$dashboard_cmd; bash"
        index=$((index + 1))
    fi

    if [ "$RUN_MAVSDK_SERVER" = true ]; then
        components["MAVSDKServer"]="cd $BASE_DIR; ./mavsdk_server_bin; bash"
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

# Prepare MAVSDK Server if it's going to be run
if [ "$RUN_MAVSDK_SERVER" = true ]; then
    prepare_mavsdk_server
fi

# Perform comprehensive system cleanup
perform_comprehensive_cleanup

# Check and kill processes using default ports
echo ""
echo "-----------------------------------------------"
echo "🔧 Cleaning up ports and processes..."
echo "-----------------------------------------------"
if [ "$RUN_MAVLINK2REST" = true ]; then
    check_and_kill_port "$MAVLINK2REST_PORT" "MAVLink2REST"
fi

if [ "$RUN_MAIN_APP" = true ]; then
    check_and_kill_port "$BACKEND_PORT" "Main Python App"
fi

if [ "$RUN_DASHBOARD" = true ]; then
    check_and_kill_port "$DASHBOARD_PORT" "Dashboard"
fi

# Final verification that system is clean
echo ""
echo "🔍 Final cleanup verification..."
local cleanup_issues=0

# Check if any PixEagle tmux sessions still exist
if tmux list-sessions 2>/dev/null | grep -q "$SESSION_NAME"; then
    echo "⚠️  PixEagle tmux session still exists after cleanup"
    cleanup_issues=$((cleanup_issues + 1))
fi

# Check if any processes are still on our ports
for port in $MAVLINK2REST_PORT $BACKEND_PORT $DASHBOARD_PORT; do
    if lsof -i ":$port" 2>/dev/null | grep -q .; then
        echo "⚠️  Port $port still occupied after cleanup"
        cleanup_issues=$((cleanup_issues + 1))
    fi
done

if [ "$cleanup_issues" -eq 0 ]; then
    echo "✅ System is clean and ready for PixEagle startup"
else
    echo "⚠️  $cleanup_issues issue(s) detected but proceeding with startup"
    echo "💡 If startup fails, try running the script again or reboot the system"
fi

echo "==============================================="

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

    if [ "$RUN_MAVSDK_SERVER" = true ]; then
        echo "✅ MAVSDK Server will be started."
    else
        echo "❌ MAVSDK Server is disabled."
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
