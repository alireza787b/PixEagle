# GM Velocity Chase Follower

**Profile:** `gm_velocity_chase`

**Control type:** `velocity_body_offboard`

**Tracker input:** `GIMBAL_ANGLES`
**Source:** `src/classes/followers/gm_velocity_chase_follower.py`

`gm_velocity_chase` converts provider-normalized gimbal angles into a complete
body-FRD velocity intent:

- `vel_body_fwd` in m/s;
- `vel_body_right` in m/s;
- `vel_body_down` in m/s;
- `yawspeed_deg_s` in degrees/s, positive clockwise.

It does not emit local-NED commands and does not infer target range.

## Angle Contract

The tracker supplies `(yaw_deg, pitch_deg, roll_deg)`. The maintained transform
uses pitch for the vertical error and roll for the lateral error. The yaw value
is retained in the provider tuple but is not the lateral-control input in this
follower.

| Mount | Neutral pitch | Positive body-down error | Lateral source |
| --- | ---: | --- | --- |
| `HORIZONTAL` | `NEUTRAL_PITCH_ANGLE` | negative pitch error before optional inversion | roll with `ROLL_RIGHT_SIGN` |
| `VERTICAL` | 90 degrees | positive pitch offset from 90 degrees before optional inversion | roll with `ROLL_RIGHT_SIGN` |

`INVERT_LATERAL_CONTROL` and `INVERT_VERTICAL_CONTROL` are provider/mount
calibration controls. Verify them with command preview on the actual gimbal;
there is no universal commercial-gimbal sign convention.

## Guidance Modes

`Follower.General.LATERAL_GUIDANCE_MODE` selects one horizontal command owner:

- `coordinated_turn`: transformed lateral error drives clockwise/counterclockwise yaw; body-right is zero.
- `sideslip`: transformed lateral error drives body-right velocity; yaw is zero.

Mode changes clear both PID histories and yaw-smoother state before the next
intent. Vertical control is enabled separately through the resolved follower
configuration.

Forward speed is documented in [Gimbal Chase Forward
Speed](../03-gnc-concepts/gimbal-forward-speed.md). Only `CONSTANT` and
`PITCH_BASED` exist.

## Minimal Configuration

```yaml
GM_VELOCITY_CHASE:
  MOUNT_TYPE: "HORIZONTAL"          # HORIZONTAL or VERTICAL
  ROLL_RIGHT_SIGN: "NEGATIVE"       # provider-specific
  FORWARD_VELOCITY_MODE: "CONSTANT"
  BASE_FORWARD_SPEED: 2.0            # m/s
  FORWARD_ACCELERATION: 2.0          # m/s^2
  NEUTRAL_PITCH_ANGLE: 0.0           # HORIZONTAL only
  INVERT_LATERAL_CONTROL: false
  INVERT_VERTICAL_CONTROL: true

Follower:
  General:
    LATERAL_GUIDANCE_MODE: coordinated_turn
    ENABLE_ALTITUDE_CONTROL: false
    CONTROL_UPDATE_RATE: 20.0
```

Velocity/rate/altitude limits are owned by `Safety.GlobalLimits` and optional
tightening overrides, not by this profile.

## Validation Sequence

1. Confirm the gimbal provider reports finite, fresh angle data.
2. In command preview, move one gimbal axis at a time and verify command sign.
3. Confirm target loss publishes the configured stop/response intent.
4. Validate speed ramps and mode switching with PX4 in the loop.
5. Enable real command publication only after operator abort and envelope tests.

Circuit breaker and command preview are separate: command preview has no PX4
publisher, while the circuit breaker is the final dispatch inhibit on the
normal command path.
