# Adding External Gimbal Providers

Add a provider beneath the application camera owner; keep vendor transport,
packet parsing and camera commands out of followers and dashboard components.
The current implementation supports `topotek_sip_udp`. Other camera models
require their own implementation and qualification, even if their command
names appear similar.

For operator setup, see [Optional Dashboard Camera Controls](../02-reference/gimbal-tracker.md#optional-dashboard-camera-controls).
`GimbalTracker.CONTROL_ENABLED` must remain `false` in shipped defaults. Local
configuration opts in, and the panel appears only when the shared provider
exposes a control adapter, independently of the selected target engine.

## Existing Boundaries

Paths below are relative to the repository root.

| Boundary | Implementation | Responsibility |
| --- | --- | --- |
| Input provider | `src/classes/gimbal_provider.py` | `GimbalInputProvider`, configuration, provider selection |
| Runtime owner | `src/classes/camera_runtime.py` | One transport lifetime, control leases, Stop generation |
| Normalized samples | `src/classes/gimbal_types.py` | `GimbalData`, `GimbalAngles`, `TrackingStatus`, timestamps and coordinate frame |
| Tracker | `src/classes/trackers/gimbal_tracker.py` | Convert fresh samples to `TrackerOutput`; gate following on fresh target lock |
| Optional control | `src/classes/gimbal_control.py` | `GimbalControl`, SIP adapter, application guards and displayed-image mapping |
| Movement settings | `src/classes/gimbal_motion.py` | Provider-advertised pulse defaults, presets and bounds |
| Typed public API | `src/classes/api_v1_contracts.py`, `api_v1_actions.py`, `api_v1_read_routes.py` | Status, validated actions, authorization, dry-run and idempotency |
| Dashboard | `GimbalControlPanel.js`, `useGimbalControl.js`, `useGimbalHold.js` | Capability-driven controls, bounded hold repetition and abort handling |

## 1. Implement And Register Input

Implement the methods in `GimbalInputProvider`: start/stop listening, current
data, connection status, statistics, health, tracking activity and provider
metadata. AppController owns the transport through `CameraRuntime`; tracker
changes release adapter-owned controls but retain the shared transport. Shut
down its threads, timers and sockets when the application stops.

Return `GimbalData` with `GimbalAngles` in degrees, ordered yaw/pitch/roll,
an explicit `CoordinateSystem`, and a timestamp. Return `TrackingStatus` with
its own timestamp. Track angle freshness and target-status freshness
independently: receiving a new angle must not renew an old target lock. Health
and diagnostic metadata belong in their provider methods; `GimbalData` is not
a container for arbitrary health fields.

Validate packet framing, checksum, sender and ranges before publishing data.
Document native axis signs, angle frame, units and the conversion you apply.
Do not silently substitute spatial angles or detection rectangles for body
angles. Map tracking states to the existing `TrackingState` enum; missing,
stale or lost status must not imply active tracking.

Register a stable ID in `canonicalize_gimbal_provider()`,
`list_supported_gimbal_providers()` and `create_gimbal_provider()`. Unknown
IDs must continue to raise `UnknownGimbalProviderError`. Extend grouped
`GimbalTracker` configuration in `configs/config_schema.yaml` and
`configs/config_default.yaml` only as needed; do not change the default
provider, tracker or `CONTROL_ENABLED` to activate a new integration.

## 2. Add Optional Controls

An input-only provider needs no control adapter. For supported camera commands,
construct `provider.manual_control` only when `CONTROL_ENABLED is True`;
otherwise leave it `None`. Implement `GimbalControl`:

- `capabilities`: operation names actually supported by the camera.
- `prepare_selection(*, x, y, width, height)`: purely validate/quantize native
  stream geometry into an immutable provider-owned selection. No transport,
  target or manual-ownership changes are allowed. Return the current adapter
  identity and selection mode with the prepared region.
- `async execute(operation, *, x, y, width, height, direction, selection_mode,
  speed_deg_s, duration_ms, prepared_selection)`: reuse a prepared selection and
  reject an adapter/mode mismatch before mutation; accept the optional keyword arguments defined by
  the protocol and return an action result containing `success` and `message`.
- `stop()`: attempt movement/zoom stop immediately and report transmission
  failure. Provider shutdown must also close the adapter and its resources;
  the SIP adapter provides `close()` for this lifecycle responsibility.

The shared API currently supports `select`, `cancel`, `pan`, `tilt`, `roll`,
`zoom`, `home`, `stop` and `set_mode`. Advertise a subset rather than showing
unsupported buttons. `selection_modes()` declares the provider modes and
point/rectangle geometry. The current request schema accepts Classic and Smart;
new mode identifiers require a typed schema extension and protocol tests. Keep
the camera's Smart mode separate from local AI.

Expose `selection_mode` when implementing mode changes. Adjustable motion
uses `motion_settings` with min/max/default speed and duration plus named
presets, matching `APIGimbalMotionSettings`. Validate provider limits before
any transmission; generic request limits are not device-specific permission.
Without adjustable movement, omit those settings and implement bounded
default steps. Never use a held browser button as an unbounded motor command:
each request must stop on its own, and explicit Stop must interrupt pending
work. Process death or network loss still requires a device-side solution.

Preserve the coordinator's following guard, lifecycle lock, tracking-session
generation change and immediate Stop path. Movement must not leave camera
tracking active unintentionally. Distinguish successful transmission from
fresh observed camera state; do not claim target acquisition from an ACK.
Clean up only tracking sessions owned by the adapter.
Validated camera retargets may continue bounded aircraft guidance; rejected
geometry must preserve that guidance and the existing target. Return actual
LOC dispatch wall/monotonic timestamps for post-selection observation guards.

**Current integration limits:** readiness requires the provider running state
and fresh angle/status samples. `matches_video_source(source)` owns source
association; Topotek retains the RTSP host check. For serial, SDK or separately
routed video, implement explicit source association and readiness with tests.
Do not bypass freshness/identity checks or add vendor branches to the UI.

## 3. Preserve Coordinate Ownership

The dashboard supplies normalized displayed-image coordinates in `[0, 1]`,
excluding letterbox bars. For a rectangle, `x`/`y` are its center and
`width`/`height` are image fractions; a point omits both dimensions.

The coordinator checks a fresh frame from the matching camera, reverses
PixEagle's rotation and flip with `inverse_video_point()`, and swaps dimensions
for 90°/270°. The adapter receives native-stream fractions and converts them
to the vendor's wire units. Do not reverse display orientation a second time.
Validate finite values, image bounds, rectangle support and quantization
before canceling an existing target or transmitting commands. SIP's fixed
click region and fuzzy descriptor are vendor details, not universal defaults.

Camera-internal crop, mirror, rotation, alternate sensor and picture-in-picture
need explicit validation against the tracker's coordinate reference. Display
orientation and physical mounting are separate. Existing follower mount
presets do not remap camera controls or establish a new camera's joint geometry.
The [mounting reference](../02-reference/gimbal-tracker.md#mount-configurations)
records current limitations; do not advertise vertical installation or flight
direction correctness from successful image selection alone.

## 4. Reuse And Verify The Public Contract

Use `GET /api/v1/gimbal/control` and
`POST /api/v1/actions/gimbal-control`. Retain shared permissions, CSRF for
browser sessions, confirmation, dry-run, idempotency and audit records. New
public fields/actions require typed models and route/security inventory
updates; do not introduce a raw-packet browser endpoint.

Use these existing tests as focused examples:

- `tests/unit/trackers/test_gimbal_provider.py`: default-off construction and
  unsupported providers.
- `tests/unit/trackers/test_gimbal_interface_protocol.py` and
  `test_gimbal_interface_status_freshness.py`: packet acceptance and independent
  sample freshness.
- `tests/unit/trackers/test_gimbal_control.py`: wire encoding, state transitions,
  rotation/flip, rectangles, pulse limits, interruption and cleanup.
- `tests/unit/core_app/test_api_v1_gimbal_control.py`: typed action validation,
  dry-run, permissions and following guard.
- Dashboard `GimbalControlPanel.test.js`, `GimbalControlHold.test.js`,
  `useGimbalControl.test.js` and `BoundingBoxDrawer.test.js`: hidden defaults,
  capabilities, mouse/touch/keyboard, hold release and image selection.

Add equivalent fixtures for the new provider. Run the changed domain tests,
route inventory and parameter reload tests, `bash scripts/check_schema.sh`,
and dashboard tests/build when its contract changes. Check that normal tracker
UI remains unchanged and disabled configuration sends no camera control
commands. Input monitoring, when Gimbal is selected, remains a separate path.

Qualify hardware separately: record model/firmware, exact config and commands,
responses, selection/retarget/cancel behavior, motor direction, hold/release,
disconnect/reconnect and each supported installation. Keep standalone camera
bench results separate from follower command-preview and aircraft validation.
Document unverified behavior rather than treating protocol compatibility as
proof of tracking quality or flight safety.

## Native integration update (slice 4b.2)

AppController now owns the provider through `CameraRuntime`; GimbalTracker
borrows it. Tracker detach releases adapter-owned control without closing the
shared transport. This allows local Classic/Smart plus manual controls with
`CONTROL_ENABLED: true`. Application shutdown closes the provider. Provider
configuration changes currently require backend restart. Standalone tracker
instances retain their own provider lifecycle for compatibility.

Provider methods `selection_modes()` and `matches_video_source(source)` expose
camera selection geometry and source association. Topotek supplies the existing
Classic/Smart modes and RTSP host guard. Native status and target-state expose
these mode capabilities; clients do not infer them from the vendor name.

The same camera routes now support captured native control ownership and
cross-client arbitration. See [Native camera controls](../../apis/native-camera-controls.md)
for guard, Stop, lease and mock-fixture details. All AppController consumers use the shared owner.
