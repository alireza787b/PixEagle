# Gimbal vector guidance policy

`GimbalTracker.GUIDANCE` is the single configuration group for the
`gm_velocity_vector` rearward and vertical state policy. It is a follower
restart change and does not create a second camera transform or SafetyManager.
The provider supplies capabilities; the policy only chooses how an already
validated body ray is commanded.

| Setting | Default | Meaning |
| --- | ---: | --- |
| `POLICY` | `reverse_then_yaw` | Give a target a bounded reverse grace, then yaw first. |
| `VERTICAL_ENTER_HORIZONTAL_NORM` | `0.20` | Enter pure vertical guidance at or below this horizontal ray magnitude. |
| `VERTICAL_EXIT_HORIZONTAL_NORM` | `0.30` | Leave vertical guidance at or above this magnitude. |
| `REARWARD_ENTRY_BEARING_DEG` | `100` | Begin rearward grace at this absolute body bearing. |
| `FORWARD_REENTRY_BEARING_DEG` | `80` | Resume direct pursuit after yaw brings the target inside this bearing. |
| `TRANSITION_DWELL_MS` | `300` | Fresh-observation dwell before a geometry state changes. |
| `REARWARD_GRACE_MS` | `500` | Maximum direct reverse grace before yaw-first. |

`CAPABILITIES` is an optional explicit fallback for a provider that cannot
advertise metadata. Leave `KNOWN: false` until the provider is qualified. When
runtime provider metadata exists, it always takes precedence over this
fallback; there is no second set of live limits.

When altitude guidance is enabled, the requested session speed scales the full
normalized body ray. A target ahead and below therefore produces forward and
descent components; a target directly below produces pure descent. When altitude
guidance is disabled, the down component is zeroed and the horizontal
projection is left at its natural magnitude. The system never hides this by
redistributing speed.

The body ray uses the canonical `GimbalTracker.MOUNT_TYPE` and
`GEOMETRY_OVERRIDE`. A provider must advertise `guidance_capabilities` with
`known`, `supports_vertical`, `supports_reverse`, `supports_yaw_fallback`, and
any azimuth/depression limits. Missing capabilities fail closed for the special
state rather than guessing from raw axis names. `sideslip` has no yaw fallback;
use `coordinated_turn` when yaw-first behavior is required.

These settings are not a target-loss supervisor. Stale tracker evidence,
Stop, circuit breaker, pilot takeover, invalid telemetry, and Offboard authority
remain governed by the existing continuity and safety owners. Ordinary 2D
camera followers do not expose session speed or this policy until their own
direction and capability contracts are qualified.

Existing configurations keep their explicit values. A deployment that has no
`GimbalTracker.GUIDANCE` group receives the documented defaults through config
migration preview; applying the migration is the operator's normal Config Sync
operation.

For a deterministic visual check without hardware, run:

```bash
PYTHONPATH=src python tools/plot_gimbal_guidance_proof.py \
  --output-dir /tmp/pixeagle-gimbal-guidance-proof
```

The CSV and PNG show the classifier state, vertical command, effective speed,
and transition timing. The GIF shows the body ray and command vector in 3D.
These artifacts validate software policy behavior; they are not SIH or camera
acceptance evidence.
