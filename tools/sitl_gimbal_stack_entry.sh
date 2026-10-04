#!/usr/bin/env bash
# Container entrypoint for the isolated camera/PX4 SIH qualification stack.
set -euo pipefail

runtime=${PIXEAGLE_SIH_RUNTIME:?}
python=${PIXEAGLE_SIH_PYTHON:?}
bin_dir=${PIXEAGLE_SIH_BIN_DIR:?}
router=${PIXEAGLE_SIH_ROUTER:?}
qgc_host=${PIXEAGLE_SIH_QGC_HOST:-127.0.0.1}

[[ -f $runtime/profile-manifest.json && -f $runtime/configs/config.yaml ]] || {
    echo "Prepared SIH profile is missing." >&2
    exit 1
}
[[ -x $python && -x $router && -x $bin_dir/mavlink2rest && -x $bin_dir/mavsdk_server_bin ]] || {
    echo "A pinned SIH runtime dependency is unavailable." >&2
    exit 1
}

instance=$($python - "$runtime/profile-manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest.get("kind") != "gimbal-sih-preflight" or not manifest.get("flight_commands_blocked"):
    raise SystemExit("Expected a prepared, initially command-blocked gimbal SIH profile")
print(manifest["instance_id"])
PY
)

mkdir -p "$runtime/logs" "$runtime/.ultralytics"
children=()
backend_pid=
cleanup() {
    if [[ -n $backend_pid ]]; then
        kill "$backend_pid" 2>/dev/null || true
        wait "$backend_pid" 2>/dev/null || true
    fi
    if ((${#children[@]})); then
        kill "${children[@]}" 2>/dev/null || true
        wait "${children[@]}" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

"$router" -t 0 -e 127.0.0.1:14569 \
    -e 127.0.0.1:12550 -e "$qgc_host":14560 127.0.0.1:14550 \
    > "$runtime/logs/router.log" 2>&1 &
children+=("$!")
"$bin_dir/mavlink2rest" -c udpin:127.0.0.1:14569 -s 127.0.0.1:8088 \
    > "$runtime/logs/mavlink2rest.log" 2>&1 &
children+=("$!")
"$bin_dir/mavsdk_server_bin" -p 50051 udpin://127.0.0.1:14540 \
    > "$runtime/logs/mavsdk.log" 2>&1 &
children+=("$!")

export PIXEAGLE_INSTANCE_ID="$instance"
export PIXEAGLE_PROJECT_ROOT="$runtime"
export PIXEAGLE_RUNTIME_LOG_DIR="$runtime/logs/runtime"
export PIXEAGLE_SIH_TRACE_DIR="$runtime/logs/traces"
export PIXEAGLE_RUN_ID="gimbal_sih_$(date -u +%Y%m%dT%H%M%SZ)"
export PIXEAGLE_ENABLE_SITL_INJECTIONS=1
export YOLO_AUTOINSTALL=False
export YOLO_CONFIG_DIR="$runtime/.ultralytics"
export PYTHONPATH="$runtime/src"
cd "$runtime"
"$python" "$runtime/src/classes/backend_supervisor.py" --root "$runtime" \
    --log "$runtime/logs/pixeagle.log" --sih &
backend_pid=$!
wait "$backend_pid"
