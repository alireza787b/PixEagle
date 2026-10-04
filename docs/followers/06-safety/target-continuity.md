# Target Continuity

`TargetContinuitySupervisor` is the single command-authority owner between
target evidence and `OffboardCommander`:

~~~text
TrackerOutput -> TargetEvidenceSnapshot -> follower nominal CommandIntent
              -> TargetContinuitySupervisor -> OffboardCommander -> PX4
~~~

Trackers may keep predictions and last-known geometry for display and
reacquisition. Those estimates do not independently authorize vehicle commands.
Followers calculate nominal commands only from confirmed evidence; they do not
implement their own loss timers, hover/orbit actions, or inactive-output paths.
They also do not reclassify confidence or image-plane velocity. Tracker evidence
qualification is the single authority for those measurements; followers retain
only finite/profile-specific coordinate and command validation.

## Authority States

| State | Meaning |
|---|---|
| `INACTIVE` | No follow-session authority has been established |
| `ACTIVE` | Confirmed identity and fresh evidence authorize the nominal intent |
| `COASTING` | A qualified bounded-decay intent is authorized |
| `REACQUIRING` | Identity is confirmed again while authority is restored |
| `HANDOFF_PENDING` | Command authority is surrendered and PX4 handoff confirmation is pending |

Identity ambiguity, operator abort, stale vehicle state, unhealthy publication,
an unconfirmed Offboard state, or exhausted loss budgets request an immediate
handoff. Live body-velocity decay also requires a finite, fresh aircraft heading
at loss entry and during the loss; an unknown heading cannot be treated as zero.
Brief recover/loss flapping and repeated taps cannot reset the original episode
budget. An operator-requested retarget preserves bounded horizontal motion while
the replacement is selected. Fresh camera angles from the new selection may
contribute provisional guidance at half nominal authority, blended 70% toward
the new direction. The half-authority cap applies to new, unconfirmed guidance;
retained previously authorized motion decays toward it through the submitted-command
slew limiter. It requires 0.5 seconds of stable confirmation,
then ramps from the last provisional command to full guidance over another
0.5 seconds. During ordinary loss, yaw and vertical
velocity are zero; horizontal motion decays. Stale angles, a manual camera
takeover, Stop, or failed flight prerequisites cannot authorize provisional
commands. The flight-loop watchdog advances the original budget and refreshes
bounded intents if capture or inference stalls. Retargeting does not switch the
tracker implementation or follower.

## Default And Qualification Boundary

The global default is `immediate_handoff`. Fresh configurations give both
`gm_velocity_chase` and `gm_velocity_vector` sparse `bounded_decay` overrides.
Other followers retain their global policy. Immediate handoff stops PixEagle
command publication and requests the configured terminal action, currently `hold`.

`bounded_decay` is implemented for multicopter
`velocity_body_offboard` commands. It decays the last confirmed
horizontal intent under independent elapsed-time and integrated-distance
budgets, then requires stable identity confirmation before restoring authority.
SIH and physical response remain qualification gates. Attitude-rate,
fixed-wing, and VTOL-transition combinations fail closed to handoff.

Both fresh gimbal profiles use 8 seconds and 4 m of commanded horizontal
travel for loss and retarget. Explicit existing configurations are preserved:
without `FollowerOverrides`, their saved global policy still applies. Adopt the
new values through Config Sync preview/apply while following is inactive.
Unit tests establish the decision boundary; SIH, HIL, field,
and real-aircraft claims require separately recorded PX4 response evidence.

## Configuration

~~~yaml
TargetContinuity:
  MODE: immediate_handoff        # immediate_handoff | bounded_decay
  MAX_COAST_TIME_S: 1.0          # hard time budget; increase only for a qualified profile
  MAX_COAST_DISTANCE_M: 2.0      # integrated commanded travel budget
  MAX_RETARGET_TIME_S: 3.0       # replacement-target deadline; camera SIH uses 8.0
  REACQUIRE_CONFIRMATION_S: 0.5  # continuous confirmed evidence required
  AUTHORITY_RESTORE_TIME_S: 1.0  # bounded restoration ramp
  RETARGET_ANGLE_BLEND_FRACTION: 0.7
  RETARGET_PROVISIONAL_AUTHORITY_FRACTION: 0.5
  RETARGET_RESTORE_TIME_S: 0.5
  TERMINAL_ACTION: hold
  FollowerOverrides:
    GM_VELOCITY_CHASE:
      MODE: bounded_decay
      MAX_COAST_TIME_S: 8.0
      MAX_COAST_DISTANCE_M: 4.0
      MAX_RETARGET_TIME_S: 8.0
      AUTHORITY_RESTORE_TIME_S: 0.5
    GM_VELOCITY_VECTOR:
      MODE: bounded_decay
      MAX_COAST_TIME_S: 8.0
      MAX_COAST_DISTANCE_M: 4.0
      MAX_RETARGET_TIME_S: 8.0
      AUTHORITY_RESTORE_TIME_S: 0.5
~~~

Sparse overrides use canonical uppercase follower names and inherit omitted
global fields. Every supplied policy is validated before publication. The
effective policy is frozen when a follow session starts; changing configuration
requires an inactive follower. Strategy selection is
resolved from the follower profile's `airframe_phase` and
`control_type`, not from follower names.

## Operator Evidence

`GET /api/v1/following/telemetry` exposes the process-local
`continuity` snapshot, including authority state, reason, episode budget,
and handoff result. This is PixEagle decision evidence. Confirm PX4 mode and
vehicle response through independent telemetry before making an operational
claim.

Camera retarget admission validates the adapter's image region before any
ownership or target-generation change. Rejected edge taps preserve the old
target and following. Provisional angles retain their provider measurement
timestamp and sequence: video processing cannot make an old angle sample new.
Post-selection evidence must come from the current camera session. Firmware
without target identifiers cannot independently prove which target produced a
measurement; this remains a physical acceptance boundary.

Guidance filters use monotonic, rate-normalized timing. Raw geometry is validated
before filtering a body-FRD line of sight. Final command slew uses the existing
follower acceleration and yaw limits against the last accepted submission;
the integrated recovery distance uses those submitted commands. Stop, altitude
restrictions and authority loss bypass smoothing. These limits measure command
intent, not actual aircraft travel or physical stopping distance.

Use command preview first:

~~~bash
make demo
~~~

The circuit breaker remains a separate final PX4 dispatch inhibit. It does not
grant continuity authority or qualify a strategy.

## Extension Rules

New followers must declare `airframe_phase` and `control_type` in
`configs/follower_commands.yaml`. A new continuity strategy belongs in
the shared capability registry and requires state-machine, controller-boundary,
schema, command-preview, and appropriate SITL/HIL evidence. Do not add
follower-name checks or follower-local loss handlers.
