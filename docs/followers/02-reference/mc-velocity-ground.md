# MC Velocity Ground Follower

> Body-frame visual centering with down-looking image axes

**Profile**: `mc_velocity_ground`
**Control type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_ground_follower.py`

Evidence and animation: [follower evidence gallery](follower-visual-guide.md).

## Behavior

The ground follower maps normalized image error to body-frame velocity:

- horizontal image error drives body-right velocity;
- image-up error drives body-forward velocity, and image-down error drives body-backward velocity;
- optional descent control drives positive-down velocity;
- yaw remains zero in this profile.

The desired image aim is resolved once by `AppController` from
`Follower.TARGET_POSITION_MODE` and `Tracking.DESIRE_AIM`. The observed image
coordinates enter the PIDs directly around that aim, including a nonzero aim.
Roll, pitch and altitude do not modify the horizontal image measurements or gains.

The image-X/body-right PID uses `mc_vel_lateral` gains; image-Y/body-forward uses
`mc_vel_forward`. This corrects the former swapped tuning lookup. Equal factory
gains are unchanged; installations with unequal custom gains should review the
axis mapping before adopting this repair.

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
```

Velocity and altitude bounds come from `Safety`. Control cadence and shared
follower behavior come from `Follower`; they are not duplicated in this
profile.

## Removed Correction Heuristic

This is an algorithm change. The former roll/pitch correction used attitude in
degrees with factors that also scaled errors by altitude. For the canonical
down camera, the roll sign reinforced tilt-induced image motion; the pitch
factor could reverse the image error. The coupled heuristic could saturate and
reverse velocity commands. It has been removed, rather than recalibrated by
changing a sign or converting its saved factors to radians.

The following exact `MC_VELOCITY_GROUND` paths are retired:
`COORDINATE_CORRECTIONS_ENABLED`, `IS_CAMERA_GIMBALED`,
`BASE_ADJUSTMENT_FACTOR_X`, `BASE_ADJUSTMENT_FACTOR_Y`, and `ALTITUDE_FACTOR`.
Saved values, including an old `true` enable flag, cannot reactivate the removed
behavior. They remain on disk until the normal ConfigSync preview and confirmed
apply removes the selected paths with a backup. Other Ground settings, including
custom values in sibling settings, are preserved; the whole section is not reset. See the
[retirement registry](../../../configs/config_retirements.yaml).

There is no automatic mapping from these factors to camera calibration. Future
attitude compensation requires an explicit, calibrated camera geometry contract.
The direct image PID behavior must be requalified with unchanged nominal and
fault scenarios, targets and acceptance tolerances. Geometry tests or an earlier
nominal pass do not establish closed-loop response after this change.

## Descent Control

Resolved shared `ENABLE_ALTITUDE_CONTROL` permits vertical guidance;
`ENABLE_DESCEND_TO_TARGET` then selects descent toward the configured relative
altitude floor. Both are off in the factory profile. The shared limits still
apply. This does not provide autonomous landing or terrain-relative range
estimation.

## Tracker Contract

The profile requires fresh image-position data. Inactive or prediction-only
output does not run nominal pursuit math. The shared target-continuity supervisor
owns any authorized recovery command or terminal handoff; the follower does not
publish its own competing inactive-output command.
