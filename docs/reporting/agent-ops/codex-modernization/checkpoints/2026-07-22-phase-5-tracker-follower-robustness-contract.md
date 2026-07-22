# Phase 5 Checkpoint: Tracker And Follower Robustness Contract

- Date: 2026-07-22
- Issues: PXE-0132; PXE-0131 and PXE-0133 deferred follow-ups
- Status: local implementation complete; exact-source publication and VPS acceptance pending
- Scope: Classic tracker validation, estimator ownership, follower axis/unit
  consistency, active config truth, and evidence claims

## Operator Findings

CSRT could lose a target too readily, rejected candidates could influence
published geometry before reacquisition consensus, and follower preview showed
unexpected yaw direction or zero forward motion. The audit also found
precomputed errors passed into `simple_pid`, ignored resolved aim points,
duplicate/dead settings, and runtime/catalog claims that exceeded evidence.

## Resulting Contract

1. A tracker proposal is private until finite geometry, frame overlap,
   confidence, appearance, motion, scale, and configured consensus accept it.
2. Rejected or prediction-only geometry may support overlay and bounded
   recovery, but it cannot become a normal follower measurement.
3. Candidate validation does not mutate estimator state. The accepted
   measurement or application-owned loss path commits one transition per frame.
4. Normalized image right/down is positive. After any camera/gimbal transform,
   positive output means body right, clockwise MAVSDK yaw, or body down.
5. `simple_pid` receives a measurement. Shared helpers preserve signed image
   error without each follower inventing another sign convention.
6. AppController resolves center/initial/custom aim policy once and supplies the
   same target point to follower implementations.
7. `mc_velocity_chase` owns a bounded forward ramp. Position and historical
   distance profiles remain stationary/yaw-centric and do not pretend to infer
   range from a 2D box.
8. Mode switches, emergency stop, and reset clear inactive controller and yaw
   smoother history before another command intent is published.
9. Chase ramps integrate monotonic elapsed time and cap one transition at the
   configured nominal cadence. Scheduler stalls and clock changes do not create
   catch-up velocity jumps.
10. Gimbal chase exposes only its implemented `CONSTANT` and `PITCH_BASED`
    forward-speed modes. Neither estimates range or interception state;
    proportional-navigation forward-speed control is not implemented.
11. Performance, accuracy, occlusion, and readiness claims are
   scenario-dependent unless an exact benchmark artifact proves otherwise.

## Configuration Cleanup

- Removed inert Particle Filter defaults and the phantom built-in
  `ParticleFilter` API catalog entry; no maintained implementation or factory
  path existed.
- Removed the unused `Estimator.USE_ESTIMATOR_FOR_FOLLOWING` flag because
  prediction-only data is intentionally follower-ineligible.
- Retired duplicate KCF, dlib, follower aim, and unimplemented distance-hold
  settings through schema version `1.6.0`.
- Retired the unused `MC_VELOCITY_CHASE.PID_UPDATE_RATE`; the active ramp
  cadence remains `RAMP_UPDATE_RATE`, while shared follower-loop cadence is
  owned by `Follower.General.CONTROL_UPDATE_RATE`.
- Removed the unimplemented gimbal `PROPORTIONAL_NAV` forward-speed option and
  replaced the stale research guide with an implementation-accurate mode page.
- Kept `Tracking.PF_CANNY_THRESHOLD1/2` active. Despite their historical names,
  they configure the shared detector edge descriptor. The existing retirement
  framework does not transfer customized values to a replacement path, so a
  direct rename would be a silent upgrade regression. PXE-0133 records the
  reusable migration gate.
- Regenerated `configs/config_schema.yaml`: 38 sections / 513 parameters.

## Main Files

- Tracker runtime: `src/classes/trackers/base_tracker.py`,
  `src/classes/trackers/csrt_tracker.py`, KCF and dlib tracker adapters,
  `src/classes/smart_tracker.py`.
- Follower runtime: `src/classes/followers/base_follower.py`, chase, position,
  ground, attitude-rate, fixed-wing, and gimbal follower implementations.
- Config/API: `configs/config_default.yaml`, `configs/config_retirements.yaml`,
  `configs/tracker_schemas.yaml`, `configs/follower_commands.yaml`, generated
  schema, Parameters/ConfigService, and typed API snapshots.
- Tests/docs: tracker, detector, follower, controller, config migration, schema,
  tracker reference, follower reference, PID/GNC, and extension guides.

## Local Evidence

- Upgrade/config/detector contract: `91 passed`.
- Complete follower unit contract: `110 passed`.
- Tracker/detector/runtime inventory: `469 passed, 40 skipped`; skips are
  optional dlib/provider paths.
- AppController Offboard safety boundary: `160 passed`.
- Required API route/reload gate: `72 passed`.
- Documentation/schema generator gate: `85 passed`.
- Smart capability evidence regression: `9 passed`.
- Schema check, Python compile, and `git diff --check`: passed.
- Real OpenCV 4.13 CSRT wrapper on deterministic textured translation:
  59/59 updates accepted, mean IoU `0.724`, minimum IoU `0.601`, robust mode.
  This is a synthetic software smoke, not aerial or field evidence.
- Complete final backend run: `3518 passed, 48 skipped, 1 warning` in
  `417.09 s`. The warning is the already tracked PXE-0127 Starlette/httpx
  test-toolchain deprecation; it is not a runtime tracker/follower failure.
- Dashboard: `54` suites / `358` tests passed and the beta.21 production build
  completed successfully. API tool-candidate inventory was regenerated after
  the snapshot cleanup and passes its `13/13` contract.
- Post-review focused gates: image-axis/chase/CSRT/static contracts `82 passed`;
  config migration `49 passed`; follower inventory `114 passed`;
  tracker/detector/Smart/static inventory `372 passed, 40 skipped`; required
  API/reload plus Offboard safety `232 passed`; docs/schema/static `89 passed`.
  These focused counts overlap the complete regression and are recorded for
  failure localization, not added together as unique coverage.

No optional independent reviewer returned a result within the bounded prior
review window. No independent-review approval is claimed. The implementation
was instead checked against focused contracts, the full affected inventory,
and the explicit residual issue register.

## Claim Boundary

This checkpoint proves local software contracts and one deterministic OpenCV
smoke. It does not prove tiny aerial-target continuity, occlusion recovery,
identity through crossings, detector quality, Raspberry Pi throughput,
RTSP/GStreamer timing, external gimbal transforms, MAVLink routing, PX4
response, SITL/HIL, aircraft behavior, or field safety.

PXE-0131 owns monotonic-time Smart recovery and representative 5/15/30 FPS,
dropped-frame, UAVDT/VisDrone, ego-motion, turn, scale, occlusion, crossing, and
distractor benchmarks. Those requirements are not replaced by more local
thresholds in this beta.

## Next Gate

1. Run the final complete backend and dashboard/version gates.
2. Commit, push, tag, and wait for exact-source CI.
3. Reconcile the authorized VPS without overwriting local config or credentials.
4. Run Classic/Smart selection and `mc_velocity_chase` command preview with PX4
   sidecars absent; verify nonzero forward/yaw intent and zero PX4 publication.
5. Hand the exact URL/version to the maintainer for browser testing.
