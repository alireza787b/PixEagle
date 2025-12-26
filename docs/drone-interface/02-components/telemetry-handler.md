# TelemetryHandler

> Data formatting and UDP broadcast for telemetry.

**Source**: `src/classes/telemetry_handler.py` (~271 lines)

## Overview

TelemetryHandler collects telemetry data from tracker and follower systems, formats it for consumption, and optionally broadcasts via UDP.

Key responsibilities:
- Gather tracker data (multiple output types)
- Gather follower data (setpoints, flight mode)
- Rate-limited UDP broadcast
- Legacy format compatibility

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TelemetryHandler                             │
├─────────────────────────────────────────────────────────────────┤
│  Configuration:                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ host: str               # UDP_HOST                       │    │
│  │ port: int               # UDP_PORT                       │    │
│  │ send_rate: int          # TELEMETRY_SEND_RATE            │    │
│  │ enable_udp: bool        # ENABLE_UDP_STREAM              │    │
│  │ send_interval: float    # 1/send_rate                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Data Sources:                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ app_controller          # Reference to main controller   │    │
│  │ tracker                 # Tracker instance               │    │
│  │ follower                # Follower instance              │    │
│  │ tracking_started_flag   # Callable for status            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  State:                                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ udp_socket              # UDP socket                     │    │
│  │ last_sent_time          # Rate limiting                  │    │
│  │ latest_tracker_data     # Cached tracker data            │    │
│  │ latest_follower_data    # Cached follower data           │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Key Methods:                                                    │
│  • send_telemetry()                                             │
│  • get_tracker_data() → dict                                    │
│  • get_follower_data() → dict                                   │
│  • gather_telemetry_data() → dict                               │
└─────────────────────────────────────────────────────────────────┘
```

## Initialization

```python
def __init__(self, app_controller, tracking_started_flag):
    """
    Initialize TelemetryHandler.

    Args:
        app_controller: AppController instance
        tracking_started_flag: Callable returning tracking status
    """
    self.host = Parameters.UDP_HOST
    self.port = Parameters.UDP_PORT
    self.send_rate = Parameters.TELEMETRY_SEND_RATE
    self.enable_udp = Parameters.ENABLE_UDP_STREAM

    self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.server_address = (self.host, self.port)
    self.send_interval = 1.0 / self.send_rate

    self.app_controller = app_controller
    self.tracker = self.app_controller.tracker
    self.follower = self.app_controller.follower
```

## Telemetry Gathering

### send_telemetry()

```python
def send_telemetry(self):
    """
    Send telemetry if rate limit allows.

    - Checks send interval
    - Gathers all telemetry data
    - Sends via UDP if enabled
    - Always updates cached data
    """
    if self.should_send_telemetry() and self.enable_udp:
        data = self.gather_telemetry_data()
        message = json.dumps(data)
        self.udp_socket.sendto(message.encode('utf-8'), self.server_address)
        self.last_sent_time = datetime.utcnow()

    # Always update cached data
    self.latest_tracker_data = self.get_tracker_data()
    if Parameters.ENABLE_FOLLOWER_TELEMETRY:
        self.latest_follower_data = self.get_follower_data()
```

### gather_telemetry_data()

```python
def gather_telemetry_data(self) -> dict:
    """
    Gather telemetry from all sources.

    Returns:
        {
            'tracker_data': {...},
            'follower_data': {...}
        }
    """
    return {
        'tracker_data': self.get_tracker_data(),
        'follower_data': self.get_follower_data(),
    }
```

## Tracker Data

### get_tracker_data()

```python
def get_tracker_data(self) -> dict:
    """
    Get latest tracker telemetry using flexible schema.

    Supports multiple tracker output types:
    - POSITION_2D: normalized bbox, center
    - POSITION_3D: x, y, depth
    - ANGULAR: bearing, elevation
    - GIMBAL_ANGLES: yaw, pitch, roll
    - MULTI_TARGET: multiple targets
    """
    # Try structured TrackerOutput first
    if hasattr(self.app_controller, 'get_tracker_output'):
        tracker_output = self.app_controller.get_tracker_output()
        if tracker_output:
            return self._format_tracker_data(tracker_output, ...)

    # Fallback to legacy format
    return self._get_legacy_tracker_data(...)
```

### _format_tracker_data()

Formats structured TrackerOutput for telemetry:

```python
def _format_tracker_data(
    self, tracker_output: TrackerOutput, timestamp: str, tracker_started: bool
) -> dict:
    """
    Format TrackerOutput with backwards compatibility.

    Returns:
        {
            # Legacy fields (backwards compatible)
            'bounding_box': [x, y, w, h],
            'center': [cx, cy],
            'timestamp': '...',
            'tracker_started': bool,

            # Enhanced structured data
            'tracker_data': {
                'data_type': 'position_2d' | 'position_3d' | 'angular' | ...,
                'tracker_id': '...',
                'tracking_active': bool,
                'confidence': float,
                'timestamp': '...',

                # Type-specific fields
                'position_2d': [x, y],
                'velocity': {'vx': ..., 'vy': ..., 'magnitude': ...},
                'quality_metrics': {...}
            }
        }
    """
```

### Data Type Specific Formatting

```python
if tracker_output.data_type == TrackerDataType.POSITION_2D:
    data['tracker_data'].update({
        'position_2d': tracker_output.position_2d,
        'bbox_pixel': tracker_output.bbox,
        'normalized_bbox': tracker_output.normalized_bbox
    })

elif tracker_output.data_type == TrackerDataType.GIMBAL_ANGLES:
    data['tracker_data'].update({
        'angular': tracker_output.angular,
        'yaw': tracker_output.angular[0],
        'pitch': tracker_output.angular[1],
        'roll': tracker_output.angular[2],
        'coordinate_system': tracker_output.raw_data.get('coordinate_system'),
        'gimbal_tracking_active': tracker_output.raw_data.get('gimbal_tracking_active')
    })
```

## Follower Data

### get_follower_data()

```python
def get_follower_data(self) -> dict:
    """
    Get latest follower telemetry.

    Returns:
        {
            # From follower.get_follower_telemetry()
            'setpoints': {...},
            'error_metrics': {...},

            # Added by handler
            'following_active': bool,
            'profile_name': '...',

            # If MAVLink enabled
            'flight_mode': int,
            'flight_mode_text': '...',
            'is_offboard': bool
        }
    """
```

**Flight Mode Integration**:
```python
if Parameters.MAVLINK_ENABLED:
    flight_mode_code = self.app_controller.mavlink_data_manager.get_data('flight_mode')
    if flight_mode_code and flight_mode_code != 'N/A':
        telemetry['flight_mode'] = flight_mode_code
        telemetry['flight_mode_text'] = px4_interface.get_flight_mode_text(flight_mode_code)
        telemetry['is_offboard'] = (flight_mode_code == 393216)
```

## Rate Limiting

### should_send_telemetry()

```python
def should_send_telemetry(self) -> bool:
    """
    Check if enough time has passed since last send.

    Returns:
        bool: True if send_interval elapsed
    """
    current_time = datetime.utcnow()
    return (current_time - self.last_sent_time).total_seconds() >= self.send_interval
```

## UDP Broadcast

The telemetry data is JSON-encoded and sent via UDP:

```python
message = json.dumps(data)
self.udp_socket.sendto(message.encode('utf-8'), self.server_address)
```

**Typical consumers**:
- Ground control stations
- Dashboard applications
- Logging systems
- Third-party integrations

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `UDP_HOST` | "127.0.0.1" | Broadcast destination |
| `UDP_PORT` | 5005 | Broadcast port |
| `TELEMETRY_SEND_RATE` | 10 | Hz |
| `ENABLE_UDP_STREAM` | true | Enable UDP broadcast |
| `ENABLE_FOLLOWER_TELEMETRY` | true | Include follower data |

## Output Format

### Full Telemetry Message

```json
{
  "tracker_data": {
    "bounding_box": [0.45, 0.48, 0.10, 0.15],
    "center": [0.50, 0.55],
    "timestamp": "2024-01-15T10:30:00.000Z",
    "tracker_started": true,
    "tracker_data": {
      "data_type": "position_2d",
      "tracker_id": "csrt_tracker",
      "tracking_active": true,
      "confidence": 0.85,
      "position_2d": [0.50, 0.55],
      "velocity": {
        "vx": 0.02,
        "vy": -0.01,
        "magnitude": 0.022
      }
    }
  },
  "follower_data": {
    "following_active": true,
    "profile_name": "MC Velocity Position",
    "setpoints": {
      "vel_body_fwd": 2.5,
      "vel_body_right": 0.0,
      "vel_body_down": -0.5,
      "yawspeed_deg_s": 15.0
    },
    "flight_mode": 393216,
    "flight_mode_text": "Offboard",
    "is_offboard": true
  }
}
```

## Legacy Compatibility

For trackers not using TrackerOutput:

```python
def _get_legacy_tracker_data(self, timestamp: str, tracker_started: bool) -> dict:
    """
    Fallback for legacy tracker data extraction.
    """
    return {
        'bounding_box': getattr(self.tracker, 'normalized_bbox', None),
        'center': getattr(self.tracker, 'normalized_center', None),
        'timestamp': timestamp,
        'tracker_started': tracker_started,
        'tracker_data': {
            'data_type': 'position_2d',
            'tracker_id': 'legacy_tracker',
            'tracking_active': tracker_started,
            'legacy_mode': True
        }
    }
```

## Related Documentation

- [Tracker System](../../trackers/README.md) - Tracker data sources
- [Follower System](../../followers/README.md) - Follower telemetry
- [PX4InterfaceManager](px4-interface-manager.md) - Flight mode data
