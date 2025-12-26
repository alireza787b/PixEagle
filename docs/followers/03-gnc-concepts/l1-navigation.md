# L1 Navigation

> Lateral guidance for fixed-wing path following

L1 Navigation is a nonlinear guidance law designed for path following. It computes lateral acceleration to drive the aircraft toward a virtual point ahead on the desired path.

---

## Basic Principle

L1 guidance creates a "carrot" (L1 point) ahead of the aircraft and commands acceleration to reach it:

```
        L1 Distance
    ◄─────────────────►

Aircraft        L1 Point        Path/Target
    ●───────────────●─────────────────────
     \              │
      \  η (angle)  │ Cross-track error
       \            │
        ──────────►
        Velocity
```

---

## Algorithm

### Lateral Acceleration Command

```
a_cmd = 2 × (V²/L₁) × sin(η)
```

Where:
- `a_cmd` = Lateral acceleration command
- `V` = Groundspeed
- `L₁` = Look-ahead distance
- `η` = Angle to L1 point

### Yaw Rate Conversion

For rate-based control:

```
ω_yaw = a_cmd / V
```

---

## Implementation

### PixEagle FW Follower

```python
def _compute_l1_guidance(self, target_x: float) -> float:
    """
    Compute L1 lateral acceleration command.

    Args:
        target_x: Normalized target x position (-1 to +1)

    Returns:
        Yaw rate command (rad/s)
    """
    # Cross-track error estimation
    cross_track = target_x * self.reference_distance

    # Eta angle (angle to L1 point)
    eta = math.atan2(cross_track, self.l1_distance)

    # L1 lateral acceleration
    airspeed = self.current_airspeed
    lateral_accel = 2 * (airspeed ** 2 / self.l1_distance) * math.sin(eta)

    # Convert to yaw rate
    yaw_rate = lateral_accel / airspeed

    # Apply damping
    yaw_rate *= self.l1_damping

    return yaw_rate
```

---

## Parameter Selection

### L1 Distance

Controls tracking tightness:

| L1 Distance | Tracking | Overshoot | Use Case |
|-------------|----------|-----------|----------|
| Small (20m) | Tight | Higher | Aggressive following |
| Medium (50m) | Balanced | Moderate | General use |
| Large (100m) | Smooth | Low | Long-range tracking |

### Rule of Thumb

```
L₁ ≈ V × τ

Where:
τ = Time constant (2-5 seconds typical)
V = Cruise airspeed
```

### Adaptive L1

Speed-dependent L1 distance:

```python
if self.enable_l1_adaptive:
    # Scale L1 with airspeed
    l1_distance = self.l1_period * airspeed
    l1_distance = clip(l1_distance, self.l1_min, self.l1_max)
```

---

## L1 Period vs L1 Distance

Two equivalent parameterizations:

**L1 Distance** (meters):
```
L₁ = constant distance ahead
```

**L1 Period** (seconds):
```
L₁ = τ_L1 × V

Where τ_L1 = L1 period constant
```

PX4 uses L1 Period internally.

---

## Damping

L1 damping reduces oscillation:

```python
# Damped L1 guidance
yaw_rate = base_l1_rate * l1_damping

# Typical values
l1_damping = 0.75  # Standard
l1_damping = 0.5   # High damping (slower response)
l1_damping = 1.0   # No damping (may oscillate)
```

---

## Comparison with Other Methods

| Method | Advantages | Disadvantages |
|--------|------------|---------------|
| **L1** | Smooth, proven | Tuning required |
| **Pure Pursuit** | Simple | Poor at high speed |
| **Stanley** | Good for ground | Not ideal for air |
| **PN** | Target tracking | Not path following |

---

## Configuration

### FW Attitude Rate Follower

```yaml
FW_ATTITUDE_RATE:
  # L1 Navigation
  L1_DISTANCE: 50.0          # meters
  L1_DAMPING: 0.75          # 0.5-1.0
  ENABLE_L1_ADAPTIVE: false
  L1_MIN_DISTANCE: 20.0
  L1_MAX_DISTANCE: 100.0

  # L1 Period (alternative)
  L1_PERIOD: 3.0            # seconds (if adaptive enabled)
```

---

## Tuning Process

1. **Start with large L1** (100m) for stability
2. **Reduce gradually** until tracking is acceptable
3. **Adjust damping** if oscillation occurs
4. **Enable adaptive** for varying speeds

### Test Pattern

```
Straight path → Turn → Evaluate:
- Overshoot on entry
- Tracking in turn
- Recovery on exit
```

---

## Cross-Track Error Estimation

For image-based tracking:

```python
# Approximate cross-track from image position
reference_distance = 50.0  # meters (estimated target distance)
cross_track = target_x * reference_distance

# With known camera FOV
fov_rad = radians(70)  # 70° horizontal FOV
angle_to_target = target_x * (fov_rad / 2)
cross_track = reference_distance * tan(angle_to_target)
```

---

## Limitations

1. **Requires speed > 0** - Divide by zero at hover
2. **Assumes smooth path** - Not for sharp corners
3. **Distance estimation** - Image provides angle, not range
4. **Wind effects** - Groundspeed ≠ airspeed in wind

---

## References

- Park, S., Deyst, J., & How, J. P. (2004). *A New Nonlinear Guidance Logic for Trajectory Tracking*. AIAA GNC Conference.
- PX4 Autopilot L1 Controller: [docs.px4.io](https://docs.px4.io)
