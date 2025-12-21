#!/bin/bash

# ============================================================================
# download_mavlink2rest.sh - MAVLink2REST Server Binary Downloader
# ============================================================================
# Downloads the correct MAVLink2REST binary for the detected platform.
#
# Features:
#   - Multi-platform support (x86_64, ARM64, ARMv7, ARM, macOS)
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
#   - Linux ARM (Generic 32-bit ARM systems)
#   - macOS (Intel and Apple Silicon)
#
# Usage: bash src/tools/download_mavlink2rest.sh
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=4
MAVLINK2REST_VERSION="v1.0.0"  # Latest release (October 20, 2025)
GITHUB_REPO="mavlink/mavlink2rest"
GITHUB_BASE_URL="https://github.com/${GITHUB_REPO}/releases/download"

# Get script and PixEagle directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BINARY_PATH="$PIXEAGLE_DIR/mavlink2rest"

# Source shared functions (colors, logging, banner)
source "$PIXEAGLE_DIR/scripts/common.sh"

# Detected platform variables
DETECTED_OS=""
DETECTED_ARCH=""
BINARY_URL=""
BINARY_NAME="mavlink2rest"

# ============================================================================
# Banner
# ============================================================================
display_banner() {
    display_pixeagle_banner "📡 MAVLink2REST Server Downloader" \
        "REST API bridge for MAVLink telemetry"
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
        Darwin)  # macOS
            log_success "OS: macOS"
            # Detect macOS architecture
            case "$arch" in
                x86_64)
                    BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-x86_64-apple-darwin"
                    log_info "Binary: mavlink2rest-x86_64-apple-darwin (Intel)"
                    ;;
                arm64|aarch64)
                    BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-aarch64-apple-darwin"
                    log_info "Binary: mavlink2rest-aarch64-apple-darwin (Apple Silicon)"
                    ;;
                *)
                    log_error "Unsupported macOS architecture: $arch"
                    log_detail "Supported: x86_64 (Intel), arm64 (Apple Silicon)"
                    show_manual_instructions
                    return 1
                    ;;
            esac
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
            BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-x86_64-unknown-linux-musl"
            log_success "Architecture: x86_64 (Intel/AMD)"
            log_info "Binary: mavlink2rest-x86_64-unknown-linux-musl"
            ;;
        aarch64|arm64)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-aarch64-unknown-linux-musl"
            log_success "Architecture: ARM64"
            log_info "Binary: mavlink2rest-aarch64-unknown-linux-musl"
            ;;
        armv7l)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-armv7-unknown-linux-musleabihf"
            log_success "Architecture: ARMv7 (32-bit)"
            log_info "Binary: mavlink2rest-armv7-unknown-linux-musleabihf"
            ;;
        arm)
            BINARY_URL="${GITHUB_BASE_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-arm-unknown-linux-musleabihf"
            log_success "Architecture: ARM (32-bit generic)"
            log_info "Binary: mavlink2rest-arm-unknown-linux-musleabihf"
            ;;
        *)
            log_error "Unsupported architecture: $arch"
            log_detail "Supported: x86_64, ARM64, ARMv7, ARM"
            show_manual_instructions
            return 1
            ;;
    esac

    return 0
}

# ============================================================================
# Step 2: Check Existing Binary
# ============================================================================
check_existing_binary() {
    log_step 2 $TOTAL_STEPS "Checking Existing Binary"

    if [[ -f "$BINARY_PATH" ]]; then
        local file_size=$(stat -f%z "$BINARY_PATH" 2>/dev/null || stat -c%s "$BINARY_PATH" 2>/dev/null || echo "0")
        local file_size_mb=$((file_size / 1024 / 1024))

        log_warn "Existing binary found (${file_size_mb}MB)"
        log_detail "Location: $BINARY_PATH"

        echo ""
        echo -en "        Backup and replace existing binary? [Y/n]: "
        read -r REPLY
        echo ""

        if [[ -z "$REPLY" ]] || [[ $REPLY =~ ^[Yy]$ ]]; then
            local backup_path="${BINARY_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
            if mv "$BINARY_PATH" "$backup_path"; then
                log_success "Backup created: $(basename "$backup_path")"
            else
                log_error "Failed to create backup"
                return 1
            fi
        else
            log_info "Download cancelled by user"
            exit 0
        fi
    else
        log_info "No existing binary found"
    fi

    return 0
}

# ============================================================================
# Step 3: Download Binary
# ============================================================================
download_binary() {
    log_step 3 $TOTAL_STEPS "Downloading Binary"

    # Display download information
    log_info "Version: $MAVLINK2REST_VERSION"
    log_info "Size: ~35-40MB"
    log_detail "URL: $BINARY_URL"

    echo ""
    echo -en "        Proceed with download? [Y/n]: "
    read -r REPLY
    echo ""

    if ! [[ -z "$REPLY" ]] && ! [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Download cancelled by user"
        exit 0
    fi

    # Determine download tool
    local download_tool=""
    if command -v curl &> /dev/null; then
        download_tool="curl"
        log_info "Using curl for download"
    elif command -v wget &> /dev/null; then
        download_tool="wget"
        log_info "Using wget for download"
    else
        log_error "Neither curl nor wget found"
        log_detail "Install curl: sudo apt install curl (or brew install curl on macOS)"
        show_manual_instructions
        return 1
    fi

    # Create temporary download file
    local temp_file="${BINARY_PATH}.tmp"

    # Download with progress
    log_info "Downloading (this may take 1-2 minutes)..."
    echo ""

    if [[ "$download_tool" == "curl" ]]; then
        if curl -L --progress-bar -o "$temp_file" "$BINARY_URL"; then
            log_success "Download completed"
        else
            log_error "Download failed"
            rm -f "$temp_file"
            show_manual_instructions
            return 1
        fi
    else
        if wget --progress=bar:force -O "$temp_file" "$BINARY_URL" 2>&1 | grep --line-buffered -o "[0-9]*%" | \
            while read -r line; do echo -ne "\r        Progress: $line"; done; then
            echo ""
            log_success "Download completed"
        else
            log_error "Download failed"
            rm -f "$temp_file"
            show_manual_instructions
            return 1
        fi
    fi

    # Move temp file to final location
    if mv "$temp_file" "$BINARY_PATH"; then
        :  # Success
    else
        log_error "Failed to move binary to final location"
        rm -f "$temp_file"
        return 1
    fi

    return 0
}

# ============================================================================
# Step 4: Validate Binary
# ============================================================================
validate_binary() {
    log_step 4 $TOTAL_STEPS "Validating Binary"

    # Check file exists
    if [[ ! -f "$BINARY_PATH" ]]; then
        log_error "Binary file not found after download"
        show_manual_instructions
        return 1
    fi
    log_success "Binary file exists"

    # Check file size (should be > 10MB, corrupted downloads are usually tiny)
    local file_size=$(stat -f%z "$BINARY_PATH" 2>/dev/null || stat -c%s "$BINARY_PATH" 2>/dev/null || echo "0")
    local file_size_mb=$((file_size / 1024 / 1024))

    if [[ $file_size -lt 1000000 ]]; then
        log_error "Binary file too small (${file_size} bytes)"
        log_detail "Expected > 1MB, download may be corrupted"
        show_manual_instructions
        return 1
    fi
    log_success "File size: ${file_size_mb}MB"

    # Set executable permissions
    if chmod +x "$BINARY_PATH"; then
        log_success "Executable permissions set"
    else
        log_error "Failed to set executable permissions"
        return 1
    fi

    # Test execution (quick version check - timeout after 3 seconds)
    log_info "Testing binary execution..."

    if timeout 3s "$BINARY_PATH" --version &>/dev/null 2>&1; then
        log_success "Binary is valid and executable"
    elif timeout 3s "$BINARY_PATH" --help &>/dev/null 2>&1; then
        log_success "Binary is valid and executable"
    else
        # Not all mavlink2rest versions support --version or --help, so this is non-fatal
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
    echo -e "   ${BOLD}1. Visit MAVLink2REST Releases:${NC}"
    echo -e "      ${CYAN}https://github.com/${GITHUB_REPO}/releases/tag/$MAVLINK2REST_VERSION${NC}"
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
    echo -e "      ${DIM}mavlink2rest-x86_64-unknown-linux-musl${NC}     (Intel/AMD Linux)"
    echo -e "      ${DIM}mavlink2rest-aarch64-unknown-linux-musl${NC}    (ARM64: RPi 4/5, Jetson)"
    echo -e "      ${DIM}mavlink2rest-armv7-unknown-linux-musleabihf${NC} (ARMv7: RPi 3)"
    echo -e "      ${DIM}mavlink2rest-arm-unknown-linux-musleabihf${NC}   (ARM generic 32-bit)"
    echo -e "      ${DIM}mavlink2rest-x86_64-apple-darwin${NC}            (macOS Intel)"
    echo -e "      ${DIM}mavlink2rest-aarch64-apple-darwin${NC}           (macOS Apple Silicon)"
    echo ""
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Success Summary
# ============================================================================
show_success_summary() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                      🎉 ${BOLD}Download Complete!${NC} 🎉"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "   ${GREEN}✅${NC} MAVLink2REST ${MAVLINK2REST_VERSION} installed"
    echo -e "   ${GREEN}✅${NC} Platform: ${DETECTED_OS} ${DETECTED_ARCH}"
    echo -e "   ${GREEN}✅${NC} Location: ${BINARY_PATH}"
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

    echo -e "${DIM}Downloading MAVLink2REST Server for your platform...${NC}"
    echo ""

    # Execute steps
    if ! detect_platform; then
        exit 1
    fi

    if ! check_existing_binary; then
        exit 1
    fi

    if ! download_binary; then
        exit 1
    fi

    if ! validate_binary; then
        log_error "MAVLink2REST Server download failed"
        log_detail "Try manually: bash $SCRIPT_DIR/download_mavlink2rest.sh"
        exit 1
    fi

    show_success_summary
    exit 0
}

# Run main function
main
