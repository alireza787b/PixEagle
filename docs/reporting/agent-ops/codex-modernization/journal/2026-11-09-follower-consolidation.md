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

S5 now binds optional measured fixed-camera calibration to the actual decoder
path and freezes the exact pixel mapping before Classic/Smart inference. Review
found and reproduced a capture-mode/epoch race; read-through-commit and source
checks repair it without adding a reader or reconnect policy. Video/producer
checks pass 334 tests and config/API/docs pass 201. Schema 2.5.0 explicitly lists
live-qualified phases instead of treating native command declarations as
permission; existing eight profiles keep their admission. Native FW direction
thresholds no longer import gimbal manoeuvre policy (1,110-test focused gate).
Full software renewal uses frozen `d5458ee85`; timing association and calibrated
FW readiness/integration remain in progress. No hardware or private tuning changed.

Renewal completed: 5,149 unit passed (11 optional skips), 196 integration passed,
and 155 Phase 0 checks passed after a documentation-only clean-clone link repair.
Per-gate revisions and initial failure logs remain at `software-gates-r2/` in
the current run root. Subsequent alignment/startup work needs its own checks.

Image/attitude association and pre-acquisition observation checks are now
committed (`016154ff2`, `919674af9`). Physical timing stays unqualified without
measured bounds; isolated SIH uses an explicitly labelled paired projection.
The shared native retarget reset preserves session controls and altitude
reference. Focused gates pass (384, 143 and 261 tests; overlapping broader checks
recorded in the checkpoint). The native adapter rebuild passes 38 contracts;
image-FW integration and actual airplane response remain next, without hardware.

The ninth profile, `fw_navigation_chase`, is registered experimentally with four
explicit geometry settings and no live-qualified phase. Native-only preview
refuses before construction, including pending-config races (523 tests). Exact
SIH frame retention and genuine aircraft-progress command recalculation repair
a reproduced premature-TTL handoff without refreshing image timestamps or
extending recovery budgets (389 relevant tests; focused cases overlap).

Renewed actual airplane gimbal components pass for both mounts with altitude
guidance off: range closes from 163.78 m to 25.25/27.49 m, altitude errors stay
below 0.25 m, and Stop confirms Hold without later publication. The first image
attempt safely rejected a harness packet mismatch immediately after engagement;
the failed run is retained for the startup handoff repair. Source, replay and
per-case scope remain in the checkpoint. No Pi, aircraft installation, private
configuration or QGC build has been changed.

The paired engagement observer repair is now verified on actual SIH. Image-FW
altitude off/on and loss/reacquisition/expiry all pass on frozen `3cb7a8355`;
each confirms Hold with no subsequent publication. Strict native evidence
validation, four browser-checked interactive replays and the retained failures
are linked by directory in the checkpoint. GM retarget memory and shared PID
PoM/manual-start defects are repaired without changing gains or the public/private
configuration. Actual airspeed-source changes and S6 provider qualification are
next; no new live phase has been admitted.

S5 component/software checkpoint closed on November 11: the source-change case
passes when the simulator explicitly enables native sensor reacceptance; its
default-latched failed assertion remains retained and explained. The native
parameter was restored, with no aircraft change. Full frozen `132396744` renewal
passes 5,514 unit, 196 integration and 155 Phase 0 tests plus schema/inventory/fatal
lint. S6 now begins with source/receipt metadata and removal of synthetic gimbal
pixels; timing/capability policy and physical qualification are separate steps.
