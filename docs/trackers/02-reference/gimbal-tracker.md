# Gimbal Tracker

> External gimbal angle integration via UDP (no image processing)

The Gimbal Tracker passively monitors external gimbal systems and provides angle data for follower control. Located at `src/classes/trackers/gimbal_tracker.py`.

---

## Overview

**Best for:**
- External gimbal hardware integration
- Camera gimbal angle-based tracking
- Systems with dedicated gimbal control
- No image processing overhead

**Key Features:**
- Status-driven passive operation
- UDP angle reception
- Coordinate transformation (gimbal → body → NED)
- Always-on angle display
- No manual tracking initiation required

**Not image-based:**
Unlike other trackers, GimbalTracker doesn't process video frames. It receives angles directly from external gimbal hardware.

---

## Architecture

```
External Camera App (controls gimbal)
    ↓
Gimbal Hardware (tracking target)
    ↓
UDP Broadcast (angles + status)
    ↓
PixEagle GimbalTracker (passive monitoring)
    ↓
    ├─→ TRACKING_ACTIVE: Provide angles to followers
    └─→ DISABLED/LOST: Continue monitoring, pause following
```

---

## Workflow

1. **PixEagle starts GimbalTracker** - Begins background UDP monitoring
2. **External camera app starts tracking** - User initiates from gimbal UI
3. **Gimbal broadcasts data** - Sends angles + `tracking_status=TRACKING_ACTIVE`
4. **GimbalTracker activates** - Provides angle data to followers
5. **External app stops tracking** - Sends `DISABLED` or `TARGET_LOST`
6. **GimbalTracker deactivates** - Pauses following but continues monitoring

---

## Configuration

```yaml
# configs/config.yaml
TRACKING_ALGORITHM: "Gimbal"

# Gimbal connection
GIMBAL_UDP_HOST: "192.168.0.108"
GIMBAL_LISTEN_PORT: 9004

GimbalTracker:
  UDP_PORT: 9003            # Control port (not used in passive mode)
  data_timeout_seconds: 5.0
  max_consecutive_failures: 10

GIMBAL_COORDINATE_SYSTEM: "GIMBAL_BODY"
GIMBAL_DISABLE_ESTIMATOR: true  # Direct data, no filtering needed
```

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

---

## TrackerOutput

```python
TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
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
        'connection_status': 'connected'
    },

    metadata={
        'tracker_type': 'external_gimbal',
        'always_reporting': True,
        'is_gimbal_tracker': True,
        'continuous_display': True,
        'external_control': True
    }
)
```

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
#     'control_method': 'passive_monitoring',
#     'listen_port': 9004,
#     'protocol': 'UDP'
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

Handles temporary UDP packet loss:

```python
# If no current data, use cached data up to timeout
if (self.last_valid_output and
    (time.time() - self.last_valid_data_time) < DATA_TIMEOUT_SECONDS):
    # Return cached data with reduced confidence
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
#     'gimbal_interface_stats': {...},
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
#     'tracker_algorithm': 'Gimbal UDP Passive',
#     'coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],
#     'requires_video': False,
#     'requires_detector': False,
#     'external_data_source': True,
#     'external_control_required': True,
#     'passive_monitoring': True,
#     'status_driven': True
# }
```

---

## Compatible Followers

GimbalTracker requires GIMBAL_ANGLES-compatible followers:

| Follower | Compatibility |
|----------|--------------|
| GMPIDPursuitFollower | Primary (designed for gimbal) |
| GMVelocityVectorFollower | Primary (designed for gimbal) |

---

## Related

- [Follower Integration](../06-integration/follower-integration.md) - How followers use gimbal data
- [External Systems](../06-integration/external-systems.md) - UDP protocol details
- [Schema System](../04-configuration/schema-system.md) - GIMBAL_ANGLES schema
