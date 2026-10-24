# Follower replay and SIH validation matrix

This matrix separates three kinds of evidence:

1. **Contract tests** check the follower’s input and command fields.
2. **Interactive synthetic replays** use an independently defined moving target
   and a generated observed-pose trace to exercise the visualizer.
3. **SIH acceptance** requires a fresh PX4-observed pose, target truth, and
   publication trace from the same run. A synthetic pose is never promoted to
   SIH evidence.

| Follower | Input | Moving-target replay | PX4/SIH status |
| --- | --- | --- | --- |
| `mc_velocity_chase` | image position | Available; forward closure, target loss, retarget | Pending fresh SIH pose/publication run |
| `mc_velocity_ground` | image position | Contract gallery only; ground image axes need their own fixture | Pending |
| `mc_velocity_distance` | image position | Contract gallery only; forward command is intentionally zero | Pending |
| `mc_velocity_position` | image position | Available; stationary-surveillance semantics and fault windows | Pending |
| `mc_attitude_rate` | image position + airframe state | Contract gallery only; rate/thrust command fields need an attitude replay | Pending |
| `fw_attitude_rate` | image position + airframe state | Contract gallery only; requires fixed-wing speed/state evidence | Pending |
| `gm_velocity_chase` | gimbal angles | Available horizontal contract replay | Pending fresh SIH pose/publication run |
| `gm_velocity_vector` | gimbal angles | Available horizontal, vertical, and combined 3D replays | Pending fresh SIH pose/publication run |

The existing imported actual trace is intentionally marked incomplete: it has
command/publication records but zero observed PX4 pose samples. The latest
managed phase-2 attempt also exited before runtime probes because its PX4/SIH
sidecars were unavailable. Those artifacts must not be described as successful
moving-target SIH validation.

The next acceptance run should use command-blocked SIH, capture the target
truth and PX4 pose in the same time base, and generate one report per profile
where the profile is supported by the fixture. The run must remain read-only to
the visualizer; it must not create target, follow, Stop, or aircraft actions.
