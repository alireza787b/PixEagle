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
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE | jq '.status'

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
# Via API
curl http://localhost:8000/api/telemetry/status

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
curl http://localhost:8088/mavlink/vehicles

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
mavlink2rest:
  data_points:
    - attitude      # Required
    - altitude      # Required
    - vfr_hud       # Required
    - heartbeat     # Required
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
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE | \
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

```python
# Check MavlinkDataManager status
curl http://localhost:8000/api/debug/mavlink_manager

# Look for:
# - polling_active: true
# - last_poll_time: recent timestamp
```

**Fix:** Restart PixEagle or just the polling:

```python
# Via API (if implemented)
curl -X POST http://localhost:8000/api/mavlink/restart_polling
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
curl -w "@curl-format.txt" http://localhost:8088/mavlink/vehicles
```

#### Poll Rate Too High

```yaml
# Reduce poll rate if server can't keep up
mavlink2rest:
  poll_rate_hz: 10  # Lower from 20
  timeout_s: 2.0    # Increase timeout
```

#### HTTP Connection Issues

```python
# In MavlinkDataManager logs
grep "timeout\|error\|failed" logs/pixeagle.log | grep mavlink
```

**Fix:** Increase timeout and add retry:

```yaml
mavlink2rest:
  timeout_s: 2.0
  retry_count: 3
```

### 4. Missing Specific Fields

**Symptoms:**
- Most data present
- Specific fields (e.g., altitude) missing
- Some messages not available

**Causes & Solutions:**

#### Message Not Published by PX4

```bash
# Check if message exists
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ALTITUDE

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
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ALTITUDE | jq
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
# Increase poll rate
mavlink2rest:
  poll_rate_hz: 30  # Higher rate = lower latency
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
time curl -s http://localhost:8088/mavlink/vehicles > /dev/null
```

## Diagnostic Tools

### Telemetry Monitor Script

```python
#!/usr/bin/env python3
"""Monitor telemetry health."""

import requests
import time

MAVLINK2REST = "http://localhost:8088"
MESSAGES = ['ATTITUDE', 'ALTITUDE', 'VFR_HUD', 'HEARTBEAT']

def check_message(name):
    url = f"{MAVLINK2REST}/mavlink/vehicles/1/components/1/messages/{name}"
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

mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20          # Balance between latency and load
  timeout_s: 1.0            # Reasonable timeout
  data_points:
    - attitude
    - altitude
    - vfr_hud
    - heartbeat
```

### For Low Latency

```yaml
mavlink2rest:
  poll_rate_hz: 50          # Higher rate
  timeout_s: 0.5            # Shorter timeout
```

### For Unreliable Networks

```yaml
mavlink2rest:
  poll_rate_hz: 10          # Lower rate
  timeout_s: 3.0            # Longer timeout
  retry_count: 3
```

## Related Documentation

- [MavlinkDataManager Component](../02-components/mavlink-data-manager.md)
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md)
- [MAVLink Configuration](../05-configuration/mavlink-config.md)
- [Connection Issues](connection-issues.md)
