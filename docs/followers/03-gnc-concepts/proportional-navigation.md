# Proportional Navigation

> Target pursuit guidance for multicopter tracking

Proportional Navigation (PN) is a missile guidance law adapted for drone target tracking. It commands lateral acceleration proportional to the line-of-sight rate.

---

## Basic Principle

The pursuer (drone) should turn at a rate proportional to the rate of rotation of the line-of-sight (LOS) to the target:

```
a_c = N × V_c × λ̇
```

Where:
- `a_c` = Commanded lateral acceleration
- `N` = Navigation constant (typically 3-5)
- `V_c` = Closing velocity
- `λ̇` = Line-of-sight rate

---

## Line-of-Sight Geometry

```
                    Target
                      ●
                     /
                    /  λ (LOS angle)
                   /
                  /
    Drone ●──────┘
           ──────→ Velocity vector
```

### LOS Rate Calculation

```python
# LOS angle from image position
lambda_angle = atan2(target_y, target_x)

# LOS rate (angular velocity)
lambda_dot = (lambda_angle - lambda_prev) / dt
```

---

## PN Variants

### Pure Proportional Navigation (PPN)

Acceleration perpendicular to LOS:

```python
a_command = N * closing_velocity * lambda_dot
```

### True Proportional Navigation (TPN)

Acceleration perpendicular to velocity:

```python
a_perpendicular = N * closing_velocity * lambda_dot * cos(heading_error)
```

### Augmented Proportional Navigation (APN)

Adds target acceleration compensation:

```python
a_command = N * closing_velocity * lambda_dot + 0.5 * N * target_accel
```

---

## Implementation in PixEagle

### mc_velocity_chase Uses PN Concepts

While not pure PN, the chase follower applies PN principles:

```python
# Simplified PN-like behavior
lateral_error = target_x  # Normalized position
lateral_velocity = pid_lateral(lateral_error)  # PID approximates PN

# Yaw rate (coordinated turn mode)
yaw_rate = pid_yaw(lateral_error)  # Turn toward target
```

### Navigation Constant Selection

| N Value | Behavior | Use Case |
|---------|----------|----------|
| 2 | Gentle curves | Slow targets |
| 3 | Standard | General pursuit |
| 4-5 | Aggressive | Fast/maneuvering targets |

---

## Coordinate Transform

Image coordinates to LOS angle:

```python
# Image position (normalized -1 to +1)
target_x = tracker_output.position_2d[0]
target_y = tracker_output.position_2d[1]

# Approximate LOS angle (radians)
fov_h = 70 * (pi / 180)  # Horizontal FOV
lambda_x = target_x * fov_h / 2

# LOS rate estimation
lambda_dot = (lambda_x - self.lambda_prev) / dt
self.lambda_prev = lambda_x
```

---

## Closing Velocity Estimation

For PN, closing velocity is important:

```python
# Option 1: Use forward velocity as proxy
closing_velocity = forward_velocity

# Option 2: Estimate from target apparent size change
if tracker_output.bbox_size:
    size_rate = (current_size - prev_size) / dt
    closing_velocity = estimate_from_size_rate(size_rate)
```

---

## Tuning Guidelines

### Conservative Settings

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 5.0
  LATERAL_GUIDANCE_MODE: "sideslip"  # Direct lateral
```

### Aggressive Pursuit

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 12.0
  LATERAL_GUIDANCE_MODE: "coordinated_turn"
  ENABLE_AUTO_MODE_SWITCHING: true
```

---

## Limitations

1. **Pure PN assumes constant target velocity** - Real targets accelerate
2. **Image-based LOS** - Less accurate than radar/LIDAR
3. **Discrete updates** - Tracker runs at 20-30Hz, not continuous
4. **No range information** - 2D image provides azimuth/elevation only

---

## Advanced Topics

### Target Maneuver Detection

Detect evasive maneuvers from LOS rate changes:

```python
if abs(lambda_dot) > threshold:
    # Target maneuvering, increase N
    navigation_constant = 5
else:
    navigation_constant = 3
```

### Predictive Pursuit

Use velocity-aware tracking:

```python
# Predict target position
predicted_x = target_x + target_vx * dt
predicted_y = target_y + target_vy * dt

# Aim for predicted position
lambda_predicted = atan2(predicted_y, predicted_x)
```

---

## References

- Zarchan, P. (2012). *Tactical and Strategic Missile Guidance* (6th ed.). AIAA.
- Shneydor, N. A. (1998). *Missile Guidance and Pursuit*. Horwood Publishing.
