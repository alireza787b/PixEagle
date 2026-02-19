# Follower Integration

> How trackers feed data to the follower system

This document covers the data flow from trackers to followers and the compatibility requirements.

---

## Data Flow Overview

```
┌──────────────────┐
│ Tracker          │
│ (CSRT, KCF, etc.)│
└────────┬─────────┘
         │ TrackerOutput
         ▼
┌──────────────────┐
│ AppController    │ ◄─── get_tracker_output()
└────────┬─────────┘
         │ TrackerOutput
         ▼
┌──────────────────┐
│ Follower         │ ◄─── follow_target(tracker_output)
│ (MC, FW, GM)     │
└────────┬─────────┘
         │ Vehicle Commands
         ▼
┌──────────────────┐
│ PX4/MAVSDK      │
└──────────────────┘
```

---

## TrackerOutput to Follower

### Position-Based Followers

Most multicopter and fixed-wing followers consume `POSITION_2D`:

```python
# In follower
def follow_target(self, tracker_output: TrackerOutput) -> None:
    if not tracker_output.tracking_active:
        self._handle_lost_target()
        return

    # Get normalized position
    x, y = tracker_output.position_2d

    # Compute control commands
    error_x = x - self.setpoint_x
    error_y = y - self.setpoint_y

    # Apply PID control
    cmd_x = self.pid_x.update(error_x)
    cmd_y = self.pid_y.update(error_y)

    # Send to vehicle
    self.send_velocity(cmd_x, cmd_y)
```

### Gimbal Followers

Gimbal followers consume `GIMBAL_ANGLES`:

```python
# In GMVelocityChaseFollower
def follow_target(self, tracker_output: TrackerOutput) -> None:
    if tracker_output.data_type != TrackerDataType.GIMBAL_ANGLES:
        logger.warning("Expected GIMBAL_ANGLES")
        return

    yaw, pitch, roll = tracker_output.angular

    # Use angles for gimbal control
    yaw_rate = self.pid_yaw.update(yaw - self.target_yaw)
    pitch_rate = self.pid_pitch.update(pitch - self.target_pitch)

    self.send_gimbal_rates(yaw_rate, pitch_rate)
```

---

## Schema Compatibility

### Compatible Tracker-Follower Pairs

| Tracker | Output Type | Compatible Followers |
|---------|-------------|---------------------|
| CSRT | POSITION_2D | MCVelocity*, FWAttitudeRate |
| KCF | VELOCITY_AWARE | MCVelocity*, FWAttitudeRate |
| dlib | POSITION_2D | MCVelocity*, FWAttitudeRate |
| Gimbal | GIMBAL_ANGLES | GMVelocityChase, GMVelocityVector |
| SmartTracker | MULTI_TARGET | MCVelocity* |

*MCVelocity includes all MC followers: Chase, Position, Distance, Ground

### Checking Compatibility

```python
from classes.schema_manager import check_compatibility

compatible = check_compatibility(
    tracker_type="CSRT",
    follower_type="MCVelocityChaseFollower"
)
# True
```

---

## Position Normalization

Trackers provide positions in normalized coordinates:

```
Frame:
+---------------------------+
|                           |
|    (-1, -1)     (1, -1)   |
|       +------------+      |
|       |            |      |
|       |   (0, 0)   |      |
|       |   center   |      |
|       +------------+      |
|    (-1, 1)      (1, 1)    |
|                           |
+---------------------------+
```

### Normalization Formula

```python
# In BaseTracker
normalized_x = (center_x - frame_width/2) / (frame_width/2)
normalized_y = (center_y - frame_height/2) / (frame_height/2)
```

### Using Normalized Position

```python
# Positive X = target is right of center → move right
# Positive Y = target is below center → move forward (in camera view)

def follow_target(self, tracker_output):
    x, y = tracker_output.position_2d

    # Common convention:
    # y > 0 → target below center → move forward
    # x > 0 → target right of center → move right

    forward_velocity = y * self.gain_forward
    lateral_velocity = x * self.gain_lateral
```

---

## Confidence Handling

Trackers provide confidence scores that followers should consider:

```python
def follow_target(self, tracker_output):
    if not tracker_output.tracking_active:
        self._handle_lost_target()
        return

    confidence = tracker_output.confidence or 0.0

    if confidence < self.min_confidence:
        # Low confidence - reduce gains or pause
        self._handle_low_confidence(confidence)
        return

    # High confidence - normal operation
    self._normal_follow(tracker_output)
```

### Confidence Thresholds

```yaml
# In follower schema
MCVelocityChaseFollower:
  min_tracking_confidence: 0.3
  reduced_gain_confidence: 0.5
```

---

## Velocity Data (Optional)

Some trackers provide velocity estimates:

```python
# KCF + Kalman provides velocity
if tracker_output.velocity:
    vx, vy = tracker_output.velocity

    # Use velocity for prediction
    predicted_x = x + vx * dt
    predicted_y = y + vy * dt
```

---

## Multi-Target Handling

SmartTracker can track multiple targets:

```python
def follow_target(self, tracker_output):
    if tracker_output.data_type == TrackerDataType.MULTI_TARGET:
        # Multiple targets available
        targets = tracker_output.targets

        # Get selected target
        selected_id = tracker_output.target_id
        selected = next(
            (t for t in targets if t['target_id'] == selected_id),
            None
        )

        if selected:
            # Follow selected target
            x, y = tracker_output.position_2d  # Already for selected
```

---

## AppController Integration

AppController coordinates tracker-follower interaction:

```python
# In AppController
def update(self):
    # Get tracker output
    tracker_output = self.tracker.get_output()

    # Check tracking state
    if tracker_output.tracking_active:
        # Feed to follower
        self.follower.follow_target(tracker_output)
    else:
        # Handle lost target
        self.follower.handle_target_lost()
```

---

## Error Handling

### Missing Data

```python
def follow_target(self, tracker_output):
    if tracker_output.position_2d is None:
        logger.warning("No position data")
        return

    x, y = tracker_output.position_2d
```

### Data Type Mismatch

```python
def follow_target(self, tracker_output):
    expected_types = [TrackerDataType.POSITION_2D, TrackerDataType.VELOCITY_AWARE]

    if tracker_output.data_type not in expected_types:
        logger.error(f"Incompatible data type: {tracker_output.data_type}")
        return
```

---

## Related

- [TrackerOutput](../01-architecture/tracker-output.md) - Output schema
- [Schema System](../04-configuration/schema-system.md) - Compatibility matrix
- [Follower Documentation](../../followers/README.md) - Follower system
