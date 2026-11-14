# PixEagle visual-training scenes

Use the normal isolated training launcher; the scenarios pin the same stock
airframe/firmware. They change visual test content, not aircraft tuning.

| Scene | Camera | Content |
| --- | --- | --- |
| `quadtailsitter-nose-camera-courtyard-v1` | Fixed nose | Accepted fixed-nose image-tracker workflow |
| `quadtailsitter-gimbal-camera-courtyard-v1` | Ideal stabilized instrumentation camera | Small scene for protocol/geometry/recovery checks |
| `quadtailsitter-gimbal-training-coast-v1` | Same ideal camera | PixEagle signs and road mural, cars, sculpture, balloons, airship, coastal road, pier and three vessels |

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

The ideal gimbal scenes use a declared RGB-D derivative of the pinned stock
camera. Its optics and aircraft remain unchanged; the derivative selects 20 Hz
RGB/depth and adds only Gazebo's read-only camera PosePublisher at simulation
step rate. Depth remains private simulator truth for clicked-point tracking;
the PixEagle tracker still receives ordinary gimbal angles and status.
Regenerate this derivative and both scene descriptors with:

```bash
PYTHONPATH=src:. python tools/build_gazebo_rgbd_camera.py --packaged /path/to/verified-build/packaged
```

The validator checks the derivative against the exact declared stock resource,
including its pose-only plugin. Other camera/aircraft/plugin edits are rejected.

For controls, model assumptions and operator checks see the
[gimbal training guide](../../docs/gimbal_simulator.md#rendered-gimbal-training)
and [Ubuntu training workflow](../../docs/followers/05-development/ubuntu-training-platform.md).
