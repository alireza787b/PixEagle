# Stock MAVLink session ownership — 16 November 2026

## Scope

Software only. The Pi, aircraft firmware/parameters, public factory configuration,
private saved profile and QGC source are unchanged in this slice. No hardware
qualification or full application admission is claimed.

## Implemented

- Standard observations reuse the existing aggregate poll and identity owner.
  Pose, local position, source epoch and mode are read together. Cached or
  rewritten packets cannot renew receipt freshness. No camera exposure time,
  estimator sample/reset counter or rescue proof is manufactured.
- Read-only aircraft parameters supply one connection-bound envelope and tuning
  snapshot. Start hashes use mode/phase/reference generations, not every pose
  packet. Ordinary polling must not recreate verification flicker.
- The canonical geometry supports explicitly degraded `latest_received_bearing`
  association: original receipts, unknown skew, no invented exposure/reset times.
  Cached bearings retain their original world ray; timed adapters stay strict.
- MC/FW strategies share the phase session, speed controls, geometry and altitude
  guard. The common phase base no longer depends on native transport types.
- The stock projection preserves the same session request through command
  construction. Reductions also constrain retained recovery intent. Restore
  returns to the normal speed/pitch/sink envelope without accelerating a lower
  request. A subsequent explicit adjustment reactivates only the configured
  expert policy. End revokes controls and the retained projection binding.
- `MavlinkCommandTransport` implements the existing commander transport contract
  with one-shot MavlinkDirect packets. It creates no background heartbeat or
  resend service. Priming is neutral and altitude-reference-bound. Acquisition
  requires a fresh post-request Offboard observation; queued RPC success alone
  grants no command authority.
- Stop revokes publication before joining any pending send. Its single Hold is
  suppressed after observed takeover, transition or disarm; unknown/replaced
  authority sends no mode request. A failed confirmation is not retried later.
  Standard MAVLink has no atomic aircraft-side compare/release receipt.
- The stock binding uses the existing FW continuity strategy in `PX4` mode.
  Unit loss/retarget checks retain the original eight-second deadline. A transition
  still observed in Offboard reports only sender quiescence, never an invented
  aircraft release. An active SDK resend owner blocks overlapping acquisition.

## Retained stock SIH evidence

Firmware `99a3048735caa5a2c277d6aa8e17a12a6133db5d`, unmodified; no parameter
writes. Paths are beneath `reports/sitl/stock-px4-qualification-20261116/`.
Each manifest retains exact staged source/configuration checksums; these are
implementation runs, not pristine release artifacts.

| Run | Result | Boundary |
| --- | --- | --- |
| `fw-direct-publication-outage-r1` | PX4 Return 1.476 s after publication stops; configured loss timeout 1 s; SDK autoresend inactive | Sender failure component; native failsafe is not overwritten by Hold |
| `fw-stock-session-steep-r3` | Range 132.54 → 63.95 m; speed adjustment, steep descent, Hold confirmed | Shared controls/phase with direct packets |
| `fw-stock-session-restore-r2` | Range 133.07 → 45.29 m; adjustment/Restore; post-Stop minimum speed 14.25 m/s | Shared controls/phase with direct packets |
| `fw-command-owner-restore-r1` | 396 successful commander submissions, zero failures; range 133.71 → 43.56 m; observed speed 13.51–21.24 m/s; post-Stop minimum 14.37 m/s; Hold confirmed | Production one-shot owner and commander, shared session |

Failed session r1/r2 retain the original observation-clock and startup-race
evidence. The fix preserves the phase owner's original receipt clock and primes
until the shared observed mode confirms acquisition. Restore r1 retains a worker
CLI-fixture failure; r2 forwards the explicit fixture flag correctly.

## Verification and remaining work

Full unit regression: 7,722 passed, 11 optional GI skips, 14 subtests. API/
integration/inventory/docs: 357 passed. Focused source/packet/session: 156;
runner/commander/owner: 54; association: 216; connection: 206; binding/continuity:
35. These overlap and are not additive. Schema and fatal Python lint pass.
The initial full run retained one description mismatch, corrected to “airspeed
reference” without falsely promising TECS. Cloud CI at `12c2559ab` passed; it
does not qualify these later changes.

Next: integrate the source and stock binding into application Start/Stop/readiness;
qualify actual MC/FW/VTOL, retarget/loss,
source degradation, process failure and client controls. Then renew client gates
and request hardware. No final tag, deployment or flight-readiness claim yet.

Before application qualification, request/measure required attitude, local-position
and phase traffic. The public aggregate poll defaults to 0.5 s; a faster guidance
loop does not create newer attitude measurements. Retain one poller and the
existing telemetry-rate configuration. Also review public speed-override admission:
saved conservative caps must not silently grant an unrestricted beginner session.
Keep expert permission in one canonical policy rather than a competing limiter.

## Latest accepted configuration requirements (pending final review)

The owner's latest values supersede the earlier 30 m public/3 m private floors
and zero private startup request. Apply only after the integration checkpoint;
retain original historical run configurations and installed values until then.

| Setting | Public factory | Private owner test overlay, outside the repository |
| --- | --- | --- |
| Default follower | MC Position; translation/engagement altitude hold, yaw centering | Gimbal Vector; stock PX4 tailsitter, fresh phase selected automatically |
| Target altitude guidance | Off | On |
| Relative altitude envelope | 5–100 m, safety enabled | Minimum 5 m; no application upper ceiling |
| MC startup request | Existing conservative supported-mode defaults | 6 m/s, adjustable during the session |
| FW upper-speed/dive policy | Normal configured envelope | Explicit experimental no-upper-speed/steep-dive policy |
| FW minimum | Aircraft operating minimum; never raw stall speed | Same minimum/authority precedence |
| Transition | End following, require new explicit Start after settling | Same |

Speed controls remain capability-driven in both clients; Position need not expose
an unsupported cruise control. Missing airspeed may degrade to an explicitly
reported speed proxy, but cannot prove stall margin. Invalid control authority or
unusable aircraft state cannot be overridden by a fallback. A relative-altitude
floor is estimator/home-referenced, not terrain clearance or pull-out assurance.
