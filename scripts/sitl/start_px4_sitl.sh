#!/bin/bash
# Start the immutable official PX4 SIH profile from the checked-in validation plan.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLAN_PATH="$PROJECT_ROOT/tools/sitl_plans/phase2_follower_validation.json"
CONTAINER_NAME="pixeagle-px4-sitl"
ARTIFACT_ROOT="$PROJECT_ROOT/reports/sitl/manual"
ARTIFACT_DIR=""
CPU_LIMIT="1.5"
MEMORY_LIMIT="1g"
PID_LIMIT="256"
LOG_MAX_SIZE="10m"
LOG_MAX_FILES="2"

show_help() {
    cat <<'EOF'
Usage: bash scripts/sitl/start_px4_sitl.sh [OPTIONS]

Starts the immutable PX4 SIH image declared by the checked-in Phase 2
validation plan. It never pulls an image, starts routing, starts PixEagle, or
touches real hardware.

Options:
  --plan PATH          Validation plan (default: checked-in Phase 2 plan)
  --name NAME          Container name (default: pixeagle-px4-sitl)
  --artifact-dir DIR   New directory for bounded command/log artifacts
  --help               Show this help

Run the managed-SIH prerequisite doctor before this helper. Pull the displayed
tag explicitly only when the operator has approved network access, then rerun
the doctor to verify its repository digest.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan)
            PLAN_PATH="${2:?missing value for --plan}"
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

if [[ ! "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
    echo "Invalid container name: $CONTAINER_NAME" >&2
    exit 2
fi
if [[ ! -f "$PLAN_PATH" ]]; then
    echo "Validation plan not found: $PLAN_PATH" >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to read the validation plan" >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for this helper" >&2
    exit 1
fi
if ! command -v timeout >/dev/null 2>&1; then
    echo "GNU timeout is required for bounded Docker operations" >&2
    exit 1
fi

mapfile -t PLAN_VALUES < <(
    python3 - "$PLAN_PATH" <<'PY'
import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
px4 = payload.get("stack", {}).get("px4", {})
image = str(px4.get("recommended_image") or "")
digest = str(px4.get("expected_repo_digest") or "")
model = str(px4.get("vehicle_model") or "")
network = str(px4.get("network_mode") or "")
image_repo = image.rsplit(":", 1)[0] if image.rfind(":") > image.rfind("/") else image

if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,299}", image):
    raise SystemExit("invalid recommended_image in validation plan")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", model):
    raise SystemExit("invalid vehicle_model in validation plan")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,260}@sha256:[0-9a-f]{64}", digest):
    raise SystemExit("missing or invalid expected_repo_digest in validation plan")
if not digest.startswith(f"{image_repo}@sha256:"):
    raise SystemExit("image tag and expected repository digest do not match")
if network != "host":
    raise SystemExit("the official managed SIH profile requires host networking")

print(image)
print(digest)
print(model)
print(network)
PY
)

if [[ ${#PLAN_VALUES[@]} -ne 4 ]]; then
    echo "Could not resolve the managed SIH profile from $PLAN_PATH" >&2
    exit 1
fi
IMAGE_TAG="${PLAN_VALUES[0]}"
IMAGE_DIGEST="${PLAN_VALUES[1]}"
MODEL="${PLAN_VALUES[2]}"
NETWORK_MODE="${PLAN_VALUES[3]}"

if ! timeout 3s docker version --format '{{.Server.Version}}' >/dev/null; then
    echo "Docker daemon is unavailable to the current user" >&2
    exit 1
fi

LOCAL_DIGESTS="$(timeout 3s docker image inspect --format '{{json .RepoDigests}}' "$IMAGE_TAG")" || {
    echo "Pinned image is not available locally: $IMAGE_TAG" >&2
    exit 1
}
python3 - "$LOCAL_DIGESTS" "$IMAGE_DIGEST" <<'PY'
import json
import sys

digests = json.loads(sys.argv[1])
expected = sys.argv[2]
if not isinstance(digests, list) or expected not in digests:
    raise SystemExit(f"local image does not contain required digest: {expected}")
PY

if timeout 3s docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "Container name already exists, refusing to reuse it: $CONTAINER_NAME" >&2
    exit 1
fi

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

mkdir -p "$ARTIFACT_DIR/logs" "$ARTIFACT_DIR/commands"

COMMAND=(
    docker run -d --rm --init
    --name "$CONTAINER_NAME"
    --network "$NETWORK_MODE"
    --pull=never
    --cpus "$CPU_LIMIT"
    --memory "$MEMORY_LIMIT"
    --pids-limit "$PID_LIMIT"
    --log-driver local
    --log-opt "max-size=$LOG_MAX_SIZE"
    --log-opt "max-file=$LOG_MAX_FILES"
    --label "org.pixeagle.sitl.managed=true"
    --label "org.pixeagle.sitl.profile=official_px4_sih"
    --label "org.pixeagle.sitl.run_id=$RUN_ID"
    --label "org.pixeagle.sitl.model=$MODEL"
    --label "org.pixeagle.sitl.image_digest=$IMAGE_DIGEST"
    -e "PX4_SIM_MODEL=$MODEL"
    "$IMAGE_DIGEST"
)

printf '%q ' "${COMMAND[@]}" > "$ARTIFACT_DIR/commands/start_px4_sitl.command"
printf '\n' >> "$ARTIFACT_DIR/commands/start_px4_sitl.command"

CONTAINER_ID="$(timeout 20s "${COMMAND[@]}")" || {
    echo "Docker did not return a managed SIH container ID" >&2
    echo "Inspect the exact name before retrying: docker container inspect $CONTAINER_NAME" >&2
    exit 1
}
if [[ ! "$CONTAINER_ID" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Docker returned an invalid container ID; inspect $CONTAINER_NAME before retrying" >&2
    exit 1
fi

INSPECTED="$(timeout 3s docker container inspect --format '{{.Id}}|{{.State.Running}}|{{.Image}}|{{.Config.Image}}|{{.HostConfig.NetworkMode}}|{{index .Config.Labels "org.pixeagle.sitl.managed"}}|{{index .Config.Labels "org.pixeagle.sitl.profile"}}|{{index .Config.Labels "org.pixeagle.sitl.run_id"}}|{{index .Config.Labels "org.pixeagle.sitl.model"}}|{{index .Config.Labels "org.pixeagle.sitl.image_digest"}}' "$CONTAINER_ID")" || {
    timeout 20s docker stop --time 10 "$CONTAINER_ID" >/dev/null 2>&1 || true
    echo "Started container could not be ownership-verified; rollback was attempted" >&2
    exit 1
}
IFS='|' read -r VERIFIED_ID RUNNING _IMAGE_ID CONFIG_IMAGE VERIFIED_NETWORK MANAGED PROFILE VERIFIED_RUN VERIFIED_MODEL VERIFIED_DIGEST <<< "$INSPECTED"
if [[ "$VERIFIED_ID" != "$CONTAINER_ID" || "$RUNNING" != "true" || "$CONFIG_IMAGE" != "$IMAGE_DIGEST" || "$VERIFIED_NETWORK" != "$NETWORK_MODE" || "$MANAGED" != "true" || "$PROFILE" != "official_px4_sih" || "$VERIFIED_RUN" != "$RUN_ID" || "$VERIFIED_MODEL" != "$MODEL" || "$VERIFIED_DIGEST" != "$IMAGE_DIGEST" ]]; then
    timeout 20s docker stop --time 10 "$CONTAINER_ID" >/dev/null 2>&1 || true
    echo "Started container failed ownership verification; rollback was attempted" >&2
    exit 1
fi

{
    echo "container_id=$CONTAINER_ID"
    echo "container_name=$CONTAINER_NAME"
    echo "image_tag=$IMAGE_TAG"
    echo "image_digest=$IMAGE_DIGEST"
    echo "model=$MODEL"
    echo "network_mode=$NETWORK_MODE"
    echo "run_id=$RUN_ID"
} > "$ARTIFACT_DIR/container.env"

set +o pipefail
timeout 3s docker logs --tail 200 "$CONTAINER_ID" 2>&1 \
    | head -c 1048576 > "$ARTIFACT_DIR/logs/px4_sitl.initial.log"
set -o pipefail

echo "PX4 SIH container started and ownership-verified."
echo "Container: $CONTAINER_NAME (${CONTAINER_ID:0:12})"
echo "Image: $IMAGE_DIGEST"
echo "Artifacts: $ARTIFACT_DIR"
echo "Stop: bash scripts/sitl/stop_px4_sitl.sh $CONTAINER_NAME"
