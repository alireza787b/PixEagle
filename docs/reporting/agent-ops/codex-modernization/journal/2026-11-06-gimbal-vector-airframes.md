# 2026-11-06 — native airframe guidance foundation

Implemented phase-bound aircraft/guidance/session-speed contracts and extended
the existing continuity/configuration and client contracts. Built a pinned
native PX4 external-mode adapter and isolated SIH firmware extension. Native
observations retain source receipt/progress, physical-body quaternion, verified
UID, qualified sensor/wind airspeed, native envelope and home-altitude reference.
Conditional mode handoff compares PX4's active mode and activation epoch, so a
delayed cleanup cannot overwrite a newer mode. Public MC defaults and saved
private tuning are preserved.

Live DDS tests exposed a missed one-time home reference after late join and an
overly strict reordered-packet latch. Both were repaired at their owning
boundaries. An airborne controller probe observed course response, bounded
publication and confirmed loiter; this is not full follower acceptance.

The [active checkpoint](../checkpoints/2026-11-06-gimbal-vector-airframes.md)
contains evidence, validation counts and the remaining implementation sequence.
No hardware, aircraft firmware, public release or main branch was changed.
