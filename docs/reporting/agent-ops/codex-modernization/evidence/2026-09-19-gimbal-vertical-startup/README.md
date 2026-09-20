# Proposed vertical mount: initial observation only

2026-09-19, 20:00 UTC onward. Operator powered the camera in the proposed
installation. Physical mounting plate / aircraft nose description remains
pending; no mapping is inferred from the word vertical alone.

Camera responds at the configured address; 1920×1080 native video is upright.
Read-only ROT queries returned ROT02. Tracking disabled, following off.
Initial short telemetry samples included pitch approximately 102–105 degrees.
Longer passive sampling spans pitch 76–112 degrees as the view/base moved;
this is not a fixed-base motor response experiment. Private video shows room,
then hand/laptop close-up. No pan, tilt, roll, home, tracking or image-setting
write was issued by the agent in this interval.

`status-samples.jsonl` contains actual typed read results. `passive-angles.json`
contains GAC-derived samples, and ROT request/reply captures retain exact bytes.
`axis_pulse.py` is prepared but **not executed** in this evidence slice; it uses
the typed PixEagle action for one bounded pulse and logs before/after telemetry.
No aircraft command or mounting/follower qualification is claimed.

Private native capture: reports/gimbal-bench/20260919T200001Z-user-manual-observe.
Before motion characterization, the operator must describe the plate/nose
orientation and hold the base steady with the camera head clear.
