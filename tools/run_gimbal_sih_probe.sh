#!/usr/bin/env bash
# Isolated camera/PX4 SIH startup probe; hold mode leaves operator controls to QGC.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cache=${PIXEAGLE_SIH_CACHE:-"$HOME/.cache/pixeagle-qgc-baseline"}
bin_dir=${PIXEAGLE_SIH_BIN_DIR:-"$HOME/PixEagle/bin"}
opencv_lib=${PIXEAGLE_SIH_OPENCV_LIB:-"$HOME/PixEagle/.venv/lib"}
python=${PIXEAGLE_SIH_PYTHON:-"$cache/slice-3b-2026-09-22/runtime/full-ai-venv/bin/python"}
router=${PIXEAGLE_SIH_ROUTER:-"$cache/slice-4-2026-09-26/mavlink-router-src/build/src/mavlink-routerd"}
backend_image=${PIXEAGLE_SIH_BACKEND_IMAGE:-sha256:ecfaf2358be090447ff9948397075ce76cefff3a152fbfab006a2d26495ea14b}
px4_image=${PIXEAGLE_SIH_PX4_IMAGE:-px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865}
host_python=${PIXEAGLE_SIH_HOST_PYTHON:-python3}
entry=$repo/tools/sitl_gimbal_stack_entry.sh

[[ $# == 2 && ( $1 == --check || $1 == --probe || $1 == --hold ) ]] || {
    echo "Usage: $0 --check|--probe|--hold PRIVATE_RUNTIME" >&2
    exit 2
}
mode=$1
runtime=$($host_python -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$2")
python_root=$(cd -- "$(dirname -- "$python")/.." && pwd)
[[ -x $python && -x $router && -d $opencv_lib && -x $bin_dir/mavlink2rest && -x $bin_dir/mavsdk_server_bin ]] || {
    echo "A local SIH dependency is unavailable." >&2
    exit 1
}
"$host_python" - "$repo" "$runtime" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from tools.prepare_sitl_gimbal_profile import validate

manifest = validate(Path(sys.argv[2]))
print(f"Validated command-blocked SIH profile: {manifest['instance_id']}")
PY
docker image inspect "$backend_image" "$px4_image" >/dev/null
if [[ $mode == --check ]]; then
    echo "Read-only SIH preflight passed. No containers or services started."
    exit 0
fi

port=$($host_python - "$runtime/profile-manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["backend_port"])
PY
)
read -r camera_bind camera_port < <($host_python - "$runtime" <<'PY'
import json
import socket
import sys
from pathlib import Path

import yaml

runtime = Path(sys.argv[1])
manifest = json.loads((runtime / "profile-manifest.json").read_text(encoding="utf-8"))
config = yaml.safe_load((runtime / "configs/config.yaml").read_text(encoding="utf-8"))
if not config["GimbalTracker"]["ENABLED"]:
    print("127.0.0.1 0")
    raise SystemExit(0)
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
    route.connect((manifest["camera_host"], int(config["GimbalTracker"]["UDP_PORT"])))
    host_address = route.getsockname()[0]
print(host_address, int(config["GimbalTracker"]["LISTEN_PORT"]))
PY
)
command -v flock >/dev/null || { echo "flock is required for SIH port ownership." >&2; exit 1; }
mkdir -p "$cache"
exec {startup_lock}>"$cache/.gimbal-sih-startup.lock"
flock -w 15 "$startup_lock" || { echo "Another SIH probe is still starting." >&2; exit 1; }

# Only reclaim containers created by this probe after their launcher has died.
# A live launcher retains its own cleanup trap and must not be interrupted.
declare -A checked_probes=()
probe_containers=$(docker ps -a --filter label=pixeagle.sih=gimbal-probe --format '{{.Names}}')
while IFS= read -r candidate; do
    [[ $candidate =~ ^(pixeagle-gimbal-probe-([0-9]+))-(px4|backend)$ ]] || continue
    probe_name=${BASH_REMATCH[1]}
    owner_pid=${BASH_REMATCH[2]}
    [[ -z ${checked_probes[$probe_name]+set} ]] || continue
    checked_probes[$probe_name]=1
    owner_command=""
    if [[ -r /proc/$owner_pid/cmdline ]]; then
        owner_command=$(tr '\0' ' ' < "/proc/$owner_pid/cmdline")
    fi
    if [[ $owner_command == *run_gimbal_sih_probe.sh* ]]; then
        continue
    fi
    owned_containers=()
    for part in backend px4; do
        name="$probe_name-$part"
        if docker inspect "$name" >/dev/null 2>&1; then
            label=$(docker inspect "$name" --format '{{index .Config.Labels "pixeagle.sih"}}')
            [[ $label == gimbal-probe ]] || {
                echo "Refusing to stop $name: SIH ownership label is missing." >&2
                exit 1
            }
            owned_containers+=("$name")
        fi
    done
    if (( ${#owned_containers[@]} )); then
        echo "Stopping orphaned SIH probe $probe_name (launcher PID $owner_pid is gone)."
        docker stop --timeout 10 "${owned_containers[@]}" >/dev/null
    fi
    if docker network inspect "$probe_name" >/dev/null 2>&1; then
        network_label=$(docker network inspect "$probe_name" --format '{{index .Labels "pixeagle.sih"}}')
        [[ $network_label == gimbal-probe ]] || {
            echo "Refusing to remove $probe_name: SIH network ownership label is missing." >&2
            exit 1
        }
        docker network rm "$probe_name" >/dev/null
    fi
done <<< "$probe_containers"

"$host_python" - "$port" "$camera_bind" "$camera_port" <<'PY'
import socket
import sys

checks = [
    (socket.SOCK_STREAM, "127.0.0.1", int(sys.argv[1]), "backend TCP"),
    (socket.SOCK_DGRAM, sys.argv[2], int(sys.argv[3]), "camera telemetry UDP"),
]
for kind, address, port, description in checks:
    if port == 0:
        continue
    with socket.socket(socket.AF_INET, kind) as probe:
        try:
            probe.bind((address, port))
        except OSError as exc:
            raise SystemExit(
                f"SIH {description} {address}:{port} is occupied. "
                "Only orphaned PixEagle probe containers are closed automatically; "
                "stop an active probe with Ctrl-C or close the other port owner."
            ) from exc
PY

run_id="gimbal-probe-$$"
px4_name="pixeagle-$run_id-px4"
stack_name="pixeagle-$run_id-backend"
network_name="pixeagle-$run_id"
archive="$runtime/logs/history/$(date -u +%Y%m%dT%H%M%SZ)-$$"
for previous in pixeagle.log router.log mavlink2rest.log mavsdk.log stack-probe-result.json; do
    if [[ -f $runtime/logs/$previous ]]; then
        mkdir -p "$archive"
        mv -- "$runtime/logs/$previous" "$archive/$previous"
    fi
done
network_started=false
cleanup() {
    docker stop --timeout 10 "$stack_name" "$px4_name" >/dev/null 2>&1 || true
    if $network_started; then docker network rm "$network_name" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker network create --driver bridge --label pixeagle.sih=gimbal-probe "$network_name" >/dev/null
network_started=true
gateway=$(docker network inspect "$network_name" --format '{{(index .IPAM.Config 0).Gateway}}')
[[ -n $gateway ]] || { echo "Dedicated Docker gateway is unavailable." >&2; exit 1; }
camera_forwarding=()
if (( camera_port > 0 )); then camera_forwarding=(-p "$camera_bind:$camera_port:$camera_port/udp"); fi
docker run -d --rm --name "$px4_name" --label pixeagle.sih=gimbal-probe \
    --network "$network_name" -p "127.0.0.1:$port:$port/tcp" \
    "${camera_forwarding[@]}" \
    -e PX4_SIM_MODEL=sihsim_quadx "$px4_image" >/dev/null
docker run -d --rm --name "$stack_name" --label pixeagle.sih=gimbal-probe \
    --user "$(id -u):$(id -g)" --network "container:$px4_name" \
    -e LD_LIBRARY_PATH=/mnt/hostlibs \
    -e PIXEAGLE_SIH_RUNTIME="$runtime" -e PIXEAGLE_SIH_PYTHON="$python" \
    -e PIXEAGLE_SIH_BIN_DIR="$bin_dir" -e PIXEAGLE_SIH_ROUTER="$router" \
    -e PIXEAGLE_SIH_QGC_HOST="$gateway" \
    -v "$runtime:$runtime" -v "$python_root:$python_root:ro" \
    -v "$router:$router:ro" -v "$bin_dir:$bin_dir:ro" -v "$opencv_lib:$opencv_lib:ro" \
    -v /usr/lib/x86_64-linux-gnu:/mnt/hostlibs:ro \
    -v "$entry:$entry:ro" "$backend_image" bash "$entry" >/dev/null
flock -u "$startup_lock"
docker image inspect "$px4_image" --format '{{.Id}}' > "$runtime/logs/px4-image-id.txt"
docker image inspect "$backend_image" --format '{{.Id}}' > "$runtime/logs/backend-image-id.txt"

# AUTOPILOT_VERSION is observational identity evidence, not a flight action.
docker exec -i "$stack_name" "$python" - <<'PY'
import time

import requests

router = "http://127.0.0.1:8088"
deadline = time.monotonic() + 45
heartbeat_seen = False
requests_sent = 0
last_error = None
while time.monotonic() < deadline:
    try:
        aggregate = requests.get(router + "/v1/mavlink", timeout=2).json()
        messages = (aggregate.get("vehicles", {}).get("1", {})
                    .get("components", {}).get("1", {}).get("messages", {}))
        if "HEARTBEAT" not in messages:
            time.sleep(0.5)
            continue
        heartbeat_seen = True
        uid = messages.get("AUTOPILOT_VERSION", {}).get("message", {}).get("uid")
        if isinstance(uid, int) and uid > 0:
            break
        message = requests.get(
            router + "/v1/helper/mavlink?name=COMMAND_LONG", timeout=2,
        ).json()
        message["message"].update(
            param1=148.0, command={"type": "MAV_CMD_REQUEST_MESSAGE"},
            target_system=1, target_component=1,
        )
        requests.post(router + "/v1/mavlink", json=message, timeout=2).raise_for_status()
        requests_sent += 1
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        last_error = type(exc).__name__
    time.sleep(2)
else:
    raise SystemExit(
        "Simulated PX4 UID was not observed by MAVLink2REST "
        f"(heartbeat_seen={heartbeat_seen}, requests_sent={requests_sent}, "
        f"last_error={last_error})"
    )
print(f"Simulated PX4 identity observed after {requests_sent} request(s).")
PY

"$host_python" - "$runtime" <<'PY'
import json
import socket
import sys
import time
from pathlib import Path

import requests

runtime = Path(sys.argv[1])
manifest = json.loads((runtime / "profile-manifest.json").read_text(encoding="utf-8"))
credentials = json.loads((runtime / "credentials.json").read_text(encoding="utf-8"))
endpoint = credentials["endpoint"]
camera_required = manifest.get("recorded_video") is None
last_error = None
deadline = time.monotonic() + 55
with requests.Session() as client:
    while time.monotonic() < deadline:
        try:
            login = client.post(endpoint + "/api/v1/auth/login", json={
                "username": credentials["username"], "password": credentials["password"],
            }, timeout=2)
            if login.status_code != 200:
                last_error = f"Login returned {login.status_code}"
                time.sleep(0.5)
                continue
            context = client.get(endpoint + "/api/v1/integration/context", timeout=3).json()
            safety = client.get(endpoint + "/api/v1/integration/safety", timeout=3).json()
            camera = client.get(endpoint + "/api/v1/gimbal/control", timeout=3).json() if camera_required else {}
            status = client.get(endpoint + "/status", timeout=3).json()
            if (context.get("instance_id") != manifest["instance_id"]
                    or safety.get("active") is not True or status.get("following_active") is not False):
                raise RuntimeError("Wrong backend identity or unexpected command/following state")
            uid = context.get("telemetry", {}).get("autopilot_uid")
            if not isinstance(uid, str) or not uid.isdigit() or int(uid) <= 0:
                last_error = "Simulated PX4 UID not yet observed"
                time.sleep(0.5)
                continue
            if (context.get("telemetry", {}).get("fresh") is not True
                    or (camera_required and (camera.get("connected") is not True
                        or camera.get("telemetry", {}).get("angles_fresh") is not True))
                    or not context.get("video", {}).get("width")
                    or not context.get("video", {}).get("height")):
                last_error = "Camera angle, video, or PX4 telemetry not yet live"
                time.sleep(0.5)
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as telemetry:
                try:
                    telemetry.bind(("0.0.0.0", 14560))
                except OSError as exc:
                    raise SystemExit("QGC telemetry port 14560 is occupied; close the old QGC session") from exc
                telemetry_deadline = time.monotonic() + 8
                while True:
                    remaining = telemetry_deadline - time.monotonic()
                    if remaining <= 0:
                        raise SystemExit("No simulated PX4 system 1 telemetry reached QGC UDP 14560")
                    telemetry.settimeout(remaining)
                    try:
                        packet, _ = telemetry.recvfrom(4096)
                    except socket.timeout as exc:
                        raise SystemExit("No simulated PX4 telemetry reached QGC UDP 14560") from exc
                    system_id = (packet[5] if len(packet) >= 10 and packet[0] == 0xFD
                                 else packet[3] if len(packet) >= 6 and packet[0] == 0xFE
                                 else None)
                    if system_id == 1:
                        break
            result = {
                "instance_id": manifest["instance_id"], "simulated_autopilot_uid": uid,
                "commands_blocked": True, "following_active": False,
                "camera_angles_fresh": True if camera_required else None, "video_dimensions": [
                    context["video"]["width"], context["video"]["height"],
                ],
                "qgc_telemetry_system_id": system_id,
                "claim": "read-only startup and association probe; no follower command sent",
            }
            (runtime / "logs/stack-probe-result.json").write_text(json.dumps(result, indent=2) + "\n")
            print("Isolated camera/PX4 SIH startup probe passed; no follower command sent.")
            break
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
            time.sleep(0.5)
    else:
        raise SystemExit(f"SIH backend or simulated UID not ready: {last_error}")
PY

# Only the verified launcher can bind replay to this owned simulator namespace.
docker exec -i "$stack_name" "$python" - "$runtime" <<'PY'
import json
import os
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest = json.loads((root / "profile-manifest.json").read_text())
probe = json.loads((root / "logs/stack-probe-result.json").read_text())
if probe["instance_id"] != manifest["instance_id"] or probe["commands_blocked"] is not True:
    raise SystemExit("SIH replay binding requires the verified blocked startup probe")
path = root / "logs/sih-replay-binding.json"
staged = path.with_suffix(".staged")
staged.write_text(json.dumps({
    "kind": "owned-isolated-sih-v1", "instance_id": manifest["instance_id"],
    "simulated_autopilot_uid": probe["simulated_autopilot_uid"],
    "network_namespace": os.readlink("/proc/self/ns/net"),
}) + "\n")
staged.chmod(0o600)
os.replace(staged, path)
PY

if [[ $mode == --hold ]]; then
    echo "Isolated SIH stack is ready with PixEagle flight commands blocked."
    echo "Login file: $runtime/credentials.json"
    echo "Backend: http://127.0.0.1:$port"
    echo "Probe and backend logs: $runtime/logs"
    echo "Press Ctrl-C to stop the owned containers after your QGC session."
    while docker inspect "$px4_name" "$stack_name" >/dev/null 2>&1; do
        sleep 1
    done
    echo "An owned SIH container exited; inspect the runtime logs." >&2
    exit 1
fi
