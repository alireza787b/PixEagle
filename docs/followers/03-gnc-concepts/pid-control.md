# PID Control

> Proportional-Integral-Derivative feedback control

PID control is the fundamental feedback mechanism used throughout PixEagle's follower system. It computes control outputs to minimize error between desired and actual values.

---

## Basic PID Equation

```
u(t) = Kp × e(t) + Ki × ∫e(τ)dτ + Kd × de(t)/dt

Where:
u(t) = Control output
e(t) = Error (setpoint - measurement)
Kp = Proportional gain
Ki = Integral gain
Kd = Derivative gain
```

---

## Term Functions

### Proportional (P)

Immediate response proportional to error:

```python
p_term = Kp * error

# Large error → large correction
# Zero error → zero correction
```

**Effect**: Response speed, but steady-state error possible

### Integral (I)

Accumulated error over time:

```python
integral += error * dt
i_term = Ki * integral

# Eliminates steady-state error
# Builds up over time
```

**Effect**: Eliminates offset, but can cause overshoot

### Derivative (D)

Rate of error change:

```python
derivative = (error - last_error) / dt
d_term = Kd * derivative

# Anticipates future error
# Dampens oscillation
```

**Effect**: Stability, but sensitive to noise

---

## PixEagle CustomPID

### Class Definition

```python
class CustomPID:
    def __init__(
        self,
        Kp: float,
        Ki: float,
        Kd: float,
        setpoint: float = 0.0,
        output_limits: Tuple[float, float] = (-inf, inf),
        proportional_on_measurement: bool = False,
        differential_on_measurement: bool = True
    ):
```

### Key Features

1. **Output Limiting** - Prevents actuator saturation
2. **Anti-windup** - Stops integral accumulation when saturated
3. **Proportional on Measurement** - Eliminates setpoint kick
4. **Derivative Filtering** - Reduces noise sensitivity

---

## Anti-Windup

Prevents integral term from growing during saturation:

```python
def __call__(self, error: float) -> float:
    # Update integral
    self._integral += error * dt

    # Compute output
    output = self._p + self._i + self._d

    # Clamp output
    if output > self.max_output:
        output = self.max_output
        # Anti-windup: don't accumulate when saturated
        self._integral -= error * dt
    elif output < self.min_output:
        output = self.min_output
        self._integral -= error * dt

    return output
```

---

## Proportional on Measurement

Standard PID has setpoint kick when setpoint changes. Proportional on Measurement avoids this:

**Standard (Proportional on Error)**:
```python
p_term = Kp * (setpoint - measurement)
# Sudden setpoint change → sudden output spike
```

**Proportional on Measurement**:
```python
p_term = -Kp * (measurement - last_measurement)
# Setpoint change doesn't cause spike
```

Enable in CustomPID:
```python
pid = CustomPID(1.0, 0.1, 0.05, proportional_on_measurement=True)
```

---

## Usage in Followers

### Velocity Control

```python
# Create PID for lateral velocity
self.pid_right = CustomPID(
    Kp=3.0,
    Ki=0.1,
    Kd=0.5,
    setpoint=0.0,  # Target: center of image
    output_limits=(-5.0, 5.0)  # m/s
)

# In control loop
error_x = 0.0 - target_x  # Error from center
vel_right = self.pid_right(error_x)
```

### Rate Control

```python
# Create PID for yaw rate
self.pid_yaw = CustomPID(
    Kp=45.0,
    Ki=1.0,
    Kd=5.0,
    setpoint=0.0,
    output_limits=(-60.0, 60.0)  # deg/s
)

# In control loop
yaw_rate = self.pid_yaw(error_x)
```

---

## Configuration

### PID Gains in config.yaml

```yaml
PID_GAINS:
  # Velocity axes
  vel_body_fwd:
    p: 2.0
    i: 0.1
    d: 0.3
  vel_body_right:
    p: 3.0
    i: 0.1
    d: 0.5
  vel_body_down:
    p: 2.0
    i: 0.05
    d: 0.3

  # Rate axes
  yawspeed_deg_s:
    p: 45.0
    i: 1.0
    d: 5.0
  rollspeed_deg_s:
    p: 60.0
    i: 2.0
    d: 10.0
  pitchspeed_deg_s:
    p: 40.0
    i: 1.5
    d: 8.0
```

---

## Tuning Methods

### Ziegler-Nichols (Classic)

1. Set Ki = Kd = 0
2. Increase Kp until oscillation
3. Record Ku (ultimate gain) and Tu (oscillation period)
4. Apply formulas:

| Type | Kp | Ki | Kd |
|------|----|----|-----|
| P | 0.5 Ku | - | - |
| PI | 0.45 Ku | 1.2 Kp/Tu | - |
| PID | 0.6 Ku | 2 Kp/Tu | Kp×Tu/8 |

### Manual Tuning

1. **Start with P only** - Get acceptable response
2. **Add D** - Reduce overshoot and oscillation
3. **Add I** - Eliminate steady-state error
4. **Fine-tune** - Balance response and stability

### PixEagle Recommendations

| Axis | P | I | D | Notes |
|------|---|---|---|-------|
| Lateral velocity | 2-4 | 0.05-0.2 | 0.3-0.8 | Higher P for snappy |
| Vertical velocity | 1-3 | 0.02-0.1 | 0.2-0.5 | Lower gains for smooth |
| Yaw rate | 30-60 | 0.5-2 | 3-10 | Higher gains, faster |

---

## Common Issues

### Oscillation

**Cause**: Kp or Kd too high
**Fix**: Reduce Kp, increase Kd slightly

### Slow Response

**Cause**: Kp too low
**Fix**: Increase Kp

### Overshoot

**Cause**: Ki too high, Kd too low
**Fix**: Reduce Ki, increase Kd

### Steady-State Error

**Cause**: Ki = 0 or too low
**Fix**: Add/increase Ki

### Noise Sensitivity

**Cause**: Kd too high
**Fix**: Reduce Kd, add derivative filter

---

## Derivative Filtering

Reduce noise amplification:

```python
# Low-pass filter on derivative
alpha = 0.1  # Filter coefficient (0-1)
filtered_derivative = alpha * raw_derivative + (1 - alpha) * last_filtered

d_term = Kd * filtered_derivative
```

---

## Reset/Bumpless Transfer

When switching modes or reinitializing:

```python
def reset(self):
    """Reset PID state for bumpless restart."""
    self._integral = 0.0
    self._last_error = 0.0
    self._last_output = 0.0
```

---

## Integration with SafetyManager

Output limits come from SafetyManager:

```python
# Velocity PID limits from config
pid_lateral = CustomPID(
    *gains,
    output_limits=(
        -safety_manager.velocity_limits.lateral,
        safety_manager.velocity_limits.lateral
    )
)
```

---

## References

- Aström, K. J., & Murray, R. M. (2021). *Feedback Systems: An Introduction for Scientists and Engineers* (2nd ed.).
- Åström, K. J., & Hägglund, T. (1995). *PID Controllers: Theory, Design, and Tuning* (2nd ed.).
