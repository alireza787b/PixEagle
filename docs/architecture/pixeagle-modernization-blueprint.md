# PixEagle Modernization Blueprint

This blueprint summarizes the approved modernization direction. The full source
plan is preserved at
`docs/reporting/agent-ops/codex-modernization/audits/2026-04-29-proposed-improvement-plan.md`.

## Architecture Principles

- Separate vision, following, flight control, telemetry, API, streaming, config,
  and UI concerns.
- Let flight-control ownership sit behind a dedicated async service.
- Keep PX4 Offboard heartbeat independent of frame processing and UI requests.
- Treat target freshness, telemetry freshness, command freshness, and Offboard
  state as first-class runtime data.
- Make APIs typed, versioned, inventory-tested, and MCP-friendly.
- Keep config, generated schema, docs, tests, and dashboard clients aligned with
  one source of truth.
- Treat external gimbals as provider instances behind a normalized gimbal input
  contract. The current Topotek SIP-over-UDP path is one provider, not the
  gimbal architecture.
- Remove legacy routes, configs, docs, and duplicated code through tracked
  deprecation gates rather than leaving permanent compatibility clutter.

## Target Runtime Flow

```text
Camera/streaming -> FramePublisher -> Detector/Tracker -> TargetState
TargetState -> TargetLossSupervisor -> Follower -> CommandIntent
CommandIntent -> CommandValidator -> FlightControlService command queue
FlightControlService -> OffboardCommander heartbeat -> MAVSDK/PX4
MAVSDK/MAVLink2REST -> TelemetryService -> TelemetrySnapshot -> SafetySupervisor/UI/API/followers
ExternalGimbalProvider -> GimbalTracker -> TargetState
```

## Target Validation Ladder

PixEagle needs layered validation so fast development stays deterministic while
flight-adjacent claims require real evidence:

- L0 unit and contract tests: follower math, tracker contracts, schema, typed
  APIs, config, and command validators without PX4.
- L1 mock integration tests: `TrackerOutput -> Follower -> CommandIntent ->
  FlightControlService` with canonical MAVSDK/MAVLink2REST telemetry fakes.
- L2 PX4 headless SITL follower tests: run PX4 in a pinned container or local
  package, route MAVLink through MavlinkAnywhere, feed synthetic targets, and
  assert Offboard entry, heartbeat continuity, setpoint behavior, target loss,
  abort, disconnect, and failsafe handling.
- L3 tracker-in-loop tests: deterministic synthetic or recorded video/gimbal
  fixtures drive detector/tracker output into the same follower/control path.
- L4 full visual SITL: X-Plane, Gazebo camera, or equivalent scene streams feed
  the real PixEagle pipeline with artifacted logs, video snippets, config
  snapshots, PX4 params, and ULog/tlog outputs.
- L5 HIL and field validation: explicit operator-approved runs only, with exact
  configs, versions, logs, abort procedures, and post-run evidence reports.

SITL success never implies real-world success by itself. It only proves the
scenario, versions, and artifacts that were actually run.

## Phase 0 Commitments

Phase 0 establishes governance and guardrails:

- clean-clone imports work without hidden local config files
- current API route inventory is frozen before migration
- schema drift is enforced
- dashboard test/build is enforced in CI
- modernization journal/checkpoint/report folders exist
- root `AGENTS.md` defines agent safety and validation expectations

## Phase Checkpoint Rule

At the end of each phase or major slice, update the modernization journal,
checkpoint report, and issue register. Reconcile the completed work against the
approved plan before starting the next slice.
