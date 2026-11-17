# Stock MAVLink application checkpoint — 17 November 2026

## Scope

The stock observation/one-shot sender foundation (`fe1b3802d`) is now joined to
the production application lifecycle. Ordinary FW/VTOL guidance uses the existing
UART/MAVLink connection; no DDS link or firmware patch is required. The native
adapter remains an explicitly selected advanced implementation, with its stricter
timing and ownership contracts preserved.

One phase/session/control model serves both transports. The application owns one
binding and commander. SDK connection generation, aircraft UID, REST source epoch,
parameter revision and phase generation qualify Start. Read-only status polling
does not acquire authority. The existing telemetry poller accepts owner-scoped
cadence demands; preparation requests standard attitude/position/phase streams
through the existing telemetry owner and releases its cadence demand on source
replacement or connection teardown.

Fixed camera inputs require their existing source-bound calibration. Gimbal
inputs reuse canonical provider/mount geometry. Stock association explicitly
reports latest received bearing; no exposure timestamp or estimator-reset counter
is invented. Cached samples retain their original world ray.

## Defect found by application SIH

The first two application runs reached Start but eventually handed off after
`follower_rejected_measurement`. Readiness associated a camera sample with a newer
connection snapshot than the active follower's command owner had observed. The
next calculation correctly refused that apparent ordering regression.

Readiness and calculation now share the **bound session's** original snapshot.
Before acquisition they still use current connection observations. Freshness and
ordering checks remain active; an expired owner snapshot cannot authorize input.
The regression covers this boundary and stale-state rejection. Failed evidence
is retained. Run r3 separately records the corrected pre-acquisition distinction:
a prepared session has no bound aircraft snapshot yet.

## Actual stock PX4 evidence

Firmware: unmodified `99a3048735caa5a2c277d6aa8e17a12a6133db5d`.
Evidence root: `reports/sitl/stock-px4-qualification-20261116/`.
Each run records exact staged source/configuration hashes and actual PX4 pose.
Camera observations are independent simulated world-target projections.

| Run | Measured result |
| --- | --- |
| `fw-application-normal-r4` | Vertical mount; 405 successful publications, zero failures; range 168.10 m to minimum 0.67 m; altitude error ≤1.90 m; loss recovery and Hold confirmed |
| `fw-application-horizontal-r1` | Horizontal mount; range 158.24 m to minimum 0.61 m; altitude error ≤2.03 m; loss recovery and Hold confirmed |
| `fw-application-descent-r1` | Explicit experimental descent; range 162.58 m to minimum 0.38 m; observed 38.20 m altitude change; loss recovery and Hold confirmed |
| `xvert-application-mc-r1` | Tailsitter hover; range 15.72 m to minimum 0.27 m; altitude error ≤0.05 m; loss recovery, speed change and Hold confirmed |
| `xvert-application-fw-r1` | Settled tailsitter FW; range 164.31 m to 41.89 m; altitude error ≤1.14 m; loss recovery, speed change and Hold confirmed |

Under `reports/sitl/stock-px4-qualification-20261117/`,
`xvert-application-takeover-r1` confirms pilot Return is retained with no later
direct mode command. `xvert-application-transition-r1` ends following on a
pilot-requested transition to MC, with no replayed mode command or automatic
following restart. In that isolated Offboard transition PX4's native sender-loss
response selects Return; it is not relabelled as Hold. Stop before a planned
transition avoids relying on this failsafe. These checks do not qualify PX4's
transition altitude/performance envelope.

These are finite scenario results, not stall-envelope, physical-camera, HTTP/QGC
end-to-end or real-aircraft qualification. Command intent is never integrated to
invent aircraft movement. The read-only reports reuse the existing 3D visualizer;
missing older per-sample phase remains unknown rather than reconstructed.

## Client contract and verification

`ground_speed_proxy` is optional, explicitly labelled feedback. It never replaces
the requested airspeed field or claims actual stall margin. Dashboard and QGC
Details no longer promise native TECS/vertical-path control for stock attitude/
thrust. Existing optional metadata handling remains backward compatible.

Recorded gates: backend unit run 7,729 passed / 11 optional skips; focused final
input/control/inventory checks 143 passed; Dashboard 69 suites / 592 tests passed
and production build passed. The API/integration run passed 356 checks and found
one stale generated inventory, subsequently regenerated and checked. Schema:
45 sections / 614 parameters. QGC incremental build and its 269-case client suite
pass. The full QGC standard Unit/Integration selection passed 536 of 559 checks
initially; all 23 video checks then passed with the installed ICE plugin directory
and X11/software-GL environment exposed. The initial shell lacked `nicesrc` and
`nicesink`; no test was removed. Final profile gates remain separate.

## Remaining before deployment

- Extend repeated-session, source-degradation and publication-failure application
  checks as needed; component publisher-loss evidence remains distinct. Preserve
  explicit Stop and require a new Start after transition.
- Review factory 5–100 m conservative defaults and private 6 m/s / 5 m floor
  overlay together. Review explicit public speed-override permission in the
  canonical safety policy; do not add competing limiters.
- Renew exact-checkpoint backend/API, schema, client and package gates, commit,
  then push one coherent checkpoint. Do not retag older binaries as current.
- Only then request a cooled Pi/camera with healthy storage/power for deployment,
  physical angle-sign verification and operator acceptance. No hardware changed.
