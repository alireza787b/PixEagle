# Gimbal Chase Forward Speed

`gm_velocity_chase` has two implemented forward-speed modes. Neither mode
estimates target range, closing speed, or time to intercept.

| Mode | Runtime behavior | Operational note |
| --- | --- | --- |
| `CONSTANT` | Ramps from the current command toward `BASE_FORWARD_SPEED` | Default. Speed does not fall to zero merely because the gimbal is neutral. |
| `PITCH_BASED` | Maps absolute gimbal pitch error to speed, then applies the same acceleration limit | Compatibility mode. Speed decays near neutral pitch and is not a range controller. |

`PROPORTIONAL_NAV` and hybrid modes are not implemented or selectable. Unknown
values fail follower construction instead of silently running `CONSTANT`.

## Configuration

```yaml
GM_VELOCITY_CHASE:
  FORWARD_VELOCITY_MODE: "CONSTANT"  # CONSTANT or PITCH_BASED
  BASE_FORWARD_SPEED: 2.0            # m/s
  FORWARD_ACCELERATION: 2.0          # m/s^2

Follower:
  General:
    CONTROL_UPDATE_RATE: 20.0        # Hz
```

The configured update rate also bounds a single ramp transition. PixEagle uses
a monotonic clock and discards excess catch-up time after a stalled loop or
reconnect, preventing one delayed sample from creating a large speed step.

Maximum velocity remains owned by `Safety.GlobalLimits` and any explicit
per-follower tightening override. See the [GM Velocity Chase
reference](../02-reference/gm-velocity-chase.md) for mount transforms and output
fields.

## Acceptance Boundary

The local contract proves mode selection, sign/unit handling, and bounded ramp
math. It does not prove pursuit performance. Before enabling PX4 publication,
validate the exact camera, gimbal signs, airframe, speed/acceleration limits,
target-loss response, and operator abort path in command preview and PX4-in-loop
tests.
