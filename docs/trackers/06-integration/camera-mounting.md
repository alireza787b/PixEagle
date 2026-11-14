# Camera mounting: one installation, one geometry

Start with the ordinary defaults: local CSRT, MC Position, no gimbal controls,
optional altitude guidance off, altitude protection and circuit breaker on.
Choose a follower that matches the camera's view. No aircraft-specific camera
offset needs to be entered for the bundled video demonstration. Existing saved
installations are preserved; use Config Sync preview/apply while inactive.

## Which settings to change

| Purpose | Canonical setting | What it changes |
| --- | --- | --- |
| Make the displayed image upright | `VideoSource.FRAME_ROTATION_DEG`, `FRAME_FLIP_MODE` | Image orientation and selection mapping; not the physical installation |
| Describe a calibrated fixed camera | `VideoSource.FIXED_CAMERA_CALIBRATION` | Source-bound intrinsics and `optical_to_body_frd_wxyz`, in the decoder's original pixel grid |
| Select external gimbal installation | `GimbalTracker.MOUNT_TYPE` | Supported provider raw-angle preset: `HORIZONTAL` or `VERTICAL` |
| Correct a measured provider convention | `GimbalTracker.GEOMETRY_OVERRIDE` | Expert axis/sign/zero corrections, shared by angle followers |
| Verify aircraft installation | `Follower.AIRFRAME_LAYOUT` | `AUTO` normally; explicit layout verifies fresh aircraft state, never forces its phase |

These settings are not interchangeable. A 90° screen rotation is not a 90°
camera installation. Do not also add mount corrections to each follower, QGC,
or Dashboard. `Setpoint.CAMERA_YAW_OFFSET` is not a complete mounting transform.

## Installation choices

| Aircraft and camera | Practical starting point | Important boundary |
| --- | --- | --- |
| Ordinary MC, fixed forward camera | MC Position for stationary centering; MC Chase for pursuit | Legacy image followers use normalized image errors and their declared viewing assumptions; arbitrary tilt calibration does not automatically redesign their guidance |
| Ordinary MC, downward camera | MC Ground and the documented image-to-body mapping | This is a tracking follower, not a qualified precision-landing controller |
| Ordinary FW, fixed forward camera | FW Navigation Chase with calibrated source and qualified image/attitude timing | Physical source timing and native adapter/firmware admission are separate prerequisites |
| Standard quadplane, fixed camera | One physical mount across MC and FW; choose the compatible phase-specific follower | Transition ends following; a new Start is explicit. Automatic installed image-follower recipes remain future work |
| Tailsitter, fixed nose camera | Same fixed physical mount; FW image tracking once the lens faces the horizon | A sky-facing MC view cannot support ground tracking just by changing follower or screen rotation |
| Gimbal/external camera on any supported aircraft | Select the actual provider and measured installation preset | Angle guidance uses fresh body angles and independent tracking state, not image coordinates |

`FIXED_CAMERA_CALIBRATION` defaults to `null`; the system must not invent lens
intrinsics, exposure timing or a physical camera rotation. For native image
guidance, the calibration binds the exact selected source, pixel dimensions,
focal lengths, principal point, distortion model and installation revision.
Its quaternion maps optical right/down/forward into **physical body FRD**.
Changing source, crop, calibration or clock invalidates the appropriate media
and measurement context. A working video stream alone does not establish these
facts. The [Gazebo launcher](../../followers/05-development/ubuntu-training-platform.md#fixed-nose-camera-on-a-tailsitter)
fills measured renderer calibration from its pinned scenario automatically.

For a Gazebo fixed camera, advanced scenario authors edit `camera_mount.pose`
(metres and roll/pitch/yaw radians, `base_link_flu`) and pin the matching SDF.
The launcher derives the optical quaternion from that same pose. It is not a
second user parameter to synchronize manually. Normal applications use the
source-bound calibration object, not the simulator's SDF configuration.

## Tailsitter and gimbal frames

Keep the mount attached to the physical aircraft. Transform the camera ray with
the full physical aircraft quaternion. Native FW navigation heading is a
separate PX4 control-frame observation; do not apply its tailsitter rotation to
the camera a second time or swap the mounting preset after transition.

The currently supported Topotek presets resolve in `gimbal_geometry.py`:
horizontal uses raw yaw for azimuth and raw pitch for depression; vertical uses
negative raw roll for azimuth and raw pitch minus 90° for depression. Raw packets
stay unchanged. The vertical preset reflects this unit's camera-only bench
observations. The horizontal preset retains the established software convention;
physical horizontal installation still requires its own direction qualification.
Neither is a general rule for all gimbal brands. Another provider must document its frame, signs, units,
freshness and independent tracking status through the [provider contract](../05-development/external-gimbal-providers.md).

Mechanical reach, stabilization behavior and observed body-ray acceptance
windows are different facts. Do not substitute `GUIDANCE.OBSERVATION_LIMITS`
for physical joint limits or assume unknown mechanics can aim everywhere.

For a future tilted or dual-camera installation, retain one calibration per
source. Source switching must retire old frame/target context before new Start
admission. Automatic dual-camera switching is not implemented. Never reuse the
front-camera calibration for a downward camera to keep an old session alive.

Before flight, verify right/left and up/down response, image selection after
rotation/flip, both aircraft phases where supported, genuine target loss,
Stop, and takeover. Simulator acceptance and physical installation acceptance
remain separate.
