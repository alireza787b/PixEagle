# Requested speed during following

GM Velocity Vector exposes a **Requested speed** control in Dashboard and the
custom QGC follower panel while following is active. Other followers expose no
speed adjustment unless their profile and implementation explicitly support it.

Use **− / +** to request a slower or faster **total 3D velocity**, in 0.5 m/s
steps. The speedometer and numeric readout sit next to follower status in QGC,
and below Stop in Dashboard's Command card. Tap the value to open an inline
numeric editor, enter an exact speed and press **Apply**. **Cancel** discards the
entry. Stop remains reachable while editing. An open editor cannot apply to a
newer speed revision or a replacement session; close and reopen it after a
conflict. No saved configuration field is added to QGC.

The collapsed row uses icons and the value instead of a truncated text label.
Explanations appear with the editor. This value is a request, not measured
aircraft speed: turns, acceleration, continuity and safety limits can reduce the
effective submitted command. A request of zero ramps translation down; tracking
and permitted yaw guidance continue. Use **Stop Following** to end the session.

**An adjustment activates a temporary velocity override.** The requested 3D speed
replaces PixEagle's saved total, forward, lateral and vertical velocity caps for
this session. The target direction determines the components; coordinated-turn
guidance still turns instead of commanding sideways flight. There is no additional
PixEagle UI speed ceiling. Existing aircraft firmware limits remain independent.
Altitude protection, acceleration, yaw/rate limits, validity checks and the
circuit breaker are unchanged. No target-distance or new pursuit law is added.

The highlighted **restore** icon means the velocity override is active. Press it
to restore the saved velocity limits. It keeps the requested speed or lowers it
to the saved ceiling; it never increases it. Restoring restrictive limits can
immediately restrict components. Ending the follow session also removes the
override. No saved safety setting is rewritten.

Changes apply to the current follow session only. They survive retargeting and
client reconnection, and are shared between Dashboard and QGC. They do not edit
configuration or aircraft parameters. Stopping, replacing the follower or
restarting the backend ends the override. Stale clients refresh before another
adjustment; reconnecting never resends an earlier button press.

During target recovery, reductions remain available and increases wait for
confirmed guidance. Adjustments do not renew the recovery time/travel budget.

## Configuration

| Setting | Meaning |
| --- | --- |
| `GM_VELOCITY_VECTOR.REQUESTED_SPEED` | Optional saved request at session start. Default `null` or an omitted key preserves the existing ceiling-based startup behavior. Clear the advanced Dashboard field to restore `null`. |
| `GM_VELOCITY_VECTOR.INITIAL_VELOCITY` | Initial condition of the existing speed ramp; not a second cruise setting. |
| `GM_VELOCITY_VECTOR.RAMP_ACCELERATION` | Existing acceleration/deceleration ramp and final command slew limit; the session control does not change it. |
| `Safety.GlobalLimits` and `Safety.FollowerOverrides.GM_VELOCITY_VECTOR` | Saved limits used before adjustment and after restore. The startup ceiling is the smaller of the effective forward and total-magnitude limits. The owned velocity override replaces velocity limits only. |
| `Follower.General.ENABLE_ALTITUDE_CONTROL` and follower override | Enable existing angle-guided climb/descent. The speed control does not enable it. |

The public demo keeps its 0.5 m/s forward ceiling, 1 m/s overall ceiling, video
file/CSRT, constant-position follower and enabled safety/circuit-breaker defaults.
Saved startup requests remain within the configured envelope. Only an explicit
session adjustment activates the velocity override; startup and reconnect do not
activate or replay one. Increasing the request does not edit the saved ceiling.
An existing saved startup request outside its configured envelope is rejected.

Altitude is the backend's **relative altitude**, referenced to the estimator/home
reference. It is not terrain clearance. Existing minimum/maximum altitude and
warning-band rules apply after smoothing and continuity blending. Blocking a
vertical component does not redirect that speed horizontally. Stale altitude or
invalid geometry follows the existing fail-closed path.

There is no distance hold, target-speed estimator or automatic overtaking
detection in this control. Screen position alone does not establish target range.

## Client and extension contract

`GET /api/v1/integration/following` adds optional `session_controls` and
`follow_connection_generation`. Each control reports ID, label, unit, minimum,
maximum, step, acknowledged value, revision, availability, increase permission,
effective submitted-command magnitude and limiting reason. Missing controls mean
unsupported; clients must not infer support from a follower name.
`maximum: null` means no configured adjustment ceiling. `configured_maximum`
describes the saved startup ceiling; `override_active` and `reset_supported`
advertise the restore affordance. Clients show acknowledged values only.

`POST /api/v1/actions/following-control` accepts the ordinary action envelope
plus `instance_id`, `runtime_id`, `follow_session_id`, `aircraft_uid`,
`connection_generation`, `control_id`, absolute `value` and `expected_revision`.
There is no frame token. Session callers use CSRF and `actions:execute`,
`status:read`, `telemetry:read` permissions. Mutations require confirmation and
idempotency; dry runs validate without mutation. Conflicts require an authoritative
refresh and a fresh operator action. An idempotent replay describes the original
action and never applies it to a replacement session.
`value: null` restores configured velocity limits through the same action,
identity, revision and idempotency contract. It is not Follow Stop.

To add a compatible follower, declare `session_controls` in its existing command
profile and implement `create_session_controls()` plus the existing command
limiting hook. Return typed `SessionControl` values with explicit startup and
restore semantics resolved through SafetyManager.
The shared base class owns value validation and revisions. An explicit velocity
implementation binds its session-owned envelope through SafetyManager; the
existing SetpointHandler and final PX4 boundary resolve it there too. The manager
holds a weak owner/provider, not a second speed value. Old cleanup cannot clear a
replacement owner's binding. Reset, teardown and emergency stop release the
binding; collected owners cannot leave an active override. The flight owner
applies the requested-speed ramp after continuity blending, so reducing speed
cannot restore an older retained command or reset recovery budgets. No new client
follower-name list or separate saved-control store is needed. Add direction,
lifecycle, continuity, reset and publication regressions before advertising
support. Non-gimbal followers may opt in with a tested vector-scaling
implementation; their existing independent-axis laws are not silently changed.

### Ordinary camera followers

Only GM Velocity Vector supports this control today. A normal-camera chase
follower can reuse the action, session ownership, limit resolver and interfaces,
but needs an explicit guidance adapter and qualification before advertising it.
Its image controller first derives the desired motion from image error and any
other existing observations. The requested speed can then set that motion's
magnitude while preserving its direction and existing acceleration/altitude
behavior. An image bounding box alone supplies neither metric range nor a
measured three-dimensional line of sight.

Independent-axis followers need an explicit decision about which translation
components are scaled together; yaw remains a separate guidance output. A
position-hold follower deliberately has zero translation, and fixed-wing
airspeed/attitude control needs its own semantics. Neither should acquire a
generic 3D-speed control merely because it is called a chase follower. Increasing
the request does not add overtaking detection or automatically enable descent.

## Acceptance

Deterministic tests verify values, permissions, session/revision races, both
mounts, direction signs, zero, slew and altitude restrictions. The isolated SIH
driver's `--session-controls` option additionally records requested/submitted
speed and independent PX4 velocity. These checks do not establish camera tracking
performance or physical flight safety; bench and operator acceptance remain
separate checkpoints.
