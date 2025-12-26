# Parameter Reference

> Complete list of follower configuration parameters

---

## Global Settings

### FOLLOWER_MODE

Selects the active follower:

```yaml
FOLLOWER_MODE: "mc_velocity_chase"
```

**Options**: `mc_velocity`, `mc_velocity_chase`, `mc_velocity_ground`, `mc_velocity_distance`, `mc_velocity_position`, `mc_attitude_rate`, `fw_attitude_rate`, `gm_pid_pursuit`, `gm_velocity_vector`

---

## Safety Limits

### SafetyLimits Section

```yaml
SafetyLimits:
  # Velocity limits (m/s)
  MAX_VELOCITY_FORWARD: 10.0
  MAX_VELOCITY_LATERAL: 5.0
  MAX_VELOCITY_VERTICAL: 3.0
  MIN_VELOCITY_FORWARD: 0.0
  DEFAULT_VELOCITY_FORWARD: 5.0

  # Rate limits (deg/s)
  MAX_YAW_RATE: 45.0
  MAX_PITCH_RATE: 30.0
  MAX_ROLL_RATE: 60.0

  # Altitude limits (m)
  MIN_ALTITUDE: 5.0
  MAX_ALTITUDE: 120.0
  ALTITUDE_WARNING_BUFFER: 5.0
  USE_HOME_RELATIVE_ALTITUDE: true
```

---

## PID Gains

### PID_GAINS Section

```yaml
PID_GAINS:
  # Velocity control
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

  # Rate control
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

  # Legacy velocity (ground view)
  x:
    p: 2.0
    i: 0.1
    d: 0.3
  y:
    p: 2.0
    i: 0.1
    d: 0.3
  z:
    p: 1.0
    i: 0.05
    d: 0.2
```

---

## MC Velocity Chase

### MC_VELOCITY_CHASE Section

```yaml
MC_VELOCITY_CHASE:
  # Forward velocity
  INITIAL_FORWARD_VELOCITY: 0.0      # m/s - starting velocity
  MAX_FORWARD_VELOCITY: 8.0          # m/s - maximum chase speed
  FORWARD_RAMP_RATE: 2.0             # m/s² - acceleration rate
  MIN_FORWARD_VELOCITY_THRESHOLD: 0.5 # m/s - minimum when moving

  # Lateral guidance
  LATERAL_GUIDANCE_MODE: "coordinated_turn"  # or "sideslip"
  ENABLE_AUTO_MODE_SWITCHING: false
  GUIDANCE_MODE_SWITCH_VELOCITY: 3.0  # m/s

  # Vertical control
  ENABLE_ALTITUDE_CONTROL: true

  # Target loss
  RAMP_DOWN_ON_TARGET_LOSS: true
  TARGET_LOSS_TIMEOUT: 2.0           # seconds
  TARGET_LOSS_STOP_VELOCITY: 0.0     # m/s
  TARGET_LOSS_COORDINATE_THRESHOLD: 990

  # Safety
  ALTITUDE_SAFETY_ENABLED: false
  EMERGENCY_STOP_ENABLED: true
  MAX_TRACKING_ERROR: 1.5

  # Smoothing
  VELOCITY_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8

  # Adaptive dive/climb (optional)
  ENABLE_ADAPTIVE_DIVE_CLIMB: false
  ADAPTIVE_SMOOTHING_ALPHA: 0.2
  ADAPTIVE_WARMUP_FRAMES: 10
  ADAPTIVE_RATE_THRESHOLD: 5.0
  ADAPTIVE_MAX_CORRECTION: 1.0
  ADAPTIVE_CORRECTION_GAIN: 0.3
  ADAPTIVE_MIN_CONFIDENCE: 0.6
  ADAPTIVE_FWD_COUPLING_ENABLED: false
  ADAPTIVE_OSCILLATION_DETECTION: true
  ADAPTIVE_MAX_SIGN_CHANGES: 3
  ADAPTIVE_DIVERGENCE_TIMEOUT: 5.0

  # Pitch compensation (optional)
  ENABLE_PITCH_COMPENSATION: false
  PITCH_COMPENSATION_MODEL: "linear_velocity"
  PITCH_COMPENSATION_GAIN: 0.05
  PITCH_DATA_SMOOTHING_ALPHA: 0.7
  PITCH_DATA_MAX_AGE: 0.5
  PITCH_COMPENSATION_MIN_VELOCITY: 1.0
  PITCH_COMPENSATION_DEADBAND: 2.0
  PITCH_COMPENSATION_MAX_ANGLE: 45.0
  PITCH_COMPENSATION_MAX_CORRECTION: 0.3
```

---

## MC Velocity Ground

### MC_VELOCITY_GROUND Section

```yaml
MC_VELOCITY_GROUND:
  TARGET_POSITION_MODE: "center"     # or "initial"
  MAX_VELOCITY_X: 10.0               # m/s
  MAX_VELOCITY_Y: 10.0               # m/s
  MAX_RATE_OF_DESCENT: 2.0           # m/s
  ENABLE_DESCEND_TO_TARGET: false
  IS_CAMERA_GIMBALED: false
  BASE_ADJUSTMENT_FACTOR_X: 0.1
  BASE_ADJUSTMENT_FACTOR_Y: 0.1
  ALTITUDE_FACTOR: 0.005
  ENABLE_GAIN_SCHEDULING: false
  GAIN_SCHEDULING_PARAMETER: "current_altitude"
  CONTROL_UPDATE_RATE: 20.0
  COORDINATE_CORRECTIONS_ENABLED: true
```

---

## FW Attitude Rate

### FW_ATTITUDE_RATE Section

```yaml
FW_ATTITUDE_RATE:
  # Flight envelope
  MIN_AIRSPEED: 12.0                 # m/s
  CRUISE_AIRSPEED: 18.0              # m/s
  MAX_AIRSPEED: 30.0                 # m/s
  STALL_MARGIN_BUFFER: 3.0           # m/s

  # Structural limits
  MAX_BANK_ANGLE: 35.0               # degrees
  MAX_LOAD_FACTOR: 2.5               # g's
  MAX_PITCH_ANGLE: 25.0              # degrees
  MIN_PITCH_ANGLE: -20.0             # degrees

  # Rate limits
  MAX_ROLL_RATE: 45.0                # deg/s
  MAX_PITCH_RATE: 20.0               # deg/s
  MAX_YAW_RATE: 25.0                 # deg/s

  # L1 Navigation
  L1_DISTANCE: 50.0                  # meters
  L1_DAMPING: 0.75
  ENABLE_L1_ADAPTIVE: false
  L1_MIN_DISTANCE: 20.0
  L1_MAX_DISTANCE: 100.0

  # TECS
  ENABLE_TECS: true
  TECS_TIME_CONST: 5.0               # seconds
  TECS_SPE_WEIGHT: 1.0
  TECS_PITCH_DAMPING: 1.0
  TECS_THROTTLE_DAMPING: 0.5

  # Thrust
  MIN_THRUST: 0.2
  MAX_THRUST: 1.0
  CRUISE_THRUST: 0.6
  THRUST_SLEW_RATE: 0.5

  # Coordinated turns
  ENABLE_COORDINATED_TURN: true
  TURN_COORDINATION_GAIN: 1.0
  SLIP_ANGLE_LIMIT: 5.0

  # Stall protection
  ENABLE_STALL_PROTECTION: true
  STALL_RECOVERY_PITCH: -5.0
  STALL_RECOVERY_THROTTLE: 1.0

  # Target loss
  TARGET_LOSS_TIMEOUT: 3.0
  TARGET_LOSS_ACTION: "orbit"
  ORBIT_RADIUS: 100.0
```

---

## Gimbal Followers

### GM_PID_PURSUIT Section

```yaml
GM_PID_PURSUIT:
  MOUNT_TYPE: "VERTICAL"
  CONTROL_MODE: "VELOCITY"
  UPDATE_RATE: 20.0
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8
  EMERGENCY_STOP_ENABLED: true
  ALTITUDE_SAFETY_ENABLED: true
  MAX_SAFETY_VIOLATIONS: 5

  TARGET_LOSS_HANDLING:
    ENABLED: true
    CONTINUE_VELOCITY_TIMEOUT: 3.0
    RESPONSE_ACTION: "hover"
```

### GM_VELOCITY_VECTOR Section

```yaml
GM_VELOCITY_VECTOR:
  MOUNT_TYPE: "VERTICAL"
  FORWARD_SPEED: 5.0
  SPEED_GAIN: 1.0
  YAW_GAIN: 30.0
  MAX_YAW_RATE: 45.0
  ENABLE_VERTICAL_PURSUIT: true
  VERTICAL_GAIN: 0.5
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8
```

---

## Per-Follower Safety Overrides

```yaml
FOLLOWER_OVERRIDES:
  MC_VELOCITY_CHASE:
    MAX_VELOCITY_FORWARD: 12.0       # Override global limit
    MAX_VELOCITY_VERTICAL: 4.0
  FW_ATTITUDE_RATE:
    MAX_VELOCITY_FORWARD: 30.0       # Higher for fixed-wing
```
