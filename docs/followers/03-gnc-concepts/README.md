# GNC Concepts

> Guidance, Navigation, and Control algorithms in PixEagle

This section covers the theoretical foundations of the control algorithms used in PixEagle's follower system.

---

## Algorithm Overview

| Algorithm | Domain | Used By | Purpose |
|-----------|--------|---------|---------|
| [Gimbal Chase Forward Speed](gimbal-forward-speed.md) | Pursuit speed | gm_velocity_chase | Implemented bounded speed modes |
| [Proportional Navigation](proportional-navigation.md) | Design note | Not implemented | Future adapter acceptance boundary |
| [L1 Navigation](l1-navigation.md) | Path following | fw_attitude_rate | Lateral guidance |
| [TECS](tecs.md) | Energy management | fw_attitude_rate | Pitch/throttle coordination |
| [PID Control](pid-control.md) | Feedback | All followers | Error correction |

---

## Control Hierarchy

```
                    ┌─────────────────────┐
                    │   GUIDANCE LAYER    │
                    │   (Path Planning)   │
                    │                     │
                    │   PN, L1, Waypoint  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   CONTROL LAYER     │
                    │   (Rate/Velocity)   │
                    │                     │
                    │   PID, TECS         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   ACTUATOR LAYER    │
                    │   (Motors/Servos)   │
                    │                     │
                    │   PX4 Mixer         │
                    └─────────────────────┘
```

---

## Coordinate Frames

PixEagle uses the following coordinate frames:

### NED (North-East-Down)

Standard aerospace convention:
- X: North
- Y: East
- Z: Down (positive toward Earth)

### Body Frame

Vehicle-relative:
- X: Forward
- Y: Right
- Z: Down

### Image Frame

Tracker output (normalized):
- X: Right in image (-1 to +1)
- Y: Down in image (-1 to +1)
- Origin: Image center

### Conversion

```python
# Normalized image axes and body-FRD commands share positive right/down signs.
error_x = self.image_axis_error(target_x, desired_x)
error_y = self.image_axis_error(target_y, desired_y)
vel_body_right = self.positive_error_pid_command(pid_right, error_x)
vel_body_down = self.positive_error_pid_command(pid_down, error_y)
```

`CustomPID` follows `simple_pid` and accepts a measurement, not a precomputed
error. Use the shared helpers so a target right/below the aim point produces a
positive body-right/body-down command after any camera or gimbal mount transform.

---

## Control Modes

### Velocity Control

Commands body-frame velocities. PX4 handles attitude.

```
vel_body_fwd   → Forward speed
vel_body_right → Lateral speed
vel_body_down  → Vertical speed
```

### Attitude Rate Control

Commands angular rates directly. Required for fixed-wing.

```
rollspeed    → Roll rate (deg/s)
pitchspeed   → Pitch rate (deg/s)
yawspeed     → Yaw rate (deg/s)
thrust       → Normalized thrust (0-1)
```

---

## Mathematical Notation

| Symbol | Meaning |
|--------|---------|
| λ | Line-of-sight angle |
| λ̇ | LOS rate |
| N | Navigation constant |
| V | Velocity magnitude |
| ω | Angular rate |
| K_p, K_i, K_d | PID gains |
| L_1 | L1 look-ahead distance |
| E_t | Total energy |
| γ | Flight path angle |

---

## References

- Zarchan, P. (2012). *Tactical and Strategic Missile Guidance* (6th ed.)
- Park, S., Deyst, J., & How, J. P. (2004). *L1 Guidance Logic*. AIAA GNC.
- Lambregts, A. A. (1983). *TECS Principles*. AIAA Paper 83-2239.
- Aström, K. J., & Murray, R. M. (2021). *Feedback Systems* (2nd ed.)
