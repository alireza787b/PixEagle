# Session speed override — software checkpoint

Implemented the approved session-control slice, with the operator's explicit
October 22 revision: a deliberate speed adjustment replaces saved PixEagle total
and per-axis velocity caps for the active session. Restore removes the override
and keeps or lowers the request. Altitude, rates, acceleration, circuit breaker,
authority and aircraft firmware limits remain unchanged. See the
[operator and extension guide](../../../../followers/04-configuration/session-speed.md).

## Implementation

- Typed `SessionControl`, optional follower profile declarations, one owned value
  and revision; only GM Velocity Vector currently opts in.
- Shared authenticated `/api/v1/actions/following-control` mutation and native
  following status, including nullable maximum, override/reset capability,
  acknowledged value, effective submitted magnitude and limiting feedback.
- SafetyManager resolves the weak session-owner/provider at existing guidance,
  setpoint and PX4 boundaries. Saved configuration is never rewritten.
- Existing speed ramp follows the request in both directions. Final shaping
  covers retained continuity commands. Restore also reapplies the existing total
  magnitude limit at the final command boundary.
- Confirmed restoration after target loss now uses the normal slew limiter;
  ordinary bounded loss alone retains immediate horizontal-only restrictions.
  The higher-speed SIH extension exposed this previous restoration bypass.
- Delayed cleanup preserves observed Position/Land/RTL authority. MAVSDK Stop
  also requests Hold; local-only cleanup instead verifies its inactive scheduler.
  Unknown shutdown remains an error. Circuit-breaker cleanup reports a confirmed
  authority release truthfully without claiming another Hold.
- The existing gimbal vertical guard respects the canonical altitude-enable flag.
- Dashboard and QGC capture press identity/revision, retain acknowledged values,
  keep Stop independent, support restore through the same action, and provide
  keyboard/touch controls. QGC keeps Start/Stop outside scrollable panel content.

## Recorded verification

| Gate | Result |
| --- | --- |
| Backend unit suite | 3,871 passed; 11 optional GStreamer skips; existing deprecation warnings retained |
| Integration/API/security/inventory/docs group | 318 passed |
| Dashboard | 65 suites / 509 tests passed; production build passed |
| QGC | Incremental Linux build and all 476 Unit/Integration suites passed with standard Flaky/Network exclusions |
| Changed QGC files | Pre-commit passed after formatting, executable mode and a historical abbreviated-hash typo false positive were corrected |
| Backend schema / fatal Python lint | 607 parameters current; fatal selector passed |
| Focused restoration/slew/authority regression | 383 passed after the confirmed restoration fix |

The private evidence root is
`~/.cache/pixeagle-qgc-baseline/session-speed-2026-10-22/`.
It preserves all failed runs, exact commands, source/driver hashes, configurations,
dependency/image receipts and raw logs. Early failures included an identical
speed pair clipped to one limit, missing telemetry-route UID observation, and
response windows that confused retained motion or settled yaw correction with
the complete retarget response. The actual restoration slew violation was fixed,
not removed from the acceptance check.

Final isolated SIH runs are `sih-vector-horizontal-override-v8` and
`sih-vector-vertical-override-v8`. They use actual production dispatch,
continuity, shaping, publication and independently observed PX4 response, with
synthetic world-target observations and no camera or external network.

| Mount | Successful publications | Requested increase | Submitted median | PX4 median |
| --- | ---: | ---: | ---: | ---: |
| Horizontal | 1,105 | 0.75 m/s | 0.749 m/s | 0.725 m/s |
| Vertical | 1,104 | 0.75 m/s | 0.749 m/s | 0.733 m/s |

The saved demo forward ceiling was 0.5 m/s, so those runs demonstrate an actual
override. Both reduced to a 0.1 m/s request and reached exactly zero submitted
translation on a zero request. Independent residual simulated speed was about
0.065–0.068 m/s; a zero request is not proof of instantaneous physical stopping.
Restore, retargeting, brief loss/reacquisition, exhausted recovery, published
slew, and delayed cleanup preserving both Land and RTL passed. Position takeover
and circuit-breaker combinations have deterministic tests, not new field proof.

Plots retain the full transition; settled altitude response is also reported
separately because continuous retargeting intentionally retains initial motion.
No gain, recovery budget or field speed ceiling was increased by this repair.

## Configuration and delivery

Public VIDEO_FILE/CSRT, constant-position follower, altitude protection and
circuit-breaker defaults are preserved. The only saved control addition is
`GM_VELOCITY_VECTOR.REQUESTED_SPEED: null`; missing/null preserves prior startup.
Saved schema bounds apply to that startup setting, not the temporary override.

The private Desktop candidate configuration changes only startup request
(explicit `null`) and enables the agreed altitude protection. It preserves
Vertical mounting, initial speed 3 m/s, acceleration 0.9 m/s², saved forward/total
limits 5/8 m/s, lateral/vertical limits 2/1 m/s, yaw limit 45°/s, and relative
altitude bounds 3–120 m with a 2 m warning band. It remains command-blocked and
**has not been deployed**. The exact private diff and source checksum accompany it.

The QGC source is `7af9a506f8af2386e4649d6e1b71e7ad9ab90ff4` on
`feature/session-speed-override-2026-10-22`. One
[Windows-only test build](https://github.com/alireza787b/qgroundcontrol/actions/runs/39804077662)
was dispatched. No public QGC PR/release or backend stable promotion is part of
this checkpoint. The existing accepted package is retained.

Next: finish the Windows artifact, then cooled-Pi/camera bench acceptance with
CB active. Confirm shared Dashboard/QGC state, override/restore/zero, retarget,
loss, reconnect and Stop. Aircraft acceptance and stable publication remain
separate gates. This evidence does not establish camera tracking quality,
distance regulation, overtaking detection, optimized flight gains or new pursuit
behavior.
