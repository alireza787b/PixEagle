# Tuning Guide

> Practical guidance for tuning PixEagle followers

---

## Tuning Philosophy

1. **Start conservative** - Low gains, slow speeds
2. **One parameter at a time** - Isolate effects
3. **Test in simulation first** - SITL before real flight
4. **Document changes** - Track what works

---

## PID Tuning

### Step 1: Proportional Only

```yaml
PID_GAINS:
  vel_body_right:
    p: 1.0
    i: 0.0
    d: 0.0
```

Increase P until:
- Response is snappy but not oscillating
- Small steady-state error is acceptable

### Step 2: Add Derivative

```yaml
  vel_body_right:
    p: 1.0
    i: 0.0
    d: 0.2  # Start at 20% of P
```

Increase D until:
- Overshoot is reduced
- No high-frequency jitter

### Step 3: Add Integral

```yaml
  vel_body_right:
    p: 1.0
    i: 0.05  # Start small
    d: 0.2
```

Increase I until:
- Steady-state error eliminated
- No overshoot or windup

### Typical Ratios

| Type | P : I : D |
|------|-----------|
| Position | 1.0 : 0.05 : 0.15 |
| Velocity | 1.0 : 0.03 : 0.10 |
| Rate | 1.0 : 0.02 : 0.05 |

---

## Velocity Tuning

### Forward Velocity (Chase)

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 5.0     # Start slow
  FORWARD_RAMP_RATE: 1.0        # Gentle acceleration
```

**Test pattern**: Track stationary target, verify stable approach.

**Increase if**: Target escapes, drone too slow
**Decrease if**: Overshoot, instability

### Lateral Velocity

```yaml
SafetyLimits:
  MAX_VELOCITY_LATERAL: 3.0     # Conservative start
```

**Test pattern**: Side-to-side target movement.

### Vertical Velocity

```yaml
SafetyLimits:
  MAX_VELOCITY_VERTICAL: 2.0    # Smooth altitude changes
```

**Test pattern**: Target moving up/down.

---

## Yaw Rate Tuning

### Coordinated Turn Mode

```yaml
PID_GAINS:
  yawspeed_deg_s:
    p: 30.0      # Start moderate
    i: 0.5
    d: 3.0
```

**Test pattern**: Target moving laterally.

**Increase P if**: Slow to turn toward target
**Decrease P if**: Overshoots, oscillates

### Rate Limit

```yaml
SafetyLimits:
  MAX_YAW_RATE: 30.0    # deg/s - start conservative
```

---

## Mode-Specific Tuning

### MC Velocity Chase

1. **Velocity ramping**:
   - `FORWARD_RAMP_RATE: 1.0` for smooth
   - `FORWARD_RAMP_RATE: 3.0` for aggressive

2. **Lateral mode**:
   - Start with `coordinated_turn`
   - Try `sideslip` for hovering scenarios

3. **Smoothing**:
   - `SMOOTHING_FACTOR: 0.9` for very smooth
   - `SMOOTHING_FACTOR: 0.7` for responsive

### FW Attitude Rate

1. **L1 Distance**:
   - Start large (100m) for stability
   - Reduce to 30-50m for tighter tracking

2. **TECS Weight**:
   - `1.0` balanced
   - `1.5` prioritize altitude
   - `0.5` prioritize speed

3. **Stall margin**:
   - Keep `STALL_MARGIN_BUFFER >= 3.0`

### Gimbal Followers

1. **Update rate**:
   - Match gimbal update rate
   - Typically 20-50 Hz

2. **Mount type**:
   - Verify `MOUNT_TYPE` matches physical setup

---

## Safety Limit Tuning

### Start Conservative

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 5.0
  MAX_VELOCITY_LATERAL: 3.0
  MAX_VELOCITY_VERTICAL: 2.0
  MAX_YAW_RATE: 30.0
  MIN_ALTITUDE: 10.0
  MAX_ALTITUDE: 50.0
```

### Increase Gradually

After successful flights, increase limits by 20-30%:

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 8.0    # +60%
  MAX_VELOCITY_LATERAL: 5.0    # +67%
```

---

## Troubleshooting

### Oscillation

**Symptoms**: Target hunts back and forth

**Solutions**:
1. Reduce P gain
2. Increase D gain
3. Add smoothing

### Slow Response

**Symptoms**: Target escapes, drone lags

**Solutions**:
1. Increase P gain
2. Increase velocity limits
3. Reduce smoothing factor

### Overshoot

**Symptoms**: Drone passes target, corrects back

**Solutions**:
1. Increase D gain
2. Reduce I gain
3. Slower ramp rate

### Altitude Drift

**Symptoms**: Drone climbs/descends unintentionally

**Solutions**:
1. Check vertical PID tuning
2. Verify altitude control enabled
3. Check gimbal compensation

---

## Test Patterns

### Stationary Target

1. Place target in view
2. Verify drone holds position
3. Check yaw tracking

### Moving Target (Linear)

1. Target moves in straight line
2. Verify pursuit behavior
3. Check velocity limiting

### Moving Target (Erratic)

1. Target changes direction frequently
2. Test target loss handling
3. Verify safety limits

### Altitude Changes

1. Target moves vertically
2. Verify altitude tracking
3. Check vertical limits

---

## Recording and Analysis

### Telemetry Logging

```bash
# Enable debug logging
export PIXEAGLE_LOG_LEVEL=DEBUG
bash run_pixeagle.sh
```

### Key Metrics

- Tracking error (distance from center)
- Response time
- Overshoot magnitude
- Command saturation frequency

### Dashboard Monitoring

1. Watch velocity plots
2. Monitor tracking error
3. Check safety violations
