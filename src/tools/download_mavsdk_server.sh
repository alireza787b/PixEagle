#!/bin/bash

# ============================================================================
# download_mavsdk_server.sh - MAVSDK Server Binary Downloader
# ============================================================================
# Downloads the correct MAVSDK Server binary for the detected platform.
#
# Features:
#   - Multi-platform support (x86_64, ARM64, ARMv7, ARMv6, macOS)
#   - Automatic architecture detection
#   - curl/wget fallback
#   - Binary validation (existence, permissions, execution test)
#   - User confirmation before download
#   - Graceful error handling with manual instructions
#
# Supported Platforms:
#   - Linux x86_64 (Intel/AMD desktops, laptops, servers)
#   - Linux ARM64 (Raspberry Pi 4/5, Jetson Nano/Xavier/Orin)
#   - Linux ARMv7 (Raspberry Pi 3, older ARM boards)
#   - Linux ARMv6 (Raspberry Pi Zero)
#   - macOS (Intel and Apple Silicon)
#
# Usage: bash src/tools/download_mavsdk_server.sh
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=4
MAVSDK_VERSION="v3.12.0"  # Latest stable (December 14, 2025)
GITHUB_BASE_URL="https://github.com/mavlink/MAVSDK/releases/download"

# Get script and PixEagle directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BINARY_PATH="$PIXEAGLE_DIR/mavsdk_server_bin"

# Source shared functions (colors, logging, banner)
source "$PIXEAGLE_DIR/scripts/common.sh"

# Detected platform variables
DETECTED_OS=""
DETECTED_ARCH=""
BINARY_URL=""
BINARY_NAME="mavsdk_server_bin"

# ============================================================================
# Banner
# ============================================================================
display_banner() {
    display_pixeagle_banner "${PACKAGE} MAVSDK Server Downloader" \
        "Multi-platform MAVLink communication server"
}

# ============================================================================
# Step 1: Platform Detection
# ============================================================================
detect_platform() {
    log_step 1 $TOTAL_STEPS "Detecting Platform"

    local os=$(uname -s)
    local arch=$(uname -m)

    DETECTED_OS="$os"
    DETECTED_ARCH="$arch"

    # OS Detection
    case "$os" in
        Linux)
            log_success "OS: Linux"
            ;;
        Darwin)
            log_success "OS: macOS"
            BINARY_URL="${GITHUB_BASE_URL}/${MAVSDK_VERSION}/mavsdk_server_macos"
            log_info "Binary: mavsdk_server_macos (Universal)"
            return 0
            ;;
        *)
            log_error "Unsupported OS: $os"
            log_detail "Supported: Linux, macOS"
            show_manual_instructions
            return 1
            ;;
    esac

    # Architecture-specific binary selection (Linux only)
    case "$arch" in
        x86_64)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-x86_64"
            log_success "Architecture: x86_64 (Intel/AMD)"
            log_info "Binary: mavsdk_server_linux-x86_64"
            ;;
        aarch64|arm64)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-arm64-musl"
            log_success "Architecture: ARM64"
            log_info "Binary: mavsdk_server_linux-arm64-musl"
            ;;
        armv7l)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-armv7l-musl"
            log_success "Architecture: ARMv7 (32-bit)"
            log_info "Binary: mavsdk_server_linux-armv7l-musl"
            ;;
        armv6l)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-armv6l-musl"
            log_success "Architecture: ARMv6 (Raspberry Pi Zero)"
            log_info "Binary: mavsdk_server_linux-armv6l-musl"
            ;;
        *)
            log_error "Unsupported architecture: $arch"
            log_detail "Supported: x86_64, ARM64, ARMv7, ARMv6"
            show_manual_instructions
            return 1
            ;;
    esac

    return 0
}

# ============================================================================
# Step 2: Check Existing Installation
# ============================================================================
check_existing() {
    log_step 2 $TOTAL_STEPS "Checking Existing Installation"

    if [[ -f "$BINARY_PATH" ]] && [[ -x "$BINARY_PATH" ]]; then
        log_warn "MAVSDK Server binary already exists"
        log_detail "Location: $BINARY_PATH"
        echo ""
        echo -en "        Replace with latest version ($MAVSDK_VERSION)? [y/N]: "
        read -r REPLY
        echo ""

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing binary"
            echo ""
            echo -e "${CYAN}No changes made. Existing binary retained.${NC}"
            echo ""
            exit 0
        fi

        # Backup existing binary
        local backup_name="${BINARY_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
        mv "$BINARY_PATH" "$backup_name"
        log_success "Backed up existing binary"
        log_detail "Backup: $(basename "$backup_name")"
    else
        log_info "No existing binary found"
    fi
}

# ============================================================================
# Step 3: Download Binary
# ============================================================================
download_binary() {
    log_step 3 $TOTAL_STEPS "Downloading MAVSDK Server"

    # Show download info
    local file_size_estimate
    if [[ "$DETECTED_ARCH" == "x86_64" ]]; then
        file_size_estimate="~15MB"
    else
        file_size_estimate="~6MB"
    fi

    log_info "Version: $MAVSDK_VERSION"
    log_info "Size: $file_size_estimate"
    log_detail "URL: $BINARY_URL"
    echo ""

    # User confirmation
    echo -en "        Proceed with download? [Y/n]: "
    read -r REPLY
    echo ""

    if [[ $REPLY =~ ^[Nn]$ ]]; then
        log_warn "Download cancelled by user"
        show_manual_instructions
        exit 0
    fi

    # Detect download tool (prefer curl over wget)
    local download_cmd=""
    if command -v curl &>/dev/null; then
        download_cmd="curl"
        log_info "Using curl for download"
    elif command -v wget &>/dev/null; then
        download_cmd="wget"
        log_info "Using wget for download"
    else
        log_error "Neither curl nor wget found"
        log_detail "Install with: sudo apt install curl"
        show_manual_instructions
        exit 1
    fi

    # Download to temporary file
    local temp_file="${BINARY_PATH}.tmp"

    log_info "Downloading (this may take 1-2 minutes)..."
    echo ""

    if [[ "$download_cmd" == "curl" ]]; then
        if curl -L --progress-bar -o "$temp_file" "$BINARY_URL"; then
            log_success "Download completed"
        else
            log_error "Download failed (curl exit code: $?)"
            log_detail "Check your internet connection"
            rm -f "$temp_file"
            show_manual_instructions
            exit 1
        fi
    else
        if wget -O "$temp_file" "$BINARY_URL" --show-progress --quiet; then
            log_success "Download completed"
        else
            log_error "Download failed (wget exit code: $?)"
            log_detail "Check your internet connection"
            rm -f "$temp_file"
            show_manual_instructions
            exit 1
        fi
    fi

    # Move temp file to final location
    mv "$temp_file" "$BINARY_PATH"
}

# ============================================================================
# Step 4: Validate Binary
# ============================================================================
validate_binary() {
    log_step 4 $TOTAL_STEPS "Validating Binary"

    # Check file exists
    if [[ ! -f "$BINARY_PATH" ]]; then
        log_error "Binary file not found after download"
        exit 1
    fi
    log_success "Binary file exists"

    # Check file size (should be > 1MB for MAVSDK server)
    local file_size
    file_size=$(stat -c%s "$BINARY_PATH" 2>/dev/null || stat -f%z "$BINARY_PATH" 2>/dev/null)

    if [[ $file_size -lt 1000000 ]]; then
        log_error "Binary file too small ($file_size bytes)"
        log_detail "Expected > 1MB, download may be corrupted"
        rm -f "$BINARY_PATH"
        show_manual_instructions
        exit 1
    fi

    local file_size_mb=$(( file_size / 1024 / 1024 ))
    log_success "File size: ${file_size_mb}MB"

    # Make executable
    chmod +x "$BINARY_PATH"
    if [[ -x "$BINARY_PATH" ]]; then
        log_success "Executable permissions set"
    else
        log_error "Failed to set executable permissions"
        exit 1
    fi

    # Test execution (quick version/help check - timeout after 3 seconds)
    log_info "Testing binary execution..."

    if timeout 3s "$BINARY_PATH" --version &>/dev/null 2>&1; then
        log_success "Binary is valid and executable"
    elif timeout 3s "$BINARY_PATH" --help &>/dev/null 2>&1; then
        log_success "Binary is valid and executable"
    else
        # Not all MAVSDK versions support --version or --help, so this is non-fatal
        log_warn "Execution test inconclusive (may be normal)"
        log_detail "Binary will be fully tested during run_pixeagle.sh"
    fi
}

# ============================================================================
# Manual Download Instructions
# ============================================================================
show_manual_instructions() {
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}${BOLD}  Manual Download Instructions${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${BOLD}1. Visit MAVSDK Releases:${NC}"
    echo -e "      ${CYAN}https://github.com/mavlink/MAVSDK/releases/tag/$MAVSDK_VERSION${NC}"
    echo ""
    echo -e "   ${BOLD}2. Download the binary for your platform:${NC}"
    echo -e "      Detected OS: ${CYAN}${DETECTED_OS}${NC}"
    echo -e "      Detected Architecture: ${CYAN}${DETECTED_ARCH}${NC}"

    if [[ -n "$BINARY_URL" ]]; then
        echo -e "      Binary name: ${CYAN}$(basename "$BINARY_URL")${NC}"
    fi

    echo ""
    echo -e "   ${BOLD}3. Save the binary to:${NC}"
    echo -e "      ${CYAN}$BINARY_PATH${NC}"
    echo ""
    echo -e "   ${BOLD}4. Make the binary executable:${NC}"
    echo -e "      ${DIM}chmod +x $BINARY_PATH${NC}"
    echo ""
    echo -e "   ${BOLD}Supported Binaries:${NC}"
    echo -e "      ${DIM}mavsdk_server_linux-x86_64${NC}        (Intel/AMD Linux)"
    echo -e "      ${DIM}mavsdk_server_linux-arm64-musl${NC}    (ARM64: RPi 4/5, Jetson)"
    echo -e "      ${DIM}mavsdk_server_linux-armv7l-musl${NC}   (ARMv7: RPi 3)"
    echo -e "      ${DIM}mavsdk_server_linux-armv6l-musl${NC}   (ARMv6: RPi Zero)"
    echo -e "      ${DIM}mavsdk_server_macos${NC}               (macOS Universal)"
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Success Summary
# ============================================================================
show_summary() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                      ${PARTY} ${BOLD}Download Complete!${NC} ${PARTY}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}${CHECK}${NC} MAVSDK Server ${MAVSDK_VERSION} installed"
    echo -e "   ${GREEN}${CHECK}${NC} Platform: ${DETECTED_OS} ${DETECTED_ARCH}"
    echo -e "   ${GREEN}${CHECK}${NC} Location: $BINARY_PATH"
    echo ""
    echo -e "   ${CYAN}${BOLD}Next Steps:${NC}"
    echo -e "      Run PixEagle: ${BOLD}bash run_pixeagle.sh${NC}"
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    display_banner

    echo -e "${DIM}Downloading MAVSDK Server for your platform...${NC}"
    echo ""

    # Execute installation steps
    detect_platform || exit 1
    check_existing
    download_binary
    validate_binary

    # Show success summary
    show_summary
}

main "$@"
