# PixEagle Final Implementation Roadmap

Date: 2026-06-02  
Status: approval-ready roadmap; implementation resumes after maintainer/founder approval  
Scope: remaining modernization from current Phase 3 through release-readiness cleanup  
Safety boundary: no Docker/PX4 runtime, SITL scenario, HIL, field, deployment, service installation, or real-aircraft validation was run for this roadmap.

## Executive Direction

Continue the modernization through a layered validation and cleanup plan. Do not
patch around bad architecture, but also do not replace working behavior without
evidence. Each slice must preserve or improve current functionality, update
docs/tests/config/API/UI in the same slice, and leave no untracked legacy path
behind.

The approved simulator strategy should be:

1. Use official PX4 SIH for fast L2 control-plane tests.
2. Use official PX4 Gazebo Harmonic for headless visual SITL and camera/video
   validation.
3. Keep the older unofficial `jonasvautherin/px4-gazebo-headless` image as a
   fallback/benchmark only, not the default.
4. Treat X-Plane as an artifacted manual validation path unless future evidence
   shows reliable headless mission automation.
5. Keep synthetic video/replay tests in normal development because they catch
   tracker/follower coordinate and freshness bugs faster than full simulation.

## Current Anchor

Active work remains Phase 3/PXE-0037:

- automated scenario stimuli/fault injection;
- automatic PX4 params/ULog/tlog collection;
- structured MavlinkAnywhere route/profile parsing;
- trace artifacts correlating tracker output, follower intent, command
  publication, and PX4 observations.

Recently added planning issue:

- PXE-0039: optional PX4 SIH CI profile.

New issue from this roadmap:

- PXE-0040: official PX4 Gazebo headless visual SITL and video-source
  integration.
- PXE-0041: final no-legacy cleanup and release-readiness evidence.

## Independent Review Integration

Three read-only reviewers checked this roadmap after drafting:

- simulator/Docker/PX4 reviewer: approved official SIH first, official Gazebo
  for L4 visual, unofficial Gazebo only as fallback, and X-Plane as manual unless
  headless automation is proven;
- CV/tracker/video reviewer: required a no-regression baseline and generated
  RTP/UDP video receiver proof before Gazebo;
- API/UI/docs reviewer: required PXE-0037 before broad cleanup, `/api/v1`
  compatibility-first migration, dashboard client normalization before UI
  replacement, and no legacy removal before parity.

This roadmap incorporates those gates. Any later slice that weakens one of
these gates must update the issue register and record the reason.

## Simulator And Docker Decision

| Layer | Default | Why | Not For |
| --- | --- | --- | --- |
| Fast PX4 control-plane | `px4io/px4-sitl:<tag>` official SIH | lightweight, headless, official PX4 package, fast MAVSDK/Offboard/telemetry evidence | tracker accuracy, camera realism, visual SITL |
| Full visual SITL | `px4io/px4-sitl-gazebo:<tag>` official Gazebo Harmonic | official PX4 package, headless mode, camera/LiDAR/depth support, versioned tags | normal PR CI, field claims |
| Fallback visual container | `jonasvautherin/px4-gazebo-headless:<tag>` unofficial | convenient RTSP/video examples and historical ecosystem use | default evidence baseline, release claim source |
| X-Plane | manual artifacted workflow | may remain useful for operator/manual regression and fixed-wing/visual workflows already known by team | generic CI, no-GUI automation unless proven |

### Official PX4 Images

PX4 now documents two packaged simulator container tracks:

- `px4io/px4-sitl:<tag>` for SIH;
- `px4io/px4-sitl-gazebo:<tag>` for Gazebo Harmonic.

PX4 documents SIH as lightweight/headless with no external dependencies and
Gazebo as full 3D simulation with camera, LiDAR, and custom worlds. The official
Gazebo Docker Hub page says the image supports `HEADLESS=1` for CI/remote use
and includes camera/LiDAR/depth sensors. Therefore, PixEagle should default to
official PX4 images and pin by tag plus digest in evidence manifests.

### Unofficial Gazebo Image

`jonasvautherin/px4-gazebo-headless` remains useful to inspect because it has
clear RTSP examples for `gz_x500_mono_cam`. However, it is not Dronecode/PX4
official. It should not be the primary accepted evidence baseline unless the
official image cannot provide required video export after investigation.

### X-Plane

X-Plane has command-line options, including `--help`, video-driver flags, sound
flags, and FPS test/pass-fail modes. Current official documentation does not
present it as a headless mission automation server equivalent to Gazebo
headless. So the roadmap should keep X-Plane under PXE-0020 as a manual
artifacted validation workflow or historical documentation cleanup, not as
PixEagle's CI automation target.

## Validation Ladder

| Level | Automation | Purpose | Gate |
| --- | --- | --- | --- |
| L0 unit/contract | normal PR CI | follower math, tracker metadata, command safety, config/schema, API inventory | required |
| L1 mock integration | normal PR CI | `TrackerOutput -> AppController -> Follower -> CommandIntent -> OffboardCommander` with fakes | required |
| L2a PX4 SIH | optional/nightly first | real PX4/MAVSDK/Offboard/telemetry contract without visual simulation | optional until PXE-0037/PXE-0039 complete |
| L2b SIH target injection | optional/nightly | deterministic target/fault response against real PX4 state machine | optional until stable |
| L3 tracker-in-loop | focused PR/nightly | generated/recorded video and gimbal traces through tracker/follower contracts | required for tracker changes |
| L4 Gazebo visual SITL | release/manual/nightly | official headless Gazebo video stream into PixEagle and PX4 interaction | release evidence gate |
| L4 X-Plane manual | manual only | maintained workflow if still valuable to operators | manual evidence only |
| L5 HIL/field | explicit approval only | hardware and real-world validation | never automated by default |

## Implementation Phases

### Phase 3A: Finish PXE-0037 Runtime Evidence

Goal: make the current SITL harness capable of producing honest accepted
runtime evidence.

Work:

- Re-run and preserve the no-regression baseline before changing simulator or
  video pathways:
  - `tests/unit/video/test_video_handler.py`;
  - `tests/unit/core_app/test_flow_controller_frame_freshness.py`;
  - `tests/unit/core_app/test_app_controller_offboard_safety.py`;
  - `tests/unit/trackers/test_smart_tracker_freshness.py`;
  - `tests/unit/trackers/test_tracker_in_loop_validation.py`;
  - focused follower command-safety tests touched by the slice.
- Replace all `manual_fault` scenario actions with owned injectors:
  - synthetic target loss;
  - video stall;
  - MAVSDK disconnect/send failure;
  - MAVLink2REST timeout;
  - operator abort;
  - commander publish failure.
- Add trace artifacts:
  - `trace/tracker_command_trace.jsonl`;
  - `trace/offboard_publish_trace.jsonl`;
  - scenario timeline with timestamps and command IDs.
- Automate PX4 params export and ULog/tlog collection where supported.
- Replace route string containment checks with structured route/profile parsing.
- Keep `pass`, `incomplete`, and `failed` semantically strict.

Acceptance:

- focused harness tests pass;
- no-regression baseline remains green or every change is explained and tested;
- dry-run and probe-only paths remain side-effect-free;
- missing PX4 evidence cannot pass;
- every runtime claim names exact command, image, config, route, logs, and
  artifact directory.

### Phase 3B: Build PXE-0039 Official SIH Profile

Goal: add a fast, optional, repeatable PX4 SIH profile for local development and
GitHub Actions.

Work:

- Pin official `px4io/px4-sitl:<tag>` and capture digest.
- Use `sihsim_quadx` for first multicopter gate unless maintainer selects a
  different frame.
- Add a no-sudo ephemeral routing path or document a dedicated-runner
  MavlinkAnywhere requirement.
- Add optional `workflow_dispatch` and nightly CI job.
- Upload all `reports/sitl/**` artifacts on `if: always()`.
- Keep normal PR CI on dry-run/unit/mock tests only until SIH has proven stable.

Acceptance:

- optional CI run starts the SIH profile and produces artifacts;
- failed/incomplete outcomes are visible and diagnosable;
- no real hardware endpoint is touched;
- no tracker/visual/HIL/field success is claimed.

### Phase 3C: Build PXE-0040 Official Gazebo Visual SITL

Goal: create the full visual simulation layer using official PX4 Gazebo
Harmonic, headless where feasible.

Work:

- Before starting Gazebo, prove generated video-stream receiver behavior:
  - file-backed generated clip;
  - `CUSTOM_GSTREAMER` or `videotestsrc` source;
  - local H.264 RTP/UDP sender into `UDP_STREAM`;
  - source config snapshot;
  - exact GStreamer sender and receiver pipelines;
  - frame count, dimensions, FPS, first/last frame hashes;
  - `VideoHandler.get_frame_status()` sequence showing fresh frames, then
    stale/unusable after sender stop.
- Add a unit/contract test that validates the UDP/RTP receiver pipeline includes
  `udpsrc`, RTP caps, `rtph264depay`, H.264 decode, BGR conversion,
  `videoscale`, configured width/height, and `appsink drop=true`.
- Add a new checked-in visual SITL plan for official
  `px4io/px4-sitl-gazebo:<tag>`.
- Use `HEADLESS=1` for CI/remote experiments.
- Start with camera-capable models such as `gz_x500_mono_cam` or
  `gz_x500_gimbal`.
- Consume Gazebo's default RTP/H.264 UDP video on port `5600`.
- First try existing PixEagle `UDP_STREAM` + `USE_GSTREAMER=true` and the
  existing RTP/H.264 GStreamer pipeline.
- Add a dedicated Gazebo video-source preset or source type only if the existing
  UDP/GStreamer path is insufficient.
- Capture short video snippets, frame traces, tracker outputs, command traces,
  PX4 logs, route profile, params, ULog/tlog, and config snapshots.
- Compare official Gazebo image to `jonasvautherin/px4-gazebo-headless` only as
  a fallback/compatibility study, especially around RTSP convenience.

Acceptance:

- generated RTP/UDP receiver proof passes before any Gazebo evidence is
  accepted;
- official Gazebo image can run headless on the selected validation host;
- PixEagle ingests simulated video and produces tracker/follower artifacts;
- evidence can prove scenario-specific visual behavior without field claims;
- if official Gazebo cannot satisfy video needs, the fallback decision is
  documented with exact missing capability and mitigation.

### Phase 3D: Production Tracker Trace PXE-0038

Goal: close the gap between deterministic probe/replay tests and production
tracker paths.

Work:

- Add production tracker or SmartTracker-backed deterministic smoke.
- Use a small generated or checked-in fixture clip.
- Record normalized tracker trace:
  - frame index;
  - bbox/angles;
  - tracker ID/confidence;
  - freshness and `usable_for_following`;
  - follower intent reason;
  - command fields;
  - commander accept/reject.
- Add redetection coverage:
  - target present;
  - target lost/stale;
  - safe hold/zero or stop;
  - target reacquired;
  - no stale pursuit leak.

Acceptance:

- tracker changes have a traceable artifact;
- CV/follower sign and freshness regressions are caught without PX4;
- L3 remains faster and easier to debug than L4 Gazebo.

### Phase 3E: X-Plane Disposition PXE-0020

Goal: remove stale/confusing X-Plane docs or rewrite them as maintained manual
evidence.

Work:

- Audit `docs/WINDOWS_SITL_XPLANE.md` and Windows MAVLink2REST defaults.
- Decide one of:
  - maintained manual X-Plane validation with current PixEagle ports, scripts,
    configs, evidence template, and no false automation claims;
  - historical archive with clear replacement path through SIH/Gazebo.
- Keep Windows guidance aligned with loopback `14569`/`8088` unless a security
  exception is explicitly documented.

Acceptance:

- no stale X-Plane instructions remain in active docs;
- manual workflow, if kept, includes exact artifacts and operator steps;
- no claim that X-Plane is headless CI until proven.

### Phase 4A: API/MCP Modernization

Goal: make the public automation surface professional, typed, and MCP-friendly.

Work:

- Start API/MCP modernization after the active Phase 3 evidence path is stable,
  but do not wait for full visual Gazebo to begin `/api/v1`.
- Introduce typed `/api/v1` routers.
- Add structured error envelope and operation IDs.
- Move dangerous actions into command/action resources with:
  - dry-run/preview where possible;
  - explicit confirmation;
  - idempotency keys;
  - audit/event records.
- Add `/api/v1` resources influenced by validation work:
  - routing profile/health;
  - telemetry MAVLink health;
  - Offboard commander state;
  - Offboard session start/abort;
  - SITL plans/runs/artifacts.
- Preserve legacy routes only as compatibility aliases with deprecation notes
  and removal tests.

Acceptance:

- route inventory tests cover old and new surfaces;
- all new JSON routes use typed request/response models, operation IDs, and
  structured errors;
- retryable/dangerous mutations have idempotency keys and explicit confirmation
  where needed;
- dashboard and future MCP clients use typed contracts;
- shell/Docker/MAVLink mutation is not exposed as ad hoc automation.

### Phase 4B: UI/UX And Dashboard Modernization

Goal: make the operator console clean, fast, reliable, and honest about stale
or unsafe states.

Work:

- Normalize dashboard API access through one typed/status-aware client before
  replacing the build toolchain.
- Migrate from Create React App/react-scripts to supported tooling such as Vite
  plus Vitest/Testing Library.
- Preserve current operator workflows:
  - live feed;
  - tracking;
  - following;
  - config;
  - models;
  - recording;
  - diagnostics.
- Improve visibility for:
  - tracker `has_output` vs active tracking;
  - stale/degraded data;
  - `usable_for_following`;
  - Offboard commander status;
  - telemetry health;
  - route/profile health;
  - validation artifact status.
- Keep UI work utilitarian and operator-focused, not decorative.

Acceptance:

- dashboard lint/test/build pass;
- no old dashboard workflow regresses;
- no direct API calls remain outside the normalized client/status store except
  explicitly documented transitional shims;
- stale/unusable tracker states are visible and tested;
- API migration does not duplicate clients or hardcoded route constants.

### Phase 5A: Gimbal Provider Expansion

Goal: keep the current Topotek SIP-over-UDP provider as one instance and make
future gimbals modular.

Work:

- Add selected provider only when hardware/protocol is chosen:
  - MAVLink Gimbal v2;
  - other commercial seeker/gimbal protocols;
  - simulator/replay provider.
- Keep follower contracts independent from provider details.
- Add provider conformance tests, replay fixtures, config schema, API status,
  and docs.

Acceptance:

- new providers plug into `GimbalInputProvider`;
- stale/provider-failed states remain fail-closed;
- docs show how developers add a gimbal without modifying followers.

### Phase 5B: Final Legacy Cleanup PXE-0041

Goal: remove all deprecated, duplicate, stale, misleading, or redundant pieces
after replacements are proven.

Work:

- Do not perform broad legacy cleanup before parity gates are in place.
- Remove or archive stale docs, old configs, backup config files, deprecated
  routes, obsolete scripts, placeholder tests, and dead code.
- Run stale-pattern docs tests across active docs.
- Verify config, generated schema, dashboard config UI, runtime defaults, and
  docs all agree.
- Produce final release-readiness evidence report.

Acceptance:

- issue register has no hidden unassigned debt;
- every compatibility alias has removal status;
- all active docs describe current behavior only;
- normal CI and selected optional validation profiles are green or explicitly
  incomplete with tracked blockers;
- final report lists exact tests, versions, evidence paths, and known limits.

## DockerHub And Image Policy

Do not create or publish a PixEagle DockerHub image yet.

Create/fork/publish only when one of these is true:

- official PX4 images cannot provide a required, documented capability;
- PixEagle needs a stable wrapper for repeatable startup, health checks, or log
  export;
- CI runtime becomes too slow or fragile without a prebuilt PixEagle validation
  image;
- maintainer chooses to distribute a validated PixEagle SITL stack.

If a PixEagle image becomes necessary:

- build from Dockerfile, not `docker commit`;
- pin base images by tag and digest;
- include SBOM/checksum where practical;
- keep secrets out of image layers;
- publish only after a clean runtime validation package exists;
- document image ownership, tags, deprecation policy, and rebuild triggers.

## Reviewer Gate For Every Slice

Before closing a slice:

- run focused tests first;
- run broader tests proportional to blast radius;
- update docs, issue register, phase map, journal, and offline copies;
- ask independent reviewers for:
  - PX4/MAVSDK/GNC safety;
  - CV/tracker/follower/video;
  - API/MCP/backend;
  - frontend UI/UX;
  - DevOps/Docker/Linux companion;
  - product/field-operator readiness;
  - code hygiene/legacy cleanup.

Concerns must be fixed or recorded as explicit tracked debt before moving to
the next slice.

## Approval Checkpoint

Recommended next slice after approval:

1. Continue PXE-0037 and implement the first owned injectors plus trace schema.
2. Then implement PXE-0039 SIH optional CI profile.
3. Then implement PXE-0040 official Gazebo visual SITL profile.

This order keeps the core harness honest before adding more simulator layers.

## Sources

- PX4 pre-built SITL packages: https://docs.px4.io/main/en/simulation/px4_sitl_prebuilt_packages
- PX4 Gazebo simulation: https://docs.px4.io/main/en/sim_gazebo_gz/index
- Docker Hub `px4io/px4-sitl-gazebo`: https://hub.docker.com/r/px4io/px4-sitl-gazebo
- Unofficial `jonasvautherin/px4-gazebo-headless`: https://github.com/JonasVautherin/px4-gazebo-headless
- X-Plane command-line options: https://developer.x-plane.com/article/command-line-options/
- X-Plane command-line usage: https://www.x-plane.com/kb/using-command-line-options/
- PX4 SIH CI validation research: `docs/reporting/agent-ops/codex-modernization/audits/2026-06-02-px4-sih-ci-validation-research.md`
