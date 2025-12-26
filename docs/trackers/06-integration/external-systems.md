# External Systems Integration

> Gimbal integration, external sensors, and data protocols

This document covers integration with external tracking data sources.

---

## Gimbal Integration

### UDP Protocol

GimbalTracker receives data via UDP:

```python
# Message format (JSON over UDP)
{
    "timestamp": 1703000000.0,
    "angles": {
        "yaw": 45.0,      # degrees
        "pitch": -10.0,   # degrees
        "roll": 0.0       # degrees
    },
    "tracking_status": {
        "state": 2,       # 0=DISABLED, 1=SELECTING, 2=ACTIVE, 3=LOST
        "confidence": 0.95
    },
    "coordinate_system": "gimbal_body"
}
```

### Configuration

```yaml
# configs/config.yaml
TRACKING_ALGORITHM: "Gimbal"
GIMBAL_UDP_HOST: "192.168.0.108"
GIMBAL_LISTEN_PORT: 9004
GIMBAL_COORDINATE_SYSTEM: "GIMBAL_BODY"
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

### FastAPI Endpoints

Tracker data exposed via REST API:

```
GET /api/tracker/status
GET /api/tracker/output
POST /api/tracker/select/{target_id}
GET /api/tracker/capabilities
```

### WebSocket Streaming

Real-time tracker data:

```python
# WebSocket endpoint
@app.websocket("/ws/tracker")
async def tracker_ws(websocket: WebSocket):
    await websocket.accept()
    while True:
        output = tracker.get_output()
        await websocket.send_json(output.to_dict())
        await asyncio.sleep(0.033)  # 30 Hz
```

---

## Data Buffering

### Handling Network Latency

```python
class GimbalTracker:
    def __init__(self, ...):
        self.data_buffer = deque(maxlen=10)
        self.DATA_TIMEOUT_SECONDS = 5.0

    def update(self, frame=None):
        data = self.gimbal_interface.get_current_data()

        if data:
            self.data_buffer.append(data)
            self.last_valid_time = time.time()
            return True, self._process_data(data)

        # Use buffered data if recent
        if (time.time() - self.last_valid_time) < self.DATA_TIMEOUT_SECONDS:
            return True, self._get_cached_output()

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
