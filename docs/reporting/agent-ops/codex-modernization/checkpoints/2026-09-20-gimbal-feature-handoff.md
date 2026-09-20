# PXE-0172: Optional gimbal controls — software handoff

Date: 2026-09-20. Feature branch: `feat/optional-gimbal-control-bench`.
Integrated upstream `f30dce2` before final checks. Operator authorized merging.

## Delivered

Default-off external camera Classic click/rectangle selection, retarget and
Cancel; camera Smart/fuzzy selection; bounded pan/tilt/roll/zoom/Home/Stop;
provider-owned speed presets/custom duration; serialized mouse/touch/keyboard
holds. Responsive remote-style controls occupy the right sidebar above Command
at desktop widths and follow video on narrow screens. One mounted component
preserves state across layout changes. Normal trackers retain their interface.

Restart/shutdown handling and SIP telemetry/parser corrections are included.
The input provider and optional control adapter remain separate from follower
math. Unknown mount values fail initialization; existing valid formulas remain.

`GimbalTracker.CONTROL_ENABLED` remains **false** in defaults and schema. Users
opt in and select Gimbal with matching RTSP input. Setup is documented in the
[gimbal reference](../../../../trackers/02-reference/gimbal-tracker.md#optional-dashboard-camera-controls).
The new [provider extension guide](../../../../trackers/05-development/external-gimbal-providers.md)
explains current contracts, capabilities, transport/video identity limits,
coordinate ownership, validation and qualification for future cameras.

## Integration fix and validation

Review found source identity was only snapshotted in one capture creation path.
Moved it to `init_video_source` before async UDP / upstream CSI auto branches.
Regression tests reopen from RTSP into UDP with both successful and failed open,
then prove selection rejects unrelated fresh frames without sending a command.
Upstream CSI changes were incorporated without conflicts.

Final checks on the combined tree:

- **659 backend tests passed**, covering gimbal protocol/control/API, follower
  contracts, restart/Offboard guards, route inventory, config reload, capture
  lifecycle and upstream CSI pipeline tests.
- **62 dashboard suites / 471 tests passed**; production build passed.
- Schema matches all 604 parameters; whitespace check passed.
- Production Chrome browser checks passed at 320/390/768/1200/1280 widths,
  including sidebar/stacked placement, 44px targets, custom settings, taps,
  mouse/touch/keyboard holds and release. Every action was intercepted;
  zero browser camera actions were forwarded.

[Evidence and commands](../evidence/2026-09-20-gimbal-final/README.md).

## Hardware boundary

Earlier horizontal evidence shows limited Classic retention and pan/hold/release
success, not complete device qualification. The latest proposed vertical session
recorded passive native video for 180 seconds starting 03:22:42 UTC; initial
GAC was about [0,100,-22.67]. The image initially showed a nearby arm/laptop and
pose later changed. No automated motion/selection command was issued in this
session. A recorded snapshot includes camera tracking active while following
remained off; subsequent status reported tracking disabled. Operator actions
were not a controlled acceptance procedure. Do not infer vertical motor mapping
or target retention from those states.

Remaining hardware acceptance: stable Classic rectangle/retarget sequence,
Smart candidate identity, and measured base-pitched-up 90° native axes/tracking
plus follower command-preview signs. Vertical installation remains explicitly
**unqualified**, with no guessed yaw/roll swap. No aircraft/SITL/HIL result.
This handoff closes implementation scope; hardware qualification remains tracked.

## Publication

Commit uses the operator-supplied author identity. Local merge can proceed after
checks. Remote publication requires restored authentication: HTTPS push dry-run
had no username credentials; GitHub rejected the loaded SSH key. No tokens were
requested or printed. No hosted PR is claimed. Local private configs, recordings
and vendor source archives remain ignored and unchanged.

### Publication completed

After the operator registered the SSH key, GitHub authenticated the account
`alireza787b`. Fetched upstream and verified a fast-forward before pushing local
`main` through `fe13be9` (feature commit `3bea324`). The origin push URL now uses
SSH. No hosted PR was created; this was the operator-authorized direct main
merge/push. Hardware qualification limits above are unchanged.
