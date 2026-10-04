# Native following for QGroundControl

Slice 4a adds a separate authenticated operator contract for aircraft following.
PixEagle remains the only follower, MAVSDK, Offboard and command-publication
owner. QGC supplies intent, an observed aircraft/target binding, a chosen
profile and an idempotency key. The existing dashboard Offboard and follower
routes retain their behavior; native requests use the routes below.

## Readiness and profile choice

`GET /api/v1/integration/following` requires a session or scoped bearer with
`status:read` and `telemetry:read`. It returns schema v1, `source` equal to
`native_following_status`, backend instance/runtime IDs, a profile generation,
the persisted `configured_mode`, effective `runtime_mode`, active
`current_mode`, compatible profile rows, target/aircraft guard, readiness codes,
active status, a session-bound Stop identity and any captured pending Start ID.
During active following, `continuity_authority_state` reports active,
coasting, reacquisition or handoff state. The separate
`continuity_target_transition_pending` flag identifies an operator retarget
using bounded transitional guidance; clients should not label it target loss.
The optional transition phase and effective command fields are diagnostic
snapshots, not proof of PX4 acceptance or aircraft response.
After a session ends, optional `last_handoff` retains its session ID, aircraft
UID, original reason, execution mode and confirmed/pending/failed/stopped result.
It clears at the next follow session or backend restart. Clients display it
only with fresh backend state and a matching aircraft association; a stopped
session must not imply that PX4 Hold was confirmed. Preview results remain
labelled as tests. QGC uses the same short continuity labels in its toolbar and
compact follower row.
A saved profile
can remain pending until the next guarded follower start. The `compatible` flag
means the registered implementation accepts the selected tracker output and is
live-qualified for its declared phase; it is not a flight qualification for an
arbitrary physical airframe.

Compatibility uses the selected tracker's canonical `data_type` from
`tracker_schemas.yaml` and the same follower compatibility matrix used by the
runtime follower. A camera tracker's derived image-position fields do not make
it an image-tracking implementation. Unknown output schemas fail closed. These
reads remain available without an aircraft so a companion-only client can show
the configured follower and readiness. Compatible profile selection is also
available in companion-only mode; it changes saved configuration but cannot
start aircraft following. Command-preview benches report
`command_preview_not_aircraft_following`. Active manual camera control adds
`camera_control_active`, and follower startup reserves the camera lifecycle
until it either establishes following or fails.

`POST /api/v1/actions/native-follower-select` requires `actions:execute` plus
the read and media scopes, CSRF for a browser session, `confirm: true`, and an
idempotency key. It accepts the current `native_context.guard`,
`binding_mode: vehicle` or `binding_mode: companion_only`,
`profile_generation` and a compatible `profile_mode`. Vehicle mode requires a
verified aircraft; companion mode is a configuration-only choice.
The backend refuses active following and persists the selection through the
existing configuration transaction under the follower lock. Its action result
reports saved versus applied state; QGC refreshes the read resource afterward.
Neither mode starts a follower when changing the profile.

## Start and Stop

`POST /api/v1/actions/native-follow-start` uses the same authenticated action
envelope and requires a verified vehicle binding, exact current target/source
guard, selected profile name/generation, tracker status `tracking`, PX4 execution
mode, fresh observed armed/in-air telemetry and the existing Offboard preflight.
The arm and landed observations must match the verified aircraft UID and
connection generation. Target selection remains available on the ground, but
Start reports `vehicle_not_armed`, `vehicle_not_airborne` or
`vehicle_flight_state_unavailable` until the aircraft is ready. It refuses
replay video, active or incompatible followers, circuit-breaker inhibition and
changed identities.
Each Start includes a random 32-hex `start_attempt_id`, which the backend
exposes while startup is pending so Stop can cancel that exact attempt.
The guard is checked before startup, before Offboard entry, after the Offboard
acknowledgement and before following becomes active on PixEagle's flight-owner
loop. These checks do not replace PX4 failsafes, target-continuity monitoring
or the existing OffboardCommander cleanup.

`POST /api/v1/actions/native-follow-stop` accepts the backend instance/runtime,
the observed follow-session ID or pending Start ID and captured aircraft UID.
It does **not**
require a fresh video frame, target revision or current QGC view. PixEagle
rechecks the session under its flight-owner lock. If its live command identity
or connection generation no longer matches the captured session, it stops local
publication without sending
an Offboard stop or final setpoint to another aircraft and reports that partial
outcome. A stale session receives a conflict; QGC must refresh status before
retrying. The Stop action is distinct from target Cancel and camera Stop.

All mutation responses are typed, actor-audited action resources. The client
must treat a timeout or lost response as an unknown outcome and read the current
status rather than blindly retrying with a new key. The existing dashboard can
change the target, source, profile or follow state concurrently; generations and
backend ownership determine which action wins. `GET /api/v1/integration/context`
advertises `following.operations.v1`; clients use the detailed following resource
for readiness and denial reasons. The general context read remains independent
of slow model or target operations.

## Evidence boundary

Recorded-video replay can qualify targeting and command preview only. It cannot
qualify aircraft following. Unit and mocked connection tests exercise guards,
profile filtering, Stop routing and API envelopes. The isolated pinned PX4 SIH
run recorded Offboard entry, sustained command publication, Stop, target-loss
cleanup, pending-Start cancellation and an armed/takeoff/follow/land cycle. Its
logs are identified in the paired slice-4a checkpoint. This is simulation
evidence; it does not imply HIL, physical camera acceptance or field-flight
safety. Gimbal-specific movement remains the next slice-4 gate.
