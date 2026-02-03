#!/bin/bash

# ============================================================================
# scripts/setup/download-binaries.sh - Binary Downloader for PixEagle
# ============================================================================
# Downloads MAVSDK Server and/or MAVLink2REST binaries for the detected platform.
#
# Features:
#   - Multi-platform support (x86_64, ARM64, ARMv7, ARMv6, macOS)
#   - Automatic architecture detection
#   - curl/wget fallback
#   - Binary validation
#
# Usage:
#   bash scripts/setup/download-binaries.sh           # Download all
#   bash scripts/setup/download-binaries.sh --mavsdk  # MAVSDK only
#   bash scripts/setup/download-binaries.sh --mavlink2rest  # MAVLink2REST only
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=4
MAVSDK_VERSION="v3.12.0"
MAVLINK2REST_VERSION="1.0.0"
GITHUB_MAVSDK_URL="https://github.com/mavlink/MAVSDK/releases/download"
GITHUB_M2R_URL="https://github.com/mavlink/mavlink2rest/releases/download"

# Get directories
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
BIN_DIR="$PIXEAGLE_DIR/bin"

# Fix CRLF line endings
[[ -f "$SCRIPTS_DIR/lib/common.sh" ]] && grep -q $'\r' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && \
    sed -i.bak 's/\r$//' "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null && rm -f "$SCRIPTS_DIR/lib/common.sh.bak"

# Source shared functions with fallback
if ! source "$SCRIPTS_DIR/lib/common.sh" 2>/dev/null; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    # Symbols
    CHECK="[✓]"; CROSS="[✗]"; PARTY=""
    log_info() { echo -e "   ${CYAN}[*]${NC} $1"; }
    log_success() { echo -e "   ${GREEN}[✓]${NC} $1"; }
    log_warn() { echo -e "   ${YELLOW}[!]${NC} $1"; }
    log_error() { echo -e "   ${RED}[✗]${NC} $1"; }
    log_step() { echo -e "\n${CYAN}━━━ Step $1/${TOTAL_STEPS}: $2 ━━━${NC}"; }
    log_detail() { echo -e "      ${DIM}$1${NC}"; }
    display_pixeagle_banner() {
        echo -e "\n${CYAN}${BOLD}PixEagle${NC}"
        [[ -n "${1:-}" ]] && echo -e "  ${BOLD}$1${NC}"
        [[ -n "${2:-}" ]] && echo -e "  ${DIM}$2${NC}"
        echo ""
    }
fi

# What to download
DOWNLOAD_MAVSDK=false
DOWNLOAD_M2R=false

# Detected platform
DETECTED_OS=""
DETECTED_ARCH=""

# ============================================================================
# Parse Arguments
# ============================================================================
parse_args() {
    if [[ $# -eq 0 ]]; then
        # No arguments = download all
        DOWNLOAD_MAVSDK=true
        DOWNLOAD_M2R=true
        return
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mavsdk)
                DOWNLOAD_MAVSDK=true
                shift
                ;;
            --mavlink2rest|--m2r)
                DOWNLOAD_M2R=true
                shift
                ;;
            --all)
                DOWNLOAD_MAVSDK=true
                DOWNLOAD_M2R=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Download MAVSDK Server and/or MAVLink2REST binaries."
                echo ""
                echo "Options:"
                echo "  --mavsdk        Download MAVSDK Server only"
                echo "  --mavlink2rest  Download MAVLink2REST only"
                echo "  --all           Download all binaries (default)"
                echo "  -h, --help      Show this help message"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# Banner
# ============================================================================
display_banner() {
    display_pixeagle_banner "Binary Downloader" "Multi-platform binary installer"
}

# ============================================================================
# Platform Detection
# ============================================================================
detect_platform() {
    log_step 1 "Detecting Platform"

    local os=$(uname -s)
    local arch=$(uname -m)

    DETECTED_OS="$os"
    DETECTED_ARCH="$arch"

    case "$os" in
        Linux)
            log_success "OS: Linux"
            ;;
        Darwin)
            log_success "OS: macOS"
            ;;
        *)
            log_error "Unsupported OS: $os"
            log_detail "Supported: Linux, macOS"
            exit 1
            ;;
    esac

    case "$arch" in
        x86_64)
            log_success "Architecture: x86_64 (Intel/AMD)"
            ;;
        aarch64|arm64)
            log_success "Architecture: ARM64"
            ;;
        armv7l)
            log_success "Architecture: ARMv7 (32-bit)"
            ;;
        armv6l)
            log_success "Architecture: ARMv6 (Raspberry Pi Zero)"
            ;;
        *)
            log_error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac
}

# ============================================================================
# Get Binary URLs
# ============================================================================
get_mavsdk_url() {
    local os="$DETECTED_OS"
    local arch="$DETECTED_ARCH"

    if [[ "$os" == "Darwin" ]]; then
        echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/mavsdk_server_macos_x64"
        return
    fi

    case "$arch" in
        x86_64)
            echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/mavsdk_server_musl_x86_64"
            ;;
        aarch64|arm64)
            echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-arm64-musl"
            ;;
        armv7l)
            echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-armv7l-musl"
            ;;
        armv6l)
            echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/mavsdk_server_linux-armv6l-musl"
            ;;
    esac
}

get_m2r_url() {
    local os="$DETECTED_OS"
    local arch="$DETECTED_ARCH"

    if [[ "$os" == "Darwin" ]]; then
        case "$arch" in
            x86_64)
                echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-x86_64-apple-darwin"
                ;;
            arm64|aarch64)
                echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-aarch64-apple-darwin"
                ;;
        esac
        return
    fi

    case "$arch" in
        x86_64)
            echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-x86_64-unknown-linux-musl"
            ;;
        aarch64|arm64)
            echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-aarch64-unknown-linux-musl"
            ;;
        armv7l)
            echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-armv7-unknown-linux-musleabihf"
            ;;
        arm)
            echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/mavlink2rest-arm-unknown-linux-musleabihf"
            ;;
    esac
}

# ============================================================================
# Download Binary
# ============================================================================
download_binary() {
    local url="$1"
    local output_path="$2"
    local name="$3"

    log_info "Downloading $name..."
    log_detail "URL: $url"

    # Ensure bin directory exists
    mkdir -p "$BIN_DIR"

    # Determine download tool
    local download_cmd=""
    if command -v curl &>/dev/null; then
        download_cmd="curl"
    elif command -v wget &>/dev/null; then
        download_cmd="wget"
    else
        log_error "Neither curl nor wget found"
        log_detail "Install with: sudo apt install curl"
        return 1
    fi

    # Download
    local temp_file="${output_path}.tmp"

    if [[ "$download_cmd" == "curl" ]]; then
        if curl -L --progress-bar -o "$temp_file" "$url"; then
            log_success "Download completed"
        else
            log_error "Download failed"
            rm -f "$temp_file"
            return 1
        fi
    else
        if wget -O "$temp_file" "$url" --show-progress --quiet; then
            log_success "Download completed"
        else
            log_error "Download failed"
            rm -f "$temp_file"
            return 1
        fi
    fi

    # Move to final location
    mv "$temp_file" "$output_path"
    chmod +x "$output_path"

    # Validate file size
    local file_size
    file_size=$(stat -c%s "$output_path" 2>/dev/null || stat -f%z "$output_path" 2>/dev/null)

    if [[ $file_size -lt 1000000 ]]; then
        log_error "Binary file too small ($file_size bytes)"
        rm -f "$output_path"
        return 1
    fi

    local file_size_mb=$(( file_size / 1024 / 1024 ))
    log_success "Binary installed: ${file_size_mb}MB"

    return 0
}

# ============================================================================
# Download MAVSDK
# ============================================================================
download_mavsdk() {
    log_step 2 "Downloading MAVSDK Server"

    local binary_path="$BIN_DIR/mavsdk_server_bin"
    local legacy_path="$PIXEAGLE_DIR/mavsdk_server_bin"

    # Check if already exists
    if [[ -f "$binary_path" ]] && [[ -x "$binary_path" ]]; then
        log_info "MAVSDK Server already exists in bin/"
        echo -en "        Replace? [y/N]: "
        read -r REPLY
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing binary"
            return 0
        fi
    elif [[ -f "$legacy_path" ]] && [[ -x "$legacy_path" ]]; then
        log_info "MAVSDK Server exists in legacy location (root)"
        echo -en "        Move to bin/ and update? [y/N]: "
        read -r REPLY
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            mv "$legacy_path" "$binary_path"
            log_success "Moved to bin/"
            return 0
        else
            log_info "Keeping existing binary"
            return 0
        fi
    fi

    local url=$(get_mavsdk_url)
    if [[ -z "$url" ]]; then
        log_error "Could not determine MAVSDK URL for this platform"
        return 1
    fi

    log_info "Version: $MAVSDK_VERSION"

    download_binary "$url" "$binary_path" "MAVSDK Server"
}

# ============================================================================
# Download MAVLink2REST
# ============================================================================
download_mavlink2rest() {
    log_step 3 "Downloading MAVLink2REST"

    local binary_path="$BIN_DIR/mavlink2rest"
    local legacy_path="$PIXEAGLE_DIR/mavlink2rest"

    # Check if already exists
    if [[ -f "$binary_path" ]] && [[ -x "$binary_path" ]]; then
        log_info "MAVLink2REST already exists in bin/"
        echo -en "        Replace? [y/N]: "
        read -r REPLY
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing binary"
            return 0
        fi
    elif [[ -f "$legacy_path" ]] && [[ -x "$legacy_path" ]]; then
        log_info "MAVLink2REST exists in legacy location (root)"
        echo -en "        Move to bin/ and update? [y/N]: "
        read -r REPLY
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            mv "$legacy_path" "$binary_path"
            log_success "Moved to bin/"
            return 0
        else
            log_info "Keeping existing binary"
            return 0
        fi
    fi

    local url=$(get_m2r_url)
    if [[ -z "$url" ]]; then
        log_error "Could not determine MAVLink2REST URL for this platform"
        return 1
    fi

    log_info "Version: $MAVLINK2REST_VERSION"

    download_binary "$url" "$binary_path" "MAVLink2REST"
}

# ============================================================================
# Summary
# ============================================================================
show_summary() {
    log_step 4 "Summary"

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "                      ${PARTY} ${BOLD}Download Complete!${NC} ${PARTY}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [[ "$DOWNLOAD_MAVSDK" == true ]]; then
        if [[ -f "$BIN_DIR/mavsdk_server_bin" ]]; then
            echo -e "   ${GREEN}${CHECK}${NC} MAVSDK Server ${MAVSDK_VERSION}"
        else
            echo -e "   ${RED}${CROSS}${NC} MAVSDK Server - failed"
        fi
    fi

    if [[ "$DOWNLOAD_M2R" == true ]]; then
        if [[ -f "$BIN_DIR/mavlink2rest" ]]; then
            echo -e "   ${GREEN}${CHECK}${NC} MAVLink2REST ${MAVLINK2REST_VERSION}"
        else
            echo -e "   ${RED}${CROSS}${NC} MAVLink2REST - failed"
        fi
    fi

    echo ""
    echo -e "   ${CYAN}${BOLD}Next Steps:${NC}"
    echo -e "      Run PixEagle: ${BOLD}make run${NC}"
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main
# ============================================================================
main() {
    parse_args "$@"

    display_banner
    detect_platform

    if [[ "$DOWNLOAD_MAVSDK" == true ]]; then
        download_mavsdk
    fi

    if [[ "$DOWNLOAD_M2R" == true ]]; then
        download_mavlink2rest
    fi

    show_summary
}

main "$@"
