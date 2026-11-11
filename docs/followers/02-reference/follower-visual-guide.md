# Follower visual guide

Open the local [current MC evidence selector](../../../reports/sitl/follower-consolidation-20261109/current-evidence/index.html)
for the latest completed canonical SIH capture of each nominal, altitude and
fault case. It uses the existing eight-profile contract catalog and links raw
results, manifests, observed-pose replays and the
[baseline comparison](../../../reports/sitl/follower-consolidation-20261109/baseline-comparison/index.html).
The [qualification inventory](../05-development/follower-sih-validation-matrix.md)
retains historical FW/VTOL evidence and the broader remaining gates.

The selector chooses by the last raw PX4 pose timestamp, including failed runs;
if that trace is unavailable, it flags invalid evidence and uses the raw result's
file time to keep the incomplete attempt visible. It never chooses a prior pass
to hide a newer failure. It checks recorded source,
configuration and scenario hashes, raw verdict/check consistency, and agreement
between the replay HTML, replay summary and raw result. A **stale replay** badge
means these saved reports disagree; use the linked raw result. **Invalid evidence**
cannot establish a pass. **Follower source differs** is an exact byte comparison
with the current checkout, including comments, and does not assert a behavior
change. Capture revisions and hashes remain in `evidence.json`; algorithm changes
need the affected cases rerun. Each row names the control telemetry source from
its captured configuration; the latest nominal capture can be an SDK variant.
Earlier attempts stay linked under each case.

These are actual PX4 SIH component runs with independent moving world targets
projected into simulated fixed-camera measurements. They do not qualify physical
camera/tracker acquisition, application startup, hardware or release. Missing MC
cases remain unqualified; MC direct rates has its own altitude hold rather than
the shared target-altitude contract: engagement-height hold plus an optional
offset, without target-vertical or altitude-chase qualification. Live retarget is
unsupported for MC rates and requires Stop, rather than simply awaiting a test.
MC rates remains experimental: these are
bounded direct-rate component observations, not interception or flight-tuning acceptance.
Its stale-telemetry row shows the observed pre-submission rejection count; an
earlier stop can avoid that guard path. This snapshot does not qualify current
gimbal, FW or VTOL modes or the new end-on-transition behavior. The baseline
comparison contains one run per firmware candidate, including the native
extension; it is not proof of a particular upstream cause.

Regenerate the offline selector after new runs or report corrections:

```bash
PYTHONPATH=src .venv/bin/python tools/sih_visualization_gallery.py \
  --evidence-root reports/sitl/follower-consolidation-20261109 \
  --sih-build-manifest reports/native-guidance/sih-canonical-build-20261109-r1/sih-build-manifest.json \
  --output reports/sitl/follower-consolidation-20261109/current-evidence/index.html
```

The supplied source-build manifest must match the existing native dependency and
extension authority. Other firmware images and incomplete attempts are recorded
as excluded, not substituted. This read-only scan does not launch Docker, run PX4
or recompute the qualification metrics. The HTML and JSON are a generation-time
snapshot; regenerate them when raw inputs change.

Open the generated [follower contract gallery](../../../tools/sih_visualization_gallery.py)
with the catalog at
[`tools/sih_visualization_scenarios/follower-contracts.yaml`](../../../tools/sih_visualization_scenarios/follower-contracts.yaml).
The gallery is read-only and shows the input contract and command intent for
all eight followers. Without the evidence arguments above, its catalog links are
historical or synthetic fixtures, not current qualification. A contract-only
card is not evidence of vehicle response.

The input contract is the key distinction. The current catalog covers every
registered follower and links a moving-target replay for each profile:

- velocity chase, ground, distance, and position use normalized image-frame
  inputs and body-velocity contracts;
- multicopter and fixed-wing attitude-rate profiles use image position plus
  airframe state and expose rate/thrust intent;
- gimbal chase and vector use provider angles after the shared mount transform.

Each linked replay is a read-only synthetic fixture until a run imports
independent PX4 pose and publication evidence. The detailed input contracts are:

- `image_position_2d` is normalized image-frame position from local camera
  tracking. It is not a gimbal angle and must not be interpreted as one.
- `gimbal_angles` is the camera-provider angle stream. Mount geometry converts
  it to a body line of sight before gimbal followers calculate commands.
- `attitude_rate_image_position` combines image tracking with the airframe
  state required by an attitude-rate follower.

The command contract remains separate from the input. Ground tracking maps
image vertical error to forward body velocity, distance centering keeps forward
velocity at zero, position tracking holds translation and can yaw or change
altitude, and fixed-wing/attitude-rate profiles output rate and thrust intent.
The visualizer never substitutes gimbal angles for pixel coordinates or claims
that a command trace is a PX4-observed response.

The [replay and SIH validation matrix](../05-development/follower-sih-validation-matrix.md)
shows which profiles have interactive synthetic replays and which still need a
fresh command-blocked PX4/SIH run.

The reusable [SIH qualification guide](../05-development/sih-follower-qualification.md)
documents the dry-run, the isolated PX4 runner, fixed-wing speed-source policy,
and the evidence boundary.

Generate a gallery for a desktop review folder with:

```bash
PYTHONPATH=src .venv/bin/python tools/sih_visualization_gallery.py \
  --output /tmp/pixeagle-follower-guide/index.html
```
