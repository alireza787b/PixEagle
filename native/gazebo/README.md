# PixEagle visual-training scenes

Use the normal isolated training launcher; the scenarios pin the same stock
airframe/firmware. They declare their visual content and payload separately from aircraft tuning.

| Scene | Camera | Content |
| --- | --- | --- |
| `*-training-coast-v2` | Native MC, native FW, quadplane, fixed-nose tailsitter or articulated gimbal | Shared coastal showcase: PixEagle art, airfield, aircraft displays, operations center, marina, vessels, cars, trees, balloons and airship |
| `quadtailsitter-nose-camera-courtyard-v1` | Fixed nose | Accepted fixed-nose image-tracker workflow |
| `quadtailsitter-gimbal-camera-courtyard-v1` | Fixed-joint articulated training gimbal | Small scene for protocol/geometry/recovery checks |
| `quadtailsitter-gimbal-training-coast-v1` | Same articulated gimbal | PixEagle signs and road mural, cars, sculpture, balloons, airship, coastal road, pier and three vessels |

The coastal scene's near signs/cars are within roughly 20–120 m of the start.
Balloons are at ENU `(45,100,55)`, `(-85,85,85)`, `(190,-30,110)` m;
the airship is at `(-130,190,100)` m. The waterfront begins around East 290 m.
The scene is intended for changing bearings, elevations, backgrounds and
apparent target sizes. Props are **static visual targets**. They do not model
traffic motion, wind, buoyancy, ocean dynamics, obstacle collisions or tracking
performance. Moving-target qualification remains a separate scenario/evidence
requirement.

Regenerate the coastal scene and its local PixEagle art with:

```bash
python tools/build_gazebo_training_world.py
```

This uses Pillow and the repository's Roboto Mono font. Assets are generated
locally; there are no online model downloads. Descriptor hashes pin every added
world/texture. The verifier restricts art to bounded nonexecutable PNG files and
requires declared static props; it does not permit hidden aircraft/plugin
changes. Do not edit archived run evidence to match a regenerated scene.
The generator also composes the fixed-camera multicopter descriptor from its
unchanged stock camera/airframe template and the same scenery. World props and
art are independent of the camera mechanism and follower choice.

The launcher defaults to the v2 showcase for all five training profiles. The
historical worlds remain available for focused regression and retained evidence.
`coastal-scenes.json` declares camera-template/output pairs. Add a compatible
scenario there, regenerate, validate its resource closure, then reference its ID
in the launcher configuration. Aircraft, mount and camera contracts stay in the
scenario descriptor; dependency locations stay in the workstation recipe. Neither
Dashboard nor QGC needs a new aircraft/world branch.

The v2 aircraft displays reuse the pinned PX4 Gazebo `rc_cessna` mesh; no new
network model download is required. Local generated PNG branding uses standard
PBR materials. Meshes retain their original upstream provenance through the
verified build manifest. These are deliberately bounded visual props, not new
aircraft dynamics, maritime physics, moving traffic or collision qualification.

The operator runner configures Gazebo's native `CameraTracking` GUI topic after
verifying the actual model name, and records its confirmed target. This spectator
view is independent of the onboard camera, PixEagle tracker and flight control.
Escape releases the spectator view; normal Gazebo camera controls remain usable.
See [Gazebo GUI](https://gazebosim.org/docs/harmonic/gui/) and
[CameraTracking](https://github.com/gazebosim/gz-gui/blob/gz-gui8/src/plugins/camera_tracking/CameraTracking.cc).

The gimbal scenes use a pinned derivative of PX4's stock ZXY gimbal, physically
attached by a fixed joint. Gazebo's standard joint-position controllers use
ideal velocity-command positioning. The descriptor records a 0.04 kg payload,
90° vertical installation roll and an ideal ±180° pitch range. That range is
an explicit training assumption: the stock restricted pitch envelope lost the
view during bank, and FL-30 travel is not measured. No hardware configuration
is widened. No detached camera/world-pose service
acts as an aircraft-following mount. Read-only pose/joint publishers supply
actual feedback. Optics derive from the pinned mono camera; hidden depth remains
simulator truth for selection, while guidance receives only angles/status.
Regenerate both composites and scene descriptors with:

```bash
python tools/build_gazebo_joint_training.py --build-manifest /path/to/verified-build/gazebo-build-manifest.json
```

Schema 5 validates the exact stock derivative, attachment, observer plugins and
private joint-control topics. The previous detached schema-4 fixture and its
builder are retired. Old reports retain their original source/version evidence.
References: [PX4 attachment example](https://github.com/PX4/PX4-gazebo-models/blob/main/models/x500_gimbal/model.sdf),
[Gazebo joint controller](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointPositionController.html).

For controls, model assumptions and operator checks see the
[gimbal training guide](../../docs/gimbal_simulator.md#rendered-gimbal-training)
and [Ubuntu training workflow](../../docs/followers/05-development/ubuntu-training-platform.md).
