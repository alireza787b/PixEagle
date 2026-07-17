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
#   - pinned manifest-based versions and checksums
#   - dry-run plan output
#   - binary provenance log
#
# Usage:
#   bash scripts/setup/download-binaries.sh           # Download all
#   bash scripts/setup/download-binaries.sh --mavsdk  # MAVSDK only
#   bash scripts/setup/download-binaries.sh --mavlink2rest  # MAVLink2REST only
#   bash scripts/setup/download-binaries.sh --all --dry-run # Print plan only
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

set -o pipefail

# ============================================================================
# Configuration
# ============================================================================
TOTAL_STEPS=4

# Get directories
SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIXEAGLE_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
BIN_DIR="$PIXEAGLE_DIR/bin"
BINARY_MANIFEST_PATH="${PIXEAGLE_BINARY_MANIFEST:-$SCRIPTS_DIR/setup/binary-manifest.env}"
PROVENANCE_LOG="$BIN_DIR/binary-provenance.jsonl"

MAVSDK_VERSION=""
MAVLINK2REST_VERSION=""
GITHUB_MAVSDK_URL=""
GITHUB_M2R_URL=""
MAVSDK_RELEASE_URL=""
MAVLINK2REST_RELEASE_URL=""

DRY_RUN=false
PLATFORM_KEY=""

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

# ============================================================================
# Manifest And Provenance Helpers
# ============================================================================
load_binary_manifest() {
    if [[ ! -f "$BINARY_MANIFEST_PATH" ]]; then
        log_error "Binary manifest not found: $BINARY_MANIFEST_PATH"
        return 1
    fi

    # shellcheck disable=SC1090
    source "$BINARY_MANIFEST_PATH"

    MAVSDK_VERSION="${PIXEAGLE_MAVSDK_VERSION:-${PIXEAGLE_BINARY_MAVSDK_VERSION:-}}"
    MAVLINK2REST_VERSION="${PIXEAGLE_MAVLINK2REST_VERSION:-${PIXEAGLE_BINARY_MAVLINK2REST_VERSION:-}}"
    GITHUB_MAVSDK_URL="${PIXEAGLE_MAVSDK_BASE_URL:-${PIXEAGLE_BINARY_MAVSDK_BASE_URL:-}}"
    GITHUB_M2R_URL="${PIXEAGLE_MAVLINK2REST_BASE_URL:-${PIXEAGLE_BINARY_MAVLINK2REST_BASE_URL:-}}"
    MAVSDK_RELEASE_URL="${PIXEAGLE_BINARY_MAVSDK_RELEASE_URL:-}"
    MAVLINK2REST_RELEASE_URL="${PIXEAGLE_BINARY_MAVLINK2REST_RELEASE_URL:-}"

    if [[ -z "$MAVSDK_VERSION" || -z "$MAVLINK2REST_VERSION" || -z "$GITHUB_MAVSDK_URL" || -z "$GITHUB_M2R_URL" ]]; then
        log_error "Binary manifest is missing required version/base URL fields"
        return 1
    fi
}

manifest_value() {
    local key="$1"
    printf '%s' "${!key:-}"
}

resolve_platform_key() {
    local os="$DETECTED_OS"
    local arch="$DETECTED_ARCH"

    case "$os:$arch" in
        Linux:x86_64) echo "LINUX_X86_64" ;;
        Linux:aarch64|Linux:arm64) echo "LINUX_ARM64" ;;
        Linux:armv7l) echo "LINUX_ARMV7" ;;
        Linux:armv6l) echo "LINUX_ARMV6" ;;
        Darwin:x86_64) echo "MACOS_X64" ;;
        Darwin:arm64|Darwin:aarch64) echo "MACOS_ARM64" ;;
        *) echo "" ;;
    esac
}

compute_sha256() {
    local path="$1"
    if command -v sha256sum &>/dev/null; then
        sha256sum "$path" | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$path" | awk '{print $1}'
    else
        return 1
    fi
}

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

record_provenance() {
    local component="$1"
    local version="$2"
    local asset="$3"
    local url="$4"
    local expected_sha="$5"
    local actual_sha="$6"
    local output_path="$7"
    local verification_mode="$8"

    mkdir -p "$BIN_DIR"
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

    printf '{"timestamp_utc":"%s","component":"%s","version":"%s","platform_key":"%s","asset":"%s","url":"%s","expected_sha256":"%s","actual_sha256":"%s","verification_mode":"%s","output_path":"%s"}\n' \
        "$(json_escape "$timestamp")" \
        "$(json_escape "$component")" \
        "$(json_escape "$version")" \
        "$(json_escape "$PLATFORM_KEY")" \
        "$(json_escape "$asset")" \
        "$(json_escape "$url")" \
        "$(json_escape "$expected_sha")" \
        "$(json_escape "$actual_sha")" \
        "$(json_escape "$verification_mode")" \
        "$(json_escape "$output_path")" >> "$PROVENANCE_LOG"
}

verify_existing_binary() {
    local output_path="$1"
    local name="$2"
    local asset="$3"
    local version="$4"
    local url="$5"
    local expected_sha="$6"
    local source_mode="$7"

    local file_size
    file_size=$(stat -c%s "$output_path" 2>/dev/null || stat -f%z "$output_path" 2>/dev/null)
    if [[ $file_size -lt 1000000 ]]; then
        log_error "$name exists but is too small ($file_size bytes)"
        return 1
    fi

    local actual_sha
    if ! actual_sha="$(compute_sha256 "$output_path")"; then
        log_error "No SHA-256 tool available (sha256sum or shasum)"
        return 1
    fi

    if [[ -n "$expected_sha" ]]; then
        if [[ "$actual_sha" != "$expected_sha" ]]; then
            log_warn "$name exists but SHA256 does not match the current manifest"
            log_detail "Expected: $expected_sha"
            log_detail "Actual:   $actual_sha"
            return 1
        fi
        log_success "$name existing binary SHA256 verified"
        record_provenance "$name" "$version" "$asset" "$url" "$expected_sha" "$actual_sha" "$output_path" "${source_mode}_sha256"
        log_detail "Provenance appended: $PROVENANCE_LOG"
        return 0
    fi

    if [[ "${PIXEAGLE_ALLOW_UNVERIFIED_BINARY:-0}" == "1" ]]; then
        log_warn "$name existing binary accepted without checksum because PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1"
        record_provenance "$name" "$version" "$asset" "$url" "" "$actual_sha" "$output_path" "${source_mode}_unverified_override"
        log_detail "Provenance appended: $PROVENANCE_LOG"
        return 0
    fi

    log_error "$name existing binary cannot be verified without a SHA256"
    return 1
}

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
            --dry-run|--print-plan)
                DRY_RUN=true
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
                echo "  --dry-run       Print the pinned download plan without writing files"
                echo "  -h, --help      Show this help message"
                echo ""
                echo "Override environment variables:"
                echo "  PIXEAGLE_MAVSDK_VERSION / PIXEAGLE_MAVSDK_ASSET / PIXEAGLE_MAVSDK_SHA256"
                echo "  PIXEAGLE_MAVSDK_URL / PIXEAGLE_MAVSDK_BASE_URL"
                echo "  PIXEAGLE_MAVLINK2REST_VERSION / PIXEAGLE_MAVLINK2REST_ASSET / PIXEAGLE_MAVLINK2REST_SHA256"
                echo "  PIXEAGLE_MAVLINK2REST_URL / PIXEAGLE_MAVLINK2REST_BASE_URL"
                echo "  PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1 for explicit lab-only unverified overrides"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [[ "$DOWNLOAD_MAVSDK" != true && "$DOWNLOAD_M2R" != true ]]; then
        DOWNLOAD_MAVSDK=true
        DOWNLOAD_M2R=true
    fi
}

# ============================================================================
# Banner
# ============================================================================
display_banner() {
    display_pixeagle_banner "Binary Downloader" "Multi-platform binary installer"
    log_detail "Manifest: $BINARY_MANIFEST_PATH"
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

    PLATFORM_KEY="$(resolve_platform_key)"
    if [[ -z "$PLATFORM_KEY" ]]; then
        log_error "No binary manifest platform key for OS/architecture: $os/$arch"
        exit 1
    fi
    log_success "Manifest platform: $PLATFORM_KEY"
}

# ============================================================================
# Get Binary Plans
# ============================================================================
get_mavsdk_asset() {
    if [[ -n "${PIXEAGLE_MAVSDK_ASSET:-}" ]]; then
        echo "$PIXEAGLE_MAVSDK_ASSET"
        return
    fi
    manifest_value "PIXEAGLE_BINARY_MAVSDK_ASSET_${PLATFORM_KEY}"
}

get_mavsdk_sha256() {
    if [[ -n "${PIXEAGLE_MAVSDK_SHA256:-}" ]]; then
        echo "$PIXEAGLE_MAVSDK_SHA256"
        return
    fi
    manifest_value "PIXEAGLE_BINARY_MAVSDK_SHA256_${PLATFORM_KEY}"
}

get_mavsdk_url() {
    if [[ -n "${PIXEAGLE_MAVSDK_URL:-}" ]]; then
        echo "$PIXEAGLE_MAVSDK_URL"
        return
    fi

    local asset="$1"
    echo "${GITHUB_MAVSDK_URL}/${MAVSDK_VERSION}/${asset}"
}

get_m2r_asset() {
    if [[ -n "${PIXEAGLE_MAVLINK2REST_ASSET:-}" ]]; then
        echo "$PIXEAGLE_MAVLINK2REST_ASSET"
        return
    fi
    manifest_value "PIXEAGLE_BINARY_MAVLINK2REST_ASSET_${PLATFORM_KEY}"
}

get_m2r_sha256() {
    if [[ -n "${PIXEAGLE_MAVLINK2REST_SHA256:-}" ]]; then
        echo "$PIXEAGLE_MAVLINK2REST_SHA256"
        return
    fi
    manifest_value "PIXEAGLE_BINARY_MAVLINK2REST_SHA256_${PLATFORM_KEY}"
}

get_m2r_url() {
    if [[ -n "${PIXEAGLE_MAVLINK2REST_URL:-}" ]]; then
        echo "$PIXEAGLE_MAVLINK2REST_URL"
        return
    fi

    local asset="$1"
    echo "${GITHUB_M2R_URL}/${MAVLINK2REST_VERSION}/${asset}"
}

print_download_plan() {
    local component="$1"
    local version="$2"
    local release_url="$3"
    local asset="$4"
    local url="$5"
    local expected_sha="$6"
    local output_path="$7"

    log_info "$component"
    log_detail "Version: $version"
    [[ -n "$release_url" ]] && log_detail "Release: $release_url"
    log_detail "Asset: $asset"
    log_detail "URL: $url"
    if [[ -n "$expected_sha" ]]; then
        log_detail "Expected SHA256: $expected_sha"
    else
        log_warn "$component has no expected SHA256 in the manifest or overrides"
    fi
    log_detail "Output: $output_path"
    log_detail "Provenance log: $PROVENANCE_LOG"
}

# ============================================================================
# Download Binary
# ============================================================================
download_binary() {
    local url="$1"
    local output_path="$2"
    local name="$3"
    local asset="$4"
    local version="$5"
    local expected_sha="$6"

    log_info "Downloading $name..."
    log_detail "URL: $url"
    if [[ -n "$expected_sha" ]]; then
        log_detail "Expected SHA256: $expected_sha"
    elif [[ "${PIXEAGLE_ALLOW_UNVERIFIED_BINARY:-0}" != "1" ]]; then
        log_error "$name has no SHA256. Provide a manifest/override SHA256 or set PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1 for lab-only use."
        return 1
    else
        log_warn "$name will be accepted without checksum verification because PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1"
    fi

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

    # Validate file size
    local file_size
    file_size=$(stat -c%s "$temp_file" 2>/dev/null || stat -f%z "$temp_file" 2>/dev/null)

    if [[ $file_size -lt 1000000 ]]; then
        log_error "Binary file too small ($file_size bytes)"
        rm -f "$temp_file"
        return 1
    fi

    local actual_sha
    if ! actual_sha="$(compute_sha256 "$temp_file")"; then
        log_error "No SHA-256 tool available (sha256sum or shasum)"
        rm -f "$temp_file"
        return 1
    fi

    local verification_mode="sha256"
    if [[ -n "$expected_sha" ]]; then
        if [[ "$actual_sha" != "$expected_sha" ]]; then
            log_error "SHA256 mismatch for $name"
            log_detail "Expected: $expected_sha"
            log_detail "Actual:   $actual_sha"
            rm -f "$temp_file"
            return 1
        fi
        log_success "SHA256 verified"
    else
        verification_mode="unverified_override"
        log_warn "No checksum verified for $name"
    fi

    # Move to final location only after validation succeeds.
    mv "$temp_file" "$output_path"
    chmod +x "$output_path"

    local file_size_mb=$(( file_size / 1024 / 1024 ))
    log_success "Binary installed: ${file_size_mb}MB"
    record_provenance "$name" "$version" "$asset" "$url" "$expected_sha" "$actual_sha" "$output_path" "$verification_mode"
    log_detail "Provenance appended: $PROVENANCE_LOG"

    return 0
}

# ============================================================================
# Download MAVSDK
# ============================================================================
download_mavsdk() {
    log_step 2 "Downloading MAVSDK Server"

    local binary_path="$BIN_DIR/mavsdk_server_bin"
    local legacy_path="$PIXEAGLE_DIR/mavsdk_server_bin"
    local asset
    local expected_sha
    local url

    asset="$(get_mavsdk_asset)"
    expected_sha="$(get_mavsdk_sha256)"
    url="$(get_mavsdk_url "$asset")"
    if [[ -z "$asset" || -z "$url" ]]; then
        log_error "Could not determine MAVSDK asset or URL for this platform"
        return 1
    fi

    print_download_plan "MAVSDK Server" "$MAVSDK_VERSION" "$MAVSDK_RELEASE_URL" "$asset" "$url" "$expected_sha" "$binary_path"
    if [[ "$DRY_RUN" == true ]]; then
        return 0
    fi

    # Check if already exists
    if [[ -f "$binary_path" ]] && [[ -x "$binary_path" ]]; then
        log_info "MAVSDK Server already exists in bin/"
        if verify_existing_binary "$binary_path" "MAVSDK Server" "$asset" "$MAVSDK_VERSION" "$url" "$expected_sha" "existing"; then
            log_info "Keeping verified existing binary"
            return 0
        fi
        echo -en "        Replace with pinned manifest binary? [y/N]: "
        read -r REPLY
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Existing MAVSDK Server was not verified and was not replaced"
            return 1
        fi
    elif [[ -f "$legacy_path" ]] && [[ -x "$legacy_path" ]]; then
        log_info "MAVSDK Server exists in legacy location (root)"
        if verify_existing_binary "$legacy_path" "MAVSDK Server" "$asset" "$MAVSDK_VERSION" "$url" "$expected_sha" "legacy_existing"; then
            echo -en "        Move verified binary to bin/? [Y/n]: "
            read -r REPLY
            if [[ -z "$REPLY" || $REPLY =~ ^[Yy]$ ]]; then
                mv "$legacy_path" "$binary_path"
                verify_existing_binary "$binary_path" "MAVSDK Server" "$asset" "$MAVSDK_VERSION" "$url" "$expected_sha" "moved_legacy" || return 1
                log_success "Moved verified MAVSDK Server to bin/"
                return 0
            fi
            log_error "Verified legacy MAVSDK Server was not moved to bin/"
            return 1
        fi
        echo -en "        Replace legacy binary with pinned manifest binary in bin/? [y/N]: "
        read -r REPLY
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$binary_path"
            log_warn "Leaving unverified legacy MAVSDK Server in place while downloading verified bin/ copy"
        else
            log_error "Legacy MAVSDK Server was not verified and was not replaced"
            return 1
        fi
    fi

    download_binary "$url" "$binary_path" "MAVSDK Server" "$asset" "$MAVSDK_VERSION" "$expected_sha"
}

# ============================================================================
# Download MAVLink2REST
# ============================================================================
download_mavlink2rest() {
    log_step 3 "Downloading MAVLink2REST"

    local binary_path="$BIN_DIR/mavlink2rest"
    local legacy_path="$PIXEAGLE_DIR/mavlink2rest"
    local asset
    local expected_sha
    local url

    asset="$(get_m2r_asset)"
    expected_sha="$(get_m2r_sha256)"
    url="$(get_m2r_url "$asset")"
    if [[ -z "$asset" || -z "$url" ]]; then
        log_error "Could not determine MAVLink2REST asset or URL for this platform"
        return 1
    fi

    print_download_plan "MAVLink2REST" "$MAVLINK2REST_VERSION" "$MAVLINK2REST_RELEASE_URL" "$asset" "$url" "$expected_sha" "$binary_path"
    if [[ "$DRY_RUN" == true ]]; then
        return 0
    fi

    # Check if already exists
    if [[ -f "$binary_path" ]] && [[ -x "$binary_path" ]]; then
        log_info "MAVLink2REST already exists in bin/"
        if verify_existing_binary "$binary_path" "MAVLink2REST" "$asset" "$MAVLINK2REST_VERSION" "$url" "$expected_sha" "existing"; then
            log_info "Keeping verified existing binary"
            return 0
        fi
        echo -en "        Replace with pinned manifest binary? [y/N]: "
        read -r REPLY
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Existing MAVLink2REST was not verified and was not replaced"
            return 1
        fi
    elif [[ -f "$legacy_path" ]] && [[ -x "$legacy_path" ]]; then
        log_info "MAVLink2REST exists in legacy location (root)"
        if verify_existing_binary "$legacy_path" "MAVLink2REST" "$asset" "$MAVLINK2REST_VERSION" "$url" "$expected_sha" "legacy_existing"; then
            echo -en "        Move verified binary to bin/? [Y/n]: "
            read -r REPLY
            if [[ -z "$REPLY" || $REPLY =~ ^[Yy]$ ]]; then
                mv "$legacy_path" "$binary_path"
                verify_existing_binary "$binary_path" "MAVLink2REST" "$asset" "$MAVLINK2REST_VERSION" "$url" "$expected_sha" "moved_legacy" || return 1
                log_success "Moved verified MAVLink2REST to bin/"
                return 0
            fi
            log_error "Verified legacy MAVLink2REST was not moved to bin/"
            return 1
        fi
        echo -en "        Replace legacy binary with pinned manifest binary in bin/? [y/N]: "
        read -r REPLY
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$binary_path"
            log_warn "Leaving unverified legacy MAVLink2REST in place while downloading verified bin/ copy"
        else
            log_error "Legacy MAVLink2REST was not verified and was not replaced"
            return 1
        fi
    fi

    download_binary "$url" "$binary_path" "MAVLink2REST" "$asset" "$MAVLINK2REST_VERSION" "$expected_sha"
}

# ============================================================================
# Summary
# ============================================================================
show_summary() {
    local failures="$1"

    log_step 4 "Summary"

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "                      ${BOLD}Dry-Run Download Plan${NC}"
    elif [[ "$failures" -eq 0 ]]; then
        echo -e "                      ${PARTY} ${BOLD}Download Complete!${NC} ${PARTY}"
    else
        echo -e "                      ${BOLD}Download Failed${NC}"
    fi
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [[ "$DOWNLOAD_MAVSDK" == true ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            echo -e "   ${CYAN}${INFO:-*}${NC} MAVSDK Server ${MAVSDK_VERSION} - planned"
        elif [[ -f "$BIN_DIR/mavsdk_server_bin" ]]; then
            echo -e "   ${GREEN}${CHECK}${NC} MAVSDK Server ${MAVSDK_VERSION}"
        else
            echo -e "   ${RED}${CROSS}${NC} MAVSDK Server - failed"
        fi
    fi

    if [[ "$DOWNLOAD_M2R" == true ]]; then
        if [[ "$DRY_RUN" == true ]]; then
            echo -e "   ${CYAN}${INFO:-*}${NC} MAVLink2REST ${MAVLINK2REST_VERSION} - planned"
        elif [[ -f "$BIN_DIR/mavlink2rest" ]]; then
            echo -e "   ${GREEN}${CHECK}${NC} MAVLink2REST ${MAVLINK2REST_VERSION}"
        else
            echo -e "   ${RED}${CROSS}${NC} MAVLink2REST - failed"
        fi
    fi

    echo ""
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "   ${CYAN}${BOLD}Dry run:${NC} no files were downloaded or modified."
    elif [[ "$failures" -eq 0 ]]; then
        echo -e "   ${CYAN}${BOLD}Provenance:${NC} $PROVENANCE_LOG"
        echo -e "      The log records downloaded binary version, URL, asset, and SHA-256."
        echo -e "      It does not claim MAVSDK, MAVLink2REST, PX4, SITL, or field runtime success."
        echo ""
        echo -e "   ${CYAN}${BOLD}Next Steps:${NC}"
        echo -e "      Run PixEagle: ${BOLD}make run${NC}"
    else
        echo -e "   ${RED}${CROSS}${NC} One or more requested binaries failed; fix the error above and rerun."
    fi
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
    load_binary_manifest || exit 1
    detect_platform

    local failures=0

    if [[ "$DOWNLOAD_MAVSDK" == true ]]; then
        download_mavsdk || failures=$((failures + 1))
    fi

    if [[ "$DOWNLOAD_M2R" == true ]]; then
        download_mavlink2rest || failures=$((failures + 1))
    fi

    show_summary "$failures"
    if [[ "$failures" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
