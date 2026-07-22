# MC Visual Centering Follower

> Compatibility profile with no forward range control

**Profile key**: `mc_velocity_distance`
**Control type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_distance_follower.py`

## Behavior

The historical profile key is retained for existing configurations, but the
implementation does **not** estimate or maintain distance. It always publishes
`vel_body_fwd: 0.0` and can:

- center the target with body-right velocity;
- optionally center vertically with body-down velocity;
- optionally use clockwise-positive yaw for horizontal centering.

Choose `mc_velocity_chase` when forward pursuit is required. A true standoff
controller requires a validated range source or a calibrated apparent-size
model and is not currently implemented.

## Command Contract

| Field | Behavior |
|---|---|
| `vel_body_fwd` | Always `0.0`; no range hold |
| `vel_body_right` | Positive when the target is right of the desired aim point |
| `vel_body_down` | Optional vertical centering, positive down |
| `yawspeed_deg_s` | Optional; positive clockwise |

The desired aim point is resolved once by `AppController` from
`Follower.TARGET_POSITION_MODE` and `Tracking.DESIRE_AIM` and is then supplied
to the follower.

## Configuration

```yaml
Follower:
  FOLLOWER_MODE: mc_velocity_distance
  TARGET_POSITION_MODE: center

Tracking:
  DESIRE_AIM: [0.0, 0.0]

MC_VELOCITY_DISTANCE:
  ENABLE_YAW_CONTROL: false
  YAW_CONTROL_THRESHOLD: 0.3
```

Shared altitude-control, smoothing, target-loss, and safety settings live under
`Follower` and `Safety`; see [Parameter Reference](../04-configuration/parameter-reference.md).

## Limitations

- No forward/backward range command is generated.
- `POSITION_3D` and bounding-box size do not activate range hold.
- Bench command preview proves command calculation only, not vehicle response.
