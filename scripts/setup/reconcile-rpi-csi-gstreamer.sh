#!/usr/bin/env bash

# Reconcile the Raspberry Pi libcamera GStreamer source without rebuilding
# OpenCV. Other platforms are intentionally left to their native camera stack.

set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
source "$SCRIPTS_DIR/lib/common.sh"

VERIFY_ONLY=false
MODEL_FILE="${PIXEAGLE_DEVICE_TREE_MODEL_FILE:-/proc/device-tree/model}"
OS_RELEASE_FILE="${PIXEAGLE_OS_RELEASE_FILE:-/etc/os-release}"
PACKAGE="gstreamer1.0-libcamera"
ELEMENT="libcamerasrc"

usage() {
    cat <<'EOF'
Usage: bash scripts/setup/reconcile-rpi-csi-gstreamer.sh [--verify-only]

On Raspberry Pi OS, install or verify the GStreamer libcamera source used by
PixEagle CSI_CAMERA. Other platforms exit without changes.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage >&2
            exit 2
            ;;
    esac
done

is_raspberry_pi() {
    local model=""
    local distro_id=""

    if [[ -r "$MODEL_FILE" ]]; then
        model="$(tr -d '\0' < "$MODEL_FILE" 2>/dev/null || true)"
    fi
    if [[ "${model,,}" == *"raspberry pi"* ]]; then
        return 0
    fi

    if [[ -r "$OS_RELEASE_FILE" ]]; then
        distro_id="$(
            sed -n 's/^ID=//p' "$OS_RELEASE_FILE" 2>/dev/null \
                | head -n 1 \
                | tr -d '"' \
                | tr '[:upper:]' '[:lower:]'
        )"
    fi
    [[ "$distro_id" == "raspbian" ]]
}

element_available() {
    command -v gst-inspect-1.0 >/dev/null 2>&1 \
        && gst-inspect-1.0 "$ELEMENT" >/dev/null 2>&1
}

if ! is_raspberry_pi; then
    exit 0
fi

if element_available; then
    log_success "Raspberry Pi CSI source available: $ELEMENT"
    exit 0
fi

if [[ "$VERIFY_ONLY" == true ]]; then
    log_error "Raspberry Pi CSI source is unavailable: $ELEMENT"
    log_detail "Repair with: bash scripts/setup/reconcile-rpi-csi-gstreamer.sh"
    exit 1
fi

command -v apt-cache >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1 || {
    log_error "Cannot install $PACKAGE because apt tools are unavailable"
    exit 1
}

if ! apt-cache show "$PACKAGE" >/dev/null 2>&1; then
    log_error "$PACKAGE is unavailable from the configured apt repositories"
    log_detail "Run sudo apt update, verify Raspberry Pi OS repositories, then retry."
    exit 1
fi

if ! pixeagle_running_as_root; then
    log_info "Installing the Raspberry Pi CSI GStreamer source"
    if ! pixeagle_sudo_validate; then
        log_error "$(pixeagle_sudo_failure_message)"
        if [[ "${PIXEAGLE_SUDO_FAILURE_REASON:-}" == "terminal_unavailable" ]]; then
            log_detail "Open an interactive terminal, run sudo -v, then retry."
        fi
        exit 1
    fi
fi

if ! pixeagle_sudo_run env \
    DEBIAN_FRONTEND=noninteractive \
    APT_LISTCHANGES_FRONTEND=none \
    apt-get install -y "$PACKAGE"; then
    log_error "Failed to install $PACKAGE"
    log_detail "Run sudo apt update, then retry this command."
    exit 1
fi

if ! element_available; then
    log_error "$PACKAGE installed, but GStreamer still cannot load $ELEMENT"
    log_detail "Inspect with: gst-inspect-1.0 $ELEMENT"
    exit 1
fi

log_success "Raspberry Pi CSI source installed and verified: $ELEMENT"
