# Tailsitter camera Home and configuration alignment

## Implementation

The camera owner reuses the provider's existing Home action after an observed,
fresh, settled PX4 tailsitter transition, including an abort back to the original
phase. It does not calculate a new mount rotation or command saved body angles.
Startup/reconnect only establishes the baseline. Manual input, Stop, tracking,
following, rescue, stale observations and expired requests suppress dispatch.

`GimbalTracker.HOME_AFTER_TRANSITION` is the sole policy setting. Public camera
providers and controls remain disabled. The Topotek adapter sends the same Home
packet as manual Center; `sent` means transmission, not confirmed leveling.
Other providers require a supported Home action. See the
[operator reference](../../../../trackers/02-reference/gimbal-tracker.md#camera-home-after-a-tailsitter-transition)
and [provider contract](../../../../trackers/05-development/external-gimbal-providers.md).

## Configuration migration

Schema 1.11 registers the undefined `Safety.ALLOW_SESSION_VELOCITY_OVERRIDE`
path for exact, operator-reviewed removal. Validation filters registered
retirements before semantic checks, preserving their stored values until a
confirmed Config Sync removal. Both public defaults and generated private
profiles use this same schema/registry generation. Private installation values
and files stay outside the repository; normal PX4 upper-speed policy replaces
an unavailable experimental policy in the command-blocked bench export.

## Verification and remaining boundary

Deterministic tests cover both transition directions, aborts, duplicate/stale
receipts, reconnect, manual/Stop priority, unavailable providers and Home packet
dispatch through the existing executor. Configuration tests cover the retirement
preview/apply boundary. Replay regressions distinguish submitted commands and
PX4-observed motion. Earlier saved-angle replay evidence is historical and does
not qualify this replacement Home policy.

Physical camera leveling after a real transition remains an operator checkpoint.
No camera or aircraft command was sent for this configuration audit. Software
validation and a complete YAML export do not qualify FW/VTOL admission or any
experimental flight envelope.
