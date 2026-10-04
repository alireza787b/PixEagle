# Camera-free follower boundary repair

Continuation of QGC slice 4b.4/4b.4d after the expanded normal-follower matrix.
The camera is unavailable. No physical aircraft/camera commands, deployment,
system installation or source publication are part of this checkpoint.

## Defaults

The fresh baseline is recorded test4 video, CSRT running on PixEagle, disabled
camera provider/control, the yaw-only `mc_velocity_position` follower, altitude
safety enabled and flight-command circuit breaker active. The audit found the
provider enabled; `GimbalTracker.ENABLED` is now false in defaults and generated
schema. The meaningful workflow test proves the provider factory is never called.
Explicit saved camera profiles remain opt-in and are not overwritten. Config
Sync preview/apply remains the way to adopt defaults.

Altitude safety and altitude guidance are distinct: safety remains active while
ordinary default guidance does not request climb/descent. All PID gains, rate
limits, speed limits and numeric angle-limit defaults remain unchanged. Schema
admits MC pitch limits 1–89° and roll 1–90°, excluding zero envelopes and the
pitch singularity. Default pitch/roll remain 35°.

## Measured-attitude guard

The existing MC pitch/roll settings were loaded but not enforced. New shared
body-rate/Euler lookahead scales the complete angular-rate vector, preserving
thrust, rate signs and existing hard rate limits. It runs after follower EMA and
again at actual publication independently of video. Actual publisher cadence,
deadline and intent lifetime plus attitude age/telemetry cadence determine the
lookahead. Effective published fields are traced.

Missing, stale, invalid or out-of-envelope attitude is a hard refusal. The
publisher begins stopping its owned MAVSDK sender and invokes handoff on the
first rejection, without waiting for three transport failures. Concurrent Stop
callers join the owned operation; a slow Stop RPC must not delay failure
notification. A later follow session must not inherit the old rejection reason.

MAVSDK uses actual attitude-stream receipt, not completion of other streams.
MAVLink2REST captures immutable per-fetch `ATTITUDE.time_boot_ms` progress;
the first cached sample is unqualified, duplicates/backward samples cannot
manufacture freshness, and connection/source changes retire prior evidence.
Existing attitude-fetch return shape is preserved. The mathematical guard is
software lookahead, not a physical inertia/braking guarantee or flight approval.

## Fixed-wing and sensorless systems

Ground speed and configured cruise speed no longer masquerade as airspeed.
Fixed-wing startup/runtime requires explicit source, owner, generation and
monotonic freshness. Missing/stale/underspeed conditions use the existing hard
handoff path, independently of target-loss continuity. No unqualified automatic
nose-down/full-throttle recovery is introduced. Explicit local Command Preview
keeps synthetic observations; it cannot satisfy aircraft startup.

This is not a requirement to install a physical sensor on every fixed-wing
aircraft. Sensorless operation needs an explicitly qualified estimate or a
separate guidance policy with known assumptions, uncertainty, wind/observability
limits and airframe-specific tests. Typed measured/synthetic acquisition remains pending; the existing live
fixed-wing qualification restriction is preserved. The operator subsequently
requested one simple opt-in ground-speed fallback in canonical configuration.
`FW_ATTITUDE_RATE.ALLOW_GROUND_SPEED_FALLBACK` is now false by default and
appears only in the Dashboard's fixed-wing configuration. Available valid
airspeed takes precedence, including low airspeed that must still refuse.
Fallback requires finite fresh ground velocity from the current owner; original
SDK stream or REST source-progress receipt is captured with the snapshot value.
Fresh polling cannot rejuvenate cached velocity. Runtime status distinguishes
`guidance_speed`/source/fallback from measured `current_airspeed`, which remains
unavailable under the proxy. Existing speed/guidance limits still apply; this
option does not claim aerodynamic stall detection or unlock the native live gate.
No QGC setting, new route or telemetry owner was added.

The earlier airplane startup failure was independently resolved as a simulator
fixture mismatch: pinned airframe `SIH_T_MAX=6` did not configure the fixed-wing
dynamics' `SIH_F_T_MAX=2`. Changing only simulator `SIH_F_T_MAX` to 6 N reached
50.15 m in 22.61 seconds. Circuit breaker remained active; no Offboard/follower
commands were sent. This is launch-fixture evidence, not fixed-wing following or
sensorless safety qualification.

## Verification and remaining gates

Combined frozen-source backend gates: **3,358 Unit passed, 41 optional skips**;
**195 Integration passed**. Default/workflow/profile: 51 passed; fixed-wing
focused/API/config: 375 passed; MC repair/Phase 0: 254 passed; REST manager:
57 passed; QGC focused client/stock-UI/package identity: nine passed. Schema and
scoped fatal lint pass. Dashboard sources were unchanged; its earlier 489-test
pass remains separately recorded. A subsequent two-line MC-specific failure
condition and cross-profile test passed the focused gate; full-suite and SIH
snapshot hashes remain distinct. The earlier failed and pre-final attempts are
retained rather than replaced.

Final short guarded MC SIH: 48 successful publications, zero failures; actual
absolute pitch 31.736°, roll 15.089°; independent response and Stop passed.
Prolonged 3-second reversal: 107 successful publications, zero transport
failures; pitch 35.171° exceeded the 35° envelope, then immediate safety handoff
confirmed Hold. **Sustained MC attitude-rate use remains a release blocker.**
Software lookahead improved the original 43.046° excursion, but cannot establish
physical braking/inertia safety. No gain/tolerance change hides that finding.

Unchanged Vector/Vertical SIH regression: 550 successful publications, zero
failures. Other unchanged gimbal cases retain their four-case 2,210-publication
record. Final software link gate: 64 passes; blocked capture/inference HTTP Stop
receipt-to-dispatch 0.74/0.72 ms, lease expiry 357.4 ms; independent 20 Hz heartbeat
maximum gaps 50.23/50.21 ms. Scheduled delays/drops are not physical-link or Pi-load
qualification. Parameterized FW startup harness: 14 mocked boundary tests pass;
actual startup-only evidence retains its separate exact probe source.

Fresh defaults are covered by a test that confirms recorded media exists and
no provider is instantiated. Existing installations are not silently reset.

The rebuilt QGC full standard-label run passed 413/414; unchanged GPS settings
UI missed its 1 s visibility deadline by about 100 ms under parallel load, and the
isolated unchanged retry passed. Both logs are retained. Debug and Release
builds pass. The actual Linux DEB dependency check needs the missing host xcb
cursor library; Windows/Android artifacts remain unbuilt.

Evidence root: `~/.cache/pixeagle-qgc-baseline/slice-4b4-2026-10-02/`;
startup probe: `slice-4b4-2026-10-01/fw-startup-only-thrust6-v1/`.
Fresh camera retest, shared bitrate/full QGC transport, Pi sustained load,
physical motor stopping, platform releases, reviewed PRs and onboard ground
acceptance remain open. No camera action is required until its operator retest.

## Operator-requested configuration checkbox

Focused backend/config/Phase 0 gate passes 736 tests. Dashboard optional schema
labels are rendered by its shared editor/details components rather than a
fixed-wing-specific screen; its checkbox persistence test verifies the canonical
key, not the display text. Full Dashboard gate passes 490 tests/64 suites, build
and lint. Final combined gates now pass **3,391 Unit** (41 optional dependency skips),
**195 Integration** and **64 link/load tests**. Source-stable link evidence:
`slice-4b4d-2026-10-02/link-ground-fallback-final/manifest.json`; blocked
capture/inference route-to-dispatch 0.77/0.64 ms, expiry 365.5 ms, independent 20 Hz
maximum gaps 50.34/50.26 ms. These are software dispatch measurements, not physical
motor/network guarantees. Original SIH snapshots remain exact; the later
receipt/metadata and UI/config changes are covered by focused/full tests rather
than relabelled SIH artifacts. Exact commands and logs remain in the cache.

A new blocked camera profile v15 snapshots the updated source/config. Preparing
it starts no services and sends no commands; physical camera retest is pending.
