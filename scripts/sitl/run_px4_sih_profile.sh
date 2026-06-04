#!/bin/bash
# Run the PixEagle PX4 SIH validation profile through the checked-in harness.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MODE="dry-run"
PLAN_NAME="phase2_follower_validation"
ARTIFACT_ROOT="reports/sitl"
RUN_ID=""
TIMEOUT_S="5.0"
STARTUP_WAIT_S="15.0"
PX4_IMAGE="${PIXEAGLE_SIH_PX4_IMAGE:-px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01}"
PX4_MODEL="${PIXEAGLE_SIH_PX4_MODEL:-sihsim_quadx}"
PX4_CONTAINER_NAME=""
PX4_CONTAINER_ID=""
PX4_PARAMS_FILE=""
PX4_LOG=""
PIXEAGLE_LOG=""
RUN_SCENARIOS=0
ALLOW_CONTROL_ACTIONS=0
AUTO_PX4_CONTAINER_ARTIFACTS=0
EMIT_JSON=0
PX4_ULOG_FILES=()
PX4_TLOG_FILES=()
PYTHON_BIN="${PYTHON_BIN:-python3}"

show_help() {
    cat <<'EOF'
Usage: bash scripts/sitl/run_px4_sih_profile.sh [OPTIONS]

Runs PixEagle's lightweight PX4 SIH validation profile using
tools/run_sitl_validation_suite.py. The default mode is side-effect-free
dry-run. Runtime modes are opt-in and never configure host routing, start
PixEagle, start MAVLink2REST, install services, or touch real hardware.

Modes:
  --mode dry-run        Validate the checked-in plan only (default)
  --mode probe-only     Collect evidence from an already running stack
  --mode execute-px4    Start only a harness-owned official PX4 SIH container

Options:
  --plan-name NAME              SITL plan name (default: phase2_follower_validation)
  --artifact-root DIR           Evidence root for runtime modes (default: reports/sitl)
  --run-id ID                   Runtime artifact run id
  --timeout-s SECONDS           Probe/action timeout (default: 5.0)
  --startup-wait-s SECONDS      PX4 startup wait in execute-px4 mode (default: 15.0)
  --px4-image IMAGE             PX4 image tag (default: px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01)
  --px4-model MODEL             PX4_SIM_MODEL (default: sihsim_quadx)
  --px4-container-name NAME     Managed execute name or probe-only container selector
  --px4-container-id ID         Probe-only operator-managed container selector
  --auto-px4-container-artifacts
                                Opt into read-only container artifact discovery
                                for probe-only; execute-px4 enables it after
                                harness-owned container verification
  --px4-params-file PATH        Import exported PX4 params.txt
  --px4-ulog PATH               Import a PX4 .ulg file; repeatable
  --px4-tlog PATH               Import a MAVLink .tlog file; repeatable
  --px4-log PATH                Import PX4 stdout/log for probe-only evidence
  --pixeagle-log PATH           Import PixEagle backend log
  --run-scenarios               Execute checked-in runtime scenario actions
  --allow-control-actions       Allow gated non-GET/control scenario actions
  --json                        Emit harness JSON
  --help                        Show this help

Accepted runtime evidence still requires complete probes, route/profile data,
scenario results, logs, PX4 params, ULog/tlog manifests, and container metadata.
SIH is L2 PX4 control-plane evidence only; it is not tracker, visual SITL, HIL,
field, or real-aircraft evidence.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="${2:?missing value for --mode}"
            shift 2
            ;;
        --plan-name)
            PLAN_NAME="${2:?missing value for --plan-name}"
            shift 2
            ;;
        --artifact-root)
            ARTIFACT_ROOT="${2:?missing value for --artifact-root}"
            shift 2
            ;;
        --run-id)
            RUN_ID="${2:?missing value for --run-id}"
            shift 2
            ;;
        --timeout-s)
            TIMEOUT_S="${2:?missing value for --timeout-s}"
            shift 2
            ;;
        --startup-wait-s)
            STARTUP_WAIT_S="${2:?missing value for --startup-wait-s}"
            shift 2
            ;;
        --px4-image)
            PX4_IMAGE="${2:?missing value for --px4-image}"
            shift 2
            ;;
        --px4-model)
            PX4_MODEL="${2:?missing value for --px4-model}"
            shift 2
            ;;
        --px4-container-name)
            PX4_CONTAINER_NAME="${2:?missing value for --px4-container-name}"
            shift 2
            ;;
        --px4-container-id)
            PX4_CONTAINER_ID="${2:?missing value for --px4-container-id}"
            shift 2
            ;;
        --auto-px4-container-artifacts)
            AUTO_PX4_CONTAINER_ARTIFACTS=1
            shift
            ;;
        --px4-params-file)
            PX4_PARAMS_FILE="${2:?missing value for --px4-params-file}"
            shift 2
            ;;
        --px4-ulog)
            PX4_ULOG_FILES+=("${2:?missing value for --px4-ulog}")
            shift 2
            ;;
        --px4-tlog)
            PX4_TLOG_FILES+=("${2:?missing value for --px4-tlog}")
            shift 2
            ;;
        --px4-log)
            PX4_LOG="${2:?missing value for --px4-log}"
            shift 2
            ;;
        --pixeagle-log)
            PIXEAGLE_LOG="${2:?missing value for --pixeagle-log}"
            shift 2
            ;;
        --run-scenarios)
            RUN_SCENARIOS=1
            shift
            ;;
        --allow-control-actions)
            ALLOW_CONTROL_ACTIONS=1
            shift
            ;;
        --json)
            EMIT_JSON=1
            shift
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

case "$MODE" in
    dry-run|probe-only|execute-px4)
        ;;
    *)
        echo "Invalid --mode: $MODE" >&2
        show_help >&2
        exit 2
        ;;
esac

if [[ "$MODE" == "execute-px4" && -n "$PX4_CONTAINER_ID" ]]; then
    echo "--px4-container-id selects an existing container and cannot be used with execute-px4" >&2
    exit 2
fi

COMMAND=(
    "$PYTHON_BIN"
    tools/run_sitl_validation_suite.py
    --plan-name "$PLAN_NAME"
    --artifact-root "$ARTIFACT_ROOT"
    --timeout-s "$TIMEOUT_S"
)

if [[ -n "$RUN_ID" ]]; then
    COMMAND+=(--run-id "$RUN_ID")
fi
if [[ "$EMIT_JSON" -eq 1 ]]; then
    COMMAND+=(--json)
fi
if [[ "$RUN_SCENARIOS" -eq 1 ]]; then
    COMMAND+=(--run-scenarios)
fi
if [[ "$ALLOW_CONTROL_ACTIONS" -eq 1 ]]; then
    COMMAND+=(--allow-control-actions)
fi

case "$MODE" in
    dry-run)
        COMMAND+=(--dry-run)
        ;;
    probe-only)
        COMMAND+=(--probe-only)
        if [[ -n "$PX4_CONTAINER_NAME" ]]; then
            COMMAND+=(--px4-container-name "$PX4_CONTAINER_NAME")
        fi
        if [[ -n "$PX4_CONTAINER_ID" ]]; then
            COMMAND+=(--px4-container-id "$PX4_CONTAINER_ID")
        fi
        if [[ "$AUTO_PX4_CONTAINER_ARTIFACTS" -eq 1 ]]; then
            COMMAND+=(--auto-px4-container-artifacts)
        fi
        ;;
    execute-px4)
        COMMAND+=(
            --execute
            --allow-process-start
            --auto-px4-container-artifacts
            --px4-image "$PX4_IMAGE"
            --px4-model "$PX4_MODEL"
            --startup-wait-s "$STARTUP_WAIT_S"
        )
        if [[ -n "$PX4_CONTAINER_NAME" ]]; then
            COMMAND+=(--px4-container-name "$PX4_CONTAINER_NAME")
        fi
        ;;
esac

if [[ -n "$PX4_PARAMS_FILE" ]]; then
    COMMAND+=(--px4-params-file "$PX4_PARAMS_FILE")
fi
for ulog_file in "${PX4_ULOG_FILES[@]}"; do
    COMMAND+=(--px4-ulog "$ulog_file")
done
for tlog_file in "${PX4_TLOG_FILES[@]}"; do
    COMMAND+=(--px4-tlog "$tlog_file")
done
if [[ -n "$PX4_LOG" ]]; then
    COMMAND+=(--px4-log "$PX4_LOG")
fi
if [[ -n "$PIXEAGLE_LOG" ]]; then
    COMMAND+=(--pixeagle-log "$PIXEAGLE_LOG")
fi

cd "$PROJECT_ROOT"
exec "${COMMAND[@]}"
