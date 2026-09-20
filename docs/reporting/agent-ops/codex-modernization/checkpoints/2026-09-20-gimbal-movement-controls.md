# PXE-0172: Adjustable camera steps and hold-to-repeat

Date: 2026-09-20. Branch: `feat/optional-gimbal-control-bench`.
Scope: optional camera movement UX and invalid mount rejection. Camera remained
offline during verification; no new hardware, flight, SITL or HIL result.

## Result

The default-off camera panel now offers one compact **Movement** selector:
Fine, Normal, Fast and Adjust. The dialog edits speed and step duration locally;
Apply changes the next pan/tilt/roll command, Cancel discards edits, and Reset
restores provider defaults. The estimate is speed × duration, not commanded
absolute angle. Choices are session-local and do not become unattended startup
settings. Ordinary/local trackers see none of these controls.

The SIP adapter advertises the presets and limits once through typed status:

| Setting | Speed | Duration |
| --- | ---: | ---: |
| Fine | 5°/s | 150 ms |
| Normal (unchanged default) | 10°/s | 250 ms |
| Fast | 20°/s | 500 ms |
| Custom bounds | 1–30°/s | 100–1000 ms |

The dashboard reads the provider contract rather than duplicating its limits.
The typed action rejects invalid/non-integer settings, wrong operations and
unsupported provider settings. Dry-run and execution both enforce provider
bounds. Actual chosen speed/duration are included in the action result. Zoom
retains its existing bounded pulse; the movement dialog does not change it.

Direction and zoom buttons accept mouse, touch and Space/Enter holds. A tap
finishes one timed step. Holding repeats only after the preceding request has
completed; the client cannot queue a train of movement requests. Release ends
repetition and requests Stop during repeats. Pointer cancellation, capture loss,
blur, hidden page, component removal and lost authority terminate the gesture.
The active button remains able to receive release while a step is busy. Stop
also clears the gesture. Expected backend interruption by Stop does not display
as a camera fault, while actual transport failures remain errors.

The backend still owns each finite pulse and its best-effort timer. Requests
already in transit may complete after release, and network loss/process death
cannot guarantee physical stop. This is not a continuous motor lease or hardware
watchdog. There is no automatic resume after release or reconnect.

## Mounting disposition

The operator clarified the proposed installation as the base pitched up 90°,
not a sideways rotation around the lens. The camera disconnected before motor
characterization, and the operator asked to finish offline before reconnecting.
The earlier upright image and pitch near 90° are not enough to identify joint
order or prove that native yaw/roll should swap. The existing Chase/Vector
formulas also differ. No guessed axis remap or default change was introduced.

One definite fault was fixed: invalid `MOUNT_TYPE` values now reject follower
initialization instead of silently selecting Vertical. Vector no longer has its
implicit vertical fallback; valid Horizontal/Vertical and legacy Vector
`TILTED_45` behavior is preserved. Only the two requested installation forms
remain in the new qualification scope. See the
[mounting audit](2026-09-19-gimbal-mounting-audit.md) for the measured mapping work.

## Files and validation

- `gimbal_motion.py` owns provider defaults, presets and validation;
  `gimbal_control.py` applies bounded speed/duration and publishes settings.
- Typed contracts/action handling and generated API candidate provenance updated.
- `GimbalControlPanel` adds the compact selector/dialog;
  `useGimbalHold` owns repeat and release behavior; `useGimbalControl` handles
  expected stop interruption without hiding other errors.
- Both GM followers reject unknown mount values. Tracker/follower domain docs,
  tests, journal and issue register updated.

Validation: **491 backend tests passed**, covering movement/wire encoding,
custom bounds, cancellation, API idempotency/dry-run, mount validation, existing
follower contracts/factory, API inventory, config reload and restart/Offboard
regressions. **62 dashboard suites / 471 tests passed**. Production build,
schema check, touched Python compilation and `git diff --check` passed.
Existing Starlette and Node deprecation warnings remain.

The production build was exercised in Chrome 150 using desktop 1280×1000 and
mobile 390×844 contexts. Browser routes intercepted every action, with simulated
completion delays; **zero browser camera actions reached the backend**. Actual
mouse/touch/keyboard tap/hold/release, custom payloads, dialog Apply, and mobile
horizontal layout passed without page errors. A settled dialog screenshot was
also inspected. This is browser behavior evidence, not physical movement proof.

The previous bench processes had exited during the interruption. The isolated
supervisor was started again with the existing command-preview/circuit-breaker,
disabled-MAVLink configuration. Runtime status confirms following off and the
new motion-settings contract. The dashboard is available on loopback port 3040;
the camera remains unavailable until the operator reconnects.

[Evidence, exact commands and source hashes](../evidence/2026-09-20-gimbal-movement-controls/README.md).

## Next camera acceptance

1. Start in normal horizontal mounting, plate above the camera, base steady and
   head clear, with a distinct object a few metres away. Record native image,
   current ROT and fresh GAC/TRC before changing anything.
2. Verify Fine tap, held movement and release/Stop on each axis; then one Normal
   and Fast step and a bounded custom setting. Observe actual travel and limit
   behavior; do not begin with maximum custom settings.
3. Test Classic click and drawn rectangle, retarget and Cancel in the browser.
   Check initial geometry against native video and camera OFT where available.
4. Power down and reinstall in the intended base-pitched-up 90° pose. Identify
   the intended aircraft nose and repeat startup/axis checks at neutral and one
   modest offset. Establish onboard tracking behavior before any mapping change.
5. Use those records to implement/validate a shared two-preset mounting mapping
   if the existing behavior does not match. Replay angles into follower command
   preview only; physical direction agreement is still required.
6. Camera Smart candidate identity remains a separate pending scene test with
   a visible AI candidate. No PR has been published yet.
