# Gimbal Tracker

> External gimbal angle integration with a normalized TrackerOutput contract

The Gimbal Tracker adapts external gimbal angle/status data into PixEagle's standard `TrackerOutput` contract. `GimbalTracker` consumes a normalized provider contract from `src/classes/gimbal_provider.py`; the current provider is the existing Topotek SIP-series UDP implementation in `src/classes/gimbal_interface.py`. This is not a MAVLink Gimbal Protocol v2 implementation yet.

---

## Overview

**Best for:**
- External gimbal hardware integration
- Camera gimbal angle-based tracking
- Systems with dedicated gimbal control
- No image processing overhead

**Key Features:**
- Status-driven external gimbal operation
- Topotek SIP-over-UDP angle/status ingestion
- Coordinate transformation (gimbal → body → NED)
- Always-on angle display
- External-app control by default; optional manual controls in the PixEagle dashboard

**Not image-based:**
Unlike other trackers, GimbalTracker doesn't process video frames. It receives angles directly from external gimbal hardware.

---

## Architecture

```
External Camera App / optional PixEagle camera controls
    ↓
Configured GimbalInputProvider
    ├─ current: Topotek SIP-series UDP hardware/simulator
    └─ future: MAVLink/vendor/simulator providers
    ↓
Normalized angles, tracking state, health, freshness, metadata
    ↓
PixEagle GimbalTracker
    ↓
    ├─→ TRACKING_ACTIVE: Provide angles to followers
    └─→ DISABLED/LOST: Continue monitoring, pause following
```

---

## Workflow

1. **PixEagle starts or selects GimbalTracker** - Begins background UDP monitoring
2. **Operator selects a target** - Use the external camera app, or enable the optional PixEagle controls below
3. **PixEagle receives gimbal data** - the configured provider queries/listens for angles and tracking state
4. **GimbalTracker activates** - Provides angle data to followers
5. **Camera tracking ends** - A cancel command or lost target changes the reported state
6. **GimbalTracker deactivates** - Pauses following but continues monitoring

Selecting Gimbal Tracker on the Tracker page starts provider monitoring
immediately. It does not require a video ROI and it does not command the gimbal
to begin target tracking.

---

## Configuration

```yaml
# configs/config.yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "Gimbal"

GimbalTracker:
  ENABLED: true
  CONTROL_ENABLED: false         # Opt in to dashboard camera controls
  PROVIDER: "topotek_sip_udp"       # Current provider implementation
  UDP_HOST: "192.168.0.108"       # Topotek gimbal IP address
  UDP_PORT: 9003                  # Topotek UDP command/query port
  LISTEN_PORT: 9004               # PixEagle response/broadcast listen port
  CONNECTION_TIMEOUT: 5.0         # Maximum age of the latest angle sample
  TRACKING_STATUS_TIMEOUT: 2.0    # Maximum age of the target-lock status
  COORDINATE_SYSTEM: "GIMBAL_BODY"
  DISABLE_ESTIMATOR: true         # Direct gimbal angle data
  data_timeout_seconds: 5.0
  max_consecutive_failures: 10
```

Legacy flat gimbal keys are not supported. Configs and docs must use the grouped
`GimbalTracker` section.

`Tracking.DEFAULT_TRACKING_ALGORITHM` is the saved startup and tracker-restart
default. The Dashboard Tracker control applies and saves a selection in one
operation; no process reboot is required. Both selectors use the selectable
factory entries from `configs/tracker_schemas.yaml`.

Angle packets and target-lock status packets are allowed to arrive at different
cadences. The provider keeps separate timestamps, composes a snapshot only from
components inside their configured freshness windows, and never treats a fresh
angle packet as proof of a fresh target lock. This keeps the operator display
useful during packet jitter while keeping follower readiness fail-closed.

### Provider Boundary

Current runtime support:

- `topotek_sip_udp`: checksum-validated `GAC` body angles and `TRC` tracking
  status from the configured camera IP. These are the authoritative inputs to
  the normalized follower contract.
- `GIC`/`GIA` spatial-angle replies are diagnostic only; they do not replace
  body angles or refresh follower angle readiness. `OFT` contains tracking-box
  information and is never parsed as angles. Polling schedules body-angle and
  tracking-status queries independently.

Current provider boundary:

- `GimbalTracker` depends on `GimbalInputProvider`, not a vendor protocol client.
- Providers return normalized yaw/pitch/roll, coordinate system, tracking state, timestamp, freshness, health, and diagnostic metadata.
- Followers should remain protocol-agnostic and consume only `TrackerOutput(data_type=GIMBAL_ANGLES, angular=(yaw, pitch, roll), ...)`.
- Future adapters should live below the tracker/provider boundary, for example MAVLink Gimbal Protocol v2, SIYI, Gremsy, Viewpro, serial vendor SDKs, or simulator providers.

### Adding Another Provider

See [Adding External Gimbal Providers](../05-development/external-gimbal-providers.md)
for the input and optional control contracts, registration points, coordinate
mapping, tests, and hardware qualification requirements. An input provider does
not automatically gain camera-control capabilities.

---

## Optional Dashboard Camera Controls

Set `GimbalTracker.CONTROL_ENABLED: true`, then select **Gimbal** as the active
tracker. The flag defaults to `false`: ordinary users retain the existing
tracking interface and external-app workflow. Controls appear only when the
actual active external provider exposes them. The current implementation is
`topotek_sip_udp`; other providers require their own adapter and capability
implementation. Changing the flag requires recreating the provider, for example
by restarting the tracker after applying configuration.

For the current SIP camera, the minimal opt-in override is:

```yaml
# configs/config.yaml (merge with your existing settings)
Tracking:
  DEFAULT_TRACKING_ALGORITHM: Gimbal
GimbalTracker:
  ENABLED: true
  CONTROL_ENABLED: true
  PROVIDER: topotek_sip_udp
  UDP_HOST: 192.168.0.108
  UDP_PORT: 9003
  LISTEN_PORT: 9004
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_OPENCV
  RTSP_URL: rtsp://192.168.0.108:554/stream=0
```

Replace both camera hosts together if yours differs. Alternatively, select
**Gimbal** through the dashboard instead of editing the saved tracker choice.
Apply the configuration and restart the tracker/provider; restart PixEagle if
the video source changed. Keep `CONTROL_ENABLED: false` to retain the standard
interface. Enabling these controls does not enable aircraft following or
qualify a mounting orientation; see [Mount Configurations](#mount-configurations).

`src/classes/gimbal_control.py` owns the camera commands separately from the
tracker and follower. It uses the provider's existing socket and lifecycle;
there is no second UDP listener or Qt application dependency. Switching away
from Gimbal closes its control adapter with best-effort cleanup.

### Select, Replace, And Cancel A Target

1. Configure the video input as `RTSP_OPENCV` or `RTSP_STREAM` using the same
   literal host as `GimbalTracker.UDP_HOST`. Point selection rejects a different
   camera, replay, other source type, or a frame older than two seconds.
2. Stop following before selecting or replacing a target. Click the desired
   point in the video; selection uses a fixed 64×64 reference-pixel region.
   Alternatively, in **Classic Tracker**, drag a rectangle around the target
   to choose its starting width and height. Dragging in either direction works.
   Click slightly inside image edges so the full region fits.
3. Click another point to replace the target. PixEagle first observes an
   inactive tracking barrier, prepares selection, then sends the new camera
   coordinates. An earlier active status is not reused as confirmation of the
   new target.
4. Choose **Cancel target** to end camera tracking. The command transitions
   through selection-ready when needed, then waits for disabled status.

Clicks are normalized against the displayed video image, excluding letterbox
bars. The backend reverses PixEagle's configured rotation and flip before
converting to the camera's coordinate reference. This does not compensate for
an independently cropped, mirrored, rotated, or picture-in-picture image inside
the camera; use its matching full-frame view. The camera's own tracking markers
may already be embedded in the stream.

Rectangle dimensions use fractions of the visible video, so resizing the
browser does not change the selected camera region. Quarter-turn display
rotations also swap width and height before transmission. The SIP adapter uses
the official Qt rectangle descriptor (`00 01`), with fuzzy selection off.
The box initializes the camera tracker; firmware can resize it afterward.

The optional camera selection mode is **Classic** (manual point or rectangle) or
**Smart** (the camera's fuzzy click selection). Camera Smart is distinct from
PixEagle's local SmartTracker: it uses camera firmware rather than a local AI
model. Mode changes require the provider's `set_mode` capability and following
to be stopped. Status `selection_mode` records provider intent, not the raw
camera `TRC` detection class or proof that an AI target was found. Enumerated AI
candidate metadata is not part of this API slice. Smart remains click-only.
Sending valid coordinates is not proof of stable tracking: acquisition,
retention, and reported physical drift require hardware evidence in the scene.

To use **Smart Tracker**, select that button in the Gimbal camera panel. PixEagle
prepares camera detection and waits for ready status. Click a detection box
drawn by the camera in the video. The SIP adapter uses the official Qt app's
fuzzy-click descriptor and small selection region; firmware decides which
nearby detection to select and what happens if none matches. PixEagle does not
claim a detected target from command acceptance alone. The camera's detection
classes and candidate metadata are not interpreted by this slice.

While ready, clicking preserves the detection session instead of disabling and
re-enabling it. Retargeting an active/lost Smart target first returns to ready.
Cancel and manual movement disable tracking; select **Smart Tracker** again to
show detections. **Classic Tracker** ends the previous session and restores
manual point/rectangle selection. The selection mode starts as Classic whenever the
provider is recreated; it is not a saved global tracker choice. These two
buttons are visible only inside the opted-in camera integration.

### Orientation And Restart

Camera-side image orientation and PixEagle display rotation are different.
First establish correct target centering in the official camera application
with the manufacturer's mounting/image settings. Then set PixEagle's display
rotation/flip for the desired view; click coordinates reverse that display
transform before transmission. Do not add coordinate offsets to compensate for
a camera that initially places the box correctly but steers away from it.

On the tested unit, the operator reported that camera-side 180° rotation fixed
opposite-direction tracking in the official app. A later read-only query
confirmed `ROT02`. This is a device/setup finding, not a universal default;
PixEagle does not automatically change the camera's persistent rotation.
Short corrected-orientation bench tests subsequently held one object for four
seconds, and two browser selections for three seconds each; this is limited
scene evidence, not general tracking qualification. AI candidate identity
checks remain pending. Choose display rotation from the actual view, rather than assuming
that every installation needs 180° on both sides.

Display rotation requires a backend restart. Start PixEagle using its supported
launcher (`scripts/run.sh` / `scripts/components/main.sh`) or the reviewed
process supervisor: the restart action exits with code 42 so a supervisor can
start a replacement. Running `python src/main.py` directly does not provide that
supervision. The local camera bench uses an isolated restart-capable launcher
and the same file for configuration loading and Settings persistence.

Shutdown releases the restart lifecycle lock before awaiting follower teardown,
rejects new follow/target starts, and then closes the external provider. Optional
camera controls attempt movement stop and cancellation of their own target;
default telemetry-only providers send no camera control commands during cleanup.
Network loss or camera firmware behavior can prevent those attempts from taking
effect. A restarted provider defaults to Classic and does not automatically
select a target or start following.

### Camera Buttons

On wide screens, the optional panel sits at the top of the right control
column; on narrow screens it follows the video, before Command. A single panel
remains mounted across responsive layout changes.

The optional panel uses a directional pad for pan/tilt, with Center camera at
its center, a separate roll pair, and a vertical zoom rocker. Small group labels
and named icon tooltips replace the always-visible tracker instructions. The
Classic/Smart selector chooses the camera tracker mode. **Cancel target** and
**Stop** remain separate labeled actions; Stop stops movement without canceling
the target. Icon buttons retain accessible names, visible keyboard focus and
44-pixel touch targets. Unsupported controls remain hidden; normal trackers
still contribute no camera panel.

| Control | Behavior |
| --- | --- |
| Pan, tilt, roll | Tap for one bounded step; hold to repeat completed steps. Normal is 10 degrees/second for 250 ms. Actual travel depends on the camera. |
| Zoom in/out | One 250 ms zoom pulse followed by stop. |
| Center camera | Sends the camera's home command; does not claim a verified final pose. |
| Cancel target | Disables tracking and stops camera/zoom motion after the state transition succeeds. |
| Stop camera | Sends movement and zoom stop commands; does not cancel the tracked target. |

The compact **Movement** selector offers Fine, Normal and Fast when the provider
advertises adjustable movement. **Adjust…** opens a dialog for speed and pulse
duration; Apply changes subsequent pan/tilt/roll steps, without moving anything.
Cancel discards the draft. Settings last for the browser session and reset on
page reload or a changed provider/settings contract. Zoom remains a fixed 250 ms
pulse, and can also be held to repeat.

The current SIP adapter advertises Fine (5°/s, 150 ms), Normal (10°/s, 250 ms),
and Fast (20°/s, 500 ms). Custom values are bounded to 1–30°/s and 100–1000 ms.
The backend owns and enforces these limits; the dashboard reads them from status.
The displayed speed × time estimate is not an exact-angle positioning promise.

Mouse, touch and Space/Enter holds issue only one movement request at a time;
the next step waits for the previous response. A quick tap completes its first
step. Release ends repetition and requests Stop during repeated movement.
Pointer cancellation, lost capture, focus loss, hidden page, unmount, disconnect
or lost authority ends the gesture. Steps already in transit may finish; each
has the existing server-side stop deadline. Stop camera also cancels the local
hold. No automatic repeat resumes after reconnect or release. Stop cannot
guarantee delivery after network/process failure.

Movement, zoom, and home first disable camera tracking. All manual target or
camera changes require following to be stopped; **Stop camera** is the sole
operation allowed while following. Stop can interrupt a pending command.
Stop and cancel remain attemptable with stale telemetry, and failures are
reported rather than assumed successful.

Pulse cleanup includes an independent best-effort timer and shutdown stop
attempts. This is not a hardware disconnect watchdog: process death, network
loss, camera firmware behavior, or an obstructed axis can prevent a stop from
taking effect.

### Typed API

- `GET /api/v1/gimbal/control`: reads `enabled`, `available`, `connected`,
  `tracking_state`, `following_active`, `selection_mode`, `capabilities`, and `reason` without
  sending commands. Requires `control:read`.
- `POST /api/v1/actions/gimbal-control`: accepts `operation` (`select`, `cancel`,
  `pan`, `tilt`, `roll`, `zoom`, `home`, `stop`, or `set_mode`). Selection requires finite
  normalized `x`/`y`. For a Classic rectangle, these are its **center**; supply
  both `width` and `height` as positive displayed-image fractions. Omit both for
  a click. The rectangle must fit within the image, and Smart rejects rectangle
  requests. Other operations reject dimension fields. Directional operations
  require `direction: -1` or `1`.
  `set_mode` requires `selection_mode: "classic"` or `"smart"` and accepts no
  coordinates or direction; other operations reject `selection_mode`.
  Pan/tilt/roll optionally accept integer `speed_deg_s` and `duration_ms`; omitted
  values use provider defaults. Explicit nulls and movement settings on other
  operations are rejected. Both dry-run and execution enforce the provider's
  advertised `motion_settings` bounds. Status supplies those bounds, defaults
  and presets; providers without adjustable movement omit them.
  Requires `actions:execute`, and browser sessions also require CSRF.

Execution requires `confirm: true` and an `idempotency_key`; a retry with the
same key returns the stored process-local action instead of sending again.
Use a new key for a new intended command. `dry_run: true` checks availability,
capabilities, and the following guard without camera mutation; source/frame
and camera state-transition checks still occur during actual selection.
Actions retain the normal authorization audit and action record. A successful
selection response means its command path completed, not that the camera
retained a target. Observe fresh status and video for the result.

See [API security policy](../../apis/api-security-policy.md) for the shared
scope, audit, and session requirements.

## Tracking States

```python
class TrackingState(Enum):
    DISABLED = 0          # Gimbal tracking off
    TARGET_SELECTION = 1  # Selecting target
    TRACKING_ACTIVE = 2   # Actively tracking
    TARGET_LOST = 3       # Target lost
    UNSUPPORTED = 4       # Camera reports tracking unavailable
```

GimbalTracker only enables following when state is `TRACKING_ACTIVE`.

## Runtime Checks

After selecting Gimbal Tracker:

- The switch response should report that external provider monitoring is active.
- Angle telemetry appears after valid provider packets reach `LISTEN_PORT`.
- Angle display may remain available while following is inactive.
- Following remains fail-closed until provider status is fresh and
  `TRACKING_ACTIVE`.

If angles do not appear, verify the grouped `GimbalTracker` host and port
settings, local firewall rules, and whether the camera sends responses to the
PixEagle computer's IP and `LISTEN_PORT`. An inactive provider now reports a
structured `monitoring_not_active` state instead of emitting one null warning
per video frame.

---

## TrackerOutput

```python
TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    # True only when the provider reports TRACKING_ACTIVE.
    # Angle display can continue while following remains inactive.
    tracking_active=True,

    # Primary gimbal angle data
    angular=(45.0, -10.0, 0.0),  # yaw, pitch, roll (degrees)

    # Converted for follower compatibility
    position_2d=(0.12, -0.08),   # Normalized from angles

    confidence=0.95,

    raw_data={
        'yaw': 45.0,
        'pitch': -10.0,
        'roll': 0.0,
        'system': 'gimbal_body',
        'tracking': 'TRACKING_ACTIVE',
        'connection_status': 'connected',
        'provider': 'topotek_sip_udp',
        'protocol': 'topotek_sip_udp',
        'measurement_source': 'external_gimbal',
        'usable_for_following': True,
        'data_is_stale': False
    },

    metadata={
        'tracker_type': 'external_gimbal',
        'always_reporting': True,
        'is_gimbal_tracker': True,
        'continuous_display': True,
        'external_control': True,
        'gimbal_provider': 'topotek_sip_udp',
        'usable_for_following': True
    }
)
```

Fresh gimbal angles are not enough to keep following active by themselves. If a
provider packet lacks a fresh tracking status, `GimbalTracker` clears its active
state and marks the output unusable for following while still exposing angle
telemetry for diagnostics.

---

## Usage

### Basic Usage

```python
from classes.trackers.tracker_factory import create_tracker

# Create gimbal tracker
tracker = create_tracker("Gimbal", video_handler, detector, app_controller)

# Start background monitoring
tracker.start_tracking(frame, bbox)  # bbox ignored for gimbal

# Update loop
while True:
    success, output = tracker.update(frame)  # frame not used

    if success and output.tracking_active:
        yaw, pitch, roll = output.angular
        print(f"Gimbal: Y={yaw:.1f}° P={pitch:.1f}° R={roll:.1f}°")
```

### Checking External Control Status

```python
if tracker.is_external_control_active():
    # Gimbal is being controlled externally and tracking
    pass

# Get tracking source info
source_info = tracker.get_tracking_source_info()
# {
#     'source_type': 'external_gimbal',
#     'control_method': 'topotek_sip_udp',
#     'provider': 'topotek_sip_udp',
#     'listen_port': 9004,
#     'protocol': 'topotek_sip_udp'
# }
```

---

## Coordinate Transformation

Gimbal angles are transformed through multiple frames:

```
GIMBAL_BODY → AIRCRAFT_BODY → NED (world)
```

### Mount Configurations

The next installation qualification is limited to **horizontal and vertical**.
Existing `GM_VELOCITY_VECTOR.MOUNT_TYPE` and
`GM_VELOCITY_CHASE.MOUNT_TYPE` choose follower-specific formulas. They do not
configure the camera's stabilization or remap its native pan/tilt/roll buttons.
Unknown mount values now prevent follower initialization instead of silently
falling back to Vertical. Existing valid presets retain their prior behavior.
The `mount_configurations` entries in `tracker_schemas.yaml` are descriptive;
the active followers do not apply that table as a shared rotation transform.

Do not assume that swapping yaw and roll supports a sideways camera. The
followers currently differ in lateral-axis interpretation, the tracker
projection differs in pitch sign, and the vector follower's angle offsets are
not a rigid mounting rotation. A successful image selection does not qualify
the resulting aircraft direction.

Before selecting settings for a new installation, establish camera startup,
stable native tracking, motor/telemetry signs and the base's direction relative
to aircraft forward/right/down. Display rotation is configured separately.
Then validate both follower mappings in command preview before any aircraft
test. No automatic mount detection or arbitrary-angle UI is added.

The [mounting audit and standalone bench procedure](../../reporting/agent-ops/codex-modernization/checkpoints/2026-09-19-gimbal-mounting-audit.md)
lists exact parameters, current gaps, manufacturer-document limits and the
measurements needed to define the vertical preset. The vertical camera
installation remains unqualified until that procedure is completed.

---

## Component Suppression

GimbalTracker doesn't need image processing:

```python
# Automatically suppressed components
self.suppress_detector = True
self.suppress_predictor = True
self.estimator_enabled = False

# Check suppression status
tracker.get_suppression_status()
# {'detector_suppressed': True, 'predictor_suppressed': True}
```

---

## Data Caching

Handles temporary provider packet loss:

```python
# If no current data, use cached data up to timeout
if (self.last_valid_output and
    (time.time() - self.last_valid_data_time) < DATA_TIMEOUT_SECONDS):
    # Return cached angles for display with reduced confidence.
    # tracking_active is false so followers fail closed on stale data.
    return self._create_stale_data_output(self.last_valid_output)
```

---

## Statistics

```python
stats = tracker.get_gimbal_statistics()
# {
#     'tracker_stats': {
#         'monitoring_active': True,
#         'tracking_started': True,
#         'total_updates': 5000,
#         'tracking_activations': 3,
#         'tracking_deactivations': 2,
#         'current_tracking_state': 'TRACKING_ACTIVE',
#         'tracking_duration': 120.5
#     },
#     'gimbal_interface_stats': {...},      # Provider runtime counters
#     'gimbal_provider_metadata': {...},
#     'coordinate_transformer_stats': {...}
# }
```

---

## Capabilities

```python
tracker.get_capabilities()
# {
#     'data_types': ['ANGULAR'],
#     'supports_confidence': True,
#     'supports_velocity': False,
#     'supports_bbox': False,
#     'tracker_algorithm': 'Topotek SIP UDP Gimbal',
#     'gimbal_provider': 'topotek_sip_udp',
#     'provider_protocol': 'topotek_sip_udp',
#     'supported_gimbal_providers': ['topotek_sip_udp'],
#     'coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],  # Contract metadata; see note below
#     'requires_video': False,
#     'requires_detector': False,
#     'external_data_source': True,
#     'external_control_required': True,
#     'external_gimbal_input': True,
#     'status_driven': True
# }
```

---

The coordinate-system capability list describes the general tracker contract.
For the current Topotek provider, follower angles come from validated `GAC`
body-angle packets; spatial replies are not promoted to follower input.

## Compatible Followers

GimbalTracker requires GIMBAL_ANGLES-compatible followers:

| Follower | Compatibility |
|----------|--------------|
| GMVelocityChaseFollower | Primary (designed for gimbal) |
| GMVelocityVectorFollower | Primary (designed for gimbal) |

---

## Related

- [Follower Integration](../06-integration/follower-integration.md) - How followers use gimbal data
- [External Systems](../06-integration/external-systems.md) - UDP protocol details
- [Schema System](../04-configuration/schema-system.md) - GIMBAL_ANGLES schema
