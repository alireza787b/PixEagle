# PixEagle Codex 5.5 Proposed Improvement Plan

Date: 2026-04-29  
Repository audited: `/home/alireza/PixEagle`  
Comparison repositories: `/home/alireza/mavsdk_drone_show`, `/home/alireza/mavlink-anywhere`  
Scope: proposal and architecture plan only. No PixEagle source files were changed for this report.

## 1. Executive Decision

PixEagle should not be patched around the current structure. The current code has enough useful parts to preserve, but the runtime, flight-control boundary, API surface, docs, and validation gates need to be rebuilt around a clearer architecture.

The recommended target is a mission-critical, aviation-grade operator system with these hard rules:

1. Flight control must be owned by a dedicated async service, not by the video frame loop.
2. Offboard setpoint publishing must continue at a fixed heartbeat independent of camera FPS, tracker latency, UI state, and streaming health.
3. All public APIs must become typed, versioned, route-inventory-tested `/api/v1/...` contracts.
4. MCP/AI-agent support must come from the same typed API contracts, not a separate ad hoc automation layer.
5. Config, schema, docs, dashboard clients, tests, and runtime behavior must have one source of truth.
6. Legacy routes, docs, configs, and aliases may exist only behind a tracked deprecation plan with removal gates.
7. Safety claims must be backed by tests, SITL scenarios, logs, and evidence reports.

The best first proof of Codex 5.5 quality is not a cosmetic cleanup. It is to land a small set of high-leverage foundations:

1. Clean-clone config and test baseline.
2. API modernization blueprint plus route inventory tests.
3. Dedicated Offboard command publisher and flight state machine.
4. Dashboard API-client normalization and streaming capability negotiation.
5. CI gates for backend, frontend, schema drift, docs hygiene, and safety regressions.

## 2. Sources Consulted

### Local Repositories

- PixEagle: `/home/alireza/PixEagle`
- MAVSDK Drone Show reference project: `/home/alireza/mavsdk_drone_show`
- MavlinkAnywhere current project: `/home/alireza/mavlink-anywhere`

### Expert Review Slices

- PX4/MAVSDK flight safety, Offboard control, telemetry ownership.
- API/MCP/AI-agent standards from `mavsdk_drone_show`.
- Current `mavlink-anywhere` bootstrap, service, endpoint, dashboard, and update procedure.
- PixEagle backend/frontend API, streaming, UI/UX, and MCP readiness.
- PixEagle tests, CI, docs, scripts, schema, dependencies, and repository hygiene.

### Official External References Checked

- PX4 Offboard Mode: https://docs.px4.io/main/en/flight_modes/offboard
- PX4 Safety and Failsafe Configuration: https://docs.px4.io/main/en/config/safety
- MAVSDK Python QuickStart: https://mavsdk.mavlink.io/main/en/python/quickstart.html
- FastAPI response models: https://fastapi.tiangolo.com/tutorial/response-model/
- FastAPI error handling: https://fastapi.tiangolo.com/tutorial/handling-errors/
- Pydantic models: https://docs.pydantic.dev/latest/concepts/models/
- MCP 2025-06-18 specification: https://modelcontextprotocol.io/specification/2025-06-18
- MCP architecture: https://modelcontextprotocol.io/specification/2025-06-18/architecture
- MCP resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- MCP tools: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP authorization: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

Key external constraints:

- PX4 Offboard requires a stream of MAVLink setpoint messages before entering Offboard and continuously during Offboard. If the stream falls below the required rate, PX4 exits Offboard after the configured timeout and triggers the configured failsafe.
- PX4 has explicit failsafes for Offboard loss, data-link loss, manual control loss, geofence, position loss, battery state, and other flight-critical conditions. PixEagle should observe and respect those instead of duplicating unsafe assumptions.
- FastAPI supports `response_model` for output validation, filtering, documentation, and OpenAPI generation. PixEagle should use this for all JSON APIs.
- FastAPI error handling should raise structured exceptions and register exception handlers rather than returning inconsistent ad hoc error bodies.
- Pydantic defaults to ignoring unknown fields unless configured. PixEagle API schemas should generally use strict models for control/config mutations.
- MCP expects clear resources, tools, schemas, lifecycle/capability negotiation, and security boundaries. PixEagle should expose AI-agent capabilities through stable resources and guarded tools.

## 3. Current Audit Classification

### Working or Mostly Working

- The repository has a large backend test suite that can pass when local dependencies and `configs/config.yaml` are provided.
- Python source parses successfully.
- Shell scripts pass syntax checks.
- The general product concept is coherent: vision tracking, detector/tracker/follower modules, MAVSDK Offboard control, telemetry, web dashboard, streaming, config editor, model management, recording, and OSD.
- `FramePublisher` is a good shared abstraction for latest-frame distribution.
- `ConfigService` already has valuable pieces: schema awareness, validation, backups, atomic writes, audit history, and reload tiers.
- `follower_commands.yaml` and `SetpointHandler` are a useful start for schema-driven command fields.
- `TargetLossHandler` has useful state concepts but is not placed correctly in the control pipeline.
- Safety-related classes exist, including `SafetyManager`, `CircuitBreaker`, safety config sections, and PX4 command interception.
- The dashboard has real operator pages for live feed, tracking, following, config, models, recording, and diagnostics.

### Partially Working

- Real-world position/velocity chase appears to have worked in at least some cases, but it depends on fragile control-loop timing and incomplete safety feedback.
- SITL/X-Plane claims are plausible but not proven by a reproducible checked-in validation plan and evidence package.
- Streaming has multiple transports, but capability negotiation and fallback are inconsistent.
- API endpoints exist for most product areas, but they are mixed, unversioned, weakly typed, and not route-inventory-protected.
- Config schema generation exists, but schema drift is not enforced in CI.
- Tests are numerous, but some are placeholders/skips and do not yet prove the flight-safety behavior PixEagle needs.
- Docs are extensive, but several infrastructure docs are stale or contradictory after `mavlink-anywhere` changes.

### Not Working or Unsafe As Written

- A clean clone lacks `configs/config.yaml`, and imports can fail unless a local generated config exists.
- `SetpointSender` is described as a threaded publisher, but the reviewed implementation does not actually send MAVSDK setpoints. It logs/validates while actual sending happens elsewhere.
- Offboard setpoint sending is coupled to `AppController.follow_target()` and therefore to the video/tracking pipeline.
- PX4 Offboard success and command-send success are not reliably propagated to the caller.
- `_safe_mavsdk_call()` returns a boolean, but send methods ignore it in important paths.
- `_should_block_px4_command()` can fail open if circuit-breaker import/config is unavailable, despite comments implying fail-safe behavior.
- `connect_px4()` can mark following active even when Offboard startup failed or setpoint sender setup is invalid.
- MAVSDK telemetry collection uses sequential infinite `async for` loops, so only the first stream effectively runs.
- MAVLink2REST access uses blocking requests in async paths and needs timeouts/backoff.
- Offboard-exit callbacks cross thread/event-loop boundaries unsafely.
- Shutdown uses `os._exit(...)` paths, which bypass normal cleanup.
- Target-loss handling is not integrated before follower command generation.
- Gimbal/tracker stale state can keep active state true and produce unsafe command continuity.
- NaN/Inf and bounds checks are incomplete at the final PX4 command boundary.
- Some docs claim behavior that the code does not implement, especially continuous setpoint publishing.

### Technical Debt and Confusion

- `src/classes/fastapi_handler.py` is a large monolith that owns too many concerns.
- API names mix `/status`, `/stats`, `/commands/*`, `/telemetry/*`, `/api/*`, `/api/yolo/*`, `/video_feed`, and `/ws/*`.
- Dashboard API calls are duplicated across `apiEndpoints.js`, `apiService.js`, direct `axios`, direct `fetch`, and raw `API_URL`.
- CORS is permissive with `allow_origins=["*"]` and credentials enabled.
- Legacy `velocity_body` and newer `velocity_body_offboard` concepts coexist without a clean deprecation boundary.
- `mavlink-anywhere`, `mavlink-router`, and `mavlink2rest` docs are mixed in ways that create wrong port and setup guidance.
- CI is backend-heavy and does not enforce frontend build/test, schema drift, route inventory, or many docs/scripts expectations.
- Dependencies are mostly unpinned and not split by runtime/dev/AI/Raspberry Pi/GStreamer roles.
- Placeholder tests and skipped tests inflate confidence.
- Large media files and generated-looking assets need fixture policy.

## 4. Comparison Standards To Adopt

### From `mavsdk_drone_show`

PixEagle should adopt these patterns directly:

- `AGENTS.md` as canonical machine-oriented instructions for Codex, Claude Code, Gemini, and future agents.
- API modernization blueprint as a living standard.
- Canonical `/api/v1/...` routes for all new public business APIs.
- Noun/subresource route names.
- Temporary compatibility aliases only with deprecation metadata and removal tests.
- Pydantic request and response models for each route.
- Shared structured error envelope with timestamp, path, details, and machine-readable error codes.
- `response_model=` on FastAPI routes.
- Route inventory tests that freeze expected routes and reject duplicate method/path pairs.
- Command submission as a job resource with `command_id`, status, phase, result, target details, history, and idempotency.
- `idempotency_key` for mutations that could be retried by browsers, operators, or AI agents.
- Stable route constants for first-party clients and tests.
- Runtime evidence reports for SITL/field claims.
- Plan-based SITL validation with checked-in scenario plans.
- Frontend design-system guidance focused on operator-console workflows, not decorative pages.
- Makefile as a thin command index only, not a second config system.

Important reference files:

- `/home/alireza/mavsdk_drone_show/docs/apis/api-modernization-blueprint.md`
- `/home/alireza/mavsdk_drone_show/tests/test_api_route_inventory.py`
- `/home/alireza/mavsdk_drone_show/gcs-server/api_errors.py`
- `/home/alireza/mavsdk_drone_show/gcs-server/api_routes/commands.py`
- `/home/alireza/mavsdk_drone_show/src/command_contract.py`
- `/home/alireza/mavsdk_drone_show/docs/guides/sitl-validation-platform.md`
- `/home/alireza/mavsdk_drone_show/docs/guides/runtime-evidence-reporting.md`
- `/home/alireza/mavsdk_drone_show/docs/guides/frontend-design-system.md`
- `/home/alireza/mavsdk_drone_show/AGENTS.md`

### From Current `mavlink-anywhere`

PixEagle should update all infrastructure docs and scripts to the current standard:

- Bootstrap is two-step:
  - `sudo ./install_mavlink_router.sh`
  - `sudo ./configure_mavlink_router.sh`
- Current managed files:
  - `/etc/mavlink-router/main.conf`
  - `/etc/default/mavlink-router`
  - `mavlink-router.service`
  - `mavlink-anywhere-dashboard.service`
- Default local service endpoints:
  - MAVSDK: `127.0.0.1:14540`
  - MAVLink2REST: `127.0.0.1:14569`
  - Local MAVLink: `127.0.0.1:12550`
  - GCS listener: UDP server mode `0.0.0.0:14550`
  - TCP server: `5760`
- QGroundControl field setup should normally point to `<device-ip>:14550`.
- `gcs_listen` is server-mode and tracks the last sender. It is convenient for field access but not a deterministic multi-client fanout bus.
- Deterministic or multi-client remote access should use explicit normal-mode endpoints or TCP server `5760`.
- Dashboard binds to `127.0.0.1:9070` by default.
- Network exposure requires explicit `--dashboard-listen 0.0.0.0:9070` and should be limited to trusted networks, VPN, or SSH tunnel.
- Dashboard API uses `/api/v1/...` routes for status, diagnostics, config, endpoints, input, service, logs, system info, templates, and health.
- Update procedure:
  - `git fetch --tags origin`
  - `git pull --ff-only`
  - `sudo ./configure_mavlink_router.sh --install-dashboard`
  - run `sudo ./install_mavlink_router.sh` only when the router binary itself must be rebuilt/reinstalled.

Important reference files:

- `/home/alireza/mavlink-anywhere/README.md`
- `/home/alireza/mavlink-anywhere/docs/DASHBOARD.md`
- `/home/alireza/mavlink-anywhere/docs/CLI-REFERENCE.md`
- `/home/alireza/mavlink-anywhere/lib/common.sh`
- `/home/alireza/mavlink-anywhere/lib/config.sh`
- `/home/alireza/mavlink-anywhere/lib/service.sh`
- `/home/alireza/mavlink-anywhere/dashboard/internal/config/validator.go`
- `/home/alireza/mavlink-anywhere/dashboard/internal/profiles`
- `/home/alireza/mavlink-anywhere/dashboard/internal/mavlink/health.go`

PixEagle docs that must be corrected:

- `/home/alireza/PixEagle/docs/drone-interface/04-infrastructure/mavlink-anywhere.md`
- `/home/alireza/PixEagle/docs/drone-interface/04-infrastructure/mavlink-router.md`
- `/home/alireza/PixEagle/docs/drone-interface/04-infrastructure/port-configuration.md`
- Any docs still teaching `14541` for MAVSDK or `14551` for MAVLink2REST as the current default.

## 5. Target Architecture

### Package-Level Shape

Recommended future shape:

```text
src/pixeagle/
  api/
    app.py
    errors.py
    schemas/
    v1/
      routers/
        system.py
        runtime.py
        telemetry.py
        tracking.py
        following.py
        flight.py
        safety.py
        streams.py
        models.py
        config.py
        recordings.py
        logs.py
        actions.py
  runtime/
    app_controller.py
    lifecycle.py
    event_bus.py
    state_store.py
    service_registry.py
  flight/
    flight_control_service.py
    offboard_commander.py
    command_contracts.py
    command_validator.py
    telemetry_service.py
    safety_supervisor.py
    px4_adapter.py
  vision/
    detectors/
    trackers/
    estimators/
    target_state.py
  following/
    followers/
    target_loss_supervisor.py
  config/
    service.py
    schema.py
    migrations.py
  streaming/
    frame_publisher.py
    protocols/
  mcp/
    server.py
    resources.py
    tools.py
  validation/
    sitl_plans/
    evidence.py
```

This does not have to be a one-commit rewrite. It should be introduced behind adapters and route aliases, then old modules should be removed when tests and docs prove parity.

### Runtime Ownership

Current flow is too coupled:

```text
camera frame -> tracker -> follower -> AppController.follow_target() -> PX4 command send
```

Target flow:

```text
Camera/streaming -> FramePublisher -> Detector/Tracker -> TargetState
TargetState -> TargetLossSupervisor -> Follower -> CommandIntent
CommandIntent -> CommandValidator -> FlightControlService command queue
FlightControlService -> OffboardCommander heartbeat -> MAVSDK/PX4
MAVSDK/MAVLink2REST -> TelemetryService -> TelemetrySnapshot -> SafetySupervisor/UI/API/followers
```

Hard boundary:

- Vision and follower modules publish intent.
- Only `FlightControlService` talks to MAVSDK command APIs.
- Only `TelemetryService` owns telemetry snapshots.
- API routes never call low-level MAVSDK directly.
- UI commands become tracked actions/jobs.

### Flight State Machine

Introduce explicit flight-control states:

- `DISCONNECTED`
- `CONNECTING`
- `CONNECTED`
- `ARMED_READY`
- `OFFBOARD_PRIMING`
- `OFFBOARD_ACTIVE`
- `DEGRADED_HOLD`
- `ABORTING`
- `RTL_REQUESTED`
- `LAND_REQUESTED`
- `FAILED`
- `LANDED_OR_DISCONNECTED`

Each transition must define:

- allowed source states
- required telemetry freshness
- required command freshness
- required PX4 mode/arming state
- required operator confirmation
- timeout
- rollback or abort action
- emitted event
- audit log line
- API-visible status

### Offboard Command Publisher

Replace the current effective behavior with a dedicated async publisher:

- Runs independent of frame processing and API requests.
- Publishes at configured fixed rate, preferably 10-20 Hz.
- Meets PX4 requirement of continuous Offboard setpoint proof-of-life.
- Primes Offboard with safe setpoints before `offboard.start()`.
- Uses last validated command until expiry.
- Falls back to neutral hold/zero/decay policy depending control type.
- Exits to degraded hold or abort if heartbeat deadline is missed.
- Records publish jitter, missed cycles, last command age, last telemetry age, and MAVSDK failures.
- Does not silently report success when MAVSDK send failed.

New command object:

```text
ValidatedSetpoint
  command_id
  source
  source_tracker_id
  control_type
  frame
  fields
  created_at
  expires_at
  validation_version
  safety_status
  limit_actions
```

### Safety Supervisor

Centralize all real-flight guardrails:

- Offboard heartbeat monitor.
- Telemetry freshness monitor.
- Tracker freshness monitor.
- Command queue backlog monitor.
- Control-loop jitter monitor.
- MAVSDK failure-rate monitor.
- PX4 mode monitor.
- Manual/RC takeover monitor.
- Battery/geofence/position health monitor when available.
- Safety-limit violation monitor.
- Repeated rejected-command monitor.
- Disk-space/logging/recording pressure monitor.

Abort and degradation policy should be explicit:

- Brief target loss: hold last safe command with decay.
- Target-loss timeout: hold/search/RTL/Land depending mode, altitude, vehicle type, and config.
- Telemetry stale: degrade or abort, never substitute zeros as truth.
- Offboard exit: disable following immediately and report hard state change.
- MAVSDK disconnect: abort active follow and require operator re-enable.
- Config reload while following: block or stage depending reload tier and risk.

### API and MCP Architecture

All public JSON APIs should move under `/api/v1`. Old routes stay as compatibility aliases only during migration.

Recommended route families:

```text
GET  /api/v1/system/health
GET  /api/v1/system/version
GET  /api/v1/capabilities
GET  /api/v1/openapi.json

GET  /api/v1/runtime/status
GET  /api/v1/runtime/events

GET  /api/v1/telemetry/snapshot
GET  /api/v1/telemetry/tracker
GET  /api/v1/telemetry/follower
GET  /api/v1/telemetry/flight

GET  /api/v1/tracking/status
POST /api/v1/tracking/sessions
GET  /api/v1/tracking/sessions/{session_id}
POST /api/v1/tracking/sessions/{session_id}/actions/stop
GET  /api/v1/tracking/target

GET  /api/v1/following/status
POST /api/v1/following/sessions
GET  /api/v1/following/sessions/{session_id}
POST /api/v1/following/sessions/{session_id}/actions/stop

GET  /api/v1/flight/status
POST /api/v1/flight/offboard-sessions
GET  /api/v1/flight/offboard-sessions/{session_id}
POST /api/v1/flight/offboard-sessions/{session_id}/actions/stop
POST /api/v1/flight/actions/hold
POST /api/v1/flight/actions/rtl
POST /api/v1/flight/actions/land

GET  /api/v1/safety/status
GET  /api/v1/safety/interlocks
GET  /api/v1/safety/violations

GET  /api/v1/streams
GET  /api/v1/streams/live/status
GET  /api/v1/streams/live/mjpeg
WS   /ws/v1/streams/live/video
WS   /ws/v1/streams/live/webrtc/signaling
GET  /api/v1/streams/qgc-gstreamer/status

GET  /api/v1/models
POST /api/v1/models
GET  /api/v1/models/{model_id}
POST /api/v1/models/{model_id}/actions/activate
POST /api/v1/models/{model_id}/actions/delete

GET  /api/v1/config/schema
GET  /api/v1/config/values
GET  /api/v1/config/changes
GET  /api/v1/config/backups
POST /api/v1/config/actions/validate
POST /api/v1/config/actions/apply

GET  /api/v1/recordings
POST /api/v1/recordings/actions/start
POST /api/v1/recordings/actions/stop

GET  /api/v1/logs/recent
GET  /api/v1/actions
POST /api/v1/actions/{action_id}/dry-run
POST /api/v1/actions/{action_id}/confirm
GET  /api/v1/commands/{command_id}
GET  /api/v1/commands/active
GET  /api/v1/commands/recent
```

Response envelope:

```json
{
  "success": true,
  "data": {},
  "warnings": [],
  "timestamp": "2026-04-29T00:00:00Z",
  "request_id": "req_..."
}
```

Error envelope:

```json
{
  "success": false,
  "error": {
    "code": "tracking.target_not_available",
    "message": "Target is not available",
    "detail": "No fresh target has been observed within the configured timeout.",
    "retryable": true,
    "details": {}
  },
  "timestamp": "2026-04-29T00:00:00Z",
  "path": "/api/v1/following/sessions",
  "request_id": "req_..."
}
```

OpenAPI extensions for safety and agent tooling:

- `x-pixeagle-risk`
- `x-requires-confirmation`
- `x-runtime-effect`
- `x-reload-tier`
- `x-idempotency-required`
- `x-safe-while-armed`
- `x-safe-while-following`
- `x-mcp-tool`
- `x-mcp-resource`

MCP first release should be conservative:

- Read-only resources first:
  - `pixeagle://runtime/status`
  - `pixeagle://safety/status`
  - `pixeagle://telemetry/snapshot`
  - `pixeagle://tracking/target`
  - `pixeagle://streams/status`
  - `pixeagle://config/schema`
  - `pixeagle://config/values`
  - `pixeagle://logs/recent`
  - `pixeagle://validation/evidence`
- Guarded tools after API contracts stabilize:
  - `pixeagle_validate_config`
  - `pixeagle_apply_config` with dry-run and confirmation
  - `pixeagle_start_tracking`
  - `pixeagle_stop_tracking`
  - `pixeagle_start_following`
  - `pixeagle_stop_following`
  - `pixeagle_hold`
  - `pixeagle_run_sitl_plan`
  - `pixeagle_collect_evidence`

Security requirements:

- Read/control separation.
- Explicit scopes: `viewer`, `operator`, `admin`, `agent`, `safety`.
- Dangerous actions require confirmation and idempotency key.
- MCP HTTP transport, if exposed remotely, must follow the current MCP authorization requirements and validate audience/resource. Local-only stdio or localhost HTTP is acceptable for the first iteration.

### Dashboard and UI/UX Target

The dashboard should become an operator console:

- First viewport shows mission-critical state:
  - backend connected
  - video healthy
  - tracker state
  - follower state
  - armed state
  - PX4 mode
  - Offboard heartbeat state
  - safety interlocks
  - active stream protocol
  - config pending restart/apply state
- One typed API client and status store.
- No direct scattered `axios.get(API_URL + ...)` calls.
- Stream page shows:
  - selected protocol
  - backend capabilities
  - last frame age
  - stream FPS
  - reconnect state
  - WebRTC ICE state
  - fallback reason
- Config editor shows:
  - reload tier
  - risk level
  - dependency metadata
  - safe while armed/tracking flags
  - pending changes
  - validation errors
  - backup/rollback status
- Model manager must protect paths and model sources.
- Dangerous actions use consistent confirmation, dry-run, command tracking, and result display.

Keep:

- `FramePublisher` latest-frame abstraction.
- Existing useful dashboard pages, but move them onto a consistent shell and typed API client.

Change:

- Browser WebRTC selection should depend on backend capability/status, not only browser support.
- WebSocket frame transport should use a documented frame envelope or separate metadata/stats channel.
- UI should avoid hiding critical safety state inside separate pages.

## 6. Phased Plan

### Phase 0 - Baseline, Governance, and No-Regressions Gate

Goal: Make the current project reproducible and auditable before major rewrites.

Deliverables:

- Add `AGENTS.md` as canonical terminal-agent instructions.
- Add `docs/architecture/pixeagle-modernization-blueprint.md`.
- Add `docs/apis/api-modernization-blueprint.md` modeled after `mavsdk_drone_show`.
- Fix clean-clone behavior around `configs/config.yaml`.
- Decide whether `configs/config.yaml` is generated, copied from default, or created by bootstrap.
- Add route inventory test for current routes before migration.
- Add schema drift CI using `scripts/check_schema.sh`.
- Add dashboard CI: `npm ci`, tests, production build.
- Add import/syntax checks for backend.
- Add docs-staleness inventory for infrastructure docs.
- Add issue register mapping each known debt to phase and acceptance gate.

Acceptance gates:

- Clean clone can import PixEagle modules without manual hidden files.
- Existing Python tests still pass or all skips are explicitly justified.
- Dashboard install/test/build runs in CI.
- Schema drift fails CI.
- Current route inventory is frozen.
- Reported local worktree stays clean after validation.

Primary files:

- `configs/config_default.yaml`
- `configs/config.yaml` policy
- `scripts/check_schema.sh`
- `.github/workflows/tests.yml`
- `dashboard/package.json`
- `tests/test_api_route_inventory.py`
- `AGENTS.md`
- docs index files

### Phase 1 - Runtime Spine and Ownership Boundaries

Goal: Build the architectural spine without changing operator behavior yet.

Deliverables:

- Introduce runtime service registry.
- Introduce immutable state snapshot store.
- Introduce event bus for runtime, safety, tracking, following, streaming, config, and flight events.
- Add typed internal domain contracts:
  - `TargetState`
  - `FollowerIntent`
  - `ValidatedSetpoint`
  - `TelemetrySnapshot`
  - `SafetyStatus`
  - `RuntimeStatus`
  - `ActionCommand`
  - `ActionResult`
- Move state mutations out of API handlers.
- Keep adapters for old `AppController` until replaced.

Acceptance gates:

- Existing UI/API behavior still works through adapters.
- Runtime state can be read without calling low-level components.
- Unit tests prove event/state ownership and thread-safety boundaries.
- No API route calls MAVSDK directly.

Primary files:

- `src/classes/app_controller.py`
- `src/classes/flow_controller.py`
- `src/classes/fastapi_handler.py`
- new `src/pixeagle/runtime/*`

### Phase 2 - Flight Safety and Dedicated Offboard Commander

Goal: Remove the main production safety risk.

Deliverables:

- Implement `FlightControlService`.
- Implement `OffboardCommander`.
- Implement explicit flight state machine.
- Implement command queue and validated setpoint expiry.
- Move MAVSDK command sends behind the Offboard commander.
- Prime Offboard with safe setpoints before start.
- Continue setpoint heartbeat independent of frames.
- Fail-closed circuit breaker behavior.
- Final PX4-boundary validator for NaN/Inf, ranges, missing fields, stale commands, control type mismatch, acceleration/jerk, thrust limits, and vehicle compatibility.
- Real return values for MAVSDK command success/failure.
- Thread-safe scheduling for Offboard exit callbacks.
- Telemetry freshness policy.

Acceptance gates:

- Test proves heartbeat continues during video stall.
- Test proves Offboard cannot start without priming.
- Test proves stale target transitions to hold/degraded/abort.
- Test proves command validator rejects NaN/Inf and over-limit fields.
- Test proves circuit breaker sends zero real MAVSDK commands.
- Test proves Offboard exit disables following and emits status.
- Test proves `connect_px4()` cannot report following active after Offboard failure.

Primary files:

- `src/classes/px4_interface_manager.py`
- `src/classes/setpoint_sender.py`
- `src/classes/setpoint_handler.py`
- `src/classes/app_controller.py`
- `src/classes/mavlink_data_manager.py`
- `src/classes/safety_manager.py`
- `src/classes/circuit_breaker.py`
- new `src/pixeagle/flight/*`

### Phase 3 - Telemetry and Target-Loss Pipeline

Goal: Make target and telemetry freshness first-class control inputs.

Deliverables:

- `TelemetryService` owns MAVSDK and MAVLink2REST snapshots.
- MAVSDK telemetry streams run concurrently, not as sequential infinite loops.
- MAVLink2REST calls use async client or thread offload with timeouts, backoff, and circuit state.
- `TargetLossSupervisor` runs before follower command generation.
- Tracker states are explicit:
  - `DETECTED`
  - `PREDICTED`
  - `LOST`
  - `STALE`
  - `UNAVAILABLE`
- Gimbal active state cannot mask stale target data.
- Recovery requires confirmation policy after target reacquisition if configured.

Acceptance gates:

- Telemetry stale never becomes fake zeros.
- Target stale blocks new pursuit commands.
- Brief target loss holds/decays safely.
- Long target loss follows configured hold/search/RTL/Land policy.
- Follower receives normalized target state, not raw tracker internals.

Primary files:

- `src/classes/mavlink_data_manager.py`
- `src/classes/px4_interface_manager.py`
- `src/classes/target_loss_handler.py`
- `src/classes/followers/*`
- `src/classes/trackers/*`
- new `src/pixeagle/flight/telemetry_service.py`
- new `src/pixeagle/following/target_loss_supervisor.py`

### Phase 4 - API v1, Command Jobs, and MCP Foundation

Goal: Make PixEagle professional, stable, and AI-agent-friendly.

Deliverables:

- Split `FastAPIHandler` into domain routers.
- Add `api/errors.py` with structured error envelopes.
- Add Pydantic schemas for all public JSON routes.
- Register FastAPI exception handlers.
- Add `response_model=` everywhere.
- Add tags, operation IDs, examples, and deprecation metadata.
- Add `/api/v1` route families.
- Keep old routes as compatibility aliases with sunset dates.
- Add route inventory tests for both current aliases and new canonical routes.
- Add command/job tracker:
  - `command_id`
  - `idempotency_key`
  - status
  - phase
  - result
  - target
  - errors
  - timestamps
- Add `/api/v1/actions` registry, dry-run, and confirm flow.
- Add read-only MCP resources over stable API/state contracts.

Acceptance gates:

- OpenAPI is useful and complete for dashboard/client generation.
- No duplicate method/path route pairs.
- Legacy routes are explicitly marked deprecated.
- Dangerous actions require idempotency and confirmation.
- MCP read-only resources match API schemas.
- Existing dashboard still works through compatibility layer until migrated.

Primary files:

- `src/classes/fastapi_handler.py`
- new `src/pixeagle/api/*`
- new `src/pixeagle/mcp/*`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/services/apiService.js`
- `tests/test_api_route_inventory.py`

### Phase 5 - Config, Schema, and Single Source of Truth

Goal: Eliminate duplicated config truth and make config safe for operators and agents.

Deliverables:

- Define canonical config source:
  - `configs/config_default.yaml` plus generated runtime copy, or
  - explicit profile overlays with generated `configs/config.yaml`.
- Add config migrations and versioning.
- Extend schema metadata:
  - stable parameter ID
  - sensitivity
  - risk level
  - dependencies
  - effective runtime value
  - reload tier
  - safe while armed
  - safe while tracking
  - safe while following
- Enforce schema drift in CI.
- Replace endpoint-heavy config API with resource/action pattern.
- Config apply supports validate, preview diff, backup, apply, rollback.
- Docs state exactly which files can be edited and which are generated.

Acceptance gates:

- Manual edits to generated schema fail CI.
- Config apply cannot silently modify safety-critical runtime values while following.
- Dashboard and API show same reload tier and risk metadata.
- Config rollback is tested.

Primary files:

- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `scripts/generate_schema.py`
- `scripts/check_schema.sh`
- `src/classes/config_service.py`
- `dashboard/src/hooks/useConfig.js`

### Phase 6 - Computer Vision, Tracking, and Model Management

Goal: Make detectors, trackers, estimators, and model operations extensible and safe.

Deliverables:

- Define plugin contracts for:
  - detectors
  - trackers
  - estimators
  - followers
  - stream processors
- Add registry and lifecycle hooks:
  - initialize
  - warmup
  - start
  - stop
  - health
  - metrics
  - config schema
- Fix SmartTracker prediction/loss/ID semantics.
- Make tracker target ID and confidence explicit.
- Decouple model activation from immediate unsafe runtime changes.
- Harden model upload/download/delete:
  - allowed extensions
  - path traversal prevention
  - size limits
  - checksums
  - source allowlist
  - quarantine/validation before activation
  - active-model rollback
- Replace detector/estimator placeholder tests with real contract/factory tests.

Acceptance gates:

- A new detector/tracker/follower can be added through documented contracts.
- Model activation is idempotent and rollback-capable.
- Target identity remains stable or explicitly reports changes.
- Tracker lost/predicted/stale states are test-covered.

Primary files:

- `src/classes/detectors/*`
- `src/classes/trackers/*`
- `src/classes/estimators/*`
- `src/classes/followers/*`
- `src/classes/model_manager.py`
- `tests/unit/detectors/*`
- `tests/unit/estimators/*`

### Phase 7 - Streaming and Dashboard Operator Experience

Goal: Turn the dashboard into a robust operator console.

Deliverables:

- Add `/api/v1/streams` resources and status.
- Backend capability negotiation for MJPEG, WebSocket, WebRTC, GStreamer.
- WebRTC endpoint returns ICE/STUN/TURN configuration and availability.
- Document WebSocket frame envelope or split metadata/stats from binary video.
- Dashboard uses one typed API client.
- Add central status store for runtime/safety/video/tracking/following/config.
- Make safety state visible globally.
- Add actionable stream diagnostics and fallback reasons.
- Add frontend tests for API client, status store, stream fallback, config apply, dangerous action confirmation.
- Add dashboard build/test CI.

Acceptance gates:

- Dashboard can run against mocked API contracts.
- Stream fallback path is deterministic and visible.
- UI shows last frame age and backend stream capability.
- Frontend build is required in CI.

Primary files:

- `src/classes/frame_publisher.py`
- `src/classes/webrtc_manager.py`
- `src/classes/gstreamer_handler.py`
- `src/classes/fastapi_handler.py`
- `dashboard/src/components/VideoStream.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/services/apiService.js`
- `dashboard/src/services/apiEndpoints.js`

### Phase 8 - MavlinkAnywhere, Bootstrap, Services, and Docs

Goal: Remove stale infrastructure guidance and make setup deterministic.

Deliverables:

- Rewrite PixEagle MAVLink infrastructure docs around current `mavlink-anywhere`.
- Stop describing `mavlink-anywhere` as MAVLink2REST.
- Update default ports:
  - MAVSDK `14540`
  - MAVLink2REST `14569`
  - local MAVLink `12550`
  - GCS listener `14550/server`
  - TCP `5760`
- Update QGroundControl instructions to use `<device-ip>:14550` for normal field access.
- Distinguish:
  - PixEagle application service
  - `mavlink-router.service`
  - `mavlink-anywhere-dashboard.service`
  - MAVLink2REST process/service
- Add PixEagle bootstrap script that checks and explains routing state rather than duplicating `mavlink-anywhere` config logic.
- Add update docs:
  - update PixEagle
  - update `mavlink-anywhere`
  - update dashboard
  - rebuild router only when needed
- Keep Makefile as thin wrappers around canonical scripts.

Acceptance gates:

- No docs teach old `14541`/`14551` defaults as current standard.
- A fresh operator can bootstrap with current `mavlink-anywhere`.
- Docs explain server-mode `gcs_listen` limitations.
- Docs distinguish deterministic endpoint fanout from field convenience.

Primary files:

- `docs/drone-interface/04-infrastructure/mavlink-anywhere.md`
- `docs/drone-interface/04-infrastructure/mavlink-router.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/drone-interface/04-infrastructure/hardware-connection.md`
- `README.md`
- `Makefile`
- bootstrap scripts

### Phase 9 - Tests, CI, SITL, HIL, and Evidence

Goal: Make safety and functionality claims provable.

Deliverables:

- Split tests:
  - unit
  - integration
  - API contract
  - frontend
  - schema
  - safety
  - SITL
  - HIL/manual gated
- Add `pytest` markers and CI matrix.
- Add route inventory tests.
- Add OpenAPI snapshot or schema compatibility tests.
- Add command-publisher timing tests.
- Add telemetry freshness tests.
- Add target-loss tests.
- Add model-manager security tests.
- Add config apply/rollback tests.
- Add dashboard API mock tests.
- Add checked-in SITL plan library.
- Add `tools/run_sitl_validation_suite.py`.
- Add evidence report generator:
  - git SHA
  - config checksums
  - PX4 version
  - mavlink-anywhere version
  - route inventory
  - test results
  - SITL logs
  - ULog paths/checksums
  - screenshots/video if applicable
  - known limitations

Acceptance gates:

- No placeholder tests count as meaningful coverage.
- Frontend and backend tests are both required.
- SITL claims require plan output and evidence artifacts.
- Field claims require ULog/evidence package.

Primary files:

- `.github/workflows/tests.yml`
- `pytest.ini`
- `tests/*`
- `dashboard/package.json`
- `tools/*`
- new `tools/sitl_plans/*`
- new `docs/guides/runtime-evidence-reporting.md`

### Phase 10 - Legacy Removal and Repo Hygiene

Goal: Leave no hidden legacy debt behind after migration.

Deliverables:

- Remove or sunset:
  - deprecated `/api/yolo/*` routes after replacement.
  - old unversioned routes after dashboard/client migration.
  - legacy `velocity_body` docs or mark as compatibility-only.
  - stale docs for old ports/procedures.
  - duplicate config paths.
  - unused scripts.
  - generated tracked artifacts that should be ignored.
- Move large sample media to fixture policy or Git LFS/external package.
- Rename generated-looking dashboard assets or document them as canonical.
- Remove placeholder docs/tests or convert to real references/issues.
- Add repo hygiene CI:
  - no `.pyc`
  - no `.pytest_cache`
  - no unexpected generated schema drift
  - no large unapproved binaries
  - no duplicate route names
  - no stale deprecated routes after sunset

Acceptance gates:

- Legacy alias inventory is empty or intentionally kept for a named release.
- Docs search for old ports/routes returns only deprecation notes.
- Repo status remains clean after test/build/docs generation.

### Phase 11 - Release and Field Validation

Goal: Move from "works somehow" to a reproducible release process.

Deliverables:

- Release checklist:
  - clean clone
  - config generation
  - backend tests
  - frontend tests/build
  - schema drift
  - route inventory
  - SITL plan suite
  - docs links
  - safety gates
  - package/build artifacts
- Bench validation:
  - no propellers
  - simulated PX4/mocked MAVSDK
  - real camera/video source
  - command inhibition verified
- SITL validation:
  - PX4 SITL
  - X-Plane path if still supported
  - MavlinkAnywhere routing
  - MAVLink2REST telemetry
  - dashboard operation
- HIL validation:
  - real autopilot
  - motor outputs inhibited where possible
  - RC override
  - Offboard loss
  - telemetry loss
- Field validation:
  - conservative envelope
  - operator abort
  - target loss
  - mode takeover
  - ULog/evidence report

Acceptance gates:

- No live flight until bench, SITL, and HIL gates pass.
- Field report includes exact versions, configs, logs, and known risks.

## 7. Edge-Case Scenario Matrix

Each scenario needs unit or integration tests, and several need SITL/HIL coverage.

1. No video frame at startup.
2. Video stalls while Offboard is active.
3. Tracker returns stale target while follower remains enabled.
4. Tracker switches target ID mid-follow.
5. Tracker confidence falls below threshold.
6. Gimbal reports active while target data is stale.
7. Detector model switch during active tracking.
8. Follower profile switch while Offboard is active.
9. Config reload requests system restart while following.
10. Config change is safe for UI but unsafe while armed.
11. MAVSDK disconnects during Offboard.
12. MAVLink2REST times out or returns malformed data.
13. PX4 exits Offboard due to setpoint loss.
14. PX4 mode changes manually from RC/QGC.
15. RC/manual control lost.
16. Data link lost.
17. Local position invalid.
18. Geofence breach.
19. Battery warning/failsafe.
20. Command queue fills or lags.
21. Command publisher misses heartbeat deadline.
22. MAVSDK call fails repeatedly.
23. API client retries a start-follow command.
24. Browser refreshes during active following.
25. WebSocket disconnects while WebRTC is active.
26. WebRTC ICE negotiation fails.
27. Recording disk fills.
28. Model upload path traversal attempt.
29. Model download URL is untrusted.
30. Dashboard stale API cache after config apply.
31. Bootstrap sees old `14541`/`14551` config.
32. MavlinkAnywhere dashboard exposed on untrusted network.
33. SITL route differs from real hardware route.
34. ULog capture fails after a field test.
35. Emergency stop is pressed during a config write.

## 8. What Not To Do

- Do not keep per-frame setpoint sending as the flight-control heartbeat.
- Do not report command success when MAVSDK send/start failed.
- Do not silently fall back to zeros for stale telemetry.
- Do not let target-loss logic live after follower command generation.
- Do not keep adding routes inside the monolithic `FastAPIHandler`.
- Do not build MCP as a separate, inconsistent side API.
- Do not preserve old routes forever.
- Do not let dashboard code call raw backend paths from many places.
- Do not keep docs that teach old ports as current.
- Do not claim SITL or field success without checked-in plans and evidence.
- Do not count placeholder tests as coverage.
- Do not introduce a second config system in Makefile or scripts.

## 9. First Implementation Slice

This is the recommended first set of changes to prove quality quickly.

### Slice 1 - Clean Clone and CI Gate

Deliver:

- Fix `configs/config.yaml` clean-clone behavior.
- Add schema drift CI.
- Add dashboard test/build CI.
- Add route inventory snapshot for current API.
- Remove or mark placeholder tests honestly.

Why first:

- It prevents future work from hiding behind local-only state.

### Slice 2 - API Modernization Blueprint and Error Contract

Deliver:

- Add PixEagle API blueprint.
- Add `api/errors.py`.
- Add structured error envelope.
- Add first `/api/v1/system/health` and `/api/v1/runtime/status` routes.
- Keep old `/status` route as alias.
- Add route inventory test.

Why second:

- It creates standards before the monolith is split.

### Slice 3 - Offboard Commander Skeleton

Deliver:

- Add `FlightControlService` and `OffboardCommander` behind current API.
- Move one control path through command queue.
- Add heartbeat tests with fake MAVSDK.
- Keep existing behavior behind feature flag until verified.

Why third:

- It addresses the highest safety risk without rewriting all followers at once.

### Slice 4 - Dashboard API Client Normalization

Deliver:

- Centralize all dashboard calls through `apiService`.
- Add compatibility mapping for old and new routes.
- Add stream capability/status endpoint use.
- Add frontend test for fallback and status display.

Why fourth:

- It prevents API migration from breaking the operator UI.

### Slice 5 - MavlinkAnywhere Docs Update

Deliver:

- Rewrite routing docs with current `mavlink-anywhere` procedures.
- Update ports.
- Update QGC instructions.
- Add update procedure.
- Add bootstrap verification checklist.

Why fifth:

- It removes operator confusion immediately and aligns PixEagle with the current ecosystem.

## 10. Definition of Done For The Modernization

PixEagle should be considered production-ready only when:

- Clean clone works without hidden local files.
- All runtime modules have clear owners and lifecycle.
- Offboard heartbeat is independent of video/tracking.
- PX4 command success/failure is accurately reported.
- Safety supervisor enforces telemetry, target, command, and Offboard freshness.
- `/api/v1` is canonical and route-inventory-tested.
- Legacy routes are removed or have active sunset tracking.
- OpenAPI has typed models, operation IDs, errors, tags, and safety metadata.
- MCP resources/tools are derived from the same contracts.
- Dashboard uses one typed API layer.
- Streaming fallback is deterministic and visible.
- Config has one source of truth, schema drift gate, migration story, and rollback.
- MavlinkAnywhere docs match current install/config/update behavior.
- Backend, frontend, schema, route, docs, and safety tests run in CI.
- SITL plans and evidence reports support all "working" claims.
- HIL/field release gates exist before real flight.
- Stale docs, redundant configs, placeholder tests, and ignored tracked files are cleaned up.

## 11. Maintainer Review Questions

Before implementation, the maintainer should decide:

1. Should the new package path be `src/pixeagle/...` while old `src/classes/...` is phased out, or should modules be migrated in place?
2. Should `/api/v1` adopt the exact `mavsdk_drone_show` response envelope, or a PixEagle-specific variant with the same fields?
3. Should `configs/config.yaml` be generated on bootstrap, committed as a default runtime config, or replaced by profile overlays?
4. Which Offboard control types are officially supported for the first production release?
5. What is the required real-world abort action default: Hold, RTL, Land, or operator-configured by vehicle profile?
6. Which SITL backends are release-blocking: PX4 default simulator, X-Plane, Gazebo, or all configured backends?
7. Should MCP start as local-only read-only, or include guarded operator actions in the first release?
8. How long should legacy API aliases remain after dashboard migration?

## 12. Bottom Line

PixEagle has a strong product direction and many useful pieces, but the current architecture is not yet production-grade. The most important defect is the flight-control heartbeat being effectively tied to the vision pipeline. The most important ecosystem gap is the unversioned, weakly typed API. The most important operations gap is stale infrastructure documentation around MavlinkAnywhere and MAVLink ports. The most important quality gap is that CI and tests do not yet prove the system's safety claims.

The path forward is a disciplined modernization, not a blind rewrite and not a patch pile. Build the runtime spine, command publisher, typed API, config truth, dashboard client, and validation gates first. Then migrate detectors, trackers, followers, streaming, docs, and legacy cleanup slice by slice until no stale route, config, doc, or test remains.
