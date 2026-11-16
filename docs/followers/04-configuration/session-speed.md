# Requested speed during following

Supported active followers advertise a **Requested speed** control to Dashboard
and the custom QGC follower panel. The backend declares its meaning through
`speed_basis`: `translation_3d` for the existing MC velocity adjustment, or
`equivalent_airspeed` for a native FW reference. Unsupported followers expose no
control; clients must not infer support from the follower name. MC Velocity Chase
and GM Velocity Vector share the MC control without sharing a pursuit law.

For the MC control, use **− / +** to request a slower or faster **total 3D
velocity ceiling**, in 0.5 m/s steps. The speedometer and numeric readout sit next to
follower status in QGC, and below Stop in Dashboard's Command card. The same control is available
near the top of **Follower**, above the saved profile selector and diagnostics,
with an independent Stop button. Idle and unsupported followers have no speed
adjustment. Tap the value to open an inline
numeric editor, enter an exact speed and press **Apply**. **Cancel** discards the
entry. Stop remains reachable while editing. An open editor cannot apply to a
newer speed revision or a replacement session; close and reopen it after a
conflict. No saved configuration field is added to QGC.

The collapsed row uses icons and the value instead of a truncated text label.
Explanations appear with the editor. This value is a request, not measured
aircraft speed: turns, acceleration, continuity and safety limits can reduce the
effective submitted command. A request of zero ramps translation down; tracking
and permitted yaw guidance continue. Use **Stop Following** to end the session.

**Factory behavior keeps saved limits.** Adjustments reduce the requested speed
and increase it again within the advertised ceiling. Experts can enable
`Safety.ALLOW_SESSION_VELOCITY_OVERRIDE`; only then does an adjustment activate
a temporary velocity override. The requested 3D ceiling
replaces PixEagle's saved total, forward, lateral and vertical velocity caps for
this session. Each follower retains its existing guidance law; coordinated-turn
guidance still turns instead of commanding sideways flight. There is no additional
PixEagle UI speed ceiling in that expert policy. Existing firmware limits remain independent.
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

A brief failed status read retains the acknowledged row with editing disabled.
Stop stays available during a pending speed change or missing schema/telemetry.
An ended or replacement session closes the old numeric editor; navigating
between pages never replays an earlier adjustment.

## Configuration

| Setting | Meaning |
| --- | --- |
| `Safety.ALLOW_SESSION_VELOCITY_OVERRIDE` | Advanced MC permission: factory `false` retains saved caps; explicit `true` permits the existing session override and Restore. It adds no controller or second resolver. |
| `GM_VELOCITY_VECTOR.REQUESTED_SPEED` | Optional saved request at session start. Default `null` or an omitted key preserves the existing ceiling-based startup behavior. Clear the advanced Dashboard field to restore `null`. |
| `GM_VELOCITY_VECTOR.INITIAL_VELOCITY` | Initial condition of the existing speed ramp; not a second cruise setting. |
| `GM_VELOCITY_VECTOR.RAMP_ACCELERATION` | Existing acceleration/deceleration ramp and final command slew limit; the session control does not change it. |
| `MC_VELOCITY_CHASE.INITIAL_FORWARD_VELOCITY` / `FORWARD_RAMP_RATE` | Existing forward-ramp initial state and acceleration. The same acceleration bounds changes of submitted translation magnitude after adjustment. No new saved startup request is introduced. |
| `Safety.GlobalLimits` and the selected follower's `Safety.FollowerOverrides` | Saved limits used before adjustment and after restore. Vector starts at the smaller forward/total ceiling; Chase reports the total ceiling while retaining its saved forward target. The owned velocity override replaces velocity limits only. |
| `Follower.General.ENABLE_ALTITUDE_CONTROL` and follower override | Enable the profile's existing vertical guidance. The speed control does not enable it. |

The public demo keeps its 0.5 m/s forward ceiling, 1 m/s overall ceiling, video
file/CSRT, constant-position follower and enabled safety/circuit-breaker defaults.
Saved startup requests remain within the configured envelope. With expert permission, only an explicit
session adjustment activates the velocity override; startup and reconnect do not
activate or replay one. Increasing the request does not edit the saved ceiling.
An existing saved startup request outside its configured envelope is rejected.

MC Chase initially reports the saved total translation ceiling (factory: 1 m/s),
while retaining its separate saved forward target (factory: 0.5 m/s), component
limits and existing image-error PID/yaw behaviour. Only an explicit speed action with expert permission
activates the shared override. After that action, the forward ramp is bounded by
the request and lateral/vertical guidance shares the total translation ceiling.
Zero ramps all translation down; it is not just a forward-speed zero and does
not promise geographic position Hold. Restore reapplies the saved limits without
raising a lower request. Stop/new Start restores the configured startup state.
No image coordinate is converted into a fabricated physical 3D ray.

The shared speed limiter receives each follower's own timing explicitly:
Chase uses `RAMP_UPDATE_RATE`; Vector uses `CONTROL_UPDATE_RATE`. Neither
follower depends on timing attributes supplied by the other implementation.

Altitude is the backend's **relative altitude**, referenced to the estimator/home
reference. It is not terrain clearance. Existing minimum/maximum altitude and
warning-band rules apply after smoothing and continuity blending. Blocking a
vertical component does not redirect that speed horizontally. Stale altitude or
invalid geometry follows the existing fail-closed path.

There is no distance hold, target-speed estimator or automatic overtaking
detection in this control. Screen position alone does not establish target range.

## Requested, submitted and observed speed

A native FW row requests **equivalent airspeed**, not total 3D ground velocity.
Its positive minimum and feasible envelope remain aircraft-owned. An acknowledged
request can be below a changing load-dependent minimum; it remains distinct from
PX4's effective reference and the aircraft's actual speed. Zero is not a FW stop
request. Use Stop to end following and request the existing native handoff.

`effective_command_magnitude` is the **submitted command**, not a measurement or
a report of PX4's internally slewed reference. The API does not currently expose
that native effective reference. Optional `observed_speed_m_s` uses the row's
`speed_basis`: a full fresh NED velocity norm for MC, or PX4's selected qualified
EAS observation for FW. A valid low EAS remains visible below the native minimum;
it is not replaced by a requested speed, trim reference or groundspeed.

Observations must match the active session's aircraft, connection, phase and,
when present, guidance generation. The existing connection-owned snapshot retains
its original measurement age; status reads cannot refresh it. Legacy MC scalar
telemetry cannot establish a full NED vector, so its observation remains absent.
For a qualified MC vector, `observed_speed_source: null` means no airspeed-source
label applies; `speed_basis: translation_3d` defines its meaning.

FW source labels are `sensor` or the qualified `ground_minus_wind` estimate.
Missing, invalid, stale or misbound airspeed leaves the observation unknown.
`native_airspeedless` additionally requires fresh matching native feedback proving
that the FW controller is active with airspeed control disabled; unavailable
EAS alone cannot establish that mode. It still reports no measured EAS or stall
margin. These fields add no observer, polling loop, controller or flight authority.
The stock MAVLink path reports `ground_speed_proxy` when fresh navigation
velocity is the available fallback. This is not measured airspeed or proof of
stall margin. See the [stock integration guide](../07-integration/stock-px4-gimbal-vtol.md)
for current qualification scope.

Missing legacy permission retains the previous override behavior until Config
Sync preview/apply accepts the new factory choice. It stays absent in saved
configuration; validation does not silently rewrite command authority.

## Client and extension contract

`GET /api/v1/integration/following` adds optional `session_controls` and
`follow_connection_generation`. Each control reports ID, label, unit, minimum,
maximum, step, acknowledged value, revision, availability, increase permission,
effective submitted-command magnitude and limiting reason. Missing controls mean
unsupported; clients must not infer support from a follower name.
Optional `description` explains the declared guidance meaning: Chase's total
translation ceiling, Vector's requested translation magnitude, or the native FW
airspeed reference. It is display metadata, not a new speed basis or policy.
Older rows can omit it; clients can show it in the existing expanded explanation.
`maximum: null` means no configured adjustment ceiling. `configured_maximum`
describes the saved startup ceiling; `override_active` and `reset_supported`
advertise the restore affordance. Clients show acknowledged values only.
Clients request `control_contract_version=2` for phase-bound controls and submit
the advertised `guidance_generation` with each mutation. Version 1 hides EAS and
all generation-bound rows, including MC; ordinary legacy MC rows without a
generation remain available. The mutation guard is unchanged.

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

A normal-camera chase follower can reuse the action, session ownership, limit
resolver and interfaces, but needs an explicit guidance adapter and qualification
before advertising it.
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
