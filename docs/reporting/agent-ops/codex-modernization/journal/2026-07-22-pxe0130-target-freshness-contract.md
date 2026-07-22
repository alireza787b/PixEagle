# PXE-0130 Target Freshness Contract

- Date: 2026-07-22
- Phase: 5
- Status: local implementation validated; target-host evidence pending

## Trigger

Operator tests showed that reacquisition clicks could be delayed or rejected,
preview intent could remain zero or be obscured by telemetry, and the meaning of
the circuit breaker, calculation bypasses, target loss, prediction, and stale
output had become difficult to reason about. The controller also had separate
freshness checks for classic updates and follower dispatch.

## Decision

PixEagle now separates two concerns:

1. Trackers may retain a lost target internally for bounded prediction,
   visualization, association, and reacquisition.
2. Followers may use normal pursuit math only from an explicitly measured,
   active, non-stale output marked usable by its source.

`evaluate_tracker_command_freshness()` is the one controller-side normalizer for
classic, Smart/AI, and external tracker outputs. Sources retain their own timing
and loss policies because frame age, detector cadence, and external gimbal
packet age are different clocks. No second universal timeout was added.

The final circuit breaker remains the last command boundary. Local follower
testing uses `COMMAND_PREVIEW`, whose controller has no MAVSDK/PX4 publisher.
Preview may skip the operational flight envelope so it can expose raw follower
intent, but it still requires current measured tracker input and finite,
schema-valid command fields.

## Implementation

- Normalized bool-like provider metadata and made prediction-only output stale
  even if a provider accidentally claims it is usable.
- Reused the output from the same classic update call instead of re-reading a
  potentially newer tracker sample.
- Canonicalized inactive external output before passing it to followers that
  explicitly implement a target-loss response.
- Preserved bounded classic/Smart recovery and overlays while blocking normal
  pursuit on prediction-only or stale data.
- Ordered rapid Smart selections and bounded click fallback to stable tracks so
  the newest operator request wins without global tracker shutdown.
- Removed the active duplicate safety-bypass flags/routes and exposed raw local
  preview intent separately from stale vehicle telemetry.

## Evidence Review

The contract matches two established patterns. NVIDIA DeepStream retains targets
in shadow tracking for bounded recovery but does not report unreliable shadow
data as normal downstream output. ByteTrack recovers occluded targets through
association rather than terminating on one weak detection. PX4 independently
applies an Offboard proof-of-life timeout and configured failsafe action; visual
recovery state is not a substitute for a current command source.

- <https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_gst-nvtracker.html>
- <https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136820001.pdf>
- <https://docs.px4.io/main/en/flight_modes/offboard>

## Local Validation

- Shared freshness/controller suite: `163 passed`.
- Classic, Smart, gimbal, frame-freshness, and tracker-in-loop suite:
  `177 passed`.
- Combined affected regression before final cleanup: `728 passed`.
- Post-cleanup Smart/freshness/base-follower/gimbal/controller suite:
  `250 passed`.
- The complete backend run collected 3516 tests and reached `3467 passed, 48
  skipped, 1 failed`; the sole failure was a stale test literal expecting
  schema `1.4.0` after the intentional `1.5.0` migration. The test now imports
  the generator's schema-version authority. Post-fix generator/follower/tracker
  regression passed `115`; the exact-commit CI run remains the final clean
  full-suite evidence.
- Required API route/reload gate: `72 passed`.
- Config/schema gate: 38 sections / 537 parameters, no drift.
- Dashboard: 54 suites / 358 tests passed; production build passed.
- API tool-candidate inventory, Python compile, and `git diff --check` passed.

Three optional read-only review tasks did not return a result within the
bounded review window and were closed. No reviewer approval is claimed or used
as evidence for this checkpoint.

## Open Evidence

- Exact-commit GitHub CI, including the clean full backend suite.
- Exact VPS replay proof for classic and Smart/AI measured/lost/reacquired
  transitions and non-commanding preview intent.
- Raspberry Pi, real RTSP camera, Topotek gimbal, routed PX4, SITL/HIL, and field
  acceptance. None is implied by the local results.
