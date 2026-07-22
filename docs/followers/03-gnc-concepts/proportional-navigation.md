# Proportional Navigation Design Note

Proportional Navigation (PN) commands lateral acceleration from line-of-sight
rate and closing velocity:

```text
a_command = N * closing_velocity * line_of_sight_rate
```

PixEagle does **not** currently implement PN in any maintained follower. The
`mc_velocity_chase` and `gm_velocity_chase` profiles use PID centering plus
bounded forward-speed ramps; describing either as PN would be incorrect.

## Why It Is Not A Runtime Option

A normalized 2D target coordinate is not enough to establish closing velocity,
range, camera-motion compensation, or a trustworthy line-of-sight derivative.
Adding a gain and differentiating frame positions would create a cadence- and
noise-sensitive controller without proving the PN assumptions.

## Gate For A Future Adapter

A future guidance adapter must provide:

1. timestamped, unit-qualified line-of-sight observations;
2. an explicit range or closing-velocity source and freshness contract;
3. camera/body/gimbal frame transforms with sign tests;
4. dropped-frame, noise, occlusion, saturation, and target-maneuver tests;
5. bounded command authority and one fail-closed publication boundary;
6. PX4-in-loop evidence before any aircraft test.

Until those contracts exist, PN remains a design topic rather than a config
choice or product capability.

## Reference

- Zarchan, P. (2012). *Tactical and Strategic Missile Guidance* (6th ed.).
