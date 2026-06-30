# External Systems Integration

> Gimbal integration, external sensors, and data protocols

This document covers integration with external tracking data sources.

---

## Gimbal Integration

### Current Provider Model

GimbalTracker consumes a `GimbalInputProvider` selected by `GimbalTracker.PROVIDER`. The current supported provider is `topotek_sip_udp`, which wraps `GimbalInterface` to query/listen for Topotek SIP-series UDP frames, then emits normalized `TrackerOutput` data:

```python
TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    angular=(45.0, -10.0, 0.0),
    tracking_active=True,
    raw_data={
        "tracking": "TRACKING_ACTIVE",
        "system": "gimbal_body",
        "provider": "topotek_sip_udp",
    },
)
```

Followers must not depend on vendor packets. New gimbal hardware support should
be implemented as a provider that returns normalized angles, tracking state,
freshness, health, and metadata.

### Configuration

```yaml
# configs/config.yaml
TRACKING_ALGORITHM: "Gimbal"

GimbalTracker:
  PROVIDER: "topotek_sip_udp"
  UDP_HOST: "192.168.0.108"
  UDP_PORT: 9003
  LISTEN_PORT: 9004
  COORDINATE_SYSTEM: "GIMBAL_BODY"
```

### Tracking States

```python
class TrackingState(Enum):
    DISABLED = 0          # Gimbal not tracking
    TARGET_SELECTION = 1  # User selecting target
    TRACKING_ACTIVE = 2   # Actively tracking
    TARGET_LOST = 3       # Target lost
```

---

## Coordinate Transformation

### Coordinate Frames

```
GIMBAL_BODY    → Local gimbal frame
AIRCRAFT_BODY  → Aircraft body frame
NED            → North-East-Down world frame
```

### Transformation Pipeline

```python
# In CoordinateTransformer
def gimbal_to_ned(self, gimbal_angles, aircraft_attitude):
    # 1. Gimbal body to aircraft body
    body_vector = self.gimbal_angles_to_body_vector(
        gimbal_angles.yaw,
        gimbal_angles.pitch,
        gimbal_angles.roll
    )

    # 2. Aircraft body to NED (using aircraft attitude)
    ned_vector = self.body_to_ned(
        body_vector,
        aircraft_attitude.roll,
        aircraft_attitude.pitch,
        aircraft_attitude.yaw
    )

    return ned_vector
```

### Mount Offset Compensation

```python
# Account for gimbal mounting offset
def apply_mount_offset(self, angles, mount_config):
    offset_yaw = mount_config.get('yaw_offset', 0.0)
    offset_pitch = mount_config.get('pitch_offset', 0.0)

    return (
        angles.yaw + offset_yaw,
        angles.pitch + offset_pitch,
        angles.roll
    )
```

---

## External Sensor Integration

### EXTERNAL Data Type

For arbitrary external data sources:

```python
TrackerOutput(
    data_type=TrackerDataType.EXTERNAL,
    timestamp=time.time(),
    tracking_active=True,
    raw_data={
        'source_type': 'radar',
        'source_id': 'radar_001',
        'target_range': 150.0,      # meters
        'target_bearing': 45.0,     # degrees
        'target_elevation': -10.0,  # degrees
        'velocity': (5.0, 2.0, 0.0) # m/s
    }
)
```

### Creating External Tracker

```python
class RadarTracker(BaseTracker):
    """External radar data tracker."""

    def __init__(self, ...):
        super().__init__(...)
        self.radar_interface = RadarInterface(port=5000)
        self.suppress_detector = True  # No image processing

    def update(self, frame=None):
        # Get radar data (frame not used)
        radar_data = self.radar_interface.get_data()

        if radar_data:
            return True, self._radar_to_output(radar_data)
        return False, None

    def _radar_to_output(self, radar_data):
        return TrackerOutput(
            data_type=TrackerDataType.EXTERNAL,
            raw_data={
                'source_type': 'radar',
                'range': radar_data.range,
                'bearing': radar_data.bearing
            }
        )
```

---

## Telemetry Integration

### MAVLink Data Access

```python
# Access aircraft attitude from MAVLink
def _get_aircraft_attitude(self):
    if self.app_controller.mavlink_data_manager:
        return {
            'roll': self.app_controller.mavlink_data_manager.get_data('roll'),
            'pitch': self.app_controller.mavlink_data_manager.get_data('pitch'),
            'yaw': self.app_controller.mavlink_data_manager.get_data('yaw')
        }
    return None
```

### Telemetry Handler Integration

```python
# Tracker data in telemetry
telemetry = {
    'tracker': {
        'type': tracker_output.data_type.value,
        'active': tracker_output.tracking_active,
        'position': tracker_output.position_2d,
        'confidence': tracker_output.confidence,
        'timestamp': tracker_output.timestamp
    }
}
```

---

## API Integration

### Current Compatibility Endpoints

Current tracker data is still exposed through compatibility REST routes while
the `/api/v1` migration is pending:

```
GET /api/v1/tracking/catalog
GET /api/v1/tracking/runtime-status
GET /api/v1/tracking/telemetry
GET /api/tracker/output        # legacy compatibility
GET /api/tracker/capabilities  # legacy compatibility
```

New public API work must use typed `/api/v1/...` contracts from
`docs/apis/api-modernization-blueprint.md`.

### Live Tracker Reads

There is no dedicated tracker WebSocket route in the current API inventory.
External systems should poll the typed REST routes above for catalog, runtime,
and telemetry snapshots. Compatibility consumers may still poll
`GET /telemetry/tracker_data` while the dashboard/API migration continues.

---

## Data Buffering

### Handling Network Latency

```python
class GimbalTracker:
    def __init__(self, ...):
        self.data_buffer = deque(maxlen=10)
        self.DATA_TIMEOUT_SECONDS = 5.0

    def update(self, frame=None):
        data = self.gimbal_provider.get_current_data()

        if data:
            self.data_buffer.append(data)
            self.last_valid_time = time.time()
            return True, self._process_data(data)

        # Use buffered data if recent
        if (time.time() - self.last_valid_time) < self.DATA_TIMEOUT_SECONDS:
            output = self._get_cached_output()
            output.tracking_active = False
            return True, output

        return False, None
```

---

## Error Handling

### Connection Loss

```python
def update(self, frame=None):
    try:
        data = self.external_interface.get_data()
    except ConnectionError:
        logger.warning("External connection lost")
        self.consecutive_failures += 1

        if self.consecutive_failures > self.MAX_FAILURES:
            self._attempt_reconnect()

        return False, self._create_inactive_output("connection_lost")
```

### Data Validation

```python
def _validate_gimbal_data(self, data):
    # Validate angle ranges
    if not (-180 <= data.yaw <= 180):
        return False

    if not (-90 <= data.pitch <= 90):
        return False

    # Validate timestamp
    if data.timestamp < (time.time() - 5.0):
        return False  # Too old

    return True
```

---

## Related

- [Gimbal Tracker](../02-reference/gimbal-tracker.md) - Implementation details
- [Schema System](../04-configuration/schema-system.md) - EXTERNAL data type
- [Follower Integration](follower-integration.md) - Data consumption
