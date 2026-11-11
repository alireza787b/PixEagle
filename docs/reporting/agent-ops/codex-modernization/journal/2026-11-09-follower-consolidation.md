# Follower consolidation — 2026-11-09

S0 inventory is complete at baseline `50bb2f763`. The canonical
[checkpoint](../checkpoints/2026-11-09-follower-consolidation.md) records scope,
verification and next work. The
[qualification inventory](../../../../followers/05-development/follower-sih-validation-matrix.md)
separates current implementations, historical actual PX4 evidence and remaining
gates. No runtime/default/private configuration, hardware, simulation or release
changed by S0. Baseline checks: 74 passed and schema current.

S1 adds the shared backend catalog/eligibility, command schema 2.2.0, explicit
measurement semantics and separate selection/live readiness. Removed duplicate
compatibility/mount metadata; no algorithm/default/private-profile changes.
Focused gates passed (829, 315 and 54 tests in overlapping commands); fatal lint
and schema pass. The checkpoint records the read-only archived FW replay and
remaining client/owner/VTOL gates.

S2 extends the existing ConfigService/Config Sync to exact nested paths, sparse
overrides and selected-leaf baselines. It retires three unused GM Chase keys
without changing gains. Combined config gates: 389 passed, one Windows-only ACL
skip; fatal lint and schema (44/613) passed. Required General loading remains
strict and is documented. Saved/private configuration and hardware are unchanged.
S3 now adds explicit configuration identity, reset/shaping/submission hooks and
common owner-side live admission. Its 1,120-test main gate and 65-test preview/
retarget gate passed; algorithms and gains remain unchanged. The checkpoint
records the intentional legacy VTOL admission restriction and developer schema
2.3 migration. Continue with S4's public MC behavior and actual SIH evidence.

S4's MC behavior fixes pass 603 follower/envelope/schema and 85 config/API/docs
tests: altitude-off paths/history, yaw-disable, Ground tuning/correction switches,
rate altitude-offset permission and monotonic yaw intervals. Existing saved
offset range is retained. These are software gates; the canonical moving-target
runner and actual PX4 response remain pending, so S4 is not closed.

Actual MC component runs now distinguish a historical simulator drift failure
from a separately pinned diagnostic firmware candidate. All four MC velocity
profiles passed nominal altitude-off/on candidate scenarios with unchanged
tuning/acceptance limits. MC direct rates failed altitude/image response; a
reproduced pitch/yaw unit defect is repaired, and timestamped altitude feedback
is being corrected before a fresh run. The checkpoint retains exact run names,
metrics, baseline provenance and remaining gates. Failed evidence is preserved
and visibly labelled. No hardware, private profile or release has changed.

The verified clean-source SIH build now supports the ordinary MC component
matrix: 28 current cases pass across five profiles, with four velocity modes'
altitude-off/on response and separate loss/retarget/takeover/stale checks at each
supported layer. Ground's uncalibrated correction and Visual Centering's
continuity-frame leakage were repaired; unchanged failed cases have fresh passes.
The single raw-validated selector retains failed history and explicit scope.
Direct rates remain advanced, with no live retarget or target-vertical claim.

Classic/Smart image provenance and the shared native FW unit-NED-ray math entry
are committed foundations; calibrated timing and public FW integration remain
pending. The full suite exposed ten stale fixture expectations, repaired with
67 affected-module tests passing. Integration passed 196 tests; the renewed
full gates write persistent logs linked in the checkpoint. No hardware or QGC
delivery is requested at this stage.

November 11 continuation: the remaining broad-suite failures exposed duplicate
manager caches in Parameters, not missing configuration. Removing those caches
keeps publication and followers on the same registered instances. The renewed
gate passes 4,975 unit tests (11 optional GStreamer skips), 196 integration and
155 Phase 0 checks; schema and fatal lint pass. S4's component/software checkpoint
is closed with its explicit optical/application/hardware exclusions.

Native timing, neutral Vector sessions/FW-only speed initialization and command
schema 2.4.0 are committed S5 foundations. Source-bound calibration and bounded
camera/attitude association are next; no native image-FW profile is enabled yet.
The checkpoint links exact revisions, persistent logs and remaining gates.
