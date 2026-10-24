# Follower visual guide

Open the generated [follower contract gallery](../../../tools/sih_visualization_gallery.py)
with the catalog at
[`tools/sih_visualization_scenarios/follower-contracts.yaml`](../../../tools/sih_visualization_scenarios/follower-contracts.yaml).
The gallery is read-only and shows the input contract and command intent for
all eight followers. It links to interactive SIH replay reports only where a
replay exists; the current linked replays are synthetic moving-target fixtures,
not PX4-in-loop acceptance. A contract-only card is not evidence of vehicle
response.

The input contract is the key distinction:

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

Generate a gallery for a desktop review folder with:

```bash
PYTHONPATH=src .venv/bin/python tools/sih_visualization_gallery.py \
  --output /tmp/pixeagle-follower-guide/index.html
```
