# Custom Telemetry

This guide covers how to add custom telemetry data points to the drone interface.

## Overview

Telemetry in PixEagle flows through:

1. **MAVLink2REST** - HTTP polling for MAVLink messages
2. **MavlinkDataManager** - Parsing and storage
3. **TelemetryHandler** - Formatting and broadcast

Adding custom telemetry involves extending each layer.

## Step 1: Identify MAVLink Message

### Find Available Messages

Check MAVLink2REST for available messages:

```bash
# List all message types
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages

# View specific message
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE
```

### Common MAVLink Messages

| Message | Fields | Use Case |
|---------|--------|----------|
| ATTITUDE | roll, pitch, yaw, rollspeed, pitchspeed, yawspeed | Orientation |
| ALTITUDE | altitude_relative, altitude_amsl | Height |
| VFR_HUD | groundspeed, airspeed, throttle, climb | Flight data |
| GLOBAL_POSITION_INT | lat, lon, alt, relative_alt, vx, vy, vz | GPS position |
| LOCAL_POSITION_NED | x, y, z, vx, vy, vz | Local position |
| BATTERY_STATUS | voltage, current, remaining | Battery |
| GPS_RAW_INT | fix_type, satellites_visible, hdop | GPS quality |

### Message Structure

MAVLink2REST returns JSON:

```json
{
  "message": {
    "type": "ATTITUDE",
    "roll": 0.05,
    "pitch": -0.02,
    "yaw": 1.57,
    "rollspeed": 0.001,
    "pitchspeed": 0.002,
    "yawspeed": 0.01
  },
  "status": {
    "time": {
      "first_message": "2024-01-01T12:00:00Z",
      "last_message": "2024-01-01T12:00:01Z",
      "frequency": 50.0
    }
  }
}
```

## Step 2: Add to MavlinkDataManager

### Define Data Point

```python
# src/classes/mavlink_data_manager.py

class MavlinkDataManager:

    def __init__(self):
        # Existing data...
        self.attitude = None
        self.altitude = None

        # New data point
        self.battery_status = None
        self.gps_quality = None
```

### Add Fetch Method

```python
class MavlinkDataManager:

    async def _fetch_battery_status(self):
        """Fetch battery status from MAVLink2REST."""
        url = f"{self.base_url}/mavlink/vehicles/1/components/1/messages/BATTERY_STATUS"

        try:
            response = await self._http_client.get(url, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                self._parse_battery_status(data)
        except Exception as e:
            logger.warning(f"Battery fetch failed: {e}")

    def _parse_battery_status(self, data: dict):
        """Parse battery status message."""
        message = data.get('message', {})

        self.battery_status = {
            'voltage_v': message.get('voltages', [0])[0] / 1000.0,  # mV to V
            'current_a': message.get('current_battery', 0) / 100.0,  # cA to A
            'remaining_pct': message.get('battery_remaining', -1),
            'timestamp': time.time()
        }
```

### Add to Polling Loop

```python
class MavlinkDataManager:

    async def _polling_loop(self):
        """Main polling loop."""
        while self._running:
            # Existing fetches...
            await self._fetch_attitude()
            await self._fetch_altitude()

            # New fetches
            if 'battery' in self.data_points:
                await self._fetch_battery_status()

            if 'gps_quality' in self.data_points:
                await self._fetch_gps_quality()

            await asyncio.sleep(1.0 / self.poll_rate_hz)
```

## Step 3: Configure Data Points

### Update Configuration

```yaml
# config_default.yaml

mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
  data_points:
    - attitude
    - altitude
    - vfr_hud
    - heartbeat
    # New data points
    - battery
    - gps_quality
```

### Load Configuration

```python
class MavlinkDataManager:

    def __init__(self, config: dict):
        self.data_points = config.get('data_points', [
            'attitude', 'altitude', 'vfr_hud', 'heartbeat'
        ])
```

## Step 4: Expose via API

### Add Getter Method

```python
class MavlinkDataManager:

    def get_battery_status(self) -> dict:
        """Get current battery status."""
        return self.battery_status or {
            'voltage_v': 0.0,
            'current_a': 0.0,
            'remaining_pct': -1,
            'timestamp': 0
        }

    def get_gps_quality(self) -> dict:
        """Get GPS quality information."""
        return self.gps_quality or {
            'fix_type': 0,
            'satellites': 0,
            'hdop': 99.0,
            'timestamp': 0
        }
```

### Integrate with TelemetryHandler

```python
# src/classes/telemetry_handler.py

class TelemetryHandler:

    def get_telemetry_packet(self) -> dict:
        """Build telemetry packet for broadcast."""
        return {
            # Existing data...
            'attitude': self.mavlink_manager.get_attitude(),
            'altitude': self.mavlink_manager.get_altitude(),

            # New data
            'battery': self.mavlink_manager.get_battery_status(),
            'gps_quality': self.mavlink_manager.get_gps_quality(),

            'timestamp': time.time()
        }
```

## Step 5: Add to FastAPI

### Create Endpoint

```python
# src/classes/fastapi_handler.py

@app.get("/api/telemetry/battery")
async def get_battery():
    """Get battery telemetry."""
    return mavlink_manager.get_battery_status()

@app.get("/api/telemetry/gps")
async def get_gps_quality():
    """Get GPS quality information."""
    return mavlink_manager.get_gps_quality()

@app.get("/api/telemetry/all")
async def get_all_telemetry():
    """Get all telemetry data."""
    return {
        'attitude': mavlink_manager.get_attitude(),
        'altitude': mavlink_manager.get_altitude(),
        'battery': mavlink_manager.get_battery_status(),
        'gps_quality': mavlink_manager.get_gps_quality(),
        'timestamp': time.time()
    }
```

## Example: GPS Quality Telemetry

### Complete Implementation

```python
# In MavlinkDataManager

async def _fetch_gps_quality(self):
    """Fetch GPS quality from GPS_RAW_INT."""
    url = f"{self.base_url}/mavlink/vehicles/1/components/1/messages/GPS_RAW_INT"

    try:
        response = await self._http_client.get(url, timeout=self.timeout)
        if response.status_code == 200:
            self._parse_gps_quality(response.json())
    except Exception as e:
        logger.warning(f"GPS quality fetch failed: {e}")

def _parse_gps_quality(self, data: dict):
    """Parse GPS_RAW_INT message."""
    message = data.get('message', {})

    # Fix type: 0=no fix, 1=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK float, 6=RTK fixed
    fix_type = message.get('fix_type', 0)

    self.gps_quality = {
        'fix_type': fix_type,
        'fix_type_name': self._get_fix_type_name(fix_type),
        'satellites': message.get('satellites_visible', 0),
        'hdop': message.get('eph', 9999) / 100.0,  # cm to m
        'vdop': message.get('epv', 9999) / 100.0,
        'timestamp': time.time()
    }

def _get_fix_type_name(self, fix_type: int) -> str:
    """Convert fix type to name."""
    names = {
        0: 'No GPS',
        1: 'No Fix',
        2: '2D Fix',
        3: '3D Fix',
        4: 'DGPS',
        5: 'RTK Float',
        6: 'RTK Fixed'
    }
    return names.get(fix_type, 'Unknown')
```

## Testing Custom Telemetry

### Unit Test

```python
# tests/unit/drone_interface/test_custom_telemetry.py

class TestBatteryTelemetry:
    """Tests for battery telemetry."""

    def test_battery_parsing(self):
        """Test battery message parsing."""
        manager = MavlinkDataManager(mock_config)

        raw_data = {
            'message': {
                'voltages': [22500],  # 22.5V in mV
                'current_battery': 1500,  # 15A in cA
                'battery_remaining': 75
            }
        }

        manager._parse_battery_status(raw_data)

        assert manager.battery_status['voltage_v'] == 22.5
        assert manager.battery_status['current_a'] == 15.0
        assert manager.battery_status['remaining_pct'] == 75


class TestGPSQuality:
    """Tests for GPS quality telemetry."""

    def test_fix_type_names(self):
        """Test fix type name conversion."""
        manager = MavlinkDataManager(mock_config)

        assert manager._get_fix_type_name(0) == 'No GPS'
        assert manager._get_fix_type_name(3) == '3D Fix'
        assert manager._get_fix_type_name(6) == 'RTK Fixed'
```

### Integration Test

```python
@pytest.mark.asyncio
async def test_battery_endpoint():
    """Test battery API endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/telemetry/battery")

        assert response.status_code == 200
        data = response.json()
        assert 'voltage_v' in data
        assert 'remaining_pct' in data
```

## Best Practices

1. **Rate Limiting**: Don't poll faster than MAVLink message rate
2. **Error Handling**: Handle connection failures gracefully
3. **Default Values**: Always provide sensible defaults
4. **Timestamps**: Include timestamps for staleness detection
5. **Units**: Document and convert units consistently
6. **Thread Safety**: Use locks for shared data access

## Related Documentation

- [MavlinkDataManager Component](../02-components/mavlink-data-manager.md)
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md)
- [TelemetryHandler Component](../02-components/telemetry-handler.md)
