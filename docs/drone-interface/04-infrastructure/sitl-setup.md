# PX4 SITL Validation Setup

PixEagle SITL validation is evidence-driven. A run is only accepted when the
scenario plan, exact commands, versions, config snapshots, route map, PixEagle
status, MAVLink health, and PX4 log artifacts are saved under one artifact
directory.

This guide covers the PixEagle validation ladder from headless PX4-in-loop
through opt-in full visual simulation. It does not claim HIL or real-aircraft
success.

## Validation Ladder

| Level | Runs in normal CI | Purpose |
| --- | --- | --- |
| L0 unit/contract | yes | follower math, tracker contracts, command validation, schema, API inventory |
| L1 mock integration | yes | tracker/follower/command flow with MAVSDK and MAVLink2REST fakes |
| L2 PX4 headless SITL | no, opt-in | PX4 Offboard entry, heartbeat, abort, disconnect, telemetry failures |
| L3 tracker-in-loop | no, opt-in/nightly | deterministic video or gimbal traces through tracker and follower contracts |
| L4 full visual SITL | manual/nightly | X-Plane, Gazebo camera, or equivalent full pipeline evidence |
| L5 HIL/field | explicit approval only | hardware and real-world validation with operator procedures |

## Source References

Checked on 2026-06-11:

- PX4 pre-built SITL package docs
  (`https://docs.px4.io/main/en/simulation/px4_sitl_prebuilt_packages`) list
  `px4io/px4-sitl:<tag>` for SIH/headless simulation and
  `px4io/px4-sitl-gazebo:<tag>` for Gazebo Harmonic. They also document
  release-version tags such as `v1.17.0`, `PX4_SIM_MODEL`, `HEADLESS=1`,
  Linux host networking, `14540/udp` for MAVSDK/offboard, and `14550/udp` for
  GCS.
- PX4 Gazebo video-streaming docs
  (`https://docs.px4.io/main/en/sim_gazebo_gz/#video-streaming`) list camera
  models including `gz_x500_mono_cam` and `gz_x500_gimbal`, with RTP/H.264 UDP
  streaming on port `5600` and a GStreamer receiver pipeline using RTP caps.
- MAVSDK documents `udpin://0.0.0.0:14540` as the standard PX4 SITL offboard
  API connection.
- Docker Hub's `px4io/px4-sitl-gazebo` page
  (`https://hub.docker.com/r/px4io/px4-sitl-gazebo`) describes the official
  Gazebo Harmonic image, camera/LiDAR/depth support, and `HEADLESS=1` for CI or
  remote use.
- `jonasvautherin/px4-gazebo-headless` remains an unofficial fallback or
  benchmark for optional camera experiments. If used, pin the exact tag and
  digest in the run manifest and do not replace the official path without a
  separate acceptance decision.
- MavlinkAnywhere source `origin/main` was reviewed at
  `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`
  (`v3.0.14-2-g7643d4d`). Its current dashboard API exposes
  `/api/v1/status`, `/api/v1/diagnostics`, `/api/v1/endpoints`,
  `/api/v1/config`, and `/api/v1/profiles/summary`.

## Ports

| Port | Owner | Purpose |
| --- | --- | --- |
| `14550/udp` | MavlinkAnywhere input in this plan | PX4 SITL ingress; use a separate explicit endpoint for QGC |
| `14540/udp` | MavlinkAnywhere output | MAVSDK Offboard commands |
| `14569/udp` | MavlinkAnywhere output | MAVLink2REST input |
| `12550/udp` | MavlinkAnywhere output | local debug/monitoring |
| `8088/tcp` | MAVLink2REST | local telemetry HTTP API |
| `5077/tcp` | PixEagle backend | status/API probes |
| `9070/tcp` | MavlinkAnywhere dashboard | local route/status API |

Keep MAVLink2REST and MavlinkAnywhere dashboard endpoints on loopback unless
the validation host has an explicit VPN/firewall/auth plan.

The harness performs read-only MavlinkAnywhere probes. HTTP health/status alone
does not prove routing. Endpoint, config, and profile-summary probes must all
succeed and satisfy the required-output checks. An older or unprepared local
dashboard can be alive while those evidence gates correctly remain incomplete.
Do not expose or mutate the sidecar merely to make a validation probe pass; use
the [Companion Runtime Contract](../../architecture/companion-runtime-contract.md)
and an operator-approved preparation step.

Each maintained SITL plan declares a MavlinkAnywhere compatibility policy:
reviewed source ref `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`
(`v3.0.14-2-g7643d4d`), minimum dashboard version `3.0.14`, loopback
read-without-credentials expectation, required read paths
`/api/v1/status`, `/api/v1/diagnostics`, `/api/v1/endpoints`,
`/api/v1/profiles/summary`, and `/api/v1/config`, structured endpoint fields,
and required profile metadata. Runtime evidence writes
`versions/mavlink_anywhere_dashboard.json` and classifies the sidecar as:

- `unavailable`: the dashboard status probe could not be reached.
- `unexpected_auth`: a required loopback read returned auth/permission
  protection where the plan expected local read access.
- `unsupported_contract_version`: the dashboard version or required read API
  contract is missing or below the plan policy.
- `unprepared_config`: the API contract is compatible, but required enabled
  normal-mode outputs or profile metadata are not prepared.
- `prepared_routing`: version, read paths, profile metadata, and required
  outputs all match the plan.

Accepted evidence also requires `security/secret_scan.json`. The scan rejects
high-confidence tokens, passwords, private keys, URL credentials, authorization
headers, query-string secrets, and Wi-Fi PSKs in copied configs, probes, logs,
traces, and text artifacts. Binary flight logs such as `.ulg`, `.tlog`, and
BSON-like files are skipped with explicit metadata instead of decoded.

## Checked-In Harness

Plan library:

- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/gazebo_visual_validation.json`

Harness:

- `tools/run_sitl_validation_suite.py`

Safe PX4 container helpers:

- `scripts/sitl/start_px4_sitl.sh`
- `scripts/sitl/stop_px4_sitl.sh`
- `scripts/sitl/run_px4_sih_profile.sh`
- `scripts/sitl/run_px4_gazebo_visual_profile.sh`

Pytest markers:

- `sitl`
- `px4`
- `e2e`
- `hardware`
- `manual`

Normal CI excludes the external runtime markers. To run the operator-gated test
entry point, set `PIXEAGLE_RUN_SITL=1` and provide a running SITL stack.

## Dry-Run Plan Validation

Dry-run is side-effect free. It validates the checked-in plan and prints the
scenario/evidence contract without starting services:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run
```

Equivalent Make target:

```bash
make sitl-dry-run
```

## Opt-In PX4 SIH Profile

PixEagle also ships a lightweight official-PX4 SIH profile wrapper:

```bash
bash scripts/sitl/run_px4_sih_profile.sh --mode dry-run --json
```

Equivalent Make target:

```bash
make sitl-sih-dry-run
```

### Optional PX4-Only Dashboard Lifecycle

The Validation page can start or stop one fixed, pinned official PX4 SIH
container when all of these conditions are true:

```bash
make managed-sih-doctor
```

The doctor is read-only: it does not pull an image, create a file, start or
stop a container, change Docker access, or modify PixEagle configuration. It
checks the selected runtime config, attributable administrator credentials,
durable audit and lifecycle-ledger targets, Docker access, the exact local
repository digest, and the fixed container-name ownership state. Use
`python3 scripts/setup/check-managed-sih.py --json` for automation. A passing
doctor is prerequisite evidence only; action-time PX4, control-state, audit,
confirmation, and ownership checks still fail closed independently.

- `Debugging.ENABLE_MANAGED_SIH` is `true` in the runtime config and PixEagle
  has been restarted;
- an attributable admin browser session or dedicated bearer principal has
  `system:admin` scope; anonymous and `local_compat` principals cannot mutate it;
- durable API security audit logging is available;
- Docker is reachable and the exact image digest declared by
  `tools/sitl_plans/phase2_follower_validation.json` is already installed;
- no following or Offboard activity is present, no other PX4 source is already
  connected for start, and the operator confirms no real aircraft, HIL rig, or
  motor-enabled hardware is connected.

The default is `false`. The browser never accepts an image, model, network,
container name, shell command, or Docker argument from the user, and it never
pulls an image. Start uses the immutable repository digest from the checked-in
plan with `--pull=never`, bounded Docker logs, and explicit CPU, memory, and PID
limits. Stop inspects the fixed name, verifies the PixEagle profile/run/model/
digest labels, immutable image ID, environment, and host-network contract, then
stops only the immutable inspected container ID. A name collision is reported
and is never stopped.

Start requires the explicit no-real-aircraft/HIL/motor-enabled-hardware
acknowledgement. Stop is an ownership-verified recovery action and does not
require that start-only acknowledgement, but it still requires an attributable
administrator, generic confirmation, idempotency, inactive control state, and
durable pre-execution plus completion audit events. Lifecycle idempotency is
retained across a PixEagle restart in the owner-only
`logs/managed_sih_actions.json` ledger; raw idempotency keys are not stored.

This lifecycle manages PX4 only. MavlinkAnywhere, MAVLink2REST, PixEagle, and
their routing remain independently supervised. The page can therefore report a
running container while the PX4 connection is still unavailable. Flight actions
are intentionally absent from this lifecycle surface.

| Component | Required for | Managed by this page |
|---|---|---|
| Docker and the pinned official PX4 image | Starting the PX4 SIH container | PX4 container only; Docker installation and image pull are operator steps |
| MAVSDK | PixEagle control connection | No |
| External `mavsdk_server` | Only when selected by the PixEagle MAVSDK configuration | No |
| MAVLink2REST | The current default telemetry path and checked-in L2 evidence plan | No |
| MavlinkAnywhere | The checked-in L2 routing/evidence plan | No; another reviewed route may be used outside that evidence profile |

Starting the container is therefore not an integrated simulator-stack start.
It does not make telemetry, OSD, Following, or Offboard ready by itself.

This is the normal developer check for the SIH profile. It validates the same
Phase 2 plan but does not start Docker, PX4, MavlinkAnywhere, MAVLink2REST, or
PixEagle, and it does not write an artifact directory.

To collect evidence from an already running operator-approved stack:

```bash
bash scripts/sitl/run_px4_sih_profile.sh \
  --mode probe-only \
  --artifact-root reports/sitl
```

Equivalent Make target:

```bash
make sitl-sih-probe
```

To start only a harness-owned PX4 SIH container and then collect probes from
the already prepared routing/MAVLink2REST/PixEagle services:

```bash
docker pull px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01

bash scripts/sitl/run_px4_sih_profile.sh \
  --mode execute-px4 \
  --px4-image px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01 \
  --px4-model sihsim_quadx \
  --artifact-root reports/sitl
```

Equivalent Make target after the image is present locally:

```bash
make sitl-sih-execute-px4
```

The wrapper uses the existing validation harness. In `execute-px4` mode the
harness command still uses Docker `--pull=never`; pull the exact pinned image
first and preserve the resulting manifest/container metadata for accepted
evidence. The wrapper does not configure MavlinkAnywhere, run
`configure_mavlink_router.sh`, start PixEagle, start MAVLink2REST, install
services, or mutate host routing. Those steps remain operator-controlled.

Checked-in GitHub workflow:

- `.github/workflows/px4-sih-validation.yml`

The workflow is opt-in through `workflow_dispatch` and has a scheduled dry-run.
It is not attached to `push` or `pull_request`, so normal PR CI does not start
Docker/PX4. `execute-px4` can optionally pre-pull the selected official PX4
image, then the harness runs with `--pull=never` and uploads `reports/sitl/**`
with `if: always()`. A runtime workflow run can still fail or remain
incomplete when the runner lacks the prepared MavlinkAnywhere/MAVLink2REST/
PixEagle stack or required PX4 params, ULog/tlog, logs, scenario, route, and
profile artifacts.

## Dev/Training Dashboard Surface

PixEagle exposes a dashboard Validation page backed by:

```http
GET /api/v1/sitl/status
```

Status requires `debug:read` and summarizes the checked-in
`phase2_follower_validation` plan, the latest local `reports/sitl/*/manifest.json`
for that plan, and the operator terminal commands. The two optional managed-SIH
lifecycle actions described above additionally require `system:admin`, explicit
confirmation, idempotency, durable audit logging, and every runtime safety
precondition to pass:

```bash
make sitl-sih-dry-run
make sitl-sih-probe
make sitl-sih-execute-px4
```

This is a training and evidence-navigation surface with one opt-in lifecycle
exception: an authorized administrator may start or stop only the fixed,
ownership-verified PX4 SIH container described above. It does not install
Docker, pull the PX4 image, or start MavlinkAnywhere, MAVLink2REST, PixEagle,
Gazebo, X-Plane, or route mutation from the browser. Raw
`/api/v1/sitl/injections/*` routes remain
validation-only API endpoints and are intentionally not exposed as dashboard
buttons. The page also shows when `PIXEAGLE_ENABLE_SITL_INJECTIONS=1` is active
so operators can confirm that flag is not accidentally enabled outside an
operator-approved validation stack.

The route and page may show an `incomplete` latest manifest. That is useful
operator feedback, not a failure of the page. Accepted L2 evidence still
requires the manifest and every referenced artifact demanded by the plan. A
visible dashboard Validation page does not imply PX4-in-loop, follower-response,
SITL runtime success, HIL, field, or real-aircraft success.

## Opt-In PX4 Gazebo Visual Profile

PixEagle's maintained full-visual simulation profile is
`tools/sitl_plans/gazebo_visual_validation.json`. It is L4 simulation evidence:
it can prove the official PX4 Gazebo container, PixEagle UDP video ingest,
tracker/follower traces, and PX4 artifact packaging for the exact run, but it
does not imply HIL, field, or real-aircraft success.

Default dry-run is side-effect free:

```bash
bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode dry-run --json
make sitl-gazebo-dry-run
```

Dry-run validates the plan, three scenario definitions, and evidence contract
without starting Docker, PX4, Gazebo, PixEagle, MavlinkAnywhere, or
MAVLink2REST.

To collect from an already running operator-approved official Gazebo stack:

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

Equivalent Make target:

```bash
make sitl-gazebo-probe
```

To start only a harness-owned official PX4 Gazebo container, pull the exact
pinned image first and keep the resulting image metadata in the evidence:

```bash
docker pull px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01

bash scripts/sitl/run_px4_gazebo_visual_profile.sh \
  --mode execute-gazebo \
  --px4-image px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01 \
  --px4-model gz_x500_mono_cam \
  --artifact-root reports/sitl
```

Equivalent Make target after the image is present locally:

```bash
make sitl-gazebo-execute-px4
```

The wrapper sets `HEADLESS=1` through the plan, uses Docker host networking,
and passes `PX4_SIM_MODEL` to the selected container. In `execute-gazebo` mode
it starts only the official PX4 Gazebo container through the harness. It does
not configure MavlinkAnywhere, start PixEagle, start MAVLink2REST, install
services, mutate host routing, or touch hardware. Those remain
operator-controlled setup steps.

The visual profile expects PixEagle to use the proven UDP/GStreamer receiver
path:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: UDP_STREAM
  UDP_URL: udp://0.0.0.0:5600
  USE_GSTREAMER: true
```

Before a Gazebo video run can be accepted, attach or reproduce the generated
RTP/UDP receiver proof:

```bash
make video-udp-proof-dry-run
make video-udp-proof-execute
```

Accepted visual evidence must include the generated receiver proof manifest,
Gazebo receiver pipeline, Gazebo frame hashes, tracker command trace, Offboard
publish trace, structured MavlinkAnywhere route/profile evidence, PixEagle
config snapshots, MavlinkAnywhere dashboard version evidence, secret-scan
report, PX4 params, PX4 logs, ULog/tlog manifests, and container metadata.
Missing, placeholder, incompatible, or secret-blocked artifacts keep the run
incomplete.

The harness now performs artifact-content checks for visual evidence. It rejects
empty or unparsable receiver proof manifests, weak RTP/H.264 pipeline text,
single-frame or duplicate-only frame hash files, empty/unparseable JSONL traces,
missing timing evidence in traces, missing Gazebo container inspection, and
missing Docker image repo digests. Strict tracker-command and Offboard-publish
records are also checked against `configs/follower_commands.yaml` version
`2.0.0`: `profile_name` must be active, `control_type` must match that profile,
and `fields` must be the exact complete profile field set with finite numeric
values. Retired `velocity_body` controls and retired fields such as `vel_x`,
`vel_y`, `vel_z`, and `yaw_rate` invalidate the evidence. A file existing at the
right path is not enough for accepted L4 evidence.

Checked-in GitHub workflow:

- `.github/workflows/px4-gazebo-visual-validation.yml`

The workflow is `workflow_dispatch` plus scheduled dry-run only. It is not
attached to `push` or `pull_request`. `execute-gazebo` can optionally pre-pull
the selected official image, then the harness runs with `--pull=never`, accepts
the same optional visual evidence import paths, and uploads `reports/sitl/**`
with `if: always()`.

## Headless PX4 SITL Stack

These commands are for an operator-approved local Linux validation host. Do not
run them against real hardware.

### 1. Pull A Pinned PX4 Image

```bash
docker pull px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01
```

Use the pinned tag above for the current checked-in evidence contract. It was
pulled and inspected with repo digest
`px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`.
Avoid `latest` for accepted artifacts unless the digest is also recorded and
the plan is intentionally updated.

### 2. Start PX4 SITL

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-px4-sitl"
bash scripts/sitl/start_px4_sitl.sh \
  --artifact-dir "reports/sitl/manual/$RUN_ID"
```

The helper reads image, digest, model, and network mode from the checked-in plan.
It verifies the local tag contains that digest, executes by digest with Docker
host networking and bounded resources/log retention, and writes the command plus
a bounded initial log to the artifact directory. It uses `--pull=never`, so a
missing image fails instead of silently changing the validated version. The
artifact directory must be new; the helper refuses to reuse an existing
directory so old logs cannot be mistaken for current evidence.

Stop only a label-verified validation container:

```bash
bash scripts/sitl/stop_px4_sitl.sh pixeagle-px4-sitl
```

The stop helper resolves the requested name once, verifies the complete
PixEagle profile/run/model/digest ownership labels, distinguishes absence from
Docker-daemon failure, and passes only the immutable inspected ID to
`docker stop`. It refuses an unowned name collision.

The Python harness can also manage only the PX4 container and then collect
probes from the already configured routing/MAVLink2REST/PixEagle services:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --execute \
  --allow-process-start \
  --artifact-root reports/sitl
```

This still does not configure MavlinkAnywhere or start PixEagle automatically;
those services are operator-controlled because they can change system routing or
application state.

When the harness owns the PX4 container, it attempts best-effort automatic PX4
artifact collection after the container labels and run ID are verified. The
collection path is read-only from the container perspective: `docker exec`
runs `find` in the plan's configured search roots, and `docker cp` copies
matching params, ULog, and tlog files into the evidence directory. If a file is
not present in the image/runtime layout, the artifact remains a placeholder and
the run remains incomplete.

### 3. Configure MavlinkAnywhere Routing

```bash
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --install-dashboard \
  --dashboard-listen 127.0.0.1:9070

sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

Dashboard installation and router configuration are separate
MavlinkAnywhere modes. Do not combine `--install-dashboard` with routing
arguments in one invocation.

This is a system routing change. It belongs in an operator-controlled setup
step, not inside normal CI or an autonomous code-editing run.

Verify local route status:

```bash
curl -s http://127.0.0.1:9070/api/v1/status
curl -s http://127.0.0.1:9070/api/v1/diagnostics
curl -s http://127.0.0.1:9070/api/v1/endpoints
curl -s http://127.0.0.1:9070/api/v1/config
curl -s http://127.0.0.1:9070/api/v1/profiles/summary
```

### 4. Configure PixEagle For SITL

Use a local `configs/config.yaml` override only for the validation host:

```yaml
PX4:
  SYSTEM_ADDRESS: udpin://127.0.0.1:14540

MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088

Follower:
  FOLLOWER_MODE: mc_velocity_position
  USE_MAVLINK2REST: true

FOLLOWER_CIRCUIT_BREAKER: false
```

`FOLLOWER_CIRCUIT_BREAKER: false` is acceptable only for this SITL stack or an
operator-approved bench/HIL procedure. Keep it enabled for ordinary no-drone
development.

### 5. Start PixEagle And Local Bridges

```bash
bash scripts/run.sh --no-dashboard --no-attach
```

The launcher starts the PixEagle-owned MAVSDK Server and MAVLink2REST bridge.
Do not start a second standalone bridge on `8088` before this command.

For runs that execute checked-in SITL validation injectors, start PixEagle with
the validation-only injection routes enabled:

```bash
PIXEAGLE_ENABLE_SITL_INJECTIONS=1 bash scripts/run.sh --no-dashboard --no-attach
```

Do not enable this flag outside an operator-approved validation stack. The
routes are disabled by default and refuse to dispatch unless PixEagle is
already in the required follow-mode state.

The checked-in Phase 2 target-loss scenario currently assumes
`Follower.FOLLOWER_MODE=mc_velocity_position` so it can assert the exact
fail-closed hold command fields (`vel_body_down=0.0` and
`yawspeed_deg_s=0.0`). Other follower modes need their own scenario assertions
before their target-loss runtime evidence can be accepted.

Probe:

```bash
curl -s http://127.0.0.1:5077/status
curl -s http://127.0.0.1:5077/api/follower/setpoints-status
```

## Collect Evidence

With the stack already running:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --artifact-root reports/sitl
```

Equivalent Make target:

```bash
make sitl-probe
```

The harness writes:

```text
reports/sitl/<timestamp>-phase2_follower_validation/
  manifest.json
  plan.json
  config/
  versions/
  route_map/
  probes/
  scenarios/
  logs/
  px4/
```

`manifest.json` is the acceptance anchor. If a probe fails or a required
artifact is a placeholder, the result is incomplete and must not be described as
successful SITL validation. The harness also checks that the structured
MavlinkAnywhere endpoint, config, and profile-summary payloads expose the
plan's required enabled non-server local endpoints as full MavlinkAnywhere
endpoint-shaped records, and that profile summary reports
`backend=mavlink-anywhere` plus `present=true`. Incidental address strings in
response text or address/port-only JSON do not satisfy this route contract.
PixEagle's runtime config must also match the SITL endpoint contract.

Plain `--probe-only` does not execute checked-in scenario actions. For the
Phase 2 evidence contract, it is a useful probe package but remains incomplete
unless `scenarios/scenario_results.json` is produced by `--run-scenarios`.

To execute checked-in scenario actions against the running stack, add
`--run-scenarios`:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --run-scenarios \
  --artifact-root reports/sitl
```

The scenario runner writes `scenarios/scenario_results.json`. Non-GET or
explicitly marked control actions are recorded as blocked unless the operator
also passes `--allow-control-actions`. Use that flag only on an
operator-approved SITL stack with no real aircraft connected.

The target-loss scenario uses the validation-only
`POST /api/v1/sitl/injections/tracker-output` route to inject an unusable
`TrackerOutput` through the same command-freshness, follower, and
OffboardCommander boundary used by live tracking. The plan asserts the
resulting command intent, zero/hold fields, and active commander state rather
than treating request acceptance alone as evidence.

The video-stall scenario uses the validation-only
`POST /api/v1/sitl/injections/video-stall` route to inject frame-status
metadata into `AppController.handle_video_frame_unavailable()`. This proves the
frame-unavailable fail-closed path without stopping the actual camera,
GStreamer pipeline, Docker container, PX4 process, or MAVLink route. The plan
asserts the same hold command fields and active commander state for the
`mc_velocity_position` profile both in the injection response and in a
post-stall `/api/follower/setpoints-status` probe.

The commander publish-failure scenario uses the validation-only
`POST /api/v1/sitl/injections/commander-publish-failure` route to record
bounded synthetic failures inside the active `OffboardCommander`, cross the
configured local failure threshold, and await the same AppController cleanup
handler used for real repeated publish failures. This proves PixEagle's local
fail-closed policy without synthesizing MAVSDK setpoint publishes, replacing
PX4 interfaces, stopping services, or changing MAVLink routing. Cleanup still
uses the normal Offboard stop path. The plan asserts before/after commander
state, the persisted failure record exposed through `/status`, and inactive
follow mode after cleanup.

The MAVSDK disconnect scenario uses the validation-only
`POST /api/v1/sitl/injections/mavsdk-disconnect` route to mark PixEagle's
local `PX4InterfaceManager` command path validation-disconnected, record
bounded commander failures, and await the same fail-closed cleanup path. The
plan asserts before/after PX4 command-path state, commander failure evidence,
inactive follow mode, and the failed Offboard stop error. This route does not
stop PX4, Docker, MavlinkAnywhere, MAVLink2REST, a MAVSDK server, network
interfaces, or MAVLink routes; it is local PixEagle evidence only.

The MAVLink2REST timeout scenario uses the validation-only
`POST /api/v1/sitl/injections/mavlink2rest-timeout` route to record a bounded
PixEagle-local MAVLink2REST client timeout. The route leaves MAVLink2REST,
PX4, Docker, MavlinkAnywhere, routing, and network interfaces running. The plan
first asserts fresh PixEagle `mavlink_telemetry` with a real last-success age,
then asserts stale/error `mavlink_telemetry` after injection, and finally
probes MAVLink2REST directly so accepted evidence distinguishes local client
freshness handling from a real service or route outage.

PX4 evidence can be automatic where the container layout supports it, or
explicitly imported from an operator-run SITL session.

For operator-managed containers, automatic copy is opt-in and requires a
specific container selector:

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
container selector is used for Docker image/container metadata only. The
harness never stops an operator-managed container. Failed scenario assertions
take precedence over missing artifacts in `manifest.json`; a failing scenario
is not hidden behind an incomplete log or PX4 artifact package.

When params, ULog, and tlog files already exist outside the container, attach
them directly to the evidence package:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --run-scenarios \
  --allow-control-actions \
  --artifact-root reports/sitl \
  --px4-params-file /path/to/params.txt \
  --px4-ulog /path/to/flight.ulg \
  --px4-tlog /path/to/flight.tlog \
  --px4-log /path/to/px4_sitl.log \
  --pixeagle-log /path/to/pixeagle.log
```

The harness copies those files under `px4/`, records size and SHA-256 checksums
in `px4/ulog_manifest.json` and `px4/tlog_manifest.json`, copies imported logs
to `logs/px4_sitl.log` and `logs/pixeagle.log`, and captures
`px4/container_metadata.json` from Docker image/container inspection when
available. In harness-owned `--execute` mode, `logs/px4_sitl.log` is produced
from the managed container stdout automatically. Explicit imports remain valid
even when automatic container discovery is unavailable or incomplete. Missing
or placeholder PX4/PixEagle evidence keeps the run incomplete.

## Required Phase 2 Scenarios

The checked-in plan covers:

- Offboard entry
- Offboard heartbeat continuity
- follower setpoint contract
- target loss
- video stall
- MAVSDK disconnect
- MAVLink2REST timeout
- operator abort
- OffboardCommander publish-failure policy

The current harness validates the scenario plan, captures runtime probes, and
can execute checked-in scenario actions. Offboard-start, Offboard-stop, and
operator-abort control actions use typed `/api/v1/actions/*` resources with
confirmation, idempotency, local action records, and explicit claim boundaries;
retired `/commands/*` control aliases are no longer registered HTTP routes.
Target-loss, video-stall, commander publish-failure injection, MAVSDK local
command-path disconnect, and MAVLink2REST local timeout injection are automated through
PixEagle's validation-only `/api/v1/sitl/injections/*` routes. The checked-in
plan now has zero `manual_fault` actions. The heartbeat and follower-setpoint
scenarios now
assert PixEagle commander counters, successful publish metadata, finite command
rate, finite active setpoint fields, and active publication source where the
current API exposes them. PX4 params/ULog/tlog collection is automatic where
the selected container exposes matching files and remains explicitly
importable otherwise. The harness writes `px4/offboard_observation.json` and
accepts PX4-observed Offboard/cadence evidence only when MAVLink2REST
HEARTBEAT reports PX4 Offboard mode with the MAVLink custom-mode flag set and
parsed tlog setpoint cadence targets the same PX4 system/component inside the
checked-in Offboard-start scenario window. The configured cadence threshold is
at least 3 setpoint messages over at least 1 second and at least 2 Hz.
Accepted PX4/SITL evidence still remains incomplete when required route data,
logs, params, ULog, tlog, config snapshots, scenario artifacts, or PX4
observation checks are missing, placeholders, mixed across systems, or
unproven. PX4-level cadence/flight-mode conclusions are not claimed from
PixEagle API counters alone.

## Optional Gazebo/Camera Path

Before accepting Gazebo camera evidence, prove the generated RTP/H.264 UDP
receiver path locally:

```bash
make video-udp-proof-dry-run
make video-udp-proof-execute
```

The guarded execute target starts only a local GStreamer `videotestsrc` sender
and records video-ingest artifacts under `reports/video/`. This is a prerequisite
for visual SITL evidence, but it is not itself PX4, tracker, follower, Gazebo,
SITL, HIL, field, or real-aircraft validation.

The maintained full visual path is the opt-in official PX4 Gazebo profile above.
It uses `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01` by default,
`HEADLESS=1`, camera model `gz_x500_mono_cam`, and PixEagle `UDP_STREAM` ingest
on port `5600`. Use
`gz_x500_gimbal` only when the scenario explicitly needs a gimbal-capable camera
model and the expected video/follower traces are defined.

Current host note from 2026-06-04: the official image pulled and direct verbose
Gazebo showed the `GstCameraSystem` configured for UDP `127.0.0.1:5600`, but
the all-in-one PX4/Gazebo entrypoint timed out waiting for Gazebo world
readiness on the current VPS/headless container path. Treat that as incomplete
L4 runtime evidence, not as a PixEagle tracker/follower failure. Run the full
visual acceptance package on native Ubuntu with GUI/GPU, a stronger headless
runner, or a separately proven official-image startup workaround.

## Acceptance Rules

- No SITL claim without `manifest.json` and the referenced artifacts.
- No HIL or field claim from SITL evidence alone.
- No real-aircraft, motor-enabled, deployment, or service-install action from
  this guide without explicit operator approval.
- Any accepted report must include exact PixEagle git status, PX4 image/tag or
  build SHA, MavlinkAnywhere version/tag, MAVLink2REST version, config
  snapshots, route map, PixEagle logs, MAVLink health, PX4 params, and PX4
  ULog/tlog manifests with checksums. Missing PX4 params, ULog, or tlog
  evidence keeps the run incomplete, not accepted.
- `manifest.json` must show `mavlink_anywhere_compatibility.classification`
  equivalent evidence as `prepared_routing` through semantic checks, and
  `security/secret_scan.json` must have `status: pass`. The secret-scan report
  never stores matched secret values or context lines; a blocked scan means the
  evidence bundle must be sanitized and re-collected.

## Related Documentation

- [Testing Without a Drone](../06-development/testing-without-drone.md)
- [MavlinkAnywhere](mavlink-anywhere.md)
- [Port Configuration](port-configuration.md)
- [MAVSDK Offboard](../03-protocols/mavsdk-offboard.md)
