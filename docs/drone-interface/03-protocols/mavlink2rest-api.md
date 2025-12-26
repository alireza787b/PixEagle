# MAVLink2REST API Reference

This document covers the MAVLink2REST HTTP API endpoints used by PixEagle for telemetry.

## Overview

MAVLink2REST provides a REST API for accessing MAVLink data via HTTP. PixEagle uses it as the primary telemetry source because it's more reliable than MAVSDK streams for high-frequency data.

## Base URL

Default configuration:
```
http://localhost:8088
```

Configurable via `config_default.yaml`:
```yaml
mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
```

## Endpoints Used by PixEagle

### GET /mavlink/vehicles/1/components/1/messages/{message_name}

Retrieves the latest message of a specific type.

#### ATTITUDE Endpoint

```http
GET /mavlink/vehicles/1/components/1/messages/ATTITUDE
```

Response:
```json
{
  "status": {
    "time": {
      "first_update": "2024-01-15T10:30:00Z",
      "last_update": "2024-01-15T10:30:01Z",
      "frequency": 50.0
    }
  },
  "message": {
    "type": "ATTITUDE",
    "time_boot_ms": 123456,
    "roll": 0.05,
    "pitch": -0.02,
    "yaw": 1.57,
    "rollspeed": 0.01,
    "pitchspeed": 0.0,
    "yawspeed": 0.02
  }
}
```

PixEagle extraction:
```python
def fetch_attitude_data(self):
    response = requests.get(f"{self.base_url}/.../ATTITUDE")
    data = response.json()
    return {
        'roll': math.degrees(data['message']['roll']),
        'pitch': math.degrees(data['message']['pitch']),
        'yaw': math.degrees(data['message']['yaw'])
    }
```

#### VFR_HUD Endpoint

```http
GET /mavlink/vehicles/1/components/1/messages/VFR_HUD
```

Response:
```json
{
  "message": {
    "type": "VFR_HUD",
    "airspeed": 5.5,
    "groundspeed": 5.2,
    "heading": 90,
    "throttle": 45,
    "alt": 50.0,
    "climb": 0.5
  }
}
```

PixEagle extraction (ground speed):
```python
def fetch_ground_speed(self):
    response = requests.get(f"{self.base_url}/.../VFR_HUD")
    data = response.json()
    vx = data['message'].get('vx', 0) / 100.0  # cm/s to m/s
    vy = data['message'].get('vy', 0) / 100.0
    return math.sqrt(vx*vx + vy*vy)
```

#### ALTITUDE Endpoint

```http
GET /mavlink/vehicles/1/components/1/messages/ALTITUDE
```

Response:
```json
{
  "message": {
    "type": "ALTITUDE",
    "time_usec": 123456789,
    "altitude_monotonic": 125.5,
    "altitude_amsl": 125.5,
    "altitude_local": 25.5,
    "altitude_relative": 25.5,
    "altitude_terrain": 30.0,
    "bottom_clearance": 25.5
  }
}
```

PixEagle uses `altitude_relative` for tracking:
```python
def fetch_altitude_data(self):
    response = requests.get(f"{self.base_url}/.../ALTITUDE")
    data = response.json()
    return {
        'altitude_relative': data['message']['altitude_relative']
    }
```

#### HEARTBEAT Endpoint

```http
GET /mavlink/vehicles/1/components/1/messages/HEARTBEAT
```

Response:
```json
{
  "message": {
    "type": "HEARTBEAT",
    "custom_mode": 393216,
    "type": 2,
    "autopilot": 12,
    "base_mode": 157,
    "system_status": 4,
    "mavlink_version": 3
  }
}
```

Flight mode extraction:
```python
def _get_current_flight_mode(self):
    response = requests.get(f"{self.base_url}/.../HEARTBEAT")
    data = response.json()
    return data['message']['custom_mode']

# Mode codes
OFFBOARD_MODE = 393216
POSITION_MODE = 196608
```

## Data Access Pattern

### MavlinkDataManager Implementation

```python
class MavlinkDataManager:
    def __init__(self):
        self.base_url = Parameters.MAVLINK2REST_URL
        self.poll_rate = Parameters.MAVLINK2REST_POLL_RATE
        self._running = False
        self._data = {}
        self._lock = threading.Lock()

    def start_polling(self):
        """Start background polling thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop)
        self._thread.daemon = True
        self._thread.start()

    def _poll_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                attitude = self._fetch_attitude()
                altitude = self._fetch_altitude()
                ground_speed = self._fetch_ground_speed()
                heartbeat = self._fetch_heartbeat()

                with self._lock:
                    self._data.update({
                        'attitude': attitude,
                        'altitude': altitude,
                        'ground_speed': ground_speed,
                        'flight_mode': heartbeat['custom_mode']
                    })
            except Exception as e:
                logger.warning(f"Polling error: {e}")

            time.sleep(1.0 / self.poll_rate)
```

## Error Handling

### Connection Errors

```python
def _safe_request(self, endpoint):
    """Make request with error handling."""
    try:
        response = requests.get(
            f"{self.base_url}/{endpoint}",
            timeout=1.0
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logger.warning("MAVLink2REST request timeout")
        return None
    except requests.ConnectionError:
        logger.error("Cannot connect to MAVLink2REST")
        return None
    except requests.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        return None
```

### Missing Data Handling

```python
def _extract_nested(self, data, *keys):
    """Safely extract nested data."""
    for key in keys:
        if data is None or not isinstance(data, dict):
            return None
        data = data.get(key)
    return data

# Usage
roll = self._extract_nested(response, 'message', 'roll')
if roll is not None:
    self._data['roll'] = math.degrees(roll)
```

## Configuration

### YAML Configuration

```yaml
mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
  timeout_s: 1.0

  # Endpoints configuration
  endpoints:
    attitude: "/mavlink/vehicles/1/components/1/messages/ATTITUDE"
    altitude: "/mavlink/vehicles/1/components/1/messages/ALTITUDE"
    vfr_hud: "/mavlink/vehicles/1/components/1/messages/VFR_HUD"
    heartbeat: "/mavlink/vehicles/1/components/1/messages/HEARTBEAT"
```

### Parameter Access

```python
class Parameters:
    # MAVLink2REST settings
    MAVLINK2REST_ENABLED = True
    MAVLINK2REST_URL = "http://localhost:8088"
    MAVLINK2REST_POLL_RATE = 20  # Hz
```

## Rate Limiting

MAVLink2REST reflects the autopilot's message rates:

| Message | Typical Rate | Poll Recommendation |
|---------|-------------|---------------------|
| ATTITUDE | 50 Hz | 20-50 Hz |
| VFR_HUD | 4 Hz | 4-10 Hz |
| ALTITUDE | 10 Hz | 10-20 Hz |
| HEARTBEAT | 1 Hz | 1-2 Hz |

PixEagle uses a single poll rate (default 20 Hz) and filters stale data.

## Debugging

### Verify MAVLink2REST is Running

```bash
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/HEARTBEAT
```

### Check Available Messages

```bash
curl http://localhost:8088/mavlink/vehicles
```

### Enable Debug Logging

```python
import logging
logging.getLogger('classes.mavlink_data_manager').setLevel(logging.DEBUG)
```

## Related Documentation

- [MAVLink Overview](mavlink-overview.md) - Protocol basics
- [MAVSDK Offboard](mavsdk-offboard.md) - Command interface
- [MavlinkDataManager Component](../02-components/mavlink-data-manager.md) - Implementation details
