#!/bin/bash
# Stop the PixEagle-managed PX4 SITL container by name.

set -euo pipefail

CONTAINER_NAME="pixeagle-px4-sitl"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: bash scripts/sitl/stop_px4_sitl.sh [container_name]"
    exit 0
fi

if [[ $# -gt 0 ]]; then
    CONTAINER_NAME="$1"
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for this helper" >&2
    exit 1
fi

if docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    docker stop "$CONTAINER_NAME"
else
    echo "Container is not running: $CONTAINER_NAME"
fi
