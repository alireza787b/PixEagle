#!/bin/bash
# Start a pinned official PX4 SITL container for PixEagle validation.

set -euo pipefail

IMAGE="px4io/px4-sitl:v1.17.0"
MODEL="sihsim_quadx"
CONTAINER_NAME="pixeagle-px4-sitl"
ARTIFACT_ROOT="reports/sitl/manual"
ARTIFACT_DIR=""
NETWORK_MODE="host"

show_help() {
    cat <<'EOF'
Usage: bash scripts/sitl/start_px4_sitl.sh [OPTIONS]

Starts a PX4 SITL container for operator-approved validation. The script does
not pull images automatically and does not touch real hardware.

Options:
  --image IMAGE        PX4 image tag (default: px4io/px4-sitl:v1.17.0)
  --model MODEL        PX4_SIM_MODEL (default: sihsim_quadx)
  --name NAME          Docker container name (default: pixeagle-px4-sitl)
  --artifact-dir DIR   New directory for command/log artifacts
  --network MODE       Docker network mode, normally host on Linux
  --help               Show this help

Before running, pull or build the exact image you intend to validate:
  docker pull px4io/px4-sitl:v1.17.0
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE="${2:?missing value for --image}"
            shift 2
            ;;
        --model)
            MODEL="${2:?missing value for --model}"
            shift 2
            ;;
        --name)
            CONTAINER_NAME="${2:?missing value for --name}"
            shift 2
            ;;
        --artifact-dir)
            ARTIFACT_DIR="${2:?missing value for --artifact-dir}"
            shift 2
            ;;
        --network)
            NETWORK_MODE="${2:?missing value for --network}"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help >&2
            exit 2
            ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" ]]; then
    RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-px4-sitl"
    ARTIFACT_DIR="$ARTIFACT_ROOT/$RUN_ID"
else
    RUN_ID="$(basename "$ARTIFACT_DIR")"
fi

if [[ -e "$ARTIFACT_DIR" ]]; then
    echo "Artifact directory already exists, refusing to reuse evidence: $ARTIFACT_DIR" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for this helper" >&2
    exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    echo "Container name already exists, refusing to reuse it: $CONTAINER_NAME" >&2
    exit 1
fi

mkdir -p "$ARTIFACT_DIR/logs" "$ARTIFACT_DIR/commands"

COMMAND=(
    docker run
    --rm
    --name "$CONTAINER_NAME"
    --network "$NETWORK_MODE"
    --pull=never
    --label "org.pixeagle.sitl.managed=true"
    --label "org.pixeagle.sitl.run_id=$RUN_ID"
    -e "PX4_SIM_MODEL=$MODEL"
    "$IMAGE"
)

printf '%q ' "${COMMAND[@]}" > "$ARTIFACT_DIR/commands/start_px4_sitl.command"
printf '\n' >> "$ARTIFACT_DIR/commands/start_px4_sitl.command"

echo "Starting PX4 SITL container: $CONTAINER_NAME"
echo "Image: $IMAGE"
echo "Model: $MODEL"
echo "Artifacts: $ARTIFACT_DIR"

"${COMMAND[@]}" 2>&1 | tee "$ARTIFACT_DIR/logs/px4_sitl.log"
