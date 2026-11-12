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

S6a now commits source/receipt identity without changing guidance gains or
capability policy (`f0928a40f`). Review reproduced a Stop lock regression and an
orphan-provider lifetime; both are repaired, with 476 captured final tests and
explicitly separate earlier transcript summaries. The pure original-source
comparison foundation (`a4ebef4cf`) passes 47 focused tests. Tracker docs no longer
recommend synthetic gimbal pixels or duplicated mount/Euler transforms. Active
session pinning and final queued-write admission remain the next consumer gate;
receipt identity does not establish physical target/exposure qualification.

Frozen S6a renewal passes 5,633 unit tests after two stale factory mocks were
replaced; integration (196), Phase 0 (155) and static/schema checks retain their
exact earlier revision. Both failed and renewed gates are preserved. The next
frame audit reproduces a real PID roll-to-yaw/vertical coupling on both mounts.
`f6793260c` repairs the command-frame boundary without retuning; 251 focused tests
pass, with component CSV/PNG rather than invented aircraft movement.
`359218ffd` supplies the queued-dispatch foundation (206 focused tests); session
source ownership, cleanup and coherent end-to-end software renewal remain open.

S6b consumer (`fdb303b3d`) now pins the original source through startup/retarget
and rechecks semantic command ownership at the actual write. Delayed continuity
cleanup retains its original session rather than adopting a replacement. The
focused gate passes 549 tests. Broad renewal found only older sender/provenance
fixture failures: corrected sender integration now passes 196 checks, Phase 0
passes 155, and the tracker fixture renewal passes 584 tests. Full unit renewal
on the combined reviewed source is pending. Failed runs remain retained; no new
SIH, hardware or full-pass claim follows from these fixture corrections. The
capability-policy and attitude-association steps still precede S6 closeout.

November 12 continuation: the reviewed input-policy/native-association cutover
and shared SIH fixtures are committed (`adb9b68f6`, `2f7082a4c`). The frozen
combined gate passes 6,072 unit, 196 integration, 155 Phase 0 and 141 special
tests; Dashboard passes all 523 tests, lint and production build. Independent
review repaired provider/timing/cache gaps, pre-acquire qualification ordering,
FW input expiry reaching MC emergency Stop, and merge imports dropping pending
legacy restrictions. The first actual MC capture safely stopped on a harness
policy-parser mismatch; raw evidence remains failed. Tools-only `115192e15`
and its 336-test gate correct that boundary without relaxing authored-scenario
restrictions or changing production/configuration bytes. Actual nominal/fault
and native-FW response renewal continues. No hardware/deployment or release is
claimed, and S6 remains open. Details and exact revisions are in the checkpoint.

Observed S6 renewal now passes eight nominal GM MC cases (both followers,
mounts and altitude modes; 3,784 successful publications) and four native GM FW
mount/altitude cases. All twelve interactive reports load with actual pose,
target and command values and working camera views. Their claims remain component
SIH with simulated observations. The first short-loss MC case restores authority;
the remaining fault matrix waits for stronger deadline and bounded-loss verdict
checks identified in independent review. Tools-only `bf98f4dd0` passes 458 frozen
affected tests. No controller tuning, deployment or hardware changes occurred.
The checkpoint records the superseded S4 takeover evidence and remaining S6/S7
gates; raw historical evidence remains immutable.

S6 component/software checkpoint is now closed: eight nominal MC, sixteen
selected MC fault and eight native FW cases pass, with both gimbal mounts and
explicit altitude modes. All 34 completed report pages load and animate in a
real browser. The original weak-excitation Vector-V fault case remains failed;
two distinct initial-climb fixtures pass the unchanged gate and are explicitly
selected with the original attempts retained. Tools-only `7327c2153` passes
487 frozen affected tests, while production bytes retain the prior full gate.
The checkpoint records exact counts, revisions and raw witness manifests.

S7 review exposed a causal-acquisition gap that mode IDs/epochs and the official
executor interface cannot resolve. A reviewed atomic ownership request/receipt
extension replaces the raw native mode-command route, preserving standard DDS
messages and one owner/lease. Implementation is in progress in a separate pinned
source checkout; transition-preserving release, new end-on-transition behavior,
firmware builds and VTOL/hardware qualification remain unclaimed. Public/private
saved configuration and QGC remain untouched.

S7's causal ownership software foundation is implemented: protocol 2 and an
atomic optional firmware request/receipt bind acquisition and release to their
original context. Independent review reproduced and repaired deadline-crossing
activation and reset-clock incarnation retirement. The replaced compare-mode
route and flag are removed; the manifest verifies their absence. Frozen backend
gates pass 6,268 unit and 196 integration tests; native helper/adapter/real
intention tests and generated-message compilation pass. The checkpoint records
exact scope, logs, source hashes and retained failed attempts. Full firmware/SIH
renewal and transition-preserving release remain next; VTOL admission stays
closed, with no hardware, saved configuration, gains or QGC changes.

The committed S7 foundation (`3233d0faa`) now also builds the complete pinned SIH
firmware. A fresh stable airplane passes renewed Gimbal Vector response on both
mounts and calibrated image-FW response: 870 successful component submissions,
confirmed native Hold, no subsequent publication, and three browser-checked
interactive reports. Causal ownership fault scenarios and neutral release
draining remain next; this does not reopen VTOL admission or qualify hardware.

Four S7 native ownership baseline cases now pass independent raw-evidence review:
Stop, confirmed socket EOF, same-ID pilot reselection and delayed cleanup after a
new acquisition. The new harness retains original receipts and distinguishes
fault verdicts from independent simulator cleanup. Two parser/coherence failures
remain archived with regressions. The selected EOF run's absolute clock origin
was not retained, so its exact deadline inequality is instrumented rather than
independently recomputable; new captures explicitly include that origin.

The long-running simulator's default logger auto-deleted its earlier 1 GiB ULog
during rotation. Actual per-case pose/status/wire/configuration evidence survives,
but no ULog corroboration is claimed. The checkpoint records this retention gap
and requires shorter runs with log archival. Registration-slot replacement,
terminal neutral draining, process restart and transition preservation remain
unqualified. Hardware and saved public/private configuration are untouched.

S7's registered-owner/neutral-release implementation is integrated after an
independent merge review. A checksum-pinned SDK overlay exposes the original
registration ID and suppresses this adapter's weak automatic unregister;
registration loss retires the process without adopting a reused slot. Terminal
release drains only neutral current-state commands under the exact original
activation. The old phase-hold helper is removed. Combined gates pass four SDK,
63 native, 63 sanitizer and 35 packaging/baseline checks, with matching SDK and
adapter compilation. Actual reuse/transition/process-restart tests remain open;
software success does not reopen VTOL or hardware admission.

An actual supported Python 3.10 interpreter reproduced the native client's use
of a 3.11-only asyncio API. The replacement preserves one RPC deadline, inline
dispatch fences and immediate captured-socket retirement without a new package.
Actual 3.10/3.12 native-client gates pass 118 tests each; 243 affected 3.12 checks
also pass. Source/test hashes, baseline lint comparison and original failures
remain in the S7 Python-compatibility evidence. No hardware behavior is claimed.

New bounded S7 captures on `05d38b175` pass normal Stop/EOF release and genuine
registration-slot reuse. Original-context Hold is observed; the stopped old
adapter retires after its slot is reused without an observed weak unregister,
and the replacement remains healthy through native takeoff. Both simulators are
stopped and their ULogs are flushed/hashed. The checkpoint links raw proofs and
the corrected visual summary and distinguishes these checks from sustained
neutral draining, target tracking and VTOL qualification. Backend phase migration
and private-protocol cleanup remain in review; hardware and saved settings are
unchanged.

S7 backend migration now pins a settled strategy at Start and ends on transition
without automatic resume. It removes the obsolete timeout through schema 1.9 Config
Sync retirement and records native release once from the original typed receipt.
Review reproduced/fixed link-loss cleanup dropping ownership before confirmation;
the same read-only reconciliation now retains unresolved context and the Start
barrier. Phase gates pass 708/87 checks, the link-loss delta 487 and root integration 67;
full combined renewal follows private-protocol retirement. Actual VTOL/MAVSDK
release boundaries, deployment and hardware acceptance remain open.

Private RPC 3 now removes the remaining phase-advance/transition-pursuit route
and advertises settled MC support explicitly. Old peers fail before acquisition;
historical evidence and the separate PX4 API/firmware versions are unchanged.
The combined scoped gate passes 727 checks; matching native/sanitizer gates pass
66 each, with 35 packaging checks. Root's 218-check renewal corrects a test-only
dynamic-config setup dependency. A source-backed 22-test review confirms the
existing pre-SDK MAVSDK Stop fence, with no new production layer or claim that
in-flight SDK/gRPC commands can be recalled. Full combined renewal and actual
VTOL/restart tests are next; no hardware or remote publication occurred.

The frozen combined renewal exposes a stale viewer transition-contract predicate
and two test-hygiene callbacks: 6,308 unit and 196 integration checks pass, but
the complete gate remains failed. The read-only viewer now uses the settled
catalog and the unchanged hygiene rule passes after explicit fake callbacks.
Shared wire evidence and a single declared simulator transition/post-release
capture are added to the existing native runner. The 383-check tool gate and
321-check root renewal pass; actual transitions, global target-clock slicing
and first-observation lifecycle repair remain pending. Prior failures stay
archived and no hardware or installed configuration changes occur.

The first validated native-loss observation now reaches the original session
before publication admission, invalidating controls and invoking existing
terminal cleanup immediately. Real-client/App tests cover missing/stale state,
coincident transition/release, replacement ownership and a racing speed edit.
The phase reason is decided in the canonical phase owner. The scoped gate passes
369/74 checks and root's integration renewal passes 325; full renewal follows.
No-reply transport errors keep the existing generic policy. Current FW guidance
documentation removes obsolete cross-transition resume instructions while
retaining historical evidence with its original scope.

The explicit-Start SIH tool now preserves one original world-target clock across
sessions and exports local report slices. It also waits read-only for the
existing terminal attempt after a transition witness, avoiding an evidence-relay
race without manufacturing completion. Its 291-check gate and root's 307-check
combination pass. The separately frozen lifecycle/viewer independent review finds
no concrete blocker; actual VTOL remains unqualified pending the next full
renewal and native ULog-backed scenarios.

The clean `66d54217a` gate now passes 6,339 unit, 196 integration and 155 Phase 0
tests. Three actual airplane component renewals pass with 871 acknowledged wire
intents, independently matched PX4 pose and native setpoint gaps ≤36 ms. The real
tailsitter transition ends its original session correctly but fails altitude.
Two completed native-only comparisons also fail the unchanged 2 m gate: 6.962 m
on default transition speed, 8.414 m on the explicit disposable trim-speed test.
The latter crosses its valid CAS threshold yet breaches altitude during transition;
it is rejected as a configuration solution. All failed/partial captures remain.
A reviewed read-only viewer fix selects tailsitter orientation from actual phase
after release without changing raw evidence or verdicts. Full-rate logger capture
is validated separately from active external publication. All simulators are
stopped; actual restart/fault/transition qualification remains open in S7, with
no hardware, profile, QGC or publication change. See the checkpoint for the table,
interactive replay entry point and exact gate/audit paths.

The reviewed S7 restart harness now preserves the dead owner's unresolved context
while testing a separate explicit fresh backend session. Independent review
repaired three evidence/cleanup gaps before execution; the corrected candidate
passes 151 focused tests and static/schema/offline-plan checks. Source cadence,
positive accepted-ACK identity, syscall timing and actual native registration
policy determine the verdict. There is no forced disarm, old receipt adoption,
authority-lease refresh or production restart service. Actual process recovery
and full combined post-merge renewal remain the next gates; the failed first
candidate and negative transition evidence stay intact.

The clean `d47835ee6` renewal passes 6,348 unit, 196 integration and 155 Phase 0
checks, with eleven optional GStreamer skips. A fresh standard-VTOL transition
meets its command, 36 ms publication-gap and 1.987 m altitude subchecks but remains
provisional: the archive guard exposes an adapter release-pending flag that
never resolves despite a genuine original Hold receipt. The repair retains one
exact terminal proof in the existing ownership context while permanently fencing
old pursuit. Its 75 native, 75 sanitizer, 35 packaging and 326 root compatibility
checks pass; actual middleware scheduling and archive acceptance still need a
new capture after independent review and full renewal. Report-only restart
preparation also exposed startup/unavailable-data
assumptions and a fixture/producer mismatch, all before actual crash testing.
Failed and provisional captures remain unchanged. No hardware, profile, QGC or
remote publication action occurred; S7 and the tailsitter altitude gate stay open.

Commit `c2e053dac` passes the complete 6,348/196/155 backend renewal and matching
75 native/75 sanitizer/35 packaging gates. Actual standard-VTOL sessions now
resolve their original release receipts cleanly, including a separate fresh FW
Start with no old-token adoption. MC→FW passes control/response checks at 1.890 m
altitude error and 52 ms active publication gap. The reverse case fails altitude
at an independently measured 4.493 m, with a 36 ms publication gap. Its failed
verdict stays intact. Strict archive/flush/stop succeeds with no pending release
or drain error. The first sparse replay has a visible gap around release and keeps
Replay-only status despite its separate component pass; no trace is filled in.
The source-qualified adapter crash case then fails its namespace-inode clock
witness after actual SIGKILL. It stops before replacement recovery, retains an
unresolved original context and is flushed/stopped. The next clock proof must
precede the signal, not infer missing offsets afterward. S7 remains open;
hardware, QGC, gains and saved configuration are unchanged. Nothing was deployed
or published remotely.

The prospective crash fixture now shares one raw Linux monotonic-domain reader
between host and report helper. Pre-signal validation replaces the invalid
inode-equality assumption while retaining original timestamps, the PID owner and
unresolved old-session barrier. The baseline regression fails before the repair;
147 source/143 helper checks and root's 373-check combination pass. R7's actual
unknown clock remains failed. Actual recovery is still pending a fresh capture;
this diagnostic change introduces no production recovery or flight-control layer.

Future terminal captures now project their already-recorded final/post-stop
packets through the same pose/state recorder as later settling. Original source
timestamps, sample IDs and receipt/publication cursors are preserved; old evidence
is not backfilled. A false publisher join cannot authorize an inactive marker.
The portable real-packet fixture reproduces the earlier gap and validates the
new recording path. Independent review, 283/74 scoped checks and root's combined
430-check renewal pass; actual fresh capture and full combined renewal remain
the next gates. No controller, schema, default, budget or hardware changed.
