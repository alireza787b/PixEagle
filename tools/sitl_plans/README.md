# PixEagle SITL Plan Library

This directory contains checked-in scenario plans for PX4-in-loop validation.
The plans are executable by `tools/run_sitl_validation_suite.py`, but they are
not part of normal CI unless an operator explicitly opts in.

## Contract

Each plan is JSON with:

- `schema_version`: currently `1`
- `name`, `title`, `level`, and `description`
- `stack`: expected PX4, MavlinkAnywhere, MAVLink2REST, and PixEagle endpoints
- `stack.px4.artifact_collection`: read-only container search roots and file
  name patterns for best-effort params, ULog, and tlog discovery
- `evidence_contract`: artifact paths that must exist or be explained in the run manifest
- MavlinkAnywhere route evidence: `/api/v1/endpoints`,
  `/api/v1/config`, and `/api/v1/profiles/summary` are parsed as structured
  endpoint objects; incidental address strings in response text or
  address/port-only JSON do not satisfy the routing contract; profile summary
  metadata must report `backend=mavlink-anywhere` and `present=true`
- `scenarios`: scenario definitions with `id`, `objective`, `stimulus`,
  executable `actions`, `probes`, `acceptance`, and `evidence`

Supported scenario action types:

- `http_request`: issue a checked-in HTTP request against PixEagle,
  MAVLink2REST, or MavlinkAnywhere
- `wait`: observe the stack for a bounded duration
- `manual_fault`: record a required fault that is not automated yet; this keeps
  accepted evidence incomplete until a real injector exists
- `operator_note`: record non-executing operator context

The current Phase 2 plan has zero `manual_fault` actions. The action type
remains supported so future plans can make unimplemented fault gaps explicit
instead of hiding them.

Non-GET or explicitly marked control actions are blocked unless the runtime
command includes `--allow-control-actions`. Phase 2 Offboard-start,
Offboard-stop, and operator-abort control actions use typed
`/api/v1/actions/*` resources with `confirm=true`, scenario-scoped idempotency
keys, local action records, and explicit claim boundaries. Retired
`/commands/*` control aliases are no longer registered HTTP routes and are not
used by the checked-in plan.

The target-loss scenario now uses PixEagle's validation-only
`POST /api/v1/sitl/injections/tracker-output` route. That route is disabled
unless PixEagle starts with `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`, and it only
dispatches into the follower path when follow mode is already active.
The checked-in assertions currently target `mc_velocity_position` and verify
the fail-closed hold fields plus the `OffboardCommander` publication boundary.

The video-stall scenario uses PixEagle's validation-only
`POST /api/v1/sitl/injections/video-stall` route. It injects frame-status
metadata into the same `handle_video_frame_unavailable()` path used by the main
loop; it does not stop cameras, GStreamer, Docker, PX4, or routing services.

The commander publish-failure scenario uses PixEagle's validation-only
`POST /api/v1/sitl/injections/commander-publish-failure` route. It records
bounded synthetic publish failures inside the running `OffboardCommander`,
trips the existing local failure policy, and awaits the normal AppController
follow-mode cleanup. It does not synthesize MAVSDK setpoint publishes, replace
PX4 interfaces, stop services, or mutate MAVLink routing; cleanup still uses
the normal Offboard stop path.

The MAVSDK disconnect scenario uses PixEagle's validation-only
`POST /api/v1/sitl/injections/mavsdk-disconnect` route. It marks the local
`PX4InterfaceManager` MAVSDK command path validation-disconnected, records
bounded commander failures, and awaits the normal fail-closed cleanup path. It
does not stop PX4, Docker, MavlinkAnywhere, MAVLink2REST, a MAVSDK server,
network interfaces, or MAVLink routes, so it proves PixEagle-local behavior
only.

The MAVLink2REST timeout scenario uses PixEagle's validation-only
`POST /api/v1/sitl/injections/mavlink2rest-timeout` route. It records a
bounded PixEagle-local client timeout, ages existing telemetry stale when
requested, and leaves MAVLink2REST, PX4, Docker, MavlinkAnywhere, routing, and
network interfaces running. The scenario first asserts fresh PixEagle telemetry
with a real last-success age, then probes MAVLink2REST directly after injection
so the evidence does not overclaim a real service outage.

The Phase 2 validation plan must cover:

- `offboard_entry`
- `offboard_heartbeat`
- `follower_setpoints`
- `target_loss`
- `video_stall`
- `mavsdk_disconnect`
- `mavlink2rest_timeout`
- `operator_abort`
- `commander_publish_failure`

## Normal Development

Use dry-run validation for fast feedback:

```bash
python3 tools/run_sitl_validation_suite.py --plan-name phase2_follower_validation --dry-run
```

Dry-run validates and prints the resolved plan without starting PX4, Docker,
MavlinkAnywhere, MAVLink2REST, or PixEagle.

To review the scenario action schedule without executing it:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --run-scenarios
```

The official PX4 SIH profile wrapper uses the same harness and defaults to the
same side-effect-free dry-run. The checked-in SIH plan currently pins
`px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01` with repo digest
`px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`.

```bash
bash scripts/sitl/run_px4_sih_profile.sh --mode dry-run --json
```

Runtime wrapper modes are explicit:

- `--mode probe-only` collects from an already running stack and starts no
  processes.
- `--mode execute-px4` starts only a harness-owned official PX4 SIH container
  with `--execute --allow-process-start`; it does not start PixEagle,
  MAVLink2REST, MavlinkAnywhere, or mutate host routing.

The matching GitHub workflow is `.github/workflows/px4-sih-validation.yml`.
It is `workflow_dispatch`/scheduled only, uploads `reports/sitl/**` on every
run, and is not part of normal `push` or `pull_request` CI.

The official PX4 Gazebo visual profile wrapper is the maintained L4 simulation
path for camera/video runs:

```bash
bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode dry-run --json
```

Runtime wrapper modes are explicit:

- `--mode probe-only` collects from an already running official Gazebo visual
  stack and starts no processes.
- `--mode execute-gazebo` starts only a harness-owned official
  `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01` container with
  `HEADLESS=1` and `PX4_SIM_MODEL=gz_x500_mono_cam` by default.

The Gazebo profile reuses the proven PixEagle `UDP_STREAM` GStreamer receiver
for RTP/H.264 video on port `5600`. Accepted evidence must include the
generated receiver proof manifest, Gazebo receiver pipeline, Gazebo frame
hashes, tracker and Offboard command traces, structured route/profile data,
PX4 params/logs/ULog/tlog manifests, and container metadata. Missing runtime
video or PX4 artifacts keep the run incomplete. The harness also validates
visual artifact content: the receiver proof must be an executed passing proof,
the receive pipeline must include strict RTP/H.264 caps, `h264parse`, BGR
conversion, and bounded appsink settings, frame hashes must contain at least
two valid and distinct decoded frames, trace JSONL must be parseable and
include timing evidence, and the PX4 metadata must include container inspection
plus an image repo digest for the Gazebo plan.

The 2026-06-04 VPS probe pulled the default official image and verified its
repo digest, but the all-in-one PX4/Gazebo entrypoint timed out waiting for the
Gazebo world before PixEagle visual evidence could be collected. Keep such runs
`incomplete`; use native Ubuntu GUI/GPU, a stronger headless runner, or a
separately proven official-image startup workaround for accepted L4 visual
evidence.

Probe-only runs can import visual artifacts explicitly:

```bash
bash scripts/sitl/run_px4_gazebo_visual_profile.sh \
  --mode probe-only \
  --px4-container-name pixeagle-px4-gazebo \
  --auto-px4-container-artifacts \
  --generated-receiver-proof-manifest reports/video/<proof-run>/manifest.json \
  --gazebo-receiver-pipeline /path/to/gazebo_receiver_pipeline.txt \
  --gazebo-frame-hashes /path/to/gazebo_frame_hashes.json \
  --tracker-command-trace /path/to/tracker_command_trace.jsonl \
  --offboard-publish-trace /path/to/offboard_publish_trace.jsonl \
  --artifact-root reports/sitl
```

The matching GitHub workflow is
`.github/workflows/px4-gazebo-visual-validation.yml`; it is
`workflow_dispatch`/scheduled only, accepts the same visual evidence import
paths, and is not normal pull-request CI.

## Evidence Runs

When a PX4/MavlinkAnywhere/PixEagle stack is already running, collect a probe
package without starting or stopping services:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --artifact-root reports/sitl
```

The run writes `reports/sitl/<timestamp>-<plan>/manifest.json` plus plan,
config, route, status, and probe artifacts. Plain probe-only collection does
not execute checked-in scenarios, so it is expected to remain incomplete for
the Phase 2 evidence contract unless `scenarios/scenario_results.json` is
provided by `--run-scenarios`. Runs are also incomplete when any required
artifact is missing/placeholder or when the route/config probes do not match
the plan. A passing complete run is still not a field claim; it is evidence for
the exact scenario, versions, endpoints, and artifacts in that directory.

To execute checked-in scenario actions against a running stack:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --run-scenarios \
  --artifact-root reports/sitl
```

Control actions such as Offboard start, Offboard stop, and operator abort
remain blocked unless the operator explicitly adds `--allow-control-actions`.
Target-loss, video-stall, commander publish-failure, MAVSDK local command-path
disconnect, and MAVLink2REST local timeout injection are automated. Accepted runtime
evidence still remains incomplete when required PX4 params, ULog/tlog,
container metadata, route data, scenario results, logs, or config snapshots are
missing or placeholder. Failed scenario assertions take precedence over missing
artifacts in the manifest result.

PX4 evidence can be imported into the artifact package without running PX4 from
the harness:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --artifact-root reports/sitl \
  --px4-params-file /path/to/params.txt \
  --px4-ulog /path/to/flight.ulg \
  --px4-tlog /path/to/flight.tlog \
  --px4-log /path/to/px4_sitl.log \
  --pixeagle-log /path/to/pixeagle.log
```

Imported params are copied to `px4/params.txt`. ULog and tlog files are copied
under `px4/ulog/` and `px4/tlog/`; their manifests include size and SHA-256
checksums. Imported PX4 and PixEagle logs are copied to `logs/px4_sitl.log`
and `logs/pixeagle.log`. `px4/container_metadata.json` is also required and is
collected from Docker image/container inspection when available.
The harness also writes `px4/offboard_observation.json`: accepted evidence
requires MAVLink2REST HEARTBEAT `custom_mode=393216` for PX4 Offboard with
the MAVLink custom-mode flag set, then parsed tlog setpoint cadence targeted
at the same PX4 system/component inside the Offboard-start scenario window.
The cadence threshold is at least 3 setpoint messages over at least 1 second
at or above 2 Hz. If tlogs are absent, `pymavlink` is not installed, scenario
timing is unavailable, or artifacts mix different PX4 system IDs, this
artifact records the reason and the run remains incomplete instead of treating
local PixEagle counters as PX4-observed proof.

When the harness starts a PX4 container with
`--execute --allow-process-start`, it attempts read-only automatic PX4 artifact
collection after the container is verified by PixEagle labels and run ID. The
auto path uses `docker exec` to run `find` in configured search roots, then
`docker cp` to copy matching params, ULog, and tlog files into the evidence
directory. If files are not found or cannot be copied, the corresponding
artifact remains a placeholder and the run remains incomplete.

For an operator-managed PX4 container, automatic copying requires both an
explicit selector and an explicit opt-in:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --run-scenarios \
  --allow-control-actions \
  --artifact-root reports/sitl \
  --px4-container-name pixeagle-px4-sitl \
  --auto-px4-container-artifacts \
  --pixeagle-log /path/to/pixeagle.log
```

Use `--px4-container-id` instead of `--px4-container-name` when the container ID
is the safer selector. Without `--auto-px4-container-artifacts`, a provided
container selector is used for metadata inspection only. Operator-managed
containers are never stopped by the harness.
