#!/bin/bash

#########################################
# PixEagle Service Management Utilities
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script provides utility functions for managing PixEagle
# as a system service. It includes user detection, service status
# checking, tmux session management, and installation helpers.
#
# Key Features:
# - Automatic user detection and flexible configuration
# - Robust error handling and status reporting
# - Tmux session management and health checking
# - Service installation and cleanup utilities
# - Cross-platform compatibility (Linux/Raspberry Pi)
#
#########################################

# Service configuration
SERVICE_NAME="pixeagle"
TMUX_SESSION_NAME="PixEagle"
SERVICE_DESCRIPTION="PixEagle UAV Tracking and Control System"

# Auto-detect project paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_TOOLS_DIR="$PROJECT_ROOT/src/tools"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Function to detect current user and set service user
detect_service_user() {
    # Get the actual user (not root if using sudo)
    if [ -n "$SUDO_USER" ]; then
        SERVICE_USER="$SUDO_USER"
        SERVICE_HOME="/home/$SUDO_USER"
    else
        SERVICE_USER="$(whoami)"
        SERVICE_HOME="$HOME"
    fi

    # Validate user exists
    if ! id "$SERVICE_USER" &>/dev/null; then
        echo -e "${RED}❌ User '$SERVICE_USER' does not exist${NC}"
        return 1
    fi

    # Set service paths based on detected user
    SERVICE_HOME="$(eval echo ~$SERVICE_USER)"
    USER_PIXEAGLE_DIR="$SERVICE_HOME/PixEagle"

    # Validate PixEagle directory exists
    if [ ! -d "$USER_PIXEAGLE_DIR" ]; then
        echo -e "${YELLOW}⚠️  PixEagle directory not found at: $USER_PIXEAGLE_DIR${NC}"
        echo -e "${BLUE}💡 Checking current directory...${NC}"

        # Try current directory or script location
        if [ -f "$PROJECT_ROOT/run_pixeagle.sh" ]; then
            USER_PIXEAGLE_DIR="$PROJECT_ROOT"
            echo -e "${GREEN}✅ Found PixEagle at: $USER_PIXEAGLE_DIR${NC}"
        else
            echo -e "${RED}❌ PixEagle installation not found${NC}"
            return 1
        fi
    fi

    export SERVICE_USER SERVICE_HOME USER_PIXEAGLE_DIR
    return 0
}

# Function to display colored status messages
print_status() {
    local status="$1"
    local message="$2"

    case "$status" in
        "info")    echo -e "${BLUE}ℹ️  $message${NC}" ;;
        "success") echo -e "${GREEN}✅ $message${NC}" ;;
        "warning") echo -e "${YELLOW}⚠️  $message${NC}" ;;
        "error")   echo -e "${RED}❌ $message${NC}" ;;
        "process") echo -e "${CYAN}🔄 $message${NC}" ;;
        "note")    echo -e "${PURPLE}📝 $message${NC}" ;;
        *)         echo -e "${WHITE}$message${NC}" ;;
    esac
}

# Function to check if service is installed
is_service_installed() {
    systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"
}

# Function to check if service is enabled
is_service_enabled() {
    systemctl is-enabled "${SERVICE_NAME}.service" &>/dev/null
}

# Function to check if service is active
is_service_active() {
    systemctl is-active "${SERVICE_NAME}.service" &>/dev/null
}

# Function to check if tmux session exists
is_tmux_session_active() {
    if command -v tmux &>/dev/null; then
        sudo -u "$SERVICE_USER" tmux has-session -t "$TMUX_SESSION_NAME" 2>/dev/null
    else
        return 1
    fi
}

# Function to get tmux session status
get_tmux_session_status() {
    if is_tmux_session_active; then
        local session_info
        session_info=$(sudo -u "$SERVICE_USER" tmux display-message -t "$TMUX_SESSION_NAME" -p "#{session_windows}")
        echo "Active ($session_info windows)"
    else
        echo "Not running"
    fi
}

# Function to check PixEagle component health
check_component_health() {
    local component="$1"
    local port="$2"

    if command -v lsof &>/dev/null; then
        if lsof -i ":$port" &>/dev/null; then
            echo -e "${GREEN}●${NC} $component (port $port)"
        else
            echo -e "${RED}●${NC} $component (port $port) - Not responding"
        fi
    else
        echo -e "${YELLOW}●${NC} $component (port $port) - Cannot check (lsof not available)"
    fi
}

# Function to get comprehensive service status
get_service_status() {
    local status_output=""

    # Detect user first
    if ! detect_service_user; then
        return 1
    fi

    echo "📊 PixEagle Service Status Report"
    echo "=================================="
    echo

    # Basic service information
    echo "🔧 Service Configuration:"
    echo "   User: $SERVICE_USER"
    echo "   Home: $SERVICE_HOME"
    echo "   Project: $USER_PIXEAGLE_DIR"
    echo

    # Service installation status
    echo "📦 Installation Status:"
    if is_service_installed; then
        print_status "success" "Service is installed"

        if is_service_enabled; then
            print_status "success" "Auto-start is enabled"
        else
            print_status "warning" "Auto-start is disabled"
        fi
    else
        print_status "warning" "Service is not installed"
        print_status "note" "Run 'sudo pixeagle-service enable' to install"
    fi
    echo

    # Runtime status
    echo "🚀 Runtime Status:"
    if is_service_active; then
        print_status "success" "Systemd service is active"
    else
        print_status "warning" "Systemd service is not active"
    fi

    local tmux_status
    tmux_status=$(get_tmux_session_status)
    if [ "$tmux_status" != "Not running" ]; then
        print_status "success" "Tmux session: $tmux_status"
    else
        print_status "warning" "Tmux session: Not running"
    fi
    echo

    # Component health check
    echo "🧩 Component Health:"
    check_component_health "MAVLink2REST" "8088"
    check_component_health "Main Python App" "5077"
    check_component_health "Dashboard" "3000"
    echo

    # Access information
    if is_tmux_session_active; then
        echo "🖥️  Access Information:"
        print_status "info" "Dashboard: http://localhost:3000"
        print_status "info" "Tmux session: sudo -u $SERVICE_USER tmux attach -t $TMUX_SESSION_NAME"
        print_status "note" "Or use: pixeagle-service attach"
    fi
}

# Function to check prerequisites
check_prerequisites() {
    local missing_deps=()

    # Check required commands
    for cmd in tmux systemctl; do
        if ! command -v "$cmd" &>/dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    # Check PixEagle files
    if ! detect_service_user; then
        return 1
    fi

    if [ ! -f "$USER_PIXEAGLE_DIR/run_pixeagle.sh" ]; then
        print_status "error" "PixEagle launcher script not found: $USER_PIXEAGLE_DIR/run_pixeagle.sh"
        return 1
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_status "error" "Missing dependencies: ${missing_deps[*]}"
        print_status "info" "Install with: sudo apt update && sudo apt install -y ${missing_deps[*]}"
        return 1
    fi

    return 0
}

# Function to create systemd service file
create_service_file() {
    if ! detect_service_user; then
        return 1
    fi

    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"

    print_status "process" "Creating systemd service file..."

    cat > "$service_file" << EOF
[Unit]
Description=$SERVICE_DESCRIPTION
Documentation=https://github.com/alireza787b/PixEagle
Wants=network-online.target
After=network.target network-online.target

[Service]
Type=forking
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$USER_PIXEAGLE_DIR
Environment=HOME=$SERVICE_HOME
Environment=USER=$SERVICE_USER
ExecStart=$USER_PIXEAGLE_DIR/run_pixeagle_service.sh
ExecStop=$USER_PIXEAGLE_DIR/src/tools/stop_pixeagle_service.sh
Restart=on-failure
RestartSec=10
KillMode=mixed
TimeoutStartSec=60
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -eq 0 ]; then
        print_status "success" "Service file created: $service_file"
        return 0
    else
        print_status "error" "Failed to create service file"
        return 1
    fi
}

# Function to remove service
remove_service() {
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"

    print_status "process" "Removing PixEagle service..."

    # Stop and disable service if active
    if is_service_active; then
        systemctl stop "${SERVICE_NAME}.service"
    fi

    if is_service_enabled; then
        systemctl disable "${SERVICE_NAME}.service"
    fi

    # Remove service file
    if [ -f "$service_file" ]; then
        rm -f "$service_file"
        systemctl daemon-reload
        print_status "success" "Service removed successfully"
    else
        print_status "warning" "Service file not found"
    fi
}

# Function to get service logs
show_service_logs() {
    local lines="${1:-50}"
    local follow="${2:-false}"

    if is_service_installed; then
        if [ "$follow" = "true" ]; then
            journalctl -u "${SERVICE_NAME}.service" -f
        else
            journalctl -u "${SERVICE_NAME}.service" -n "$lines" --no-pager
        fi
    else
        print_status "warning" "Service is not installed"
        return 1
    fi
}

# Function to attach to tmux session
attach_to_session() {
    if ! detect_service_user; then
        return 1
    fi

    if is_tmux_session_active; then
        print_status "info" "Attaching to PixEagle tmux session..."
        print_status "note" "Use Ctrl+B, then D to detach without stopping PixEagle"
        echo
        exec sudo -u "$SERVICE_USER" tmux attach -t "$TMUX_SESSION_NAME"
    else
        print_status "warning" "PixEagle tmux session is not running"
        print_status "info" "Start PixEagle first with: pixeagle-service start"
        return 1
    fi
}

# Export functions for use in other scripts
export -f detect_service_user print_status is_service_installed is_service_enabled
export -f is_service_active is_tmux_session_active get_service_status check_prerequisites
export -f create_service_file remove_service show_service_logs attach_to_session