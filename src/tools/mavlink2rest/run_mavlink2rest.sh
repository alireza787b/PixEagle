#!/bin/bash

# =============================================================================
# MAVLink2REST Run Script
# =============================================================================
#
# This script runs the mavlink2rest binary with specified or default settings.
# The binary should be downloaded using: bash src/tools/download_mavlink2rest.sh
#
# Usage:
#   ./run_mavlink2rest.sh [MAVLINK_SRC] [SERVER_IP_PORT]
#
# Example:
#   ./run_mavlink2rest.sh "udpin:0.0.0.0:14550" "0.0.0.0:8088"
#
# If parameters are not provided, default values will be used.
#
# Author: Alireza Ghaderi
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# =============================================================================

# Get base directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Default Configuration
DEFAULT_MAVLINK_SRC="udpin:127.0.0.1:14569"  # Default MAVLink source (from MAVSDK)
DEFAULT_SERVER_BIND="0.0.0.0:8088"           # Default server bind address

# Binary location
MAVLINK2REST_BIN="$BASE_DIR/mavlink2rest"

# =============================================================================
# Function Definitions
# =============================================================================

display_usage() {
    echo "Usage: $0 [MAVLINK_SRC] [SERVER_BIND]"
    echo ""
    echo "Arguments:"
    echo "  MAVLINK_SRC    MAVLink source connection string (default: $DEFAULT_MAVLINK_SRC)"
    echo "  SERVER_BIND    Server bind address (default: $DEFAULT_SERVER_BIND)"
    echo ""
    echo "Examples:"
    echo "  $0 \"udpin:0.0.0.0:14550\" \"0.0.0.0:8088\""
    echo "  $0 \"serial:/dev/ttyUSB0:115200\" \"127.0.0.1:8088\""
    echo ""
    echo "Installation:"
    echo "  If binary not found, download with:"
    echo "  bash $BASE_DIR/src/tools/download_mavlink2rest.sh"
}

# =============================================================================
# Main Script Logic
# =============================================================================

# Check if help is requested
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    display_usage
    exit 0
fi

# Parse command-line arguments or use defaults
MAVLINK_SOURCE="${1:-$DEFAULT_MAVLINK_SRC}"
SERVER_BIND="${2:-$DEFAULT_SERVER_BIND}"

# Check if binary exists
if [[ ! -f "$MAVLINK2REST_BIN" ]] || [[ ! -x "$MAVLINK2REST_BIN" ]]; then
    echo "❌ mavlink2rest binary not found at: $MAVLINK2REST_BIN"
    echo ""
    echo "   Download it using:"
    echo "   bash $BASE_DIR/src/tools/download_mavlink2rest.sh"
    echo ""
    exit 1
fi

# Display configuration
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MAVLink2REST Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MAVLink Source:  $MAVLINK_SOURCE"
echo "  Server Bind:     $SERVER_BIND"
echo "  Binary:          $MAVLINK2REST_BIN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run mavlink2rest
exec "$MAVLINK2REST_BIN" -c "$MAVLINK_SOURCE" -s "$SERVER_BIND"
