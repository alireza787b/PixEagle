# Offboard Mode Issues

This guide covers troubleshooting for PX4 offboard mode problems.

## Understanding Offboard Mode

### Requirements

PX4 offboard mode requires:

1. **Continuous setpoints** - At least 2 Hz (10+ Hz recommended)
2. **Initial setpoint** - Must be sent before entering offboard
3. **Valid setpoint** - Values within acceptable ranges
4. **Armed state** - Drone must be armed

### Mode Code

```python
OFFBOARD_MODE_CODE = 393216
```

## Common Issues

### 1. "Offboard Mode Rejected"

**Symptoms:**
- Mode switch fails
- PX4 stays in Position/Hold mode
- Log shows "Offboard rejected"

**Causes & Solutions:**

#### No Setpoints Before Mode Switch

```python
# WRONG - switching before sending setpoints
await drone.offboard.start()  # Rejected!

# CORRECT - send initial setpoint first
from mavsdk.offboard import VelocityBodyYawspeed

initial = VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
await drone.offboard.set_velocity_body(initial)
await asyncio.sleep(0.5)  # Let setpoint establish
await drone.offboard.start()  # Now accepted
```

#### Setpoint Rate Too Low

```yaml
# config_default.yaml
px4:
  offboard_rate_hz: 20  # Must be > 2 Hz
```

Check actual rate:

```bash
# In logs
grep "setpoint" logs/pixeagle.log | head -20

# Calculate rate
grep "setpoint" logs/pixeagle.log | \
  awk '{print $1}' | \
  uniq -c | head -5
```

### 2. "Failsafe: No Offboard"

**Symptoms:**
- Drone exits offboard mode
- Switches to Position Hold or RTL
- Log shows "No offboard" warning

**Causes & Solutions:**

#### Setpoint Stream Interrupted

Check for gaps in setpoint sending:

```bash
# Look for timing gaps
grep "send_velocity" logs/pixeagle.log | \
  awk '{print $1}' | \
  while read t; do echo "$t"; done
```

**Fix:** Ensure continuous sending even during calculations:

```python
class SetpointSender:
    """Continuous setpoint sender."""

    def __init__(self, rate_hz=20):
        self.rate = rate_hz
        self.last_setpoint = VelocityBodyYawspeed(0, 0, 0, 0)

    async def run(self):
        while self.active:
            # Always send, even if unchanged
            await self.drone.offboard.set_velocity_body(self.last_setpoint)
            await asyncio.sleep(1.0 / self.rate)
```

#### Thread/Async Conflict

```python
# WRONG - blocking in async context
def calculate_setpoint(self):
    time.sleep(0.5)  # Blocks everything!
    return setpoint

# CORRECT - non-blocking
async def calculate_setpoint(self):
    await asyncio.sleep(0.1)  # If delay needed
    return setpoint
```

### 3. "Mode Change Detected"

**Symptoms:**
- Unexpected mode transition
- PixEagle loses control
- Offboard exit callback triggered

**Causes & Solutions:**

#### RC Override

Pilot took manual control:

```python
# MavlinkDataManager monitors this
def _handle_flight_mode_change(self, new_mode):
    if self._was_in_offboard and new_mode != OFFBOARD_MODE:
        logger.warning(f"Exited offboard! New mode: {new_mode}")
        self._trigger_exit_callback()
```

**Mode codes:**

| Mode | Code | Reason |
|------|------|--------|
| Position | 196608 | RC override |
| Hold | 327680 | Manual hold |
| RTL | 84148224 | Safety/RC |
| Land | 50593792 | Low battery |

#### Geofence Violation

Check PX4 geofence settings:

```bash
# QGroundControl parameters
GF_ACTION = 1  # Warning only
GF_MAX_HOR_DIST = 200  # meters
GF_MAX_VER_DIST = 100  # meters
```

### 4. "Setpoint Rejected"

**Symptoms:**
- Commands sent but drone doesn't move
- No visible response
- Values seem to be ignored

**Causes & Solutions:**

#### Invalid Setpoint Values

```python
# Check for NaN or Inf
import math

def validate_setpoint(vel):
    if math.isnan(vel.forward_m_s) or math.isinf(vel.forward_m_s):
        raise ValueError("Invalid forward velocity")
    # ... check all fields
```

#### Control Type Mismatch

Mixing control types causes rejection:

```python
# WRONG - velocity then attitude without proper switch
await drone.offboard.set_velocity_body(velocity)
await drone.offboard.set_attitude_rate(attitude)  # May conflict

# CORRECT - stop and restart with new type
await drone.offboard.stop()
await drone.offboard.set_attitude_rate(initial_attitude)
await drone.offboard.start()
```

### 5. "Arm Rejected"

**Symptoms:**
- Cannot arm before offboard
- "Reject arm" in logs

**Causes & Solutions:**

#### Pre-arm Checks Failed

```bash
# Check in QGroundControl
# Vehicle Setup > Safety > Arming Checks
```

Common failures:
- No GPS lock
- Accelerometer not calibrated
- Safety switch not pressed

#### Kill Switch Active

```bash
# Check RC kill switch
# MAVLink HEARTBEAT will show CRIT_RC_ONLY
```

## Debugging Workflow

### 1. Check Setpoint Flow

```python
# Add debug logging
class PX4InterfaceManager:

    async def send_velocity_body(self, fields):
        logger.debug(f"Sending velocity: {fields}")

        velocity = VelocityBodyYawspeed(
            forward_m_s=fields['vel_body_fwd'],
            right_m_s=fields['vel_body_right'],
            down_m_s=fields['vel_body_down'],
            yawspeed_deg_s=fields['yawspeed_deg_s']
        )

        try:
            await self.drone.offboard.set_velocity_body(velocity)
            logger.debug("Velocity sent successfully")
        except Exception as e:
            logger.error(f"Velocity send failed: {e}")
```

### 2. Monitor Flight Mode

```python
# Register callback
def on_mode_change(mode):
    logger.info(f"Flight mode changed to: {mode}")

mavlink_manager.register_flight_mode_callback(on_mode_change)
```

### 3. Check MAVLink Messages

```bash
# Via MAVLink2REST
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/HEARTBEAT | jq

# Look at custom_mode field
# 393216 = Offboard
```

### 4. PX4 Logs

```bash
# Download flight log from SD card
# Analyze with Flight Review: https://logs.px4.io/

# Or use pyulog
ulog_info flight.ulg
ulog_params flight.ulg | grep OFFBOARD
```

## Configuration Checklist

### PixEagle Config

```yaml
# config_default.yaml

px4:
  connection_string: "udp://:14541"
  offboard_rate_hz: 20          # >= 10 Hz

safety:
  max_velocity_forward: 8.0
  max_velocity_lateral: 5.0
  max_velocity_vertical: 3.0
  max_yaw_rate: 45.0

circuit_breaker:
  active: false                  # Must be false for flight
```

### PX4 Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| COM_OF_LOSS_T | 0.5 | Offboard loss timeout (s) |
| COM_OBL_ACT | 0 | Action on loss (0=Land) |
| COM_RC_OVERRIDE | 0 | RC override in offboard |
| COM_RCL_EXCEPT | 4 | RC loss exceptions |

## Recovery Procedures

### If Offboard Fails During Flight

1. **RC Takeover**: Switch to Position mode
2. **RTL**: Trigger Return to Launch
3. **Land**: Initiate landing

```python
# Emergency RTL
async def emergency_rtl(self):
    """Trigger RTL on failure."""
    try:
        await self.drone.action.return_to_launch()
        logger.warning("RTL triggered due to offboard failure")
    except Exception as e:
        logger.error(f"RTL failed: {e}")
        # Last resort
        await self.drone.action.land()
```

### Automatic Recovery

```python
class PX4InterfaceManager:

    def __init__(self):
        self.offboard_retry_count = 0
        self.max_retries = 3

    async def handle_offboard_exit(self):
        """Handle unexpected offboard exit."""
        if self.offboard_retry_count < self.max_retries:
            logger.warning("Attempting offboard recovery...")
            await self._restart_offboard()
            self.offboard_retry_count += 1
        else:
            logger.error("Max retries reached, triggering RTL")
            await self.emergency_rtl()
```

## Related Documentation

- [PX4 Configuration](../05-configuration/px4-config.md)
- [MAVSDK Offboard API](../03-protocols/mavsdk-offboard.md)
- [Safety Integration](../05-configuration/safety-integration.md)
- [Connection Issues](connection-issues.md)
