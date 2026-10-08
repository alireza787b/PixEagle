# Native target operations — QGC slice 3

The capability `target.operations.v1` adds displayed-frame guards to the existing
typed action routes. It does not connect an aircraft, change following, expose
gimbal movement, or introduce a second tracker implementation. The existing
dashboard and native clients operate on the same AppController target state.
Legacy requests without `native_context` retain their signatures and behavior.

## State and permissions

`GET /api/v1/integration/target-state` requires a browser session or scoped bearer
with `status:read` and `telemetry:read`; loopback compatibility is insufficient.
The response is `Cache-Control: no-store` and contains:

- `schema_version: 1`, `source: "native_target_state"`, `instance_id`, `runtime_id`.
- Decimal-string `target_revision`, `mode: classic | smart | external`,
  `tracker_type`, nullable `external_selection_mode: classic | smart`.
- `tracking_active`, `following_active`, and `target_status:
  idle | acquiring | tracking | lost | unavailable`. Tracking intent and
  observed acquisition remain distinct; camera command acceptance is not proof
  of target acquisition. After automatic Classic recovery timeout, `lost` persists
  with `tracking_active:false` and `target_lost_recovery_timeout` in `reason_codes`;
  explicit Cancel or a new target/mode/tracker session clears the terminal reason.
  Smart exhaustion also persists as `lost` with `tracking_active:false` and
  `target_lost_<reason>` until Cancel, a new accepted selection or mode/model
  transition. Predicted and tentative Smart observations remain `acquiring`,
  never fresh measured tracking. Smart's `occluded` reason means other detections
  remained while the selected target could not be matched; it is not proof of
  physical occlusion.
- `allowed_actions`, `reason_codes`, and `mode_availability`, whose `classic`,
  `smart`, and `external` entries contain `available` and nullable readable `reason`.
  In external mode, Classic/Smart availability describes camera selection modes,
  not the local AI runtime. Other modes use local Smart model readiness.
- An opaque `guard` to capture and echo with the interaction. It contains version,
  instance/runtime, target revision, mode/tracker, command and telemetry
  generations, nullable aircraft UID/system/component, and nullable stream ID,
  stream epoch and source epoch. Integer-like identities remain strings.

Native mutations require `actions:execute`, `status:read`, `telemetry:read`, and
`media:read`, plus existing browser CSRF rules. An operator account has these
scopes; a viewer cannot mutate targets. A real authenticated actor is recorded
in the action audit; client `source` is only an untrusted client label.

`binding_mode: "companion_only"` permits target operations without a QGC aircraft
binding when the backend advertises `target.unbound_tracking.v1`. This works
with recorded video, a local camera, or a camera on a companion that is already
connected to an aircraft. It never authorizes aircraft following. Older backends
without this capability require both backend aircraft connections to be
disconnected for companion-only target mutations. `binding_mode: "vehicle"` requires current
verified backend command/telemetry association matching the captured guard;
QGC also verifies its selected vehicle before submission. During active
following, only selecting a replacement target with the current tracker is
admitted. A qualified camera follower preserves bounded horizontal motion
during the replacement handshake; other paths retain their own fail-closed
transition policy. A failed camera selection ends following;
it never resumes the old target silently. Cancel, tracker/model/engine changes,
and camera mode changes remain blocked until following stops. Existing
authorized dashboard Stop/Abort retains its prior behavior.

Catalog rows in both `ui_trackers` and `tracker_types` resolve to one
`factory_key` and canonical `request_tracker_type`. Consumers merging the lists
must deduplicate on `factory_key`. Availability and a concise unavailable reason
are shared across aliases. Read-only checks cover active OpenCV APIs, optional
dlib, and verified model artifacts; they neither create trackers nor download
models. Availability indicates prerequisites, not hardware/performance
qualification. Runtime switching still validates and can fail if prerequisites
change after catalog observation.

## Exact displayed frame

The existing strict `provenance` v1 JSON and `geometry_verified: false` remain
unchanged. Each selectable WS JPEG additionally carries the adjacent sibling:

```json
{
  "selection_geometry": {
    "version": "1", "verified": true,
    "geometry_id": "opaque-geometry-epoch",
    "mapping": "full_frame_scale",
    "encoded_width": 640, "encoded_height": 480,
    "analysis_width": 1280, "analysis_height": 720,
    "target_revision": "3", "token": "opaque-retained-frame-token",
    "max_age_ms": 1500
  }
}
```

This verifies the local encoded-image-to-analysis mapping only, not aircraft
alignment or camera mounting. The operator gesture pins the actual presented
frame, surface transform, mode, client session and state guard at press. It
returns normalized encoded-image coordinates after excluding letterbox bars and
undoing presentation rotation/mirroring. Metadata from the latest received frame
must never replace the pinned frame.

For local PixEagle tracking, the backend retains original clean analysis pixels
before overlays, the exact Smart detections observed on that frame, and capture
orientation. Camera-owned selection instead retains the displayed frame and
verified analysis dimensions: camera firmware accepts displayed-image coordinates
and does not consume local analysis pixels. Only the variant actually sent on the
WebSocket is selectable, so an unused raw/OSD variant cannot evict a displayed
selection. The capture cache is bounded by 90 publications, 128 MiB of retained
pixel arrays and 1500 ms of backend capture age. A WebSocket sender also pins
the sampled selectable frame before encoding it. Delivery pins are limited to
three recent frames per client and 96 MiB overall, expire after 1500 ms, and
are removed on disconnect or source reset. QGC's latest-frame acknowledgment
holds the sender at the displayed frame while the operator acts; capture-cache
churn cannot evict that frame. Clients without acknowledgment can still advance
past an older displayed frame, and either cache can evict under its memory cap.
Returned snapshots own read-only pixels and copied candidates. Missing,
unknown, cached, expired, mismatched or evicted frames fail explicitly. Smart
selection uses the retained candidates and remains tentative until confirmed by
a current detector measurement. No historical-frame motion compensation is
claimed.

On a slow link, clients must select against the exact displayed frame and respect
its capture age. Neither client nor server may silently retarget the same click
to a newer frame. A frame older than the advertised limit is rejected and the
operator must tap fresh video; this is a safety boundary, not a guaranteed
minimum network bandwidth.

Camera-owned retarget admission checks that 1500 ms frame limit before changing
the camera. Its stop/ready handshake can outlast that limit. At the final
location send, the backend instead verifies the reserved target revision, the
same camera and stream, a currently live video source, and a six-second action
deadline. It retains the admitted click coordinates and never substitutes a
newer frame. A changed source or target rejects the send and fails the active
following transition closed. QGC waits up to eight seconds for the camera
selection result; camera command acceptance still does not prove a new lock.

## Existing action requests

Use `confirm: true`, `dry_run: false`, and a new `idempotency_key` for each new
intention. Add this field to the normal action body:

```json
{
  "native_context": {
    "guard": { "...": "the complete captured target-state guard" },
    "binding_mode": "companion_only",
    "frame": {
      "provenance": { "...": "the exact displayed JPEG provenance" },
      "selection_geometry": { "...": "the adjacent geometry object" }
    }
  }
}
```

The ellipsis objects above are explanatory placeholders, not valid requests.
Echo the complete typed objects. `frame` is required only for point/rectangle
selection, and is omitted for Cancel, tracker switch and explicit mode changes.

| Existing POST path under `/api/v1/actions/` | Additional action fields |
| --- | --- |
| `tracking-start` | `bbox: {coordinate_space:"normalized", x,y,width,height}` using top-left coordinates, **or** `point: {coordinate_space:"normalized",x,y}`. A point initializes a centered 64-analysis-pixel square, clamped inside the image. |
| `smart-click` | `click: {coordinate_space:"normalized",x,y}`. |
| `tracking-stop` | No selection fields. Tracking-only Cancel; no following stop call. |
| `smart-mode-toggle` | Native requests require explicit `enabled: true/false`; ordinary legacy toggle remains supported. |
| `tracker-switch` | `tracker_type` from the catalog. Ordinary tracker choices use `persist:false`. Advanced engine changes use `persist:true` with `restore_engine_selection:true` and require `config:write`; they apply the runtime choice and save the startup engine. An explicit tracker choice leaves local Smart mode and selects that implementation. |
| `gimbal-control` | Only `operation: select/cancel/set_mode`. Selection uses normalized center `x,y`, optional Classic rectangle `width,height`; mode changes use `selection_mode: classic/smart`. No movement operations. |

If the configuration schema, defaults, or retirement definitions changed after
the backend started, a persisted engine change is rejected with
`configuration_source_changed` and `restart_required: true`. Restart PixEagle
from Backend settings, refresh the catalog/state, then retry. The runtime
switch is rolled back before this error is returned. It does not mean that the
selected tracker is incompatible, and it never silently rewrites a follower or
tracker choice.

Engine restoration remembers the local Classic implementation and Smart intent,
or the camera's selection-mode intent. The local model continues to use its
existing canonical model configuration; camera tracking neither loads nor
replaces that model. Returning to Camera re-establishes its selected mode but
does not restore a previous target lock. Explicit tracker choices override the
remembered implementation. Unavailable remembered choices fail visibly rather
than selecting a different tracker silently. Memory lasts for this backend
process; startup still follows the saved profile. The restoration flag requires
native context. Persisted engine changes report `runtime_applied` and `saved`
separately. A save failure can leave the runtime engine changed; clients must
show the partial result and refresh state before retrying. Target state includes
`saved_engine` so clients can distinguish the current runtime engine from its
startup choice. A same-engine retry saves the running tracker without replacing
its target or interrupting manual camera control. Neither a successful
save nor a rollback restores the previous target or resumes following.

Tracker/model changes reserve the camera lifecycle and terminate an active
manual gesture only after the native guard and audit accept the action. Dry-run,
rejected guards and idempotent replay do not stop the operator's camera motion.
Local Smart cannot be activated while the camera engine is selected; Camera
Smart uses the separate provider selection-mode action.

The existing `APIActionResponse` additionally returns `result.target_state`,
`result.native_target_revision`, and authenticated `audit_event.actor`.
Native idempotence is actor-scoped and bound to the entire canonical body;
changed payload reuse rejects with `idempotency_conflict`. A replay is the
original action result, not a fresh state observation; refresh before a new
interaction and do not overwrite newer UI state with an old response.

Structured guard failures use HTTP 409 and codes such as
`native_context_stale`, `target_revision_stale`, `frame_context_invalid`,
`frame_expired`, `frame_evicted`, `target_following_active`,
`companion_aircraft_active`, and `target_mode_unavailable`. Invalid shapes or
coordinates use 422; missing credentials/scopes use 401/403. Do not automatically
retry a rejected selection against a newer frame. Cancel needs no fresh video,
but does require a current runtime/source/target guard so it cannot silently
cancel another client's replacement target.

## Serialization and camera boundary

Mutations run on the flight-owner event loop under its follower lifecycle lock,
then the tracker/model lock. Synchronous target commit also holds the telemetry
observer and publisher source transactions, in that order. Source retirement
cannot interleave validation and tracker initialization. Age is checked again
after pixel preparation and durable audit, immediately before mutation.
Successful dashboard target/mode/model/tracker changes advance the same target
generation, invalidating pending native gestures. No exclusive-controller lease
is introduced.

Camera handshakes await status without holding synchronous locks. The final LOC
send enters a short guarded source transaction and checks capture age/context
again. It uses retained orientation, not a subsequently edited video setting.
The existing supported provider and matching full-frame RTSP source are
required. Independently cropped or transformed camera-internal views and
physical target retention still need camera/hardware qualification; local
software mapping is not proof of those properties.

The isolated replay tool accepts `prepare --role operator` only in a new private
snapshot. Existing viewer snapshots, normal accounts and production configs are
preserved. Following preview/inhibit, loopback API, disabled telemetry/gimbal
and recorded-file settings remain mandatory. Core supports Classic here; local
Smart needs its optional Full AI runtime and a compatible trusted model. The
replay advertises external camera selection unavailable. `--video test1.mp4` selects
the bundled clean soccer-ball recording and disables the private demo OSD layer
while retaining actual tracker feedback; the default `test4.mp4` profile remains
unchanged. Asset path, checksum and demo OSD policy are pinned in its manifest.
