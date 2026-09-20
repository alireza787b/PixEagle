# Gimbal mounting audit and next bench slice

Date: 2026-09-19
Issue: PXE-0172
Branch: `feat/optional-gimbal-control-bench`
Baseline: `463fbbc5acbc107d32cffc6c85cc3670923016ee` plus the existing optional-control worktree
Scope: source and supplied manufacturer reference review; no runtime edits,
camera commands, aircraft commands, or installation changes in this audit.

## Finding

PixEagle already has horizontal and vertical follower presets. These are
specific angle-to-control formulas, **not general support for an arbitrary
physical mounting rotation**. Selecting `VERTICAL` alone does not establish
that this camera will initialize, stabilize, track, or generate the correct
aircraft direction when installed on its side or with its base pointing forward.
The proposed installation must first be identified relative to the aircraft's
forward/right/down axes and measured on the standalone bench.

The operator narrowed the next implementation scope to **HORIZONTAL and
VERTICAL only**. Do not add arbitrary-angle controls or a generic calibration
interface in this slice. `TILTED_45` is mentioned below because it already exists,
not as a proposed third installation to qualify. Keep the common transformation
boundary extensible so a later preset does not require editing each follower.

Keep these four concerns separate:

1. Camera firmware initialization, stabilization, motor axes, limits, and its
   own image-to-motor tracking loop.
2. Camera image orientation (`ROT`) and PixEagle display rotation/flip.
3. Interpretation of camera angle telemetry relative to the mounting base.
4. Conversion of a target direction into aircraft-body follower commands.

Changing a follower parameter cannot repair wrong-direction motion inside the
camera's onboard tracker. Changing displayed pixels cannot establish a valid
aircraft mounting transform.

## Existing settings and their actual scope

| Setting | Runtime meaning / boundary |
| --- | --- |
| `GimbalTracker.CONTROL_ENABLED` | Default-off optional camera control adapter; does not select a mounting orientation. |
| `GimbalTracker.COORDINATE_SYSTEM` | Stored preference in the tracker, not a mounting transform. Current provider supplies authoritative `GIMBAL_BODY` GAC encoder angles; spatial GIC/GIA data is diagnostic. Selecting another string does not switch the implemented angle source. |
| `VideoSource.FRAME_ROTATION_DEG` | Display transform: 0, 90, 180, or 270 degrees. Selection mapping reverses this transform before sending camera coordinates. |
| `VideoSource.FRAME_FLIP_MODE` | Display flip: `none`, `horizontal`, `vertical`, `both`; also reversed for selection coordinates. |
| `GM_VELOCITY_VECTOR.MOUNT_TYPE` | `HORIZONTAL`, `VERTICAL`, `TILTED_45`; selects formulas described below. |
| `GM_VELOCITY_VECTOR.MOUNT_ROLL_OFFSET_DEG`, `MOUNT_PITCH_OFFSET_DEG`, `MOUNT_YAW_OFFSET_DEG` | Adds offsets to individual incoming angles. These are not a fixed mounting rotation composed with camera attitude. Roll offset has no effect on horizontal or tilted vector direction because those formulas ignore roll. |
| `GM_VELOCITY_VECTOR.INVERT_GIMBAL_ROLL`, `INVERT_GIMBAL_PITCH`, `INVERT_GIMBAL_YAW` | Inverts each corrected angle **after** adding its offset. Default false. |
| `GM_VELOCITY_CHASE.MOUNT_TYPE` | `HORIZONTAL` or `VERTICAL`; controls neutral pitch and vertical-error formula. |
| `GM_VELOCITY_CHASE.NEUTRAL_PITCH_ANGLE` | Horizontal neutral pitch only; vertical hard-codes 90 degrees. |
| `GM_VELOCITY_CHASE.ROLL_RIGHT_SIGN` | `NEGATIVE` or `POSITIVE`; roll-to-lateral sign convention. Both chase presets currently use roll for lateral error. |
| `GM_VELOCITY_CHASE.INVERT_LATERAL_CONTROL`, `INVERT_VERTICAL_CONTROL` | Invert the derived control errors; current defaults false and true respectively. |
| `GM_VELOCITY_CHASE.MAX_ROLL_ANGLE`, `MAX_PITCH_ANGLE` | Normalize control errors; not mechanical mounting rotations. |
| `Setpoint.CAMERA_YAW_OFFSET` | Added to aircraft attitude yaw in `PX4InterfaceManager._consume_mavsdk_attitude()`. Not a 3D gimbal-base transform and not a substitute for either follower's mounting settings. |

Follower mount settings have `follower_restart` reload tier. Video rotation/flip
requires backend restart. Preserve the separate bench configuration and do not
silently rewrite the operator's normal configuration.

## Current transformation paths and gaps

Relevant runtime sources:

- `src/classes/gimbal_interface.py`: GAC magnetic encoder angles in degrees;
  tuple order yaw, pitch, roll, tagged `GIMBAL_BODY`.
- `src/classes/trackers/gimbal_tracker.py`: passes those angles unchanged in
  `TrackerOutput.angular`; generates `position_2d` through a separate generic
  `CoordinateTransformer` constructed with default zero camera offsets.
- `src/classes/followers/gm_velocity_vector_follower.py`: its own direction math.
- `src/classes/followers/gm_velocity_chase_follower.py`: its own control-error math.
- `src/classes/gimbal_control.py`: physical camera speed commands, with pan
  mapped to GSY, tilt to GSP, roll to GSR. It does not read follower mount settings.

For corrected angles yaw `y`, pitch `p`, roll `r` in radians, the vector follower
normalizes these forward/right/down components:

| Preset | Forward | Right | Down |
| --- | --- | --- | --- |
| `HORIZONTAL` | `cos(p) cos(y)` | `cos(p) sin(y)` | `sin(p)` |
| `VERTICAL` | `cos(y) cos(p − π/2)` | `−sin(r)` | `sin(p − π/2)` |
| `TILTED_45` | `cos(p − π/4) cos(y)` | `cos(p − π/4) sin(y)` | `sin(p − π/4)` |

The vertical formula couples independent components and normalizes afterwards;
it is not a documented rigid rotation of the horizontal formula. For example,
with pitch 90 and roll 0, yaw +30 and −30 both normalize to forward. That may
match a narrow legacy convention, but cannot establish general 3D kinematics.
Unknown mount strings currently fall back to vertical instead of rejecting them.

The chase follower uses `roll * sign / MAX_ROLL_ANGLE` for lateral error under
**both** presets. Its horizontal vertical error starts as
`−(pitch − neutral) / MAX_PITCH_ANGLE`; vertical starts as
`(pitch − 90) / MAX_PITCH_ANGLE`, then inversion flags apply. Therefore a switch
between vector and chase is not guaranteed to preserve target direction for the
same physical horizontal camera. Do not hide this discrepancy with new defaults.

There is also a pitch-sign disagreement: the generic `CoordinateTransformer`
used for the tracker's projected position assumes positive pitch up and produces
`down = −sin(pitch)`, whereas vector-horizontal produces `down = +sin(pitch)`.
Gimbal followers use `angular`, so projected UI position is not proof of the
direction they will command. The supplied protocol itself describes positive
pitch downward for speed control but upward in angle-control prose; direct
measurement must establish the GAC convention for this unit and firmware.

`configs/tracker_schemas.yaml` contains descriptive `mount_configurations`,
including a yaw/roll swap and `pitch-90`, but no runtime reader applies that
mapping to these followers. `src/classes/gimbal_transforms.py` is a separate
legacy engine; repository search found no active follower importing it. Editing
either surface alone would not change the active follower behavior.

## Supplied manufacturer evidence

Private reference copies are under `reports/gimbal-bench/vendor-reference/`;
existing evidence manifests retain source hashes. The reviewed Qt control source
is `Downloads/VideoPlayer qt5 mingw32/VideoPlayer/gimbalcontrol.cpp` and
`mainwindow.cpp`.

- UDP/UART guide sections 4.2–4.3 distinguish yaw/pitch/roll speed commands,
  base-relative magnetic encoder commands/readback (GAC), and spatial gyroscope
  commands/readback. Firmware kinematic order and support for sideways startup
  are not specified in those sections.
- Section 5.6 documents image `ROT00` and `ROT02` (0/180 degrees). It does not
  document a 90-degree installation mode or claim this changes the IMU/base axes.
- PTZ includes heading lock, follow, home and calibration. These are not evidence
  of a sideways installation mode. Do not invoke calibration speculatively.
- The FL-30 manual lists pitch −45 to +100, roll −45 to +45, yaw −150 to +150
  degrees. The generic protocol lists different angle-command ranges. The exact
  connected model and actual limits require confirmation; a mechanically narrow
  roll axis cannot be assumed to replace a broad yaw axis after remounting.
- The Qt application sends direct GSY/GSP movement commands and uses camera
  tracking. No host mounting transform was found in the reviewed control path.
  The camera must provide a stable onboard tracking loop in its installation.

The user's camera-side 180-degree correction and subsequent short horizontal
bench success are evidence for that unit/configuration, not for sideways
installation or all firmware. A sideways configuration remains unqualified.

## Next no-flight bench plan

1. Record a photo or unambiguous description of the mounting plate, lens and
   intended aircraft nose, with aircraft forward/right/down marked. State which
   axis the base rotates around and in which direction; “vertical” is ambiguous.
   Record model label, firmware, current ROT, native frame orientation, and
   existing known-working horizontal settings before changing anything.
2. With aircraft control disconnected, keep `FOLLOWER_CIRCUIT_BREAKER: true`,
   `COMMAND_PREVIEW`, MAVLink disabled, and following off. Use one camera UDP
   owner. Mount the standalone camera with clearance; power it up in the proposed
   position without forcing motorized axes.
3. Observe initialization and stationary GAC/TRC/native video before sending
   motion. Stop if it strains, oscillates, or rests at a limit. A display rotation
   cannot fix that behavior. Record heading-lock/follow state if available.
4. Apply one short, low-speed native-axis pulse at a time, with Stop between
   pulses: yaw positive/negative, pitch positive/negative, roll positive/negative.
   Correlate physical movement and image movement with all three GAC channels.
   Do not infer a pan/roll swap from one movement at one pose. Repeat at a second
   modest pose if the first sequence is stable and mechanically clear.
5. Verify camera-native manual tracking on a distinct stationary target before
   configuring PixEagle display rotation. If the camera moves away from its own
   selected target, resolve firmware installation/orientation support first.
   Preserve the working baseline; do not automatically apply ROT02 to every mount.
6. Set PixEagle display rotation/flip to the observed view. Test click and drawn
   rectangle selection at center and off-center, retarget, Cancel, and Stop.
   Preserve native image, displayed selection, transmitted LOC, OFT and TRC.
7. Replay recorded angles into follower **command preview only**, with known
   targets forward, left/right and above/below. Check signs, nonzero components,
   neutral position, continuity loss, bounds, and both desired installation
   profiles. No PX4 publication is required to identify mapping failures.

If an existing preset exactly matches measured behavior, document a reproducible
configuration for that specific installation. Otherwise implement one shared,
tested transformation boundary with just the two requested presets, based on
the provider's documented/measured angle convention and rotation order. A fixed
base-to-aircraft rotation composed with the camera direction is a possible
internal implementation once those inputs are known; this does not require
exposing arbitrary-angle settings. Adding Euler offsets or swapping labels is
insufficient evidence of a correct vertical preset. Keep provider telemetry
normalization, installation geometry, follower guidance, and image selection
separate. Preserve defaults and qualify each installation independently. The
vertical mapping decision is pending the measured bench sequence, not settled
by the existing preset name.

Questions for the manufacturer only if bench/source evidence cannot resolve them:
Does this exact model/firmware support powering up and tracking with the base
rotated 90 degrees? Which configuration/calibration procedure is required? Are
GAC values joint encoder angles or an orientation decomposition, in what order
and with what signs/zero reference? Does ROT affect only pixels, or the internal
tracking coordinate convention? What usable limits remain in that installation?

## Validation and boundary

Read-only inspection plus:

```sh
PYTHONPATH=src .venv/bin/pytest -q \
  tests/unit/core_app/test_coordinate_transformer.py \
  tests/unit/followers/test_gm_velocity_vector_control.py \
  tests/test_gm_velocity_vector_smoke.py
```

Result: **56 passed** on Python 3.12.3 / pytest 9.1.1. These verify existing
software behavior; they do not resolve the sign inconsistencies or prove a
camera mounting geometry. Changed file: this audit only. No new hardware,
flight, SITL or HIL result is claimed. Next slice is the bounded standalone
mounting characterization above, followed by any necessary shared transform fix.

## Initial proposed-vertical startup observation, 20:00 UTC

Operator powered the camera; telemetry and upright 1920×1080 native video
returned. Read-only ROT queries still report ROT02; tracking and following are
off. Initial pitch was around 102–105 degrees; the base/view then moved, so no
stationary reference or motor-response mapping is claimed. No motion or tracking
command was issued. The mounting plate / intended aircraft nose description and
steady clear scene are needed before bounded axis characterization.
[Initial records](../evidence/2026-09-19-gimbal-vertical-startup/README.md) preserve
telemetry, read-only configuration replies and the prepared (unexecuted) pulse
script. Images remain private under local reports.

## Subsequent offline correction, 2026-09-20

Both GM follower constructors now reject unknown mount values instead of
silently selecting Vertical; the vector fallback was removed. Valid legacy
formulas remain unchanged. Operator clarified a base-pitched-up 90° installation,
then chose to reconnect after offline work. Motor/telemetry mapping therefore
remains pending; no yaw/roll swap or rigid transform has been asserted from that
description alone. See [movement/acceptance checkpoint](2026-09-20-gimbal-movement-controls.md).
