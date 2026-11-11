# Creating a follower

Start from an existing follower with the same input and command contract.
Describe what it controls and what it does not estimate. Image centering does
not establish range; a provider bearing is not a measured pixel.

1. Declare the stable ID in `configs/follower_commands.yaml` (schema 2.5.0):
   `family`, `visibility`, `config_section`, label/purpose, aircraft phase,
   control type, every required command field, and required tracker schemas.
   Set `live_qualified_phases: []` until the profile's phase-specific gate passes;
   declaring native contracts never grants that permission.
   The [command schema](../04-configuration/schema-system.md) is authoritative.
2. Register its implementation in `FollowerFactory`. An unimplemented YAML
   declaration remains unavailable. Do not add another compatibility matrix.
   The shared catalog evaluates observation meaning, actual fields and live
   aircraft admission separately from profile selection.
3. Implement `BaseFollower` using that profile ID. Read algorithm settings from
   its declared configuration section; use FollowerConfigManager for shared
   behavior and SafetyManager for the resolved operational envelope. Do not
   derive settings from a class name or add a second maximum-speed setting.
4. Return a complete nominal `CommandIntent` through `set_command_fields()`.
   Return success only if that snapshot was accepted. Exceptions/invalid input
   must invalidate obsolete intent. Never publish MAVSDK/DDS commands from
   strategy calculations.
5. Implement `reset_target_state(reason)` when the strategy has controller history.
   Retarget preparation invalidates intent and calls this hook; the base hook
   is an explicit no-op for stateless implementations. A target transition
   preserves acknowledged session controls; ending the session clears them.
6. Only if needed, override `prepare_authorized_command(fields, loss_decay=...)`
   for post-continuity shaping and `on_command_submitted(fields)` for accepted
   submission history. Preserve session-limit resolution before shaping;
   rejected submissions cannot advance command history. Native FW keeps its
   own command contract and must not enter an MC velocity guard.
7. Add canonical defaults/schema documentation through Config Sync. Preserve
   sparse overrides and saved installations. Public target-altitude guidance
   stays off, with altitude safeguards and the circuit breaker on.

The AppController flight owner owns admission, continuity, final authorization,
publication and teardown. Do not add strategy-local loss timers, Hold/RTL
requests or reconnect action replay. Current VTOL admission stays unavailable
until the transition-preserving release gate passes; declaring native phases
does not grant it.

`VectorGuidanceSession` accepts preconstructed phase controls and an explicit
supported-phase set. Gimbal Vector supplies its existing MC declaration; a
FW-only strategy uses `AirframeSessionControls.for_fixed_wing`, which waits for
native measured EAS or trim without inventing an MC request or ceiling. An
unsupported phase ends the session and cannot revive it. Associated world rays
use `calculate_ned`; provider/body rays use the existing capability-checked path.
These are calculation/lifecycle boundaries, not camera timing or VTOL release
qualification.

## Calibrated image input boundary (S5/S6 preparation)

The `guidance_observation.py` and `image_bearing.py` contracts preserve
exact capture identity, source/target generations, geometry, dimensions and the
actual pixel. Unknown calibration or inverse mapping is `None`; bearing conversion
requires explicit matching calibration and mapping. Receipt time remains receipt
time; geometry alone does not establish exposure timing, attitude alignment or
flight authority. Classic/Smart output now carries a committed measured image
sample; reads reuse it without refreshing its timestamp. Repeated, predicted,
failed, cached or superseded frames cannot create a new measured sample.
Calibration/attitude alignment and live image-FW admission remain separate gates.

## Verification

The registered [FW Navigation Chase](../02-reference/fw-navigation-chase.md)
demonstrates the native image contract. Its ordinary factory constructor reads
only explicit `FW_NAVIGATION_CHASE` geometry plus shared operational/policy
settings. It remains experimental with no live-qualified phase; constructor
success, input selection compatibility and native command shape grant no
aircraft authority.

Use real constructors and actual defaults as well as focused math fixtures.
Cover complete fields/units, nonzero aim, both axis signs, finite output,
bounds, altitude off/on, configuration identity under class renaming, reset
ordering, rejected submissions and Stop/takeover races. Preview compatibility
does not imply permission to start live following.

Run the relevant tests with the repository interpreter, then use the
[SIH qualification workflow](sih-follower-qualification.md) for an independently
defined moving world target and actual PX4 pose. A dry-run or synthetic replay
is a contract check, not aircraft-response evidence. Preserve failed runs,
exact revisions/configuration, publication traces and handoff reasons.

Add one concise reference page linked from the
[visual guide](../02-reference/follower-visual-guide.md). Show the declared input,
command meaning and evidence status; reuse the existing read-only visualizer.
See the [consolidation checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-09-follower-consolidation.md)
for currently completed boundaries and remaining qualification.

## Image and attitude association

`observation_alignment.py` accepts explicit calibrated image and observed
attitude references; it never fetches the latest attitude or grants authority.
Physical capture is unqualified by default. Receive-time qualification requires
source-bound evidence for camera acquisition-to-receipt delay, total attitude
sample-to-publication-receipt delay, relative-clock uncertainty and allowed skew.
The attitude delay includes source processing and transport; DDS-adjusted source
timestamps are not host monotonic timestamps. The separate, default-disabled
SIH API pairs a simulated projection with the exact observed state used to
generate it. Only the trusted isolated fixture may opt in; this is not hardware
synchronization. Preserve the returned immutable progress record: exact duplicate
pairs reuse it, while rewritten/reordered captures, changed source/geometry/
calibration/target, aircraft/runtime or quaternion-reset bindings are rejected.
Changing timing kind, bounds or evidence also requires an explicit owner reset;
a new capture cannot silently upgrade SIH pairing to physical qualification.
Ending or rebinding an owner explicitly resets that record. CaptureStamp receipt
time remains unchanged, and neither path adds exposure timestamps or attitude
interpolation.
