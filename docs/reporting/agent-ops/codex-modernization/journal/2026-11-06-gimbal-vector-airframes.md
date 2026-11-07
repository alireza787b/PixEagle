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
submitted contract. Application startup/teardown was completed in the subsequent
lifecycle slice; native moving-target/VTOL qualification remains open.

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

The application now selects the command owner by declared capability and fresh
observed aircraft kind. One native binding joins the existing publisher and
continuity supervisor across MC/FW/transition. It seeds a phase-safe objective,
joins publication before handoff, preserves terminal reasons and unresolved
cleanup, and avoids MAVSDK Stop for a native owner. Native speed controls use
native authority, with edits paused during phase confirmation. Applied pending
configuration is rechecked against the same qualification rule before connection.
No native service, firmware or aircraft was installed or changed.

The resumed 2026-11-07 check found that typed telemetry could still expose MC
schema defaults for a native FW publication. It now returns the current
published contract and guidance identity, and leaves retired/stale contracts
unknown. Observed native publication count is session-relative and separate
from local RPC success. The combined backend/API/configuration gate passes
1,590 cases; one existing Starlette deprecation warning remains.

The pure-MC frame repair now reuses the same physical/quaternion/heading
conversion as native VTOL MC. Actual attitude receipt age stays independent of
camera/video processing, and the legacy MAVSDK camera-yaw offset is excluded
from physical attitude. Both mounts and explicit altitude-off semantics pass
independent direction fixtures. The combined gate passes 1,608 cases. The pinned
native image rebuild also passes all 28 normal and 28 sanitizer contracts.

Transition review found a drifting baseline: MC-to-FW holding could follow
physical yaw through the tailsitter pitch-over, or retain an earlier FW course
after an MC phase. A per-episode reference now latches the preceding course and
request while applying current native speed bounds. Phase flaps do not replace
it; settled pursuit clears it. MC provisional retarget calculations no longer
mutate FW guidance. The focused lifecycle/continuity gate passes 94 tests.
