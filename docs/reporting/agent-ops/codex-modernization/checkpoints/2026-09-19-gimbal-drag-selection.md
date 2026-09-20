# PXE-0172: Classic rectangle selection and mounting readiness

Date: 2026-09-19. Branch: `feat/optional-gimbal-control-bench`.

## Delivered slice

The optional external camera Classic mode now supports a single click or a
dragged rectangle. A click retains the existing fixed 64-pixel reference region;
a drag supplies the target's initial width and height. Smart remains camera
fuzzy-click selection. Normal local trackers and default-disabled installations
retain their existing workflow.

The typed `select` request accepts optional `width` and `height`, both required
together, in displayed-image fractions. `x`/`y` describe the rectangle center.
The backend reverses display rotation/flip, swaps dimensions for 90/270 degrees,
and sends the official Qt rectangle descriptor 1 through the existing provider.
Invalid or out-of-image geometry is rejected before any camera mutation; Smart
rectangle requests are rejected. Existing following, freshness, authorization,
idempotency, cancellation and shutdown guards still apply.

The browser draws a temporary rectangle, supports reverse/touch drags, excludes
letterbox bars and buttons, clips the release to the image edge, and rejects a
gesture whose video geometry or availability changed. Pointer cancellation sends
nothing. A completed gesture consumes the following click so it cannot retarget
twice. Small motion remains a click; a one-dimensional drag is discarded.

Changed source areas: `gimbal_control.py`, `api_v1_contracts.py`,
`api_v1_actions.py`, dashboard `BoundingBoxDrawer` and `GimbalControlPanel`, their
tests, generated API candidate provenance, tracker documentation and reports.
No configuration defaults or follower guidance formulas changed in this slice.

## Validation

- 213 backend tests passed: control/wire geometry, typed actions, route inventory,
  generated candidates, parameter reload and restart lifecycle.
- Dashboard: 61 suites / 443 tests passed; production build passed.
- Schema check, touched Python compilation and `git diff --check` passed.
- The isolated bench backend accepted a typed restart, returned with replacement
  PID 61231 (previous 27870), and exposes both rectangle fields in its live API
  schema. Following remains off and mode resets to Classic. Camera is offline.
- Separate mounting audit: 56 existing coordinate/vector/smoke tests passed;
  these describe existing software, not mounting qualification.

Exact command lines, logs, runtime response and source hashes are in the
[evidence bundle](../evidence/2026-09-19-gimbal-drag-mount-readiness/README.md).
The drawn rectangle path still needs real-camera acceptance. No new camera
motion, aircraft commands, SITL or HIL were run during this slice.

## Earlier corrected-orientation session, now preserved

Before this rectangle change, the operator reconnected the camera. Read-only
ROT queries returned `ROT02`, and native video was upright. The isolated bench
display was changed 180→0 through Settings; typed Restart returned with PID
16221→27870. The normal user configuration was preserved.

At approximately 19:07:25 UTC, an off-center orange pen-holder selection moved
toward image center and remained tracked for a four-second guarded observation,
then was cancelled. OFT centers moved from approximately (1018,242) to (954,559.5)
in the 1920×1080 reference. No target-lost observation occurred in that trial.
At 19:09:52–19:10:00, two actual browser selections each reported active for
twelve 250 ms samples, followed by successful Cancel. These are short, specific
scene checks, not universal tracking retention evidence.

Subsequent operator Classic/Smart clicks included temporary losses. Passive
video showed a briefly selected fan and later a larger bag region. No visible
preselection AI candidate was confirmed, so descriptor-9 command acceptance and
active status do not establish AI identity or detection selection. That test
was deferred by the operator. Private images remain in local `reports/`; the
bundle retains frame hashes/timing, wire records and action records.

## Next slice: only horizontal and vertical installations

The [mounting audit](2026-09-19-gimbal-mounting-audit.md) identifies existing
parameters and disagreements between follower axis/sign conventions. The
descriptive tracker schema does not perform a runtime yaw/roll swap. No generic
mount-angle UI or new mounting preset is added.

The operator will power the standalone camera in the intended vertical position.
First identify the mounting plate and intended aircraft nose, then record startup,
stationary telemetry/video and bounded native-axis pulses. Establish stable
camera-native tracking before changing display orientation. Repeat point/box,
retarget and Cancel in PixEagle, then replay the measured directions through
command preview. Only those observations can justify a shared horizontal/vertical
mapping; firmware support for sideways startup is currently unverified.
