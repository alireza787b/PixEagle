#!/bin/bash
# Stop one ownership-verified PixEagle PX4 SIH container by immutable ID.

set -euo pipefail

CONTAINER_NAME="pixeagle-px4-sitl"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: bash scripts/sitl/stop_px4_sitl.sh [container_name]"
    exit 0
fi
if [[ $# -gt 1 ]]; then
    echo "Usage: bash scripts/sitl/stop_px4_sitl.sh [container_name]" >&2
    exit 2
fi
if [[ $# -eq 1 ]]; then
    CONTAINER_NAME="$1"
fi
if [[ ! "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
    echo "Invalid container name: $CONTAINER_NAME" >&2
    exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for this helper" >&2
    exit 1
fi
if ! command -v timeout >/dev/null 2>&1; then
    echo "GNU timeout is required for bounded Docker operations" >&2
    exit 1
fi

INSPECT_ERROR="$(mktemp)"
trap 'rm -f "$INSPECT_ERROR"' EXIT
if ! INSPECTED="$(timeout 3s docker container inspect --format '{{.Id}}|{{.State.Running}}|{{index .Config.Labels "org.pixeagle.sitl.managed"}}|{{index .Config.Labels "org.pixeagle.sitl.profile"}}|{{index .Config.Labels "org.pixeagle.sitl.run_id"}}|{{index .Config.Labels "org.pixeagle.sitl.model"}}|{{index .Config.Labels "org.pixeagle.sitl.image_digest"}}' "$CONTAINER_NAME" 2>"$INSPECT_ERROR")"; then
    if grep -qi "no such" "$INSPECT_ERROR"; then
        echo "Container is absent: $CONTAINER_NAME"
        exit 0
    fi
    echo "Docker could not inspect $CONTAINER_NAME: $(head -c 512 "$INSPECT_ERROR")" >&2
    exit 1
fi

IFS='|' read -r CONTAINER_ID RUNNING MANAGED PROFILE RUN_ID MODEL IMAGE_DIGEST <<< "$INSPECTED"
if [[ ! "$CONTAINER_ID" =~ ^[0-9a-f]{64}$ || "$MANAGED" != "true" || "$PROFILE" != "official_px4_sih" || -z "$RUN_ID" || -z "$MODEL" || ! "$IMAGE_DIGEST" =~ @sha256:[0-9a-f]{64}$ ]]; then
    echo "Refusing to stop container without the complete PixEagle SIH ownership contract: $CONTAINER_NAME" >&2
    exit 1
fi
if [[ "$RUNNING" != "true" ]]; then
    echo "Owned container is already stopped: $CONTAINER_NAME (${CONTAINER_ID:0:12})"
    exit 0
fi

if ! timeout 20s docker stop --time 10 "$CONTAINER_ID"; then
    echo "Docker did not stop the verified SIH container; inspect immutable ID $CONTAINER_ID" >&2
    exit 1
fi
echo "Stopped verified PX4 SIH container: $CONTAINER_NAME (${CONTAINER_ID:0:12})"
