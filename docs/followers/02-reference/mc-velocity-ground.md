# MC Velocity Ground Follower

> Body-frame visual centering for a downward or oblique camera

**Profile**: `mc_velocity_ground`
**Control type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_ground_follower.py`

## Behavior

The ground follower maps normalized image error to body-frame velocity:

- horizontal image error drives body-right velocity;
- vertical image error drives body-forward velocity;
- optional descent control drives positive-down velocity;
- yaw remains zero in this profile.

The desired image aim is resolved once by `AppController` from
`Follower.TARGET_POSITION_MODE` and `Tracking.DESIRE_AIM`. Gimbal attitude and
altitude response scaling are applied to the error around that aim point, so a
nonzero desired aim remains an equilibrium.

## Configuration

```yaml
Follower:
  FOLLOWER_MODE: mc_velocity_ground
  TARGET_POSITION_MODE: center

Tracking:
  DESIRE_AIM: [0.0, 0.0]

MC_VELOCITY_GROUND:
  MAX_RATE_OF_DESCENT: 1.0
  ENABLE_DESCEND_TO_TARGET: false
  IS_CAMERA_GIMBALED: false
  BASE_ADJUSTMENT_FACTOR_X: 0.1
  BASE_ADJUSTMENT_FACTOR_Y: 0.1
  ALTITUDE_FACTOR: 0.005
  COORDINATE_CORRECTIONS_ENABLED: true
```

Velocity and altitude bounds come from `Safety`. Control cadence and shared
follower behavior come from `Follower`; they are not duplicated in this
profile.

## Camera Corrections

When `IS_CAMERA_GIMBALED` is false, current roll and pitch are used to correct
the observed image coordinates. When coordinate corrections are enabled, the
resulting image error is scaled using current altitude before entering the
lateral and forward PIDs.

These corrections depend on camera mounting and require bench/SITL validation
before any flight test.

## Descent Control

`ENABLE_DESCEND_TO_TARGET` permits positive-down velocity only while the shared
minimum-altitude limit allows it. It does not provide autonomous landing or
terrain-relative range estimation.

## Tracker Contract

The profile requires fresh `POSITION_2D` data. Inactive or prediction-only
tracker output publishes an explicit zero body-velocity command instead of
running pursuit math.
