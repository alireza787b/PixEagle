# PX4 SIH CI Validation Research

Date: 2026-06-02  
Slice: Phase 3 research/design for PXE-0037, with follow-up PXE-0039  
Repository: `/home/alireza/PixEagle`  
Status: decision report only; no Docker, PX4 runtime, SITL, HIL, field, deployment, or service installation was run.

## Executive Decision

Use PX4 SIH as PixEagle's lightweight PX4-in-loop validation backend, but only
for L2 control-plane evidence.

SIH is the right tool for proving that PixEagle can interact with a real PX4
state machine through MAVSDK, Offboard, MAVLink routing, MAVLink2REST telemetry,
operator abort, stale target, and fail-closed command paths. It is not a visual
simulation and must not replace tracker/video validation, Gazebo/X-Plane visual
SITL, HIL, or field testing.

The recommended stack for accepted L2 evidence is:

```text
PX4 SIH container
  -> MavlinkAnywhere / mavlink-router profile
       input: 0.0.0.0:14550
       outputs:
         127.0.0.1:14540  PixEagle MAVSDK / Offboard
         127.0.0.1:14569  MAVLink2REST input
         127.0.0.1:12550  local debug
MAVLink2REST: 127.0.0.1:8088
PixEagle backend: 127.0.0.1:5077
MavlinkAnywhere dashboard/API: 127.0.0.1:9070
```

Normal PR CI should keep PX4 runtime side effects out by default. Add PX4 SIH
as an opt-in `workflow_dispatch` or scheduled/nightly job first. Promote it to
a required PR gate only after PXE-0037 removes `manual_fault` blockers,
automatic PX4 params/ULog/tlog collection works, and the route/profile checks
are structured rather than text-matched.

## Why SIH Fits

PX4 documents SIH as a lightweight, headless simulator with physics running
inside PX4 through uORB. The official docs also describe prebuilt Docker images
for SIH using `px4io/px4-sitl:<tag>`, with `14540/udp` for MAVSDK/offboard and
`14550/udp` for GCS/QGroundControl. Docker Hub currently describes
`px4io/px4-sitl` as a lightweight, headless, multi-arch PX4 SIH image.

For PixEagle, that gives a practical CI/local-development path:

- one small official PX4 container instead of a full Gazebo stack;
- no camera or renderer dependency;
- enough PX4 behavior to test MAVSDK connection, Offboard entry, heartbeat,
  command cadence, timeout/failsafe reactions, telemetry freshness, and abort;
- reproducible evidence when image tags/digests, configs, route profiles, logs,
  PX4 params, ULog/tlog, and scenario results are captured.

PX4's own testing docs recommend MAVSDK-based integration tests against SITL and
state that the tests are run in CI. MAVSDK docs also state the standard PX4 SITL
offboard API port is `14540`, and Offboard requires an initial setpoint before
start plus continuous setpoint streaming. Those constraints match the problems
PixEagle has already been modernizing around `OffboardCommander`.

## What SIH Can Prove

SIH can produce meaningful evidence for:

- PX4 discovery through MAVSDK on the configured endpoint.
- Offboard preconditions: setpoint priming before `start()`, accepted/rejected
  mode transition, and error propagation.
- Offboard heartbeat and cadence against real PX4 loss behavior.
- `OffboardCommander` independence from camera FPS, tracker cadence, UI state,
  and streaming health.
- Command sign/unit contracts after follower output reaches MAVSDK/PX4.
- Target loss, stale tracker output, video stall, redetection, and safe-hold or
  Offboard-stop policy when driven by owned PixEagle injectors.
- MAVLink2REST telemetry presence, request freshness, timeout behavior, and
  payload-frequency visibility.
- Operator abort: final safe publish or Offboard stop attempt, then local
  `following_active=false`.
- MavlinkAnywhere route/profile compatibility with companion-computer defaults.
- Evidence manifest discipline: exact image, container, command, config,
  route, probes, params, ULog/tlog, and scenario results.

## What SIH Cannot Prove

SIH must not be used to claim:

- real tracker accuracy;
- camera optics, compression, lens/FOV, exposure, lighting, target appearance,
  occlusion, or detection robustness;
- gimbal image geometry or vendor gimbal behavior unless separately injected or
  simulated;
- Gazebo/X-Plane aerodynamic, terrain, obstacle, sensor, wind, or camera-world
  fidelity;
- real companion serial/radio/Wi-Fi latency, power, vibration, RC/operator
  behavior, or field safety;
- HIL or real-aircraft readiness.

For visual validation, keep L3 synthetic/replay tests and L4 full visual SITL.
PX4's Gazebo docs show camera-capable models and video streaming over UDP, and
unofficial `jonasvautherin/px4-gazebo-headless` can provide RTSP experiments,
but those are heavier visual-simulation paths, not replacements for the SIH
control-plane gate.

## Docker And Image Strategy

Start with the official PX4 SIH image:

```text
px4io/px4-sitl:<pinned-tag>
```

Current PixEagle plan/helper already references:

```text
px4io/px4-sitl:v1.17.0
PX4_SIM_MODEL=sihsim_quadx
```

Before requiring this in CI, make the PX4 target explicit:

- `v1.16.x` if the maintainers want stable PX4 release conservatism;
- `v1.17.0` if the maintainers intentionally want the current project default;
- in both cases, record the image digest in the evidence manifest.

Do not fork PX4 or maintain a custom PX4 image for the first SIH gate. A custom
wrapper image is justified only if evidence shows real pain around readiness,
log export, params/ULog extraction, or dependency startup. Do not patch PX4
flight behavior to make tests pass.

Accepted runs should:

- pre-pull the pinned image;
- use `--pull=never` for accepted evidence so the validated image cannot change
  silently;
- label managed containers with PixEagle run IDs;
- refuse stale artifact directories;
- record `docker image inspect`, container inspect, command line, model, network
  mode, and digest;
- keep Docker cleanup scoped only to harness-owned containers.

## GitHub Actions Feasibility

PX4 SIH is feasible in GitHub Actions on `ubuntu-latest`, but should begin as
an optional job.

Recommended rollout:

1. Normal PR CI: keep current fast gates plus `sitl-dry-run`; no PX4 process.
2. Optional SIH smoke: `workflow_dispatch` and nightly schedule; uploads
   `reports/sitl/**` on `if: always()`.
3. Required SIH gate: only after runtime injectors, auto PX4 evidence
   collection, and structured route validation are implemented.

Prefer a normal Ubuntu runner job that starts containers/processes explicitly
with scripts or a small Compose profile. GitHub service containers can map UDP
ports, but their networking differs depending on whether the job itself runs on
the host or inside a container. PixEagle's first PX4 gate is easier to reason
about with explicit Linux host networking and captured commands.

Use Docker Compose only when we manage more than one runtime service in CI.
Compose is useful for a full stack because it gives one YAML for services,
networks, volumes, logs, and lifecycle. For the first SIH proof, keep one
official PX4 container plus existing PixEagle harness orchestration.

## Routing Decision

Accepted L2 evidence should route through MavlinkAnywhere or a
MavlinkAnywhere-generated `mavlink-router` profile. Direct PX4 ports are useful
as a diagnostic profile only.

Rationale:

- direct PX4 proves "PixEagle can talk to PX4";
- routed PX4 proves the actual companion-computer contract PixEagle expects:
  MAVSDK output, MAVLink2REST output, local debug output, and route diagnostics;
- MAVLink2REST is a telemetry bridge, not the command/control router;
- MavlinkAnywhere already exposes `/api/v1/status`, `/api/v1/diagnostics`,
  `/api/v1/config`, and profile APIs that can become structured evidence.

CI should not run `sudo ./configure_mavlink_router.sh` on a generic runner.
That is a host/system routing change. Add a no-sudo ephemeral routing mode for
CI or run on a dedicated validation runner where MavlinkAnywhere is
pre-provisioned.

## Required Evidence Contract

A passing L2 SIH run must include:

- `manifest.json` with exact mode, result, run ID, command, timestamps, and
  claim boundary;
- PixEagle git status and runtime versions;
- PX4 image tag, digest, model, network mode, container metadata, command, and
  full PX4 log;
- PixEagle config snapshots and logs;
- MavlinkAnywhere route/profile/status/diagnostics/config evidence;
- MAVLink2REST source/bind/profile, `/v1/mavlink` probe, and message freshness;
- PixEagle `/status`, current config, follower health, setpoint publication,
  Offboard commander status, and later typed `/api/v1` equivalents;
- `scenarios/scenario_results.json` with no `manual_fault` blockers for a pass;
- PX4 params;
- ULog and tlog manifests with size and SHA-256 checksums;
- trace artifacts:
  - `trace/tracker_command_trace.jsonl`;
  - `trace/offboard_publish_trace.jsonl`;
  - later, normalized production tracker traces for PXE-0038.

The current harness already has strong foundations but still needs:

- owned injectors instead of `manual_fault`;
- automatic PX4 params/ULog/tlog collection;
- structured route/profile parsing;
- target/video/MAVSDK/MAVLink2REST fault controls;
- trace artifacts that correlate tracker state, follower intent, command
  publication, and PX4 observations.

## Test Ladder

Keep the ladder intentionally separated:

| Level | Runs In Normal PR CI | Purpose |
| --- | --- | --- |
| L0 unit/contract | yes | follower math, tracker geometry, config/schema, typed API models, command validation |
| L1 mock integration | yes | `TrackerOutput -> AppController -> Follower -> CommandIntent -> OffboardCommander` with fakes |
| L2a PX4 SIH control-plane | optional/nightly first | PX4 discovery, Offboard entry, heartbeat, target loss, abort, telemetry timeout, fail-closed behavior |
| L2b PX4 SIH plus synthetic target injection | optional/nightly | follower response to deterministic target traces with real PX4 state machine |
| L3 tracker-in-loop | optional/nightly or focused PR | generated/recorded video and gimbal traces through tracker/follower contracts |
| L4 full visual SITL | release/manual | Gazebo/X-Plane camera scene streams through PixEagle with video/log/config artifacts |
| L5 HIL/field | explicit approval only | hardware and real-world evidence with operator procedure and abort plan |

Do not collapse these into one giant scenario. Layered tests isolate bugs
faster: pixel geometry bugs belong in L0/L3, sign/unit/follower bugs in
L0/L1/L2b, MAVSDK/PX4 contract bugs in L2, and camera-scene realism in L4.

## Scenario Coverage For PXE-0037

The SIH implementation should automate these existing scenarios:

- `offboard_entry`: `following_active=true` only after PX4 Offboard succeeds.
- `offboard_heartbeat`: commander counters advance while frame updates stop.
- `follower_setpoints`: finite, bounded command intents reach the expected PX4
  command type with expected sign/unit mapping.
- `target_loss`: stale target cannot continue pursuit; safe hold/zero or
  documented Offboard stop is recorded.
- `video_stall`: video status becomes unusable, tracker output becomes command
  unusable, and heartbeat behavior remains intentional.
- `mavsdk_disconnect`: command send failure crosses the failure threshold and
  local following is stopped/degraded according to policy.
- `mavlink2rest_timeout`: telemetry freshness becomes false and consumers do
  not treat stale telemetry as current.
- `operator_abort`: final safe publish or Offboard stop is recorded, then
  `following_active=false`.
- `commander_publish_failure`: repeated publish failures produce failed/degraded
  health and fail-closed local state.

## API And MCP Implications

MCP/AI-agent support should come through PixEagle's typed `/api/v1` contracts,
not through direct shell, Docker, or MAVLink mutation.

Recommended Phase 4 API resources influenced by this research:

- `GET /api/v1/routing/profile`
- `GET /api/v1/routing/health`
- `GET /api/v1/telemetry/mavlink`
- `GET /api/v1/flight/offboard-commander`
- `POST /api/v1/flight/offboard-sessions`
- `POST /api/v1/flight/offboard-sessions/{id}/abort`
- `GET /api/v1/sitl/plans`
- `POST /api/v1/sitl/runs`
- `GET /api/v1/sitl/runs/{id}`

Dangerous actions need typed request/response models, structured errors,
operation IDs, idempotency keys, dry-run or preview where possible, explicit
confirmation, and audit/event records. This matches the PixEagle API blueprint
and the newer `mavsdk_drone_show` SITL Control pattern.

## Companion Repository Drift

Refs refreshed on 2026-06-02:

| Project | Ref Checked | Note |
| --- | --- | --- |
| MavlinkAnywhere | `origin/main` `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`, latest tag `v3.0.14` | unchanged from prior refresh |
| Smart Wi-Fi Manager | `origin/main` `a5414fc7d7df1fde47db11aeed1681f5515ea350`, latest tag `v2.1.14` | unchanged from prior refresh |
| MAVSDK Drone Show | `origin/main` `f8a4016496fe0189b16c3fe5d060980991900ddf`, latest tag `v5.5.42-simurgh-quickscout-readiness` | advanced since prior refresh |

MDS still reinforces the same standards for PixEagle:

- typed `/api/v1` operations for SITL lifecycle;
- operation tracking instead of shell scraping;
- no `docker commit` as a normal release path;
- official stock image vs custom pinned image decision recorded up front;
- image rebuilds only when runtime contents or startup behavior change;
- runtime evidence reports generated from accepted logs/artifacts.

## Updated Remaining Slices

1. Finish PXE-0037 runtime validation automation:
   - replace `manual_fault` with owned injectors;
   - automate PX4 params/ULog/tlog collection;
   - add trace artifacts;
   - parse structured MavlinkAnywhere route/profile data.
2. Add PXE-0039 lightweight PX4 SIH CI profile:
   - pin PX4 image tag and digest;
   - add optional `workflow_dispatch`/nightly job;
   - document no-sudo ephemeral routing or dedicated-runner requirement;
   - upload evidence artifacts on every run.
3. Add PXE-0038 production tracker trace smoke:
   - production tracker or SmartTracker-backed deterministic clip;
   - normalized trace artifact;
   - redetection and stale-pursuit regression coverage.
4. Resolve PXE-0020 X-Plane/Windows SITL:
   - rewrite as maintained L4 manual evidence flow or move to historical docs.
5. Proceed to Phase 4 API/MCP:
   - typed `/api/v1`, structured errors, command/action resources, telemetry
     health model, routing/SITL resources.
6. Proceed to dashboard modernization:
   - stale/unusable tracker visibility;
   - API client normalization;
   - supported frontend toolchain.
7. Continue gimbal provider expansion:
   - current Topotek SIP-over-UDP remains one provider instance;
   - add MAVLink Gimbal v2 or vendor providers when hardware/protocol is chosen.
8. Final cleanup:
   - remove deprecated docs, duplicate configs, compatibility aliases, stale
     scripts, placeholder tests, and redundant code only after replacements are
     proven.

## Risks And Open Decisions

- Choose PX4 target version: stay with current plan `v1.17.0` or pin to a
  stable `v1.16.x` release for the first required gate.
- Decide whether the optional CI job runs on GitHub-hosted Ubuntu only or a
  dedicated self-hosted validation runner.
- Decide whether MavlinkAnywhere should add a first-class no-sudo ephemeral
  route mode, or PixEagle should generate a local `mavlink-routerd` config from
  the same profile schema.
- Confirm which follower modes are release-blocking for the first L2 gate.
- Confirm artifact retention policy for CI evidence, especially ULog/tlog and
  video snippets that may become large.
- Keep `FOLLOWER_CIRCUIT_BREAKER: false` isolated to SITL/bench evidence. It
  must not leak into real aircraft or ordinary no-drone development.

## Expert Review Summary

Four read-only reviewers were consulted:

- PX4/SIH/MAVSDK: approved SIH as L2 control-plane gate only; warned against
  visual or field overclaims.
- Docker/CI/DevOps: approved official image first, opt-in CI, explicit
  artifacts, and no PX4 fork unless evidence demands a wrapper.
- Tracker/follower/CV: approved separate synthetic video, replay, injection,
  and SIH layers with a shared trace schema.
- MAVLink/API/MCP: approved routed MavlinkAnywhere profile as accepted path,
  direct PX4 only as diagnostic, and typed `/api/v1` resources for MCP.

Consensus: proceed with SIH, but keep it narrow, evidence-driven, and layered.

## Sources

- PX4 SIH Simulation: https://docs.px4.io/main/en/sim_sih/
- PX4 Pre-built SITL Packages: https://docs.px4.io/main/en/simulation/px4_sitl_prebuilt_packages
- Docker Hub `px4io/px4-sitl`: https://hub.docker.com/r/px4io/px4-sitl
- PX4 MAVSDK Integration Testing: https://docs.px4.io/main/en/test_and_ci/integration_testing_mavsdk
- PX4 Offboard Mode: https://docs.px4.io/main/en/flight_modes/offboard
- MAVSDK Offboard Control: https://mavsdk.mavlink.io/main/en/cpp/guide/offboard.html
- MAVSDK Connections: https://mavsdk.mavlink.io/main/en/cpp/guide/connections.html
- MAVLink2REST: https://github.com/mavlink/mavlink2rest
- GitHub Actions service containers: https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers
- GitHub Actions artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- Docker Compose: https://docs.docker.com/compose/
- Docker port publishing: https://docs.docker.com/engine/network/port-publishing/
- PX4 Gazebo Simulation: https://docs.px4.io/main/en/sim_gazebo_gz/
- Unofficial `jonasvautherin/px4-gazebo-headless`: https://github.com/JonasVautherin/px4-gazebo-headless
