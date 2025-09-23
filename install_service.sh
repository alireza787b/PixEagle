#!/bin/bash

#########################################
# PixEagle Service Installation Script
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
#
# This script installs the PixEagle service management system,
# making it available system-wide as 'pixeagle-service' command.
# It provides automatic detection, validation, and setup with
# comprehensive user guidance.
#
# Features:
# - Automatic environment detection and validation
# - Flexible user and path configuration
# - System-wide command installation
# - Comprehensive error handling and rollback
# - User-friendly setup guidance
# - Plug-and-play installation
#
# Usage: bash install_service.sh
#
#########################################

# Installation configuration
INSTALL_DIR="/usr/local/bin"
SERVICE_COMMAND="pixeagle-service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

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
        "header")  echo -e "${WHITE}🚀 $message${NC}" ;;
        *)         echo -e "${WHITE}$message${NC}" ;;
    esac
}

# Function to display installation banner
show_banner() {
    cat << "EOF"

  _____ _      ______            _
 |  __ (_)    |  ____|          | |
 | |__) |__  _| |__   __ _  __ _| | ___
 |  ___/ \ \/ /  __| / _` |/ _` | |/ _ \
 | |   | |>  <| |___| (_| | (_| | |  __/
 |_|   |_/_/\_\______\__,_|\__, |_|\___|
                            __/ |
                           |___/

┌─────────────────────────────────────────────────────────────────┐
│              PixEagle Service Installation Script               │
│                                                                 │
│ This installer will set up the PixEagle service management     │
│ system, making it available as a system-wide command.          │
└─────────────────────────────────────────────────────────────────┘

EOF
}

# Function to check if running as root
check_root_privileges() {
    if [ "$EUID" -ne 0 ]; then
        print_status "error" "This installer must be run as root"
        print_status "info" "Please run: sudo bash install_service.sh"
        exit 1
    fi
}

# Function to detect and validate environment
validate_environment() {
    print_status "process" "Validating installation environment..."

    # Check operating system
    if [ ! -f /etc/os-release ]; then
        print_status "error" "Cannot detect operating system"
        return 1
    fi

    local os_info=$(grep "^ID=" /etc/os-release | cut -d'=' -f2 | tr -d '"')
    print_status "info" "Detected OS: $os_info"

    # Check if systemd is available
    if ! command -v systemctl &>/dev/null; then
        print_status "error" "systemd is required but not found"
        print_status "note" "This service system requires systemd-based Linux distribution"
        return 1
    fi

    # Check required commands
    local missing_deps=()
    for cmd in tmux; do
        if ! command -v "$cmd" &>/dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_status "warning" "Missing dependencies: ${missing_deps[*]}"
        print_status "process" "Installing missing dependencies..."

        if command -v apt-get &>/dev/null; then
            apt-get update && apt-get install -y "${missing_deps[@]}"
        elif command -v yum &>/dev/null; then
            yum install -y "${missing_deps[@]}"
        elif command -v pacman &>/dev/null; then
            pacman -S --noconfirm "${missing_deps[@]}"
        else
            print_status "error" "Cannot auto-install dependencies. Please install: ${missing_deps[*]}"
            return 1
        fi
    fi

    print_status "success" "Environment validation completed"
    return 0
}

# Function to detect PixEagle installation
detect_pixeagle() {
    print_status "process" "Detecting PixEagle installation..."

    # Get the actual user (not root when using sudo)
    local target_user
    if [ -n "$SUDO_USER" ]; then
        target_user="$SUDO_USER"
    else
        print_status "error" "Cannot detect target user. Please run with sudo."
        return 1
    fi

    local user_home="/home/$target_user"
    local pixeagle_locations=(
        "$user_home/PixEagle"
        "$SCRIPT_DIR"
        "/opt/PixEagle"
        "$user_home/Projects/PixEagle"
        "$user_home/Desktop/PixEagle"
    )

    local pixeagle_dir=""
    for location in "${pixeagle_locations[@]}"; do
        if [ -f "$location/run_pixeagle.sh" ]; then
            pixeagle_dir="$location"
            break
        fi
    done

    if [ -z "$pixeagle_dir" ]; then
        print_status "error" "PixEagle installation not found"
        print_status "info" "Searched in:"
        for location in "${pixeagle_locations[@]}"; do
            print_status "note" "  - $location"
        done
        print_status "info" "Please ensure PixEagle is properly installed"
        return 1
    fi

    print_status "success" "PixEagle found at: $pixeagle_dir"
    print_status "info" "Target user: $target_user"

    # Export for use by other functions
    export PIXEAGLE_DIR="$pixeagle_dir"
    export TARGET_USER="$target_user"
    export TARGET_HOME="$user_home"

    return 0
}

# Function to validate PixEagle installation
validate_pixeagle() {
    print_status "process" "Validating PixEagle installation..."

    local required_files=(
        "run_pixeagle.sh"
        "src/tools/service_utils.sh"
        "pixeagle-service"
    )

    local missing_files=()
    for file in "${required_files[@]}"; do
        if [ ! -f "$PIXEAGLE_DIR/$file" ]; then
            missing_files+=("$file")
        fi
    done

    if [ ${#missing_files[@]} -gt 0 ]; then
        print_status "error" "Missing required files in PixEagle installation:"
        for file in "${missing_files[@]}"; do
            print_status "note" "  - $file"
        done
        return 1
    fi

    # Check if PixEagle appears to be properly configured
    if [ ! -f "$PIXEAGLE_DIR/configs/config.yaml" ] && [ ! -f "$PIXEAGLE_DIR/configs/config_default.yaml" ]; then
        print_status "warning" "PixEagle configuration files not found"
        print_status "note" "Run 'bash init_pixeagle.sh' to initialize PixEagle first"
    fi

    print_status "success" "PixEagle installation validation completed"
    return 0
}

# Function to install service command
install_service_command() {
    print_status "process" "Installing pixeagle-service command..."

    local source_script="$PIXEAGLE_DIR/pixeagle-service"
    local target_script="$INSTALL_DIR/$SERVICE_COMMAND"

    # Check if target directory exists
    if [ ! -d "$INSTALL_DIR" ]; then
        print_status "process" "Creating installation directory: $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
    fi

    # Copy and modify the service script to include proper paths
    print_status "process" "Creating system-wide service command..."

    cat > "$target_script" << EOF
#!/bin/bash
# PixEagle Service Management Tool - System Installation
# Auto-generated by install_service.sh

# Set the correct PixEagle directory
export PIXEAGLE_INSTALL_DIR="$PIXEAGLE_DIR"

# Execute the actual service script
exec bash "$PIXEAGLE_DIR/pixeagle-service" "\$@"
EOF

    # Make executable
    chmod +x "$target_script"

    # Verify installation
    if [ -x "$target_script" ]; then
        print_status "success" "Service command installed: $target_script"
        return 0
    else
        print_status "error" "Failed to install service command"
        return 1
    fi
}

# Function to set up file permissions
setup_permissions() {
    print_status "process" "Setting up file permissions..."

    # Make scripts executable
    chmod +x "$PIXEAGLE_DIR/pixeagle-service"
    chmod +x "$PIXEAGLE_DIR/run_pixeagle_service.sh"
    chmod +x "$PIXEAGLE_DIR/src/tools/service_utils.sh"

    # Set ownership to target user
    chown -R "$TARGET_USER:$TARGET_USER" "$PIXEAGLE_DIR"

    # Ensure service utilities are readable by all
    chmod 644 "$PIXEAGLE_DIR/src/tools/service_utils.sh"

    print_status "success" "File permissions configured"
}

# Function to test installation
test_installation() {
    print_status "process" "Testing installation..."

    # Test if command is available
    if command -v "$SERVICE_COMMAND" &>/dev/null; then
        print_status "success" "Command '$SERVICE_COMMAND' is available"
    else
        print_status "error" "Command '$SERVICE_COMMAND' not found in PATH"
        return 1
    fi

    # Test help command
    if "$SERVICE_COMMAND" help &>/dev/null; then
        print_status "success" "Service command is functional"
    else
        print_status "warning" "Service command may have issues (check manually)"
    fi

    print_status "success" "Installation test completed"
    return 0
}

# Function to show post-installation instructions
show_completion_message() {
    print_status "header" "Installation Complete!"
    echo
    print_status "success" "PixEagle service management system has been installed successfully"
    echo
    print_status "info" "Available commands:"
    print_status "note" "  pixeagle-service start     - Start PixEagle immediately"
    print_status "note" "  pixeagle-service stop      - Stop PixEagle"
    print_status "note" "  pixeagle-service status    - Show detailed status"
    print_status "note" "  pixeagle-service enable    - Enable auto-start on boot"
    print_status "note" "  pixeagle-service disable   - Disable auto-start"
    print_status "note" "  pixeagle-service logs      - Show service logs"
    print_status "note" "  pixeagle-service attach    - Access tmux session"
    print_status "note" "  pixeagle-service help      - Show detailed help"
    echo
    print_status "info" "Quick start:"
    print_status "note" "  1. Test: pixeagle-service status"
    print_status "note" "  2. Start: pixeagle-service start"
    print_status "note" "  3. Enable auto-start: sudo pixeagle-service enable"
    echo
    print_status "info" "For more information, visit:"
    print_status "note" "  https://github.com/alireza787b/PixEagle"
    echo
}

# Function to handle installation errors
handle_installation_error() {
    print_status "error" "Installation failed"
    print_status "info" "Cleaning up partial installation..."

    # Remove service command if it was installed
    if [ -f "$INSTALL_DIR/$SERVICE_COMMAND" ]; then
        rm -f "$INSTALL_DIR/$SERVICE_COMMAND"
        print_status "info" "Removed service command"
    fi

    print_status "info" "Please check the error messages above and try again"
    exit 1
}

# Function to uninstall service
uninstall_service() {
    print_status "process" "Uninstalling PixEagle service management..."

    # Remove service command
    if [ -f "$INSTALL_DIR/$SERVICE_COMMAND" ]; then
        rm -f "$INSTALL_DIR/$SERVICE_COMMAND"
        print_status "success" "Removed service command"
    fi

    # Disable service if it exists
    if systemctl list-unit-files | grep -q "pixeagle.service"; then
        print_status "process" "Disabling and removing systemd service..."
        systemctl stop pixeagle.service 2>/dev/null || true
        systemctl disable pixeagle.service 2>/dev/null || true
        rm -f /etc/systemd/system/pixeagle.service
        systemctl daemon-reload
        print_status "success" "Systemd service removed"
    fi

    print_status "success" "PixEagle service management uninstalled"
}

# Main installation process
main() {
    # Handle command line arguments
    case "${1:-}" in
        "uninstall"|"remove")
            show_banner
            check_root_privileges
            uninstall_service
            exit 0
            ;;
        "help"|"--help"|"-h")
            show_banner
            echo "Usage: sudo bash install_service.sh [uninstall]"
            echo
            echo "Commands:"
            echo "  (no args)  - Install PixEagle service management"
            echo "  uninstall  - Remove PixEagle service management"
            echo "  help       - Show this help message"
            exit 0
            ;;
    esac

    # Set up error handling
    set -e
    trap 'handle_installation_error' ERR

    # Main installation sequence
    show_banner
    check_root_privileges
    validate_environment
    detect_pixeagle
    validate_pixeagle
    install_service_command
    setup_permissions
    test_installation
    show_completion_message
}

# Execute main function
main "$@"