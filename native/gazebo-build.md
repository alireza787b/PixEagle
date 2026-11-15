# Pinned Gazebo firmware build

`tools/build_native_guidance.py --target gazebo` uses the existing simulator
builder, source verification and artifact/image binding. It prepares or compiles
firmware only; it never starts PX4, Gazebo or an adapter. SIH remains the default
for existing callers. The initial 0001–0007 build and disarmed startup checks
passed in `reports/native-guidance/gazebo-quadtailsitter-control-20261113-r1`
and `reports/sitl/follower-consolidation-20261111/s7-gazebo-disarmed-runtime-r1`.
These are build/startup evidence, not flight qualification.

## Inputs

The firmware revision and reviewed extension still come from
`dependencies.lock.json` and `px4/extension.json`. The separate `gazebo_build`
recipe selects `px4_sitl_default`, Harmonic, `4018_gz_quadtailsitter` and `default`.
It adds these exact resource dependencies to the existing SIH dependency list:

| Submodule | Commit |
| --- | --- |
| `Tools/simulation/gz` | `a15af9628536914ff7201c992fce5e3cb5d70db9` |
| `src/modules/simulation/gz_plugins/optical_flow/PX4-OpticalFlow` | `a4d4cfde0c023be6b1ff8c8e796862413bc99272` |

Initialize the listed paths recursively in a new standalone source checkout,
then apply the canonical extension. Existing source/evidence is never repaired
or overwritten by this builder. The stock model has four motors, no aerodynamic
control surfaces, and simulated airspeed; it is not the private compact model.

The initial compiler and runtime use the same official Linux amd64 image:

```text
ghcr.io/px4/px4-dev-ros2-gazebo@sha256:4e7bb18e46f8007d3e601e25597f84117ef14d282df10999e2dc0a9fe7d4e1f2
```

Registry metadata was inspected on 2026-11-13 without pulling image layers.
The exact firmware-revision image tag was absent. The image above was resolved
from `main-jazzy`, but the recipe uses its immutable platform manifest digest.
Its official source label identifies PX4 commit
`9941e2f769980fe19dbf74791c12e809058baa20`; this is dependency-image provenance,
not the firmware revision being compiled. Image configuration digest:
`sha256:9fb353749b5c699276d5b0a37de223483c13f613d1d6f4b29cd0bdfaa9d2e70b`.

The registry's bound SPDX attestation
`sha256:bff120ac97ccddc7c2c0d595fcd214f4e5fe6ce5545daa77a26dc782207e121a`
reports Gazebo Harmonic 1.0.0, sim8 8.15.0, transport13 13.6.0, sensors8 8.3.0,
plugin2 2.0.4, OpenCV 4.6 development packages, Protobuf 3.21.12 compiler/development
packages, and GStreamer development/runtime packages. This supports reusing the
image before considering a custom Apt install. Actual compilation and shared
library loading remain gates. The larger development image deliberately avoids
a second dependency install for the first cross-check; runtime slimming is later.
The generated image replaces its ROS convenience entrypoint with the packaged
PX4 executable, without sourcing ROS or starting a service during the build.

Primary references: [official image workflow](https://github.com/PX4/PX4-Autopilot/blob/9941e2f769980fe19dbf74791c12e809058baa20/.github/workflows/ros_dev_container.yml),
[pinned model](https://github.com/PX4/PX4-gazebo-models/blob/a15af9628536914ff7201c992fce5e3cb5d70db9/models/quadtailsitter/model.sdf),
[Harmonic installation](https://gazebosim.org/docs/harmonic/install_ubuntu/).

## Build-only workflow

After explicitly obtaining the locked image and source dependencies:

```bash
python3 tools/build_native_guidance.py --target gazebo \
  --px4-source /path/to/verified-patched-PX4 \
  --prepare-only --output-dir reports/native-guidance/gazebo-prepared

python3 tools/build_native_guidance.py --target gazebo \
  --px4-source /path/to/verified-patched-PX4 \
  --output-dir reports/native-guidance/gazebo-built
```

Use a new output directory for each command. Preparation follows the existing
Micro-CDR cache behavior; it may obtain that locked dependency if missing.
Compilation uses `DONT_RUN=1 GZ_DISTRO=harmonic make px4_sitl_default -j2 j=2`,
with the reviewed submodule list and network disabled. It never invokes the
`gz_quadtailsitter` launch target. No image pull or Apt install occurs inside
this builder. Input image pins must already exist locally for compilation.
PX4's pinned Makefile forwards its lowercase `j` variable to Ninja; GNU Make's
`-j2` alone does not bound the native compiler jobs. The shared SIH build uses
the same explicit forwarding. Historical R1 build commands remain retained.

The builder extracts artifacts from a stopped compiler container. Alongside
`bin` and `etc`, it packages the full pinned models/worlds trees, PX4's server
configuration and built shared plugins. Resource hashes must match the verified
source or the single declared sensor derivative after packaging. `gazebo-build-manifest.json` has distinct
`pixeagle_gazebo_build` identity and `org.pixeagle.gazebo` image labels. Use the
same validator with explicit `simulator="gazebo"`; SIH callers reject this
manifest. Both response and hardware qualification remain false.

SIH target, defaults, manifest shape and label namespace are preserved; only
the shared Make-to-Ninja job forwarding changes its compiler command.
The recipe fingerprint continues to include the shared builder source hash:
old manifests remain bound to their original builder version, with no
compatibility bypass or retroactive adoption. Validation hashes the builder
bytes in the explicitly selected build repository. An old manifest therefore
requires its frozen authority, such as `/home/alireza/PixEagle-gazebo-build` for
the retained 0001–0007 build. Actual builds refuse mixed executing/authority
builder versions; select and run the matching authority deliberately. A current
extension cannot adopt an older ELF simply by naming a resource variant.

## Packaged no-pitot variant

The default `stock` selection preserves the resource tree. The explicit build
option `--gazebo-resource-variant quadtailsitter-no-pitot-v1` selects the reviewed
descriptor in `native/gazebo/variants/`. It requires Gazebo and the same locked
quad model/world/4018 airframe. Unknown variants and variants on other targets
fail before preparation. No native sensor policy or startup parameter is changed.

The builder verifies the complete upstream source and extracted stock package
first. Only then does it remove the exact sensor block from the new package's
`gazebo/models/airspeed/model.sdf`. Source and package SHA256 values, the deletion
bytes and descriptor checksum are bound into the recipe. Every other resource
must still match the upstream tree. The 15 g passive housing, inertia and visual
remain, preserving the plant without copying a second quad model. The upstream
submodule and firmware source remain unchanged. Source provenance retains the
upstream hash; artifact provenance records the derived hash.

The ordinary package/image validator enforces this one declared difference.
Stock cannot masquerade as sensor-free, and sensor-free cannot masquerade as
stock, even after updating artifact hashes. ELF, bin and etc are outside the
sensor transform. Any future paired comparison must use matching firmware
authority and actually verify their identical hashes; the current stock ELF
has 0001–0007; the later stock and no-pitot builds use 0001–0009. Each retains
its own manifest and build authority. The variant provides no firmware reuse
or extension-validation bypass.

This is a build-only seam. The no-pitot runner, startup sensor configuration,
per-sample native readiness feedback, publisher-absence proof and actual flight
acceptance remain separately reviewed work. The measured-EAS baseline runner
is unchanged. Removing instrumentation is not equivalent to overriding a valid
low airspeed or treating groundspeed as measured EAS. Response and hardware
qualification remain false for every built manifest.

## Runtime verification

The canonical native vector and ownership runners, and the shared isolated host,
now use `simulation_build_manifest` / `--simulation-build-manifest` instead of
`sih_build_manifest` / `--sih-build-manifest`. Update developer invocations of
these tools together; historical report-owned scripts and their evidence remain
bound to their original version. The separate SIH evidence gallery is unchanged.

The manifest discriminant selects the existing strict SIH or Gazebo validator.
There is no second model selector or transport configuration. Unknown kinds and
Gazebo without a verified manifest are rejected. Historical builds still
require their exact reviewed authority and builder fingerprint.
Explicit `build_repository` in the native verifier/source-contract helpers must
identify that authority, never a fallback when current validation fails.

For Gazebo, verification requires the exact packaged image ID and actual running
PX4 executable hash, the isolated container, mapped native socket and aircraft
UID. Read-only scene-info, topic-list and parameter probes must agree on
`default`, `quadtailsitter_<instance>` and airframe 4018. Expected rotor/surface,
VTOL-type and bridge-enable values come from unique unconditional literal
`param set-default` declarations in the verified packaged airframe, not controller
constants. Missing, inherited, computed or ambiguous values are refused. The
packaged and runtime airframe hashes must also agree. The current declarations
specify four motors and zero control surfaces. The full runtime model/world/server/plugin tree must match the build
manifest, with the packaged resource paths in the PX4 process environment.
The process transport partition must be nonempty; probes use that same partition.
The source contract and pre-transition recheck use the same manifest kind.
These probes publish no flight or scene-modification commands.

SIH preserves its existing verified-binary contract for isolated composite
ROS/adapter images, recording their actual runtime image separately. Gazebo's
packaged image requirement also owns its model/plugin dependencies. The shared
host derives Gazebo startup from that manifest, with a private writable workdir,
operator UID, isolated network, transport partition and existing owned cleanup.
`simulation_launch_args` is the same primary launch seam used by the host and
native baseline tools. An explicit requested model must agree with the verified
Gazebo manifest; conflicts are rejected before staging or launch. Omitting the
model selects the manifest-derived Gazebo model or the existing SIH quad default.
This keeps callers that explicitly require SIH quad from launching a VTOL model.
Verified SIH builds also receive a private writable
rootfs and operator UID; the compatibility-image launch is unchanged. Optional
literal `PX4_PARAM_*` startup values are validated as finite numbers here; the
caller must restrict fixture parameter names/bounds and read back the values.
The pinned rcS applies them before Navigator, with no mid-flight parameter write.
Shared `owned_container_info` and `stop_owned_container` helpers verify the
original full container ID and ownership token; stopping rechecks identity and
stopped state without removing the container or prescribing log policy.
This does not qualify the legacy MC worker on a VTOL model or bypass App admission.

## Explicit MC camera runtime scenario

`native/gazebo/scenarios/x500-mono-camera-aruco-v1.json` selects the stock
`4010_gz_x500_mono_cam` airframe and `aruco` world from the unchanged, verified
stock package (`3d4eb66f…` manifest, `656d044f…` image, `0c6f6557…` firmware ELF).
Its runtime selection is separate from that build's recorded 4018/default
selection. The original build manifest, image, firmware and resource files are
not rewritten. `tools/sih_baseline.py` and its recipe fingerprint are unchanged;
historical builds still require their matching build authority.

After `verified_simulation_build` succeeds, callers can explicitly pass
`gazebo_scenario="x500-mono-camera-aruco-v1"` to `simulation_launch_args` and
`verify_simulator`. The former only stages the private rootfs and returns argv;
the latter only probes an already running simulator. Omitting this argument
preserves the existing SIH/quad-tailsitter defaults. A conflicting explicit
model is refused before staging. This helper slice adds no flight runner or
public configuration setting. The existing full-App startup and aircraft
admission contracts still apply.

The descriptor pins the complete selected model directories, textures, world,
server config, packaged plugins and the exact 4010 → 4001 → `rc.mc_defaults`
include chain. Only literal, unconditional identity declarations are read;
shell is never executed by the validator. Runtime checks retain the exact image,
binary and full Gazebo resource tree, and additionally require the selected
airframe-chain hashes, MC identity parameters, declared scene objects and single
camera topic. The result records `gazebo.runtime_scenario` beside the unchanged
`firmware_build`. Descriptor changes produce a new scenario hash, not a new or
retroactively qualified firmware build. No-pitot packages cannot use this stock
descriptor.

The proposed bench spawn is Gazebo **ENU** `[-6, 0, 0, 0, 0, 0]` (metres/radians),
facing the marker at the origin. The existing camera sits 0.12 m forward,
0.03 m sideways and 0.242 m above its base link. It emits 1280×960 images at
30 Hz with horizontal FOV 1.74 rad (99.6947°). Total modeled vehicle mass is
2.1143076923 kg, including the 0.05 kg camera. The static ground marker is only
0.5×0.5 m. Visible pixel area and perspective through the intended altitude
range must be measured before a demo; no tracker success is implied by a topic.

For instance 0 the expected Gazebo image topic is
`/world/aruco/model/x500_mono_cam_0/link/camera_link/sensor/camera/image`.
The pinned `GstCameraSystem` automatically sends the single camera as RTP/H.264
to `127.0.0.1:5600` inside the isolated network namespace. A normal PixEagle
GStreamer input in that namespace can use `udp://0.0.0.0:5600`. Routing that video
to the custom QGC, authentication, App startup and optional GUI rendering belong
to the separately reviewed lab topology. Do not loop the processed output back
into its input port. `HEADLESS=1` suppresses Gazebo's GUI; OGRE2 camera rendering,
H.264 decoding and advancing image frames remain actual bench gates.

The separate stock `moving_platform` world is available for later motion tests,
but is not selected here: its 5×5 m deck starts 2 m above ground and applies
force/torque noise even at requested zero speed. No new target physics,
controller, native parameter tuning, public defaults or flight permission is
introduced by this scenario.

### Raised visual training target

`x500-mono-camera-board-v1` is a separate version 2 descriptor. It reuses the same
stock image/ELF, 4010 aircraft, camera, calibration and spawn. Its one added world,
`native/gazebo/worlds/training_board_v1.sdf`, preserves the stock `aruco` world
and tiny marker, adding a static visual board. The loader compares the world
structure after removing that declared board and restoring the original name;
physics, lighting, georeference, existing objects and plugins must be unchanged.
The addition cannot overwrite any packaged resource. Before launch the verified
world is copied into the private run directory, made read-only and mounted at
its declared new resource path. Runtime verification requires that read-only
file mount and the full original resource tree plus exactly the added hash/mode.
The original build manifest and `x500-mono-camera-aruco-v1` bytes remain unchanged.

The board is centered at **Gazebo world ENU [12, 0, 6] metres**, with zero
roll/pitch/yaw. Its 6×6 m vertical panel faces -X; the black border, white inset,
opposing black squares and orange center supply distinct visual features.
The target is visual-only, with no collision, sensor, plugin or motion controller.
Typed descriptor metadata binds its static pose, panel dimensions and aim point
to the SDF. This is fixture metadata, not synthetic tracker input or a safety
boundary; it does not prevent flying through the panel.

With unchanged spawn [-6,0,0], level attitude and aircraft height about 6 m, the
camera-to-panel range is about 17.8 m. The pinned 1.74 rad horizontal FOV predicts
roughly 90×90 pixels at 640×480 analysis resolution (roughly 180×180 at 1280×960).
It also geometrically fits the camera view at the bench pose. These are pinhole
estimates, not rendering/CSRT evidence. The prior disarmed stock-marker capture
showed only a 44×1-pixel dark line; its capture PASS and visibility limitation
remain unchanged. The added world requires its own rendered-frame/visibility
check before an operator demo and later airborne tracking/following evidence.

### Standard VTOL camera courtyard (resource preparation only)

`standard-vtol-mono-camera-courtyard-v1` is an explicit schema-3 scenario over
that same stock build/image. It selects unchanged `4004_gz_standard_vtol` and
`rc.vtol_defaults`: MAV type 22, VTOL type 2, five rotors (four lift plus pusher)
and three control surfaces. The pinned `rcS` accepts `PX4_SYS_AUTOSTART=4004`
before filename lookup; `px4-rc.gzsim` separately spawns the distinct
`standard_vtol_mono_cam` model from `PX4_SIM_MODEL`. No parameter/default or
firmware file is changed. The descriptor pins both startup scripts.

The new model is exactly two merged stock includes (`standard_vtol`, `mono_cam`)
and one fixed camera joint. Validation rejects extra links, controllers,
plugins, altered joints, rotated mounts or undeclared model files. Its SDF and
model.config plus one new world use the same private, read-only resource mounts
and full runtime tree/scene verification as the prior target scenario. Stock
model directories and all previous descriptor/world files stay byte-identical.

The declared camera pose is **[0.12, 0.03, 0.242, 0, 0, 0] relative to
`base_link` FLU**: 0.12 m forward, 0.03 m left, 0.242 m up. Both the include and
joint explicitly use that frame, avoiding an inherited model-height offset.
The mount stays fixed in MC and FW; a standard quadplane needs no tailsitter
phase rotation. In physical FRD the translation is [0.12, -0.03, -0.242] m.
The original camera link adds 0.05 kg and its original inertia/offset to the
5.02500003 kg aircraft: composite link-mass sum **5.07500003 kg**. This payload
impact is explicit; it is not a claim of identical plant response.

Camera output remains the pinned 1280×960, 30 Hz, 1.74-rad horizontal-FOV sensor
and H.264 port 5600. Instance 0 image topic is
`/world/training_courtyard_v1/model/standard_vtol_mono_cam_0/link/camera_link/sensor/camera/image`.
Future fixed-camera calibration must bind this declared sensor/mount and actual
capture-path signature/analysis geometry through the existing calibration
contract. Do not copy the x500 runtime source signature, invent exposure timing,
or apply an additional phase rotation. This resource slice creates no active
calibration or image-to-attitude timing qualification.

The offline world preserves the original `aruco` gravity, lighting and
georeference. New static visual-only objects are:

| Object | World ENU center (m) | Geometry |
| --- | --- | --- |
| Initial contrasting board | [35, 25, 10] | 10×10 m vertical, facing -X |
| Far contrasting board | [150, -45, 12] | 16×16 m vertical, facing -X |
| Blue/orange buildings | [80, 60, 10], [180, -60, 7] | 20×18×20 m and 20×18×14 m |
| Parked vehicle props | [45, 32, 0.3], [110, -32, 0.3] | Pinned local rover body mesh and static wheel visuals |

Spawn remains [-6, 0, 0] facing +X. The new visuals leave the central strip
|y| < 20 m clear; they add no collision, sensor, joint or motion plugin. The
stock ground/marker remains. They are visual features, not obstacle-avoidance
or collision protection. No Fuel asset is fetched. Actual render visibility,
camera occlusion, airborne geometry and tracking response remain untested.

The ordinary training launcher now admits declared VTOL kinds only with the
verified native adapter and calibrated stamped-image source. MC Chase remains
MAVSDK-based for pure MC; the isolated VTOL path uses one native owner. FW
Navigation Chase requires its native image/timing resolver and request-time
phase/intention fence. Following ends on transition and requires a fresh explicit
Start once settled. The standard-quadplane operator run passed these normal
application workflows; see the [acceptance checkpoint](../docs/reporting/agent-ops/codex-modernization/checkpoints/2026-11-14-quadplane-acceptance-tailsitter.md).
Scenario availability alone grants no flight authority or hardware qualification.

### Tailsitter fixed-nose camera

`quadtailsitter-nose-camera-courtyard-v1` reuses the pinned 4018 stock plant and
populated courtyard. Its wrapper adds only the pinned camera and fixed joint.
The camera weighs 0.050 kg, with inertia diagonal 0.00004 kg m² and camera-frame
inertial offset [0.03, 0.03, 0.03] m. Its base-link FLU mount is
`[0, 0, 0.34, 0, -pi/2, 0]`. The image is 1280×960, horizontal FOV 1.74 rad,
30 Hz. The training server overlay removes the unused stock video encoder.

The scenario's fixed mount supplies the calibration quaternion through one
canonical rotation composition. It looks skyward in MC hover and forward in FW;
there is no phase-switched mount or second tailsitter rotation. Ordered literal
defaults are resolved in shell include order (VTOL defaults specify MAV type 22,
4018 overrides it to 20); ambiguous same-file assignments, computed values and
conditional identity remain rejected. Runtime parameters are independently
verified. See the [operator guide](../docs/followers/05-development/ubuntu-training-platform.md#inputs-frames-and-replacement-cameras).

## Next gates

No simulator launch or flight was performed for this verifier extension. Keep
actual PX4 pose and independent Gazebo truth with measured clock/frame alignment,
and seal ULogs before cleanup.

The first retained stock quad cycle passes startup but fails native altitude
and final hover-stability gates; see the [actual baseline evidence](native-transition-baseline.md#observed-stock-quad-response).
Native flight qualification remains open. Preserve the Duo failure evidence and
allocator regressions independently of the new plant's outcome. Ownership
release and fresh explicit Start after each transition remain later gates.

A separate no-pitot-from-start case must remove the simulated sensor explicitly
and record native sensorless configuration and selected source. Existing FW
stable-window default requires valid EAS. The shared predicate now supports
explicit, per-sample native airspeed-control feedback: fresh unavailable
observations qualify only with disabled native airspeed control; a valid low
measurement cannot be bypassed. It also checks progressing samples, aircraft
identity, altitude reference and bounded receipt association. The vector runner
now retains each accepted state with that packet's native airspeed-control flag
through initial FW settling, the pre-projection refresh, and post-transition
settling. Feedback must match the packet's state, navigation state and epoch,
with a bounded receipt checked at acceptance. Duplicate-time composite refreshes
replace the state and flag together without becoming a new stability sample.
Missing, stale or mismatched feedback cannot qualify unavailable FW airspeed;
measured EAS and MC settling retain their existing rules.

These caller paths are covered by synthetic packet regressions in
`tests/test_native_sensorless_callers.py`; run them with
`PYTHONPATH=src pytest tests/test_native_sensorless_callers.py tests/test_native_vector_sih.py -q -p no:cacheprovider`.
The existing coverage job selects both modules through `pytest tests/`.
The separate [no-pitot guidance fixture](guidance-cycle.md#explicit-no-pitot-guidance-fixture)
declares `SYS_HAS_NUM_ASPD=0`, requires the matching verified resource variant,
retains the native airspeed-control default and probes for absent sensor
publishers before flight actions. Its explicit 14 m/s ground-motion condition
checks actual velocity along the canonical native heading in the settled window
and fresh Start. The pinned no-wind world is part of that diagnostic assumption;
this condition does not estimate airspeed or stall margin. Standalone native
transition capture remains measured-only. Actual no-pitot flight is still pending.
The Gazebo airspeed callback does not currently use the SIH failure-injection
hook, so an accepted `failure airspeed off` command alone is not evidence of
sensor absence. No-pitot behavior, pursuit, S7 admission, S8 steep descent,
private aircraft equivalence and hardware remain unqualified.

### Versioned visual courtyard for operator training

`standard-vtol-mono-camera-courtyard-v4` selects the authentic-version-metadata
firmware package (`96f0968e…` manifest) and the separate
`training_courtyard_v2.sdf` world. All earlier descriptors/worlds remain intact.
`x500-mono-camera-board-v3` selects that same package with its original MC scene
unchanged. Aircraft, camera, plugins, defaults and controller resources are
byte-identical to the preceding package; the real firmware ELF hash differs.

The v2 courtyard adds 11 declared, static, collision-free visual models:
a 600×600 m pattern of contrasting 100 m field blocks, crossed dark roads,
white runway edges/thresholds, and eight striped buildings distributed around
ENU radii 210–252 m. Buildings are 18–30 m tall and stay outside the original
central flight corridor. There are 215 total visuals, no downloaded textures,
new plugins or collision geometry; added boxes disable their own shadows.
These are tracking features, not physical obstacle protection. Existing targets,
world gravity, georeference, aircraft mass and fixed camera calibration are unchanged.

At 35 m altitude, visible 20 m features at 150–250 m range subtend roughly
43–72 native camera pixels (about 22–36 at 640-wide analysis), when they are in
view. This pinhole estimate is not a rendering or tracking qualification.
A skyward or aircraft-occluded view can still contain no usable ground features;
resource presence cannot correct attitude, framing, or tracker drift onto the nose.
Actual visibility in MC and FW remains an operator bench check.
