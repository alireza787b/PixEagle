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
has 0001–0007, while the current extension additionally has 0008/0009. The new
variant provides no firmware reuse or extension-validation bypass.

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
The native-only baseline Runtime helper remains unchanged. No sensorless fixture,
variant admission or startup-parameter qualification is established by these
software checks, and no no-pitot-from-start flight was performed. Groundspeed
must not masquerade as measured airspeed or stall margin.
The Gazebo airspeed callback does not currently use the SIH failure-injection
hook, so an accepted `failure airspeed off` command alone is not evidence of
sensor absence. No-pitot behavior, pursuit, S7 admission, S8 steep descent,
private aircraft equivalence and hardware remain unqualified.
