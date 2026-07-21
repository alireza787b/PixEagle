# Telemetry Gaps

This guide covers troubleshooting for telemetry data reception issues.

## Understanding Telemetry Flow

```
PX4 → MAVLink → mavlink-router → MAVLink2REST → MavlinkDataManager
                              ↘
                                MAVSDK → PX4InterfaceManager
```

## Quick Diagnosis

### Check Telemetry Status

```bash
# MAVLink2REST status
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE | jq '.status'

# Expected output
{
  "time": {
    "first_message": "2024-01-01T12:00:00Z",
    "last_message": "2024-01-01T12:01:00Z",
    "frequency": 50.0
  }
}
```

### Check PixEagle Telemetry

```bash
# Via PixEagle API
curl http://127.0.0.1:5077/telemetry/follower_data
curl http://127.0.0.1:5077/api/follower/setpoints-status

# Or check logs
grep "telemetry" logs/pixeagle.log | tail -20
```

## Common Issues

### 1. No Telemetry Data

**Symptoms:**
- All values are zero or null
- Dashboard shows "No Data"
- Timestamps not updating

**Causes & Solutions:**

#### MAVLink2REST Not Receiving

```bash
# Check vehicle count
curl http://127.0.0.1:8088/v1/mavlink/vehicles

# Expected: {"vehicles":[1]}
# Problem: {"vehicles":[]}
```

**Fix:** Check MAVLink source:

```bash
# Is SITL running?
ps aux | grep px4

# Is mavlink-router forwarding to MAVLink2REST?
cat /etc/mavlink-router/main.conf | grep -A3 "mavlink2rest"
```

#### Wrong Data Points Configured

```yaml
# config_default.yaml
MAVLink:
  MAVLINK_DATA_POINTS:
    roll: /vehicles/1/components/1/messages/ATTITUDE/message/roll
    pitch: /vehicles/1/components/1/messages/ATTITUDE/message/pitch
    altitude_msl: /vehicles/1/components/1/messages/ALTITUDE/message/altitude_amsl
    altitude_agl: /vehicles/1/components/1/messages/ALTITUDE/message/altitude_relative
    groundspeed: /vehicles/1/components/1/messages/VFR_HUD/message/groundspeed
    flight_mode: /vehicles/1/components/1/messages/HEARTBEAT/message/custom_mode
    arm_status: /vehicles/1/components/1/messages/HEARTBEAT/message/base_mode
```

### 2. Stale Telemetry (Old Data)

**Symptoms:**
- Data present but not updating
- Timestamps in the past
- Frequency shows 0 Hz

**Causes & Solutions:**

#### Message Source Stopped

```bash
# Check message frequency
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE | \
  jq '.status.time.frequency'

# If 0 or very low, source isn't sending
```

**Fix:** Restart MAVLink source:

```bash
# Restart SITL
cd ~/PX4-Autopilot
make px4_sitl gazebo

# Or restart mavlink-router
sudo systemctl restart mavlink-router
```

#### Polling Loop Stuck

```bash
# Check follower/setpoint visibility exposed by the current API
curl http://127.0.0.1:5077/api/follower/setpoints-status

# Check recent telemetry broadcast payload
curl http://127.0.0.1:5077/telemetry/follower_data
```

**Fix:** Restart PixEagle after confirming MAVLink2REST is healthy:

```bash
bash scripts/stop.sh
bash scripts/run.sh --no-attach
```

### 3. Intermittent Data Loss

**Symptoms:**
- Data comes and goes
- Gaps in telemetry stream
- Occasional timeout errors

**Causes & Solutions:**

#### Network Issues

```bash
# Check for packet loss
ping -c 100 localhost | grep loss

# Check network latency
curl -w "@curl-format.txt" http://127.0.0.1:8088/v1/mavlink/vehicles
```

#### Poll Rate Too High

```yaml
# Increase interval if the local server or companion computer cannot keep up.
MAVLink:
  MAVLINK_POLLING_INTERVAL: 1.0
  MAVLINK_REQUEST_TIMEOUT_S: 5.0
  MAVLINK_REQUEST_RETRIES: 1
  MAVLINK_STALE_TIMEOUT_S: 3.0
```

#### HTTP Connection Issues

```python
# In MavlinkDataManager logs
grep "timeout\|error\|failed" logs/pixeagle.log | grep mavlink
```

**Fix:** confirm MAVLink2REST is local and healthy, then tune the typed
MAVLink freshness settings if the companion computer is overloaded. `/status`
exposes `mavlink_telemetry.status`, `fresh`, `last_success_age_s`,
`request_timeout_s`, `request_retries`, and `last_error`. For new
diagnostics, query `GET /api/v1/telemetry/health` and inspect
`transport.latest_request_ok`, `transport.latest_request_result`,
`request_freshness.fresh`, and `payload.has_payload`. A degraded response means
the cached payload can still be fresh even though the newest MAVLink2REST
request failed.

```bash
bash scripts/stop.sh
bash scripts/run.sh --no-attach
```

The full launcher owns MAVLink2REST. Do not start a second bridge beside an
active manual or managed PixEagle runtime.

### 4. Missing Specific Fields

**Symptoms:**
- Most data present
- Specific fields (e.g., altitude) missing
- Some messages not available

**Causes & Solutions:**

#### Message Not Published by PX4

```bash
# Check if message exists
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE

# If 404, PX4 might not be sending it
```

**Fix:** Configure PX4 to send message:

```bash
# In QGroundControl or via MAVLink
# Set message rate
param set MAV_0_RATE 50  # Hz for main telemetry
```

#### Parsing Error

```python
# Check for parsing errors in logs
grep "parse\|KeyError\|TypeError" logs/pixeagle.log | grep mavlink
```

**Fix:** Check message structure:

```bash
# View raw message
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE | jq
```

### 5. Wrong Values

**Symptoms:**
- Data present but incorrect
- Units seem wrong
- Values don't match QGroundControl

**Causes & Solutions:**

#### Unit Conversion Errors

```python
# Common unit issues:
# - Attitude in radians (convert to degrees)
# - Altitude in mm (convert to m)
# - Velocity in cm/s (convert to m/s)

# In MavlinkDataManager
def _parse_attitude(self, data):
    import math
    message = data.get('message', {})

    self.attitude = {
        'roll_deg': math.degrees(message.get('roll', 0)),   # rad to deg
        'pitch_deg': math.degrees(message.get('pitch', 0)),
        'yaw_deg': math.degrees(message.get('yaw', 0))
    }
```

#### Frame Reference Issues

```
NED Frame (PX4):
- North = +X
- East = +Y
- Down = +Z (altitude is negative when above ground)

Body Frame:
- Forward = +X
- Right = +Y
- Down = +Z
```

### 6. High Latency

**Symptoms:**
- Data arrives late
- Noticeable delay in dashboard
- Timestamps significantly behind

**Causes & Solutions:**

#### Polling Interval Too Long

```yaml
# Lower interval = lower latency, with higher CPU/network load.
MAVLink:
  MAVLINK_POLLING_INTERVAL: 0.2
```

#### Processing Delay

```python
# Check processing time
import time

class MavlinkDataManager:
    async def _fetch_attitude(self):
        start = time.time()
        # ... fetch and parse ...
        elapsed = time.time() - start
        if elapsed > 0.05:  # 50ms
            logger.warning(f"Slow attitude fetch: {elapsed:.3f}s")
```

#### Network Latency

```bash
# Measure round-trip time
time curl -s http://127.0.0.1:8088/v1/mavlink/vehicles > /dev/null
```

## Diagnostic Tools

### Telemetry Monitor Script

```python
#!/usr/bin/env python3
"""Monitor telemetry health."""

import requests
import time

MAVLINK2REST = "http://127.0.0.1:8088"
MESSAGES = ['ATTITUDE', 'ALTITUDE', 'VFR_HUD', 'HEARTBEAT']

def check_message(name):
    url = f"{MAVLINK2REST}/v1/mavlink/vehicles/1/components/1/messages/{name}"
    try:
        r = requests.get(url, timeout=1)
        if r.status_code == 200:
            data = r.json()
            freq = data.get('status', {}).get('time', {}).get('frequency', 0)
            return f"{name}: {freq:.1f} Hz"
        return f"{name}: NOT FOUND"
    except Exception as e:
        return f"{name}: ERROR ({e})"

while True:
    print("\033[H\033[J")  # Clear screen
    print("=== Telemetry Monitor ===")
    for msg in MESSAGES:
        print(check_message(msg))
    print(f"\nTime: {time.strftime('%H:%M:%S')}")
    time.sleep(1)
```

### Log Analysis

```bash
# Find telemetry errors
grep -i "telemetry\|mavlink" logs/pixeagle.log | grep -i "error\|warn\|fail"

# Check update frequency
grep "attitude_updated" logs/pixeagle.log | \
  awk '{print $1}' | uniq -c

# Find gaps (more than 1 second between updates)
grep "attitude" logs/pixeagle.log | \
  awk 'NR>1 {print $1-prev} {prev=$1}' | \
  awk '$1 > 1 {print "Gap:", $1, "seconds"}'
```

## Configuration Optimization

### For Reliable Telemetry

```yaml
# config_default.yaml

MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5
  MAVLINK_DATA_POINTS:
    roll: /vehicles/1/components/1/messages/ATTITUDE/message/roll
    pitch: /vehicles/1/components/1/messages/ATTITUDE/message/pitch
    altitude_msl: /vehicles/1/components/1/messages/ALTITUDE/message/altitude_amsl
    altitude_agl: /vehicles/1/components/1/messages/ALTITUDE/message/altitude_relative
    groundspeed: /vehicles/1/components/1/messages/VFR_HUD/message/groundspeed
    flight_mode: /vehicles/1/components/1/messages/HEARTBEAT/message/custom_mode
    arm_status: /vehicles/1/components/1/messages/HEARTBEAT/message/base_mode
```

### For Low Latency

```yaml
MAVLink:
  MAVLINK_POLLING_INTERVAL: 0.2
```

### For Unreliable Networks

```yaml
MAVLink:
  MAVLINK_POLLING_INTERVAL: 1.0
```

## Related Documentation

- [MavlinkDataManager Component](../02-components/mavlink-data-manager.md)
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md)
- [MAVLink Configuration](../05-configuration/mavlink-config.md)
- [Connection Issues](connection-issues.md)
