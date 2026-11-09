# Creating a follower

Start from an existing follower with the same input and command contract.
Describe what it controls and what it does not estimate. Image centering does
not establish range; a provider bearing is not a measured pixel.

1. Declare the stable ID in `configs/follower_commands.yaml` (schema 2.3.0):
   `family`, `visibility`, `config_section`, label/purpose, aircraft phase,
   control type, every required command field, and required tracker schemas.
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

## Verification

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
