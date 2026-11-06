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

The next integration slice composes the existing MC follower with native FW
guidance through one phase/session owner. It tests generation-bound edits,
full-quaternion mount handling, phase-safe baselines, final native guards and
shared loss deadlines across transitions. Repeated processing of old camera
angles no longer completes guidance dwell. The shared publisher preserves new
intents arriving during a phase acknowledgement and records the effective
submitted contract. Application startup/teardown wiring and complete native
moving-target/VTOL qualification remain open.

The operator clarified flight-path priority rather than literal nose alignment.
A canonical native FW policy and optional installation-layout verification now
have schema/configuration contracts, with normal PX4/native-throttle defaults.
Unavailable experimental capability resolves visibly to the normal envelope.
The PX4 frame audit found a tailsitter heading mismatch: read-only native
observations now export PX4's own transformed FW heading/axis, rather than
repeating the conversion on the companion. The updated firmware/ROS interface
builds; 28 native/sanitizer and 1,545 backend/configuration cases pass. Native
phase holding bridges a contract change only under the original unexpired
command lease, including a native load-dependent speed floor above trim.
Legacy direct-rate FW adoption and
the owner-bound unrestricted firmware implementation remain open.
