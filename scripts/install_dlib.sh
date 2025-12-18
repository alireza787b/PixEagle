#!/bin/bash

# scripts/install_dlib.sh
# Intelligent dlib installation script for PixEagle
# Auto-detects system resources and handles low-memory systems automatically
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# Date: January 2025
# Author: Alireza Ghaderi

set -e  # Exit on error

# Get script directory for sourcing common functions
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source shared functions (colors, logging, banner)
source "$SCRIPT_DIR/common.sh"

# Banner
display_banner() {
    display_pixeagle_banner "${PACKAGE} dlib Installation" \
        "GitHub: https://github.com/alireza787b/PixEagle"
}

# Script-specific logging (non-indented style)
log_info() {
    echo -e "${BLUE}${INFO}${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}${WARN}${NC} $1"
}

# Check if venv exists
check_venv() {
    log_section "Step 1: Checking Virtual Environment"

    if [ ! -d "venv" ]; then
        log_error "Virtual environment not found!"
        log_info "Please run 'bash init_pixeagle.sh' first to set up PixEagle."
        exit 1
    fi

    log_success "Virtual environment found"
}

# Check if dlib already installed
check_existing_dlib() {
    log_section "Step 2: Checking Existing Installation"

    source venv/bin/activate

    if python -c "import dlib" 2>/dev/null; then
        DLIB_VERSION=$(python -c "import dlib; print(dlib.__version__ if hasattr(dlib, '__version__') else 'unknown')")
        log_success "dlib is already installed (version: $DLIB_VERSION)"
        echo -e "\n${GREEN}No installation needed. You're ready to use the dlib tracker!${NC}\n"
        deactivate
        exit 0
    fi

    log_info "dlib not found - proceeding with installation"
    deactivate
}

# Detect system memory
detect_memory() {
    log_section "Step 3: Detecting System Memory"

    # Get total RAM in MB
    if command -v free &> /dev/null; then
        TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
    else
        log_warning "Cannot detect memory automatically"
        TOTAL_RAM=4000  # Assume sufficient memory
    fi

    log_info "Total system RAM: ${TOTAL_RAM}MB"

    # Determine if low memory system
    if [ "$TOTAL_RAM" -lt 3000 ]; then
        LOW_MEMORY=true
        log_warning "Low memory system detected (< 3GB)"
        log_info "Will use swap file to prevent build failures"
    else
        LOW_MEMORY=false
        log_success "Sufficient memory detected (>= 3GB)"
        log_info "Direct installation will be used"
    fi
}

# Backup swap configuration
backup_swap_config() {
    log_info "Backing up swap configuration..."

    # Check if running on Raspberry Pi with dphys-swapfile
    if [ -f "/etc/dphys-swapfile" ]; then
        sudo cp /etc/dphys-swapfile /etc/dphys-swapfile.backup
        log_success "Swap config backed up to /etc/dphys-swapfile.backup"
        SWAP_METHOD="dphys"
    elif [ -f "/etc/default/swapfile" ]; then
        sudo cp /etc/default/swapfile /etc/default/swapfile.backup
        log_success "Swap config backed up"
        SWAP_METHOD="swapfile"
    else
        log_warning "No standard swap config found - will create swap file manually"
        SWAP_METHOD="manual"
    fi
}

# Create temporary swap
create_temp_swap() {
    log_section "Step 4: Creating Temporary Swap Space"

    log_info "This process will:"
    log_info "  1. Backup your current swap configuration"
    log_info "  2. Create a temporary 2GB swap file"
    log_info "  3. Install dlib"
    log_info "  4. Restore original swap configuration"
    echo ""
    log_warning "Your system settings will be automatically restored after installation."
    echo ""
    read -p "Proceed with swap modification? [yes/no]: " choice

    case "$choice" in
        yes|Yes|Y|y)
            log_info "User confirmed - proceeding..."
            ;;
        *)
            log_error "Installation cancelled by user"
            exit 1
            ;;
    esac

    backup_swap_config

    if [ "$SWAP_METHOD" == "dphys" ]; then
        # Raspberry Pi method
        log_info "Configuring swap using dphys-swapfile..."
        sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
        sudo dphys-swapfile setup
        sudo dphys-swapfile swapon
        log_success "Temporary 2GB swap activated"

    elif [ "$SWAP_METHOD" == "swapfile" ]; then
        # Generic swapfile method
        log_info "Configuring swap using swapfile..."
        sudo sed -i 's/^SWAPSIZE=.*/SWAPSIZE=2048/' /etc/default/swapfile
        sudo service swapfile restart
        log_success "Temporary 2GB swap activated"

    else
        # Manual method
        log_info "Creating manual swap file..."
        SWAP_FILE="/tmp/pixeagle_swap"

        # Create 2GB swap file
        sudo dd if=/dev/zero of=$SWAP_FILE bs=1M count=2048 status=progress
        sudo chmod 600 $SWAP_FILE
        sudo mkswap $SWAP_FILE
        sudo swapon $SWAP_FILE

        log_success "Temporary 2GB swap file created at $SWAP_FILE"
    fi

    # Verify swap
    CURRENT_SWAP=$(free -m | awk '/^Swap:/{print $2}')
    log_success "Current swap space: ${CURRENT_SWAP}MB"
}

# Install dlib
install_dlib() {
    log_section "Step 5: Installing dlib"

    source venv/bin/activate

    log_info "Starting dlib compilation..."
    log_warning "This may take 10-30 minutes depending on your system"
    echo ""

    # Upgrade pip first
    pip install --upgrade pip

    # Install dlib with verbose output
    if pip install dlib; then
        log_success "dlib installation completed successfully"
    else
        log_error "dlib installation failed"
        deactivate
        restore_swap
        exit 1
    fi

    deactivate
}

# Restore swap configuration
restore_swap() {
    log_section "Step 6: Restoring Original Swap Configuration"

    if [ "$LOW_MEMORY" != true ]; then
        log_info "Swap modification was not needed - skipping restore"
        return
    fi

    if [ "$SWAP_METHOD" == "dphys" ]; then
        log_info "Restoring dphys-swapfile configuration..."
        sudo cp /etc/dphys-swapfile.backup /etc/dphys-swapfile
        sudo dphys-swapfile setup
        sudo dphys-swapfile swapon
        log_success "Original swap configuration restored"

    elif [ "$SWAP_METHOD" == "swapfile" ]; then
        log_info "Restoring swapfile configuration..."
        sudo cp /etc/default/swapfile.backup /etc/default/swapfile
        sudo service swapfile restart
        log_success "Original swap configuration restored"

    else
        # Manual cleanup
        log_info "Removing temporary swap file..."
        SWAP_FILE="/tmp/pixeagle_swap"
        if [ -f "$SWAP_FILE" ]; then
            sudo swapoff $SWAP_FILE
            sudo rm -f $SWAP_FILE
            log_success "Temporary swap file removed"
        fi
    fi

    # Verify final swap
    FINAL_SWAP=$(free -m | awk '/^Swap:/{print $2}')
    log_info "Final swap space: ${FINAL_SWAP}MB"
}

# Verify installation
verify_installation() {
    log_section "Step 7: Verifying Installation"

    source venv/bin/activate

    if python -c "import dlib" 2>/dev/null; then
        DLIB_VERSION=$(python -c "import dlib; print(dlib.__version__ if hasattr(dlib, '__version__') else 'installed')")
        log_success "dlib successfully installed and verified!"
        log_info "Version: $DLIB_VERSION"
    else
        log_error "Installation verification failed"
        log_error "dlib was installed but cannot be imported"
        deactivate
        exit 1
    fi

    deactivate
}

# Display usage instructions
show_usage_instructions() {
    log_section "Installation Complete!"

    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  dlib tracker is now ready to use!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    echo -e "${BLUE}📝 To enable dlib tracker:${NC}\n"
    echo -e "1. Edit your configuration:"
    echo -e "   ${YELLOW}nano configs/config.yaml${NC}\n"
    echo -e "2. Set the tracking algorithm:"
    echo -e "   ${YELLOW}DEFAULT_TRACKING_ALGORITHM: dlib${NC}\n"
    echo -e "3. Configure performance mode (optional):"
    echo -e "   ${YELLOW}DLIB_Tracker:${NC}"
    echo -e "   ${YELLOW}  performance_mode: balanced  # fast | balanced | robust${NC}\n"

    echo -e "${BLUE}🚀 Then start PixEagle:${NC}"
    echo -e "   ${YELLOW}bash run_pixeagle.sh${NC}\n"

    echo -e "${BLUE}📚 For more information:${NC}"
    echo -e "   See configs/config_default.yaml (lines 195-230) for all dlib parameters\n"
}

# Main execution
main() {
    display_banner

    # Change to PixEagle directory if script is run from elsewhere
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PIXEAGLE_DIR="$(dirname "$SCRIPT_DIR")"
    cd "$PIXEAGLE_DIR"

    log_info "Working directory: $PIXEAGLE_DIR"

    # Run installation steps
    check_venv
    check_existing_dlib
    detect_memory

    # Handle low memory systems
    if [ "$LOW_MEMORY" = true ]; then
        create_temp_swap
    else
        log_section "Step 4: Swap Management"
        log_info "Sufficient memory available - skipping swap modification"
    fi

    # Install dlib
    install_dlib

    # Restore swap if modified
    if [ "$LOW_MEMORY" = true ]; then
        restore_swap
    fi

    # Verify and show instructions
    verify_installation
    show_usage_instructions

    log_success "All done! Happy flying! 🚁"
}

# Run main function
main
