# Phase 2 Offboard Safety Audit

Date: 2026-05-21  
Slice: Phase 2 Offboard commander and safety truth  
Primary issues: PXE-0007, PXE-0013  
Decomposed issues: PXE-0025 through PXE-0033

## Scope

This audit maps the current Offboard command publication, safety state, and
operator-abort behavior before refactoring. It is not a SITL/HIL/flight
validation artifact.

## Current Command Path

Current runtime flow:

1. `FlowController` obtains a frame.
2. `AppController.update_loop()` updates trackers only when a frame reaches the
   loop.
3. `AppController.follow_target()` calls the active `Follower`.
4. The concrete follower writes fields into its `SetpointHandler`.
5. `AppController.follow_target()` directly awaits a PX4 send method based on
   `self.follower.get_control_type()`.
6. `SetpointSender` runs in a thread, but only validates/logs current fields; it
   does not send MAVSDK Offboard setpoints.

That means the current Offboard command stream is coupled to video/tracker loop
cadence. It is not a guaranteed independent heartbeat.

## Findings

### Critical: Frame-Loop-Coupled Offboard Publication

- `AppController.update_loop()` only calls `follow_target()` inside tracker paths.
- `AppController.follow_target()` performs the real MAVSDK dispatch.
- `SetpointSender._send_commands_sync()` explicitly does not send commands.
- A video stall, slow tracker, or blocked frame loop can starve PX4 Offboard
  setpoints.

Issue: PXE-0007.

### Critical: Offboard Start Failure Can Become Local Success

- `PX4InterfaceManager.start_offboard_mode()` catches start exceptions and
  returns an error dict.
- `AppController.connect_px4()` does not inspect that result before appending
  "Offboard mode started" and setting `following_active=True`.
- The API can report success when MAVSDK Offboard start was rejected.

Issue: PXE-0025.

### High: Command Send Failures Do Not Propagate

- `_safe_mavsdk_call()` returns `False` on MAVSDK errors.
- Velocity/attitude send methods ignore the boolean result.
- `AppController.follow_target()` can return success after a failed MAVSDK
  publication.

Issue: PXE-0026.

### High: Operator Abort Paths Are Not Flight-Control-Complete

- `cancel_activities()` and stop-tracking paths can clear tracker state without
  stopping Offboard, publishing a final zero/hold command, or clearing
  `following_active`.
- Dashboard/API operator guidance does not define the status checks needed to
  verify that an abort actually reached PX4.

Issue: PXE-0027.

### High: Offboard Exit Callback Is Not Thread-Safe

- `MavlinkDataManager` polls in a background thread.
- It invokes the registered callback synchronously from that thread.
- `AppController` registers a callback that calls `asyncio.create_task()`, which
  requires a running event loop in the current thread.
- If scheduling fails, follow mode may not be disabled after PX4 exits Offboard.

Issue: PXE-0028.

### High: SetpointSender Shutdown Can Be Skipped

- `_disconnect_px4_internal()` calls `self.setpoint_sender.get_status()`.
- `SetpointSender` has no `get_status()` method.
- The exception path can skip `stop()` and drop the sender handle while the
  daemon thread keeps running.

Issue: PXE-0029.

### High: Target-Loss And Inactive Paths Can Skip Safe Publication

- Some followers update safe setpoints and return `False`.
- `AppController.follow_target()` treats `False` as "do not publish."
- Other inactive paths can retain previous nonzero fields when no new safe
  command is published.

Issue: PXE-0031.

### High: Video Freshness Is Not A Command-Freshness Contract

- `FlowController` skips `update_loop()` when frame acquisition returns `None`.
- `VideoHandler` can return cached frames without canonical frame-age metadata.
- Classic tracker outputs can look active from `tracking_started` even when
  measurement freshness is weak or prediction-only.

Issue: PXE-0032.

### Medium: Rate And Safety Config Are Not Single Source Of Truth

- `FOLLOWER_DATA_REFRESH_RATE` is documented/schemaed as Hz but used as sleep
  seconds.
- `CONTROL_UPDATE_RATE` and `SETPOINT_PUBLISH_RATE_S` do not currently define
  real MAVSDK publish cadence.
- Circuit-breaker and safety-manager unavailable paths disagree between modules.
- Setpoint limit mappings are duplicated and disagree for attitude-rate fields.

Issues: PXE-0030, PXE-0033.

### Medium: Docs Overstate Current Safety Behavior

- Offboard and SetpointSender docs describe an independent continuous
  publication path that is not implemented.
- Safety docs describe `trigger_failsafe()` as terminate, while current code
  calls RTL.
- Operator abort docs do not define a verified stop-following checklist.

Issue: PXE-0013.

## First Safe Fix Order

1. Add tests for Offboard start failure, command send failure propagation,
   SetpointSender shutdown, and thread-safe Offboard-exit callback scheduling.
2. Fix those fail-open paths without yet introducing the full Offboard commander.
3. Correct docs that overstate independent heartbeat behavior.
4. Add the dedicated commander/flight-control service that owns fixed-rate
   Offboard publishing, command TTL, last-command age, and fail-closed state.
5. Add video-stall, tracker-stale, follower-target-loss, operator-abort, and
   MAVSDK-disconnect tests against that boundary.
6. Only then claim improved Offboard safety beyond unit/mock evidence.

## Tests To Add

- Offboard start rejected: API/controller returns failure, `following_active`
  remains false, no sender thread survives.
- MAVSDK send failure: PX4 send method returns false/degraded and
  `AppController.follow_target()` does not report success.
- Disconnect with sender: `SetpointSender.stop()` is called even if status
  inspection fails or is unavailable.
- MAVLink Offboard exit from polling thread: callback disables following through
  a thread-safe event-loop handoff or synchronous safe-state fallback.
- Video stall while following: no-frame path triggers fail-closed command or
  explicit command-stream stop.
- Target-loss timeout: followers publish a final zero/hold command or stop the
  command stream, including yaw-rate fields.
- Safety unavailable: command dispatch is blocked or explicitly degraded unless
  an operator-approved bypass is configured.

## Current Evidence

- Local audit of:
  - `src/classes/app_controller.py`
  - `src/classes/flow_controller.py`
  - `src/classes/setpoint_sender.py`
  - `src/classes/px4_interface_manager.py`
  - `src/classes/mavlink_data_manager.py`
  - `src/classes/followers/*`
  - `src/classes/target_loss_handler.py`
  - Offboard/safety docs under `docs/drone-interface/`
- Reviewer council completed read-only review across PX4/GNC, architecture/API,
  tracker/follower/CV, and docs/operator readiness.

## Status

PXE-0007 and PXE-0013 remain in progress. No Phase 2 safety signoff is claimed.
