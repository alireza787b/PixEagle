# Native camera controls

Slice 4b.2 adds `camera.control.v1` to integration capabilities. Camera control
uses the existing authenticated routes `GET /api/v1/gimbal/control`
(`control:read`) and `POST /api/v1/actions/gimbal-control` (`actions:execute`).
Session mutations retain CSRF, confirmation, idempotency and audit enforcement.
These routes remain the dashboard facade; there is no second vendor socket in QGC.

`CameraRuntime` belongs to AppController. It owns one provider, independent of
the active tracker. GimbalTracker borrows that provider and adapts samples to
`GIMBAL_ANGLES`; detaching stops adapter-owned control but preserves the shared
transport. Application shutdown closes it. Standalone tracker construction
retains a private provider for non-AppController/test consumers.

The existing `GimbalTracker` configuration remains authoritative. No keys were
renamed. With `CONTROL_ENABLED: true`, the provider starts for local trackers
as well. With controls disabled it starts only when Gimbal monitoring is used.
Provider configuration changes require a backend restart in this checkpoint.
The default local workflow creates no camera IO.

## Status and operations

Status retains existing fields and adds:

- `instance_id`, `runtime_id`, `provider_id` and opaque `camera_id`;
- opaque `camera_generation` and current video `source_epoch`;
- `guard: {camera_id, camera_generation, source_epoch}`;
- `target_engine: local|camera`, independent of `enabled` camera controls;
- `selection_modes: [{id, label, point, rectangle}]`, supplied by the provider;
- `motion_active`, `capabilities` and bounded `motion_settings`.

Native target-state also includes `external_selection_modes`; tracker catalog
entries expose `target_engine`. Clients must not infer camera ownership from a
tracker label. In local mode, camera target select/mode/cancel capabilities are
omitted, while supported movement controls remain available. The dashboard
keeps its local tracker controls in this combination.

For native movement, send the normal action envelope plus:

```json
{
  "operation": "pan",
  "direction": 1,
  "confirm": true,
  "idempotency_key": "a-new-key-for-this-step",
  "camera_context": {
    "client_id": "stable-per-client-instance",
    "guard": {
      "camera_id": "copied-from-status",
      "camera_generation": "copied-from-status",
      "source_epoch": "copied-from-status"
    }
  }
}
```

Optional `speed_deg_s` and `duration_ms` must satisfy provider bounds. Camera
selection, cancel and mode continue using the retained-frame `native_context`
target contract. Movement and target contexts cannot be mixed in one request.
Stop uses the captured camera context without direction. It accepts a stale
source/generation for that same camera identity and increments the movement
generation immediately, invalidating late starts carrying an earlier guard.
A different camera identity always rejects, including Stop.

The executor validates context at admission and immediately before protocol
movement after the asynchronous state handshake; lifecycle reservations exclude following.
Following blocks camera mutation except Stop and a validated camera-owned
retarget. The adapter prepares immutable selection geometry before lifecycle
reservations, target-generation changes or continuity transitions. Rejected
edge taps and rectangles preserve the current target and following session.
The prepared region is reused for dispatch, with source/runtime ownership
rechecked after the handshake. A failure after camera mutation still invokes
the guarded handoff. Dashboard and native requests share this executor.
Native idempotency is scoped to
authenticated credential and client identity, with payload conflict detection.
A busy operation excludes concurrent clients; a finite movement lease excludes
interleaved holds. Stop preempts work. Finite compatibility calls stop independently; first-party holds use the
renewable manual protocol documented below.
If the final pulse Stop cannot be transmitted, the action reports failure so a
client does not continue its hold from a successful movement result. Explicit
Stop remains available for retry against the captured camera owner.

No command acknowledgement establishes actual motor motion. UDP transmission,
network loss and device watchdog limitations remain unchanged. Camera firmware
Classic/Smart is separate from the PixEagle model inventory. Camera host/source
association and inverse orientation stay in the backend provider/control layer.

## Validation fixture

For a synthetic camera with real authentication and native action guards:

```bash
PYTHONPATH=src .venv/bin/python tools/native_integration_fixture.py \
  --port 18091 --instance-id camera-mock --no-aircraft --mock-camera
```

This loopback fixture uses its documented `operator` / `fixture-only` account;
it is not a deployment account. Only explicit `--mock-camera` grants the fixture
operator role. It emits synthetic frames and advertises movement-only camera
capabilities; no hardware sockets, PX4 connections or vendor packets are created.
Protocol selection/handshake behavior is covered separately by mocked tests.

Run `test_camera_runtime.py`, `test_api_v1_gimbal_control.py`, camera provider,
tracker, protocol/freshness tests and native target tests, plus route/config/
schema gates. Dashboard regression covers preserved local controls, captured
camera context and bounded hold release. Physical qualification begins at 4b.3.

## Renewable manual control (4b.3 bench correction)

Providers implementing `prepare_manual(command_guard)` and
`send_manual_intent(axis, value)` advertise `manual_begin` and `manual_update`.
First-party QGC and dashboard controls use this protocol rather than repeated
finite pulses. Use the existing action envelope and camera context, adding:

```json
{
  "operation": "manual_begin",
  "gesture_id": "a-new-UUID-for-this-press",
  "sequence": 0,
  "intent": {"axis": "pan", "value": 0.5}
}
```

Begin prepares camera ownership but **cannot move a motor**. After its accepted
response, send `manual_update` with the same gesture, increasing sequence
numbers starting at 1, and the latest intent every 100 ms. Valid axes are the
provider-advertised `pan`, `tilt`, `roll`, and `zoom`; value is finite in [-1,1].
The current SIP provider supports one axis at a time. Stick magnitude selects
bounded angular speed; zoom supports direction only. Zero stops movement.

There is one replaceable intent, never a movement backlog. The lease expires
350 ms after HTTP ingress of the latest accepted update. Inputs delayed in
admission are rejected. Begin also expires without renewal; no update can
revive an expired or stopped gesture. Renewals continue during preparation.
A dedicated camera executor runs independently of capture, inference and the
flight owner loop. It checks expiry at 20 ms intervals and performs the camera
tracking-disable handshake once per gesture. The same provider and UDP sockets
are used for every client. Finite compatibility pan/tilt/roll/zoom/Home and Stop
also use this executor, with final context/expiry checks before transmission.
These are software timing bounds, not a device-side watchdog or hard-real-time
guarantee during process death, network loss, or OS starvation.

Release sends `stop` immediately with the captured `camera_context`,
`gesture_id` and next sequence. A Stop arriving before begin retires that
gesture. A delayed Stop from an older gesture cannot stop a newer gesture or
discrete operation. Unscoped Stop remains an explicit same-camera abort.
Successful Stop/expiry changes the camera guard; use `result.camera_status.guard`
or refresh status before another press. A failed Stop blocks further control
and following/lifecycle admission until an explicit Stop retry succeeds.
Normal hold duration is governed by renewal, not a five/ten-second UI cutoff.

Action results include `manual` (also present in camera status): gesture ID,
sequence, state (`preparing`, `moving`, `idle`, `stopped`, `expired`, `failed`),
reason, renewal/lease intervals, and monotonic acceptance/dispatch/stop times.
The action `timing` includes ingress and completion monotonic times. Success
means acceptance/transmission, never proof of physical motion. Expected
`camera_control_interrupted` from a superseded finite command is cancellation,
not an unknown motor outcome. Clients ignore obsolete gesture responses.

Runtime lifecycle reservations atomically exclude following startup from
manual control, and terminate manual ownership before changing tracker/model
ownership. Following is not unlocked merely because a failed Stop ended a UI
hold. Camera/source changes and stale camera samples terminate the lease.

Status `telemetry` provides fresh `angles_deg` (yaw/pitch/roll), independent
`angles_age_ms`, `angles_max_age_ms`, and `coordinate_system`. Clients expire
cached values between polls. Missing/stale angles are unavailable, never zero.
The SIP provider does not expose verified zoom telemetry: `zoom_available` is
false and `zoom` is null. Display orientation and physical axis mapping remain
separate qualifications.

Regression tests use fake providers to cover blocked inference/capture,
expiry during preparation, latest-intent replacement, reversal, stale input,
Stop-before-begin, obsolete Stop, cross-client exclusion, lifecycle races and
failed Stop. They send no camera or aircraft commands. Hardware responsiveness,
vertical-axis interpretation and camera-owned tracking still need the operator
bench checkpoint.

Camera retarget guidance uses the angle's actual receipt time/sequence and the
tracking-status receipt time, independently of video processing. Fresh frames
cannot renew old angle data. Samples must belong to the current provider and
postdate the admitted LOC dispatch; camera firmware without request IDs does
not independently acknowledge a specific replacement target.

Native following status optionally retains `last_handoff` with captured follow
session, aircraft identity, reason and result (`pending`, `confirmed_hold`,
`stopped`, `failed`). It is cleared on the next session start and never restored
from client settings. `stopped` includes local preview/withheld commands and
does not claim PX4 entered Hold. Teardown marks the session stopping before
awaiting the publisher; concurrent callers share its outcome and guidance
cannot report deliberate shutdown as a new publisher failure.
