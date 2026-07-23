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
- No manual tracking initiation required

**Not image-based:**
Unlike other trackers, GimbalTracker doesn't process video frames. It receives angles directly from external gimbal hardware.

---

## Architecture

```
External Camera App / Gimbal UI
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
2. **External camera app starts tracking** - User initiates from gimbal UI
3. **PixEagle receives gimbal data** - the configured provider queries/listens for angles and tracking state
4. **GimbalTracker activates** - Provides angle data to followers
5. **External app stops tracking** - Sends `DISABLED` or `TARGET_LOST`
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
  PROVIDER: "topotek_sip_udp"       # Current provider implementation
  UDP_HOST: "192.168.0.108"       # Topotek gimbal IP address
  UDP_PORT: 9003                  # Topotek UDP command/query port
  LISTEN_PORT: 9004               # PixEagle response/broadcast listen port
  CONNECTION_TIMEOUT: 5.0         # Provider data/tracking freshness timeout
  COORDINATE_SYSTEM: "GIMBAL_BODY"
  DISABLE_ESTIMATOR: true         # Direct gimbal angle data
  data_timeout_seconds: 5.0
  max_consecutive_failures: 10
```

Legacy flat gimbal keys are not supported. Configs and docs must use the grouped
`GimbalTracker` section.

`Tracking.DEFAULT_TRACKING_ALGORITHM` is the saved startup and tracker-restart
default. The Tracker-page selector changes the active tracker for the current
process only; it does not silently rewrite operator configuration. Both
selectors use the selectable factory entries from `configs/tracker_schemas.yaml`.

### Provider Boundary

Current runtime support:

- `topotek_sip_udp`: Topotek SIP-series UDP frames using `GAC`, `GIC`, `TRC`, and `OFT` packet forms.

Current provider boundary:

- `GimbalTracker` depends on `GimbalInputProvider`, not a vendor protocol client.
- Providers return normalized yaw/pitch/roll, coordinate system, tracking state, timestamp, freshness, health, and diagnostic metadata.
- Followers should remain protocol-agnostic and consume only `TrackerOutput(data_type=GIMBAL_ANGLES, angular=(yaw, pitch, roll), ...)`.
- Future adapters should live below the tracker/provider boundary, for example MAVLink Gimbal Protocol v2, SIYI, Gremsy, Viewpro, serial vendor SDKs, or simulator providers.

### Adding Another Provider

To add another gimbal:

1. Implement the `GimbalInputProvider` protocol in `src/classes/gimbal_provider.py` or a provider module imported by it.
2. Return normalized `GimbalData` from `src/classes/gimbal_types.py` with `GimbalAngles`, `TrackingStatus`, timestamps, and health metadata. Do not return vendor packet structures to followers.
3. Add a stable provider ID to `list_supported_gimbal_providers()` and `create_gimbal_provider()`.
4. Add config schema/defaults and tests for provider selection, unsupported-provider failure, angle bounds, coordinate frames, health, and stale-data behavior.
5. Document the protocol, required hardware setup, coordinate conventions, and whether tracking is externally controlled.

---

## Tracking States

```python
class TrackingState(Enum):
    DISABLED = 0          # Gimbal tracking off
    TARGET_SELECTION = 1  # Selecting target
    TRACKING_ACTIVE = 2   # Actively tracking
    TARGET_LOST = 3       # Target lost
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

```yaml
# configs/tracker_schemas.yaml
mount_configurations:
  HORIZONTAL:
    name: "Horizontal Mount"
    coordinate_mapping:
      yaw: "yaw"
      pitch: "pitch"
      roll: "roll"
    transformation_type: "DIRECT"

  VERTICAL:
    name: "Vertical Mount (90° Rotated)"
    coordinate_mapping:
      yaw: "roll"
      pitch: "pitch-90"
      roll: "yaw"
    transformation_type: "ROTATIONAL_90"
```

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
#     'coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],
#     'requires_video': False,
#     'requires_detector': False,
#     'external_data_source': True,
#     'external_control_required': True,
#     'external_gimbal_input': True,
#     'status_driven': True
# }
```

---

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
