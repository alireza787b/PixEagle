# Follower consolidation and aircraft qualification plan

Date: 2026-11-09; updated 2026-11-11. S0–S3 and the S4/S5 MC/native-image-FW
component/software checkpoints are complete; S6 implementation is in progress. Application, optical,
installation and release qualification remain separate. Follow the [checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-09-follower-consolidation.md)
for actual verification; later slices and qualification remain pending.

This is the single plan for consolidating follower definitions, configuration,
clients and MC/FW/VTOL composition. It extends the
[modernization blueprint](../../architecture/pixeagle-modernization-blueprint.md)
and [native airframe checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-06-gimbal-vector-airframes.md).
It does not change running software, grant aircraft authority or qualify a mode.

## 1. Scope and confirmed decisions

Deliver a reliable public MC baseline, an explicitly qualified public FW pursuit
path, and an advanced external/gimbal Vector profile for the private tailsitter.
Reuse working guidance calculations behind explicit contracts. Extract only
needed interfaces; avoid a whole-repository rewrite, a universal controller,
arbitrary plugin loading or an MC-by-FW combination generator.

Operator answers recorded on 2026-11-09:

1. **End following on transition; require a new Start afterward.** A profile
   selects its strategy at Start from fresh settled MC/FW state. An active
   session never switches strategy. Transition, unexpected phase change or
   takeover ends it. No automatic resume or pursuit during transition.
2. **Manual steering is a future UI/joystick guidance idea.** Keep manual vehicle
   control separate from manually designating a direction for a pursuit strategy.
   Recommend the latter as an optional explicit input, initially in isolated
   simulation, with activation/expiry and no fabricated tracker lock. Camera
   movement alone must not authorize aircraft pursuit.

True distance keeping, precision/moving-platform landing, arbitrary camera
switching, direct-rate VTOL combinations and target pursuit during transitions
are separate future behaviors. Do not advertise them through names or presets.

## 2. Truthful mode inventory

The eight original IDs remain stable while behavior is preserved. S5 adds the
experimental, live-gated `fw_navigation_chase` profile. Operator labels
describe purpose; velocity/rates describe command contracts; gimbal describes an
input family. A profile's implementation, input compatibility, current readiness
and qualification are separate facts.

| Current ID | Operator meaning | Contract / scope |
| --- | --- | --- |
| `mc_velocity_position` | Stationary tracking | Zero horizontal velocity, visual yaw, optional target-derived vertical guidance; not a claim of exact geographic position lock |
| `mc_velocity_chase` | MC visual chase | Image-error guidance and forward-speed ramp; velocity commands |
| `mc_velocity_ground` | Downlooking ground follow | Image horizontal/vertical map to right/forward motion; not a landing controller |
| `mc_velocity_distance` | Visual centering | Zero forward motion, lateral/yaw and optional vertical centering; no measured range hold |
| `mc_attitude_rate` | MC visual chase, direct rates | Rates/thrust; advanced qualification and recovery contract |
| `fw_attitude_rate` | FW visual guidance, direct rates | Existing research implementation; current live gate remains until qualified |
| `fw_navigation_chase` | Calibrated FW image pursuit | New native course/EAS/vertical contract; explicit calibration and timing association; live gate remains closed |
| `gm_velocity_chase` | Gimbal PID pursuit | Provider observations; MC velocity guidance |
| `gm_velocity_vector` | External/gimbal Vector pursuit | MC Vector and developing native FW/transition strategies; qualification is phase-specific |

**Public FW qualification remains open.** There is no general image-based FW
body-velocity Chase today. The new navigation strategy commands course,
equivalent airspeed (EAS), and altitude/height rate through native PX4 control.
Image input uses a calibrated bearing adapter with explicit sample association;
physical capture timing and installation acceptance remain unqualified. It
reuses the native strategy without renaming a gimbal implementation to imply
ordinary camera support.

Keep direct-rate implementations separately identifiable for research. Do not
duplicate the native FW energy controller, force rates through a navigation
command adapter, or enable a gated implementation by referencing it in a recipe.
Decide replacement/retirement only after behavior and evidence review.

## 3. Minimal architecture

| Concept | Owns | Must not own |
| --- | --- | --- |
| Observation/provider | Measurement, identity, time, frame and validity | Aircraft commands or invented range |
| Strategy | One declared input/phase calculation and its PID/filter state | Publication, target-loss timers, mode changes or a global setpoint handler |
| Profile | Stable ID, purpose, requirements, strategy/tuning references and supported controls | A second runtime configuration service |
| VTOL profile | Approved MC/FW strategy bindings and end-on-transition policy | Copies of each strategy or unrestricted combinations |
| Follow session | Resolved profile, aircraft/target binding, phase generations, temporary controls and reset lifecycle | A second independent continuity supervisor |
| Command owner | Authorized shaping, publication, expiry and teardown | Camera preprocessing or guidance algorithms |

Resolve one profile at session start. Single-phase profiles reference one
strategy; VTOL profiles select one approved phase strategy for that session. Strategies may be
stateful, with explicit entry/reset/exit hooks and complete typed command intent
or an explicit failure. Keep one active publication owner and continuity owner.

Reuse `GuidancePhaseSession`, `NativeFollowBinding`, the existing commander and
continuity supervisor. Generalize the current Vector binding only as real reuse
requires it. Keep one owner per active session. End and release it on transition;
a later Start creates a new owner/session after settled-phase checks. Pure MC
keeps its existing MAVSDK path. Choose the supported native/MAVSDK transport at
Start; never exchange publishers inside a running session.

Do not instantiate two existing `BaseFollower` objects on one controller: their
construction assigns the shared setpoint handler and carries independent history.
Remove class-name-derived config lookup and profile-name-based shaping/identity
decisions where they obstruct composition. Use explicit validated declarations
and a registry of known implementations; config is not executable dispatch code.

## 4. Observation, mount and PX4 frames

Use existing tracker/evidence contracts, extended with two explicit variants:

- **Image measurement:** real image coordinate/aim point, geometry identity,
  dimensions, normalization, crop, rotation/mirroring and source revision.
- **Calibrated bearing:** finite unit direction with declared physical-body FRD
  or NED frame and calibration/provider revision; no implied metric range.

Shared metadata identifies source/target generation, measurement sequence, sample
and receipt time, time basis/clock mapping and uncertainty, plus actual evidence
validity. Optional real range/position can be added later without manufacturing
it from a monocular box. A synthesized gimbal `position_2d` is not an actual image
measurement and must not imply image-follower compatibility.

Keep strategy manoeuvre support, provider observation semantics and installation
bounds separate. A fresh GAC/TRC pair supports the accepted **boresight-guided MC**
behavior; it does not prove target-centre alignment, exposure time or a full-sphere
mechanical envelope. Unknown mechanics remain unqualified without cancelling an
already observed valid MC direction under its accepted installation semantics.
They cannot authorize invented observations or automatic gimbal aiming. Existing
filtering, feasible aircraft steering and bounded continuity remain command
intent derived from evidence, not new measurements. Unknown convention/frame,
stale evidence and unsupported aircraft phases still refuse guidance.

S6 first adds source/receipt identity and removes synthetic pixels without
changing accepted angular calculations. The capability-policy cutover then uses
Config Sync and an effective-before/after comparison: current Topotek metadata
masks fallback flags, so copying their default false values into new active
restrictions would silently disable accepted MC behavior. Preserve applicable
non-default restrictions and intersect declared installation bounds; no provider
may widen them. Record each authority's origin instead of adding a second
SafetyManager. Physical native FW timing/installation gates remain closed.

Pin the observation source before awaited follow startup and retain it through
same-source retargets. Compare independent current ownership and analysis geometry
with the original sample binding; video delivery epochs cannot substitute for
camera ownership. Missing data enters the existing continuity policy. A definite
source change ends that session. At the actual command write, recheck a captured
semantic session/target guard after queued waits, without inference/model locks.
Ordinary frame progress must not invalidate every pending command. Superseded
targets/sessions skip without failed-link counts; source changes in the current
session use existing authority-bound teardown after publication locks release.
Record the exact accepted fields sent, not a later mutable handler snapshot.

Startup records whether mode acquisition may actually have been dispatched.
Refusal beforehand cannot request Hold on an aircraft it never acquired. MAVSDK's
normal Stop also requests Hold; use the existing read-only sender-quiescence path
when no such mode change is authorized, and retain cleanup ownership/block a new
Start if quiescence is unconfirmed. Do not add another publisher or loss timer.

Installation geometry is camera/provider-owned. Fixed cameras have a fixed
optical-to-physical-body transform; moving cameras add measured pose. Converting
an off-centre pixel requires calibration and dynamic orientation, including
optical roll. Boresight is sufficient only when the provider's tracked-target
measurement actually represents that boresight. Preserve ordinary image-PID
strategies under their declared mounting assumptions; do not force all input
through bearings.

Pinned source inspection used PixEagle `2c0b0d280bc2442262601b2e1de1df9e41daf93b`
and PX4 `155f415168cef08dca2f5d85d2bc258b44a589ec` with the extension identified by
[`native/px4/extension.json`](../../../native/px4/extension.json). Source findings:

1. Raw `vehicle_attitude.q` is Hamilton physical FRD-to-NED. PX4's physical
   convention is fixed; the FW controller applies its own tailsitter conversion.
2. Its FW controller computes `R_fw = R_physical * Ry(+90 degrees)` and exports
   qualified FW heading/forward direction. In that convention FW-forward is
   physical-body **-Z**, not +X. Do not add another rotation in camera geometry.
3. MAVLink `ATTITUDE_QUATERNION.repr_offset_q` is a display offset. Geometry must
   use raw attitude, never a display-adjusted quaternion.
4. MAVLink BODY_NED velocity uses a heading-only rotation with down unchanged.
   That rule does not apply indiscriminately to acceleration or angular rates.
   Each command variant declares its own units/frame and native adapter.

The current Topotek VERTICAL neutral maps to physical +X. A tailsitter's
"vertical mount" label therefore does not establish installation correctness.
Measure forward/right/down reference rays against the aircraft's physical FRD;
retain a preset only when the actual bracket/provider conventions match it.

**Measurement alignment remains new work.** Current Vector calculation rotates
a ray using latest state. The adapter now exports optional attitude sample and
publication timing, with independent receipts and reset identity; it does not
establish camera exposure alignment. Preserve clock/source progress and validate
bounded age/skew/uncertainty. Receipt time stays labelled as receipt time. A qualified
receive-time approximation must state its limits. Add interpolation only when
bounded-skew tests demonstrate the need. Reject unqualified timing rather than
inventing capture time or silently using unrelated attitude.

One camera source remains selected throughout the initial session design. A new
Start in a settled phase selects its strategy; phase changes never automatically
select another camera. Visibility loss follows the existing continuity policy.
Future source handoff needs new generations, filter
reset and confirmed target identity; two cameras saying "tracking" is insufficient.

## 5. Aircraft, controls and authority

Fresh PX4 observations establish aircraft kind, phase, rescue state and authority.
The configured aircraft layout verifies the installation; it does not set phase.
Unknown/mismatched state cannot become permission to assume MC or FW.

| Situation | Contract |
| --- | --- |
| MC profile on MC | Its declared MC command semantics |
| MC-only profile on VTOL in MC | Allowed only when explicitly qualified; leaving its supported phase ends pursuit without obsolete cleanup cancelling PX4/pilot authority |
| FW profile on FW, including qualified VTOL FW | Native navigation or explicitly qualified direct-rate contract |
| VTOL profile | Choose the supported MC/FW strategy at Start; transition ends following and requires a new Start |
| Rescue, takeover, expiry, disarm or terminal fault | End/revoke authority; no automatic restart |

No profile requests transition because of speed or target direction. Start is
unavailable during transition. End the active session with an owner-aware release
to PX4 transition control, then require a fresh Start after settled-phase and
target checks. Tracking/video may remain active. Clear session overrides and
experimental policy bindings; do not restore them in the new session. The new
session has a new identity, control initialization and continuity budget.

**Transition-preserving release is not implemented by today's ordinary Stop.**
`ExternalMode::stopOwnedMode()` currently requests AUTO_LOITER when it still owns
the mode, including socket disconnect; `NativeFollowBinding.stop()` expects Hold.
Neither proves that an ongoing pilot-requested transition will be preserved.
S7 must distinguish ordinary Stop-to-Hold from transition termination, verify
actual authority release/native transition, and report its distinct result.
Use fresh observed phase/ownership, not an arbitrary client-provided reason, to
authorize this outcome. Test takeover before/after release, lost replies, EOF and
late cleanup. Never cancel the transition with an obsolete Hold or simply drop
publication while still retaining authority. Safe setpoints until confirmed
release belong to the transport handoff, not continuing target pursuit. No
transition baseline is required from a session after its release is confirmed.

Retargets and tracking flaps within a session do not renew continuity deadlines.
An ended session cannot be revived by a phase change or redetection. Apply the
selected phase's recovery, not MC decay/4 m travel rules to FW flight. Do not
blend commands or retain controller history across ended MC/FW sessions.

Controls are advertised by the backend, not follower-name checks in either UI:

- MC Vector: existing requested 3D speed, including zero; preserve the deliberate
  temporary replacement of saved velocity caps and independent Restore semantics.
- FW navigation: EAS reference, separate from observed speed, with the native
  positive/load-dependent minimum. Initialize each new FW session from qualified
  engagement airspeed or PX4 trim; MC zero never becomes a FW speed request.
- Other strategies expose controls only after an implementation and tests exist.
  A speed widget must not make direct rates claim a guaranteed speed controller.

Keep one SafetyManager/config resolver and one shared FW envelope/policy. Strategy
anti-windup may use effective bounds; it must not invent competing limit sources.
Retain final authorization after continuity/shaping and PX4's native constraints.

Native FW uses selected qualified airspeed, supported wind estimation or native
sensorless operation. Groundspeed remains navigation data, not measured EAS.
Valid low airspeed is not bypassed by a groundspeed proxy. Missing sensors cannot
establish real stall margin. Reconcile the older rate profile's proxy semantics
explicitly before sharing policy; do not silently reinterpret legacy values.

Altitude guidance off means no target-directed climb/descent. MC velocity
profiles suppress the vertical component without horizontal redistribution;
native FW holds engagement altitude. Direct-rate profiles need their own proved
altitude behavior; disabling target guidance is not a guarantee of altitude hold.
Altitude safety remains separate and uses the declared estimator/home-relative
reference, not terrain clearance. FW boundary tests must include finite vertical
response: requesting zero descent is not proof that altitude will stop changing.
Use the native response/performance envelope and measure the approach margin;
do not claim floor protection from a single instantaneous command check.

## 6. Public and private configurations

**Public baseline:** VIDEO_FILE, local PixEagle CSRT, Stationary tracking,
optional target-altitude guidance off, altitude safety and circuit breaker on.
Offer MC Chase as the other basic choice when compatible. FW native pursuit
becomes a normal choice only after its camera, runtime/firmware and SIH gates
pass. Direct rates and specialized followers remain Advanced/Experimental as
their evidence warrants. Demo video remains command-preview unless the existing
isolated SIH authorization explicitly permits publication.

**Private tailsitter overlay:** preserve accepted MC tuning, vertical provider
mapping and existing session-speed behavior. Previously requested profile intent
was zero startup request, 6 m/s configured MC maximum, and a 5 m minimum relative
altitude, with altitude guidance explicitly enabled. S0 must compare that intent
with the last accepted saved configuration; do not silently overwrite subsequent
tuning. Session speed may replace the saved velocity cap through its declared
control, while altitude/rate/authority protections retain their own semantics.
Verify the physical installation against PX4 FRD before adoption. Add explicit
native FW configuration and phase-specific controls; read performance limits
from the actual aircraft rather than copying simulator gains. Source, mount,
tracker engine and flight strategy remain independent choices with checked
compatibility.

Normal FW envelope behavior is tested first. Experimental upper-speed/path-
priority and minimum dive throttle use one lease-bound firmware policy and remain
off publicly. Existing unrestricted capability is false. Implement and qualify
the matching extension before enabling that private experiment; configuration
alone does not activate it. Retain underspeed/altitude/attitude/actuator limits
and restore policy on release. A throttle floor cannot guarantee control authority
or deceleration in a dive.

Profiles reference existing named tuning plus sparse, typed overrides. Resolve
and freeze session configuration with provenance; supported session controls stay
separate. Preserve intentional inheritance/absence. Use ConfigService preview,
backup, generation checks and atomic apply. Extend its existing nested migration
handling before removing nested retired keys. Never reset a whole section to
defaults to remove one child. Persist one canonical result, remove converted
runtime readers, and retain a compact versioned migration ledger.

## 7. Dashboard and QGC

Both clients consume the same profile catalog, eligibility and start readiness:
stable ID, label/purpose, family/basic-advanced visibility, observation semantics,
supported phases, command contracts, controls and qualification/availability.
Keep selected-but-unavailable profiles visible with one actionable reason.

Beginner flow: connect/verify -> compatible profile -> target -> Start. Installed
profiles provide phase strategy selection; ordinary operators do not assemble
recipes or choose ROS/DDS/MAVSDK. Aircraft changes never silently overwrite saved
connection details, profile or installation geometry.

Reuse the compact control row, acknowledged values, revisions, pending state and
Restore. Labels/units follow backend semantics; hide unsupported controls on older
clients. Reject stale session/phase editors. Show Transition / Following ended /
Target lost / Following / Stopping consistently. Transition disables Start; a
settled phase makes a fresh Start available without replaying the old one. Stop remains reachable independently.
Preserve touch sizing, panel layout, auth/media recovery and read-only reconnect;
never replay aircraft, camera or target actions after reconnection.

QGC keeps vehicle parameters in Facts and firmware-specific behavior behind its
FirmwarePlugin boundary. It does not own a duplicate follower limit/config store.
Keep the fork private/unpublished and create no public QGC PR or release.

## 8. Implementation slices and exit gates

The checkpoint records completed slices; remaining rows are planned. Record
actual revision, checks and remaining work at each slice. Implementation
completion and flight qualification are different statuses.

| Slice | Deliverable | Exit gate |
| --- | --- | --- |
| S0: inventory | Snapshot all eight implementations, saved/private config, requirements and evidence; reconcile stale matrices/docs; record confirmed scope | One reviewed behavior/qualification inventory; no inflated pass claims or silent default adoption |
| S1: catalog | One typed descriptor and eligibility evaluator, explicit input/phase/command semantics and registered implementations | All eight descriptors validated; unavailable, incompatible and not-ready cases distinguished |
| S2: config | Nested migration, exact retirements, generated schema alignment and effective provenance | Preview/apply/rollback, custom-value preservation, inheritance/conflict tests; no retired runtime reads after cutover |
| S3: strategy boundary | Extract needed calculations/reset hooks; remove profile-name/class-name coupling; retain one owner | Characterization fixtures preserve accepted behavior and rejected commands; Stop/takeover/reset races pass |
| S4: public MC | Audit/fix stationary, velocity chase, ground and visual centering; test MC rates at its declared advanced layer | Actual stable-start SIH per behavior; moving targets, mount signs, altitude off/on, limits/loss/retarget/takeover; failed modes stay unavailable |
| S5: public FW | Calibrated image observation -> native FW pursuit; shared EAS/envelope/altitude policy; explicit rate-profile disposition | Actual stable-flight airplane SIH, both altitude modes, sensor changes, bounded turn/path, loss/Stop; no fake measured airspeed |
| S6: external Vector | Timestamp/frame-aware provider boundary and preserved PID/Vector algorithms; measured mount presets | Independent geometry/timing fixtures, horizontal/vertical mounts, ordinary MC/FW SIH, no synthetic image-coordinate substitution |
| S7: VTOL composition | First qualify transition-preserving authority release; select MC Vector/FW native strategy at Start; end on transition; later image pair only if qualified | Actual tailsitter and standard VTOL, both directions, fresh Start after each transition, abort/rescue/takeover/loss overlap, no late Hold or obsolete commands |
| S8: experimental FW | Owner-bound upper-speed/path-priority/minimum-throttle extension, restore and adoption policy | Native normal-behavior regression, finite requests, underspeed/restore/expiry tests and actual SIH; capability remains false until verified |
| S9: clients | Same backend contract in Dashboard/QGC; basic/advanced choices, phase controls and migration messaging | Backend/schema/API and Dashboard gates; QGC build/lint and Unit/Integration with standard exclusions; old-client tests |
| S10: evidence/cleanup | One evidence selector, concise reference figures, generated status matrix and extension guide; remove replaced branches | Links/animations load; trace values present; raw PX4 truth retained; no duplicate runtime catalogs or stale active guidance |
| S11: packaging/bench | Pinned Linux x86-64/ARM64 adapter/setup, service/restart/update/rollback; Windows-first QGC then Linux/Android artifacts | Clean-install/update tests and checksums; cooled Pi/camera bench, then separate disarmed Pixhawk/installation acceptance |
| S12: X-Plane | Operator-started simulator integration and keyboard/manual observation provider | Starts only after supported SIH matrix and reports pass; exact simulator/model/firmware identity, no hardware routing or fabricated truth |
| S13: release/field | Reviewed PixEagle commits/tag/release, private fork delivery and exact configuration handoff | Accepted artifacts/config diff/rollback; firmware flashing and aircraft trials require separate operator approval |

S4/S5 may expose algorithm defects: fix their cause and retest, not just raise
limits or alter targets until a report turns green. S5 and S8 are different gates;
normal FW must work independently of an optional experimental policy. S9 starts
against S1 mocks and follows finalized strategy semantics; large CI builds wait
for a coherent tested candidate. No repeated speculative build matrix runs.

## 9. Verification and evidence contract

Use deterministic tests first, then actual isolated PX4 SIH with stable airborne
starts and independent moving world targets. Cover every existing implementation
at its supported layer; preserve live gates on unqualified modes. Include:

- Both mounts, camera rotation/mirroring/crop, forward/down/rearward rays,
  combined roll/pitch/yaw, +/-180-degree wrapping, near-vertical orientation,
  raw/display quaternion separation and the FW-forward physical -Z convention.
- Clock/skew/uncertainty boundaries, stale/future/duplicate/reordered samples,
  source/estimator resets, invalid calibration and no freshness from polling.
- Requested/effective/observed speed, zero MC request, changing limits,
  altitude on/off/boundaries, anti-windup/saturation and cadence/stall behavior.
- Valid/invalid/repeated retarget, video-only outage versus actual target loss,
  reconnect, one continuity deadline, publisher failure and competing clients.
- Stop, takeover, Land/RTL, disarm, process death, late cleanup and repeated
  teardown; no command or policy restoration after ownership is gone.
- End on transition, no pursuit or automatic resume, transition completion/abort/
  QuadChute under PX4 authority, old-session invalidation, rejected Start while
  transitioning and correct fresh-session controls after settlement.
- Continuous publication while authority requires it; bounded queues and camera
  Stop dispatch <=100 ms / lease-expiry Stop <=400 ms under inference/video load.

Airframes: `sihsim_quadx`, `sihsim_airplane`, `sihsim_xvert` and a pinned standard
VTOL. Freeze physical/envelope acceptance metrics before each comparison. The
existing standard-VTOL altitude failure remains open; do not relax its gate to
rename it passed. Repeat the full application/API path after component tests.

Each accepted run retains exact code/firmware/patch/config/schema/parameter and
runtime identities, observation/target truth, actual PX4 pose and attitude,
nominal/authorized/published commands, phase/authority, speeds, constraints,
results and ULog. Extend the existing read-only visualizer/selector, producing
HTML playback, CSV/JSON and PNG; GIF/MP4 are optional derived summaries. Never
integrate commands into invented aircraft movement or interpolate stale gaps.
Use behavior-specific metrics: position mode does not need to catch a target;
centering does not claim range hold; pursuit needs measured path/closure response.

One machine-readable qualification inventory should generate the matrix and
report links. Separate contract/synthetic, observed SIH, real camera, prop-off
aircraft and field evidence. A single test, AI review or build is not all-mode or
all-installation acceptance.

## 10. X-Plane and future extensions

Current X-Plane support is unmaintained; see the
[disposition](../../WINDOWS_SITL_XPLANE.md). Restore it only as a separate validated
workflow after S10. Pin X-Plane/PX4XPlane, the actual quad-tailsitter model,
firmware and routing; identify its differential-thrust plant separately from the
SIH airframe. Do not transfer simulator tuning to hardware.

A keyboard camera simulator feeds an explicit manual-designation variant at the
shared guidance-input boundary, with declared frame, limits, timestamps and an
activation/expiry lease. A real provider reports measurements; a human requests
a direction. Neither is silently relabelled as the other. This optional input
does not publish aircraft commands directly or manufacture an automatic tracker
lock. Keep manual designation, camera actuation and target truth separate. Test
deadman/focus loss, disconnect, conflicting owners and no reconnect replay; retain
actual simulator/PX4 motion as movement truth. A real rendered-camera tracker loop
remains distinct from angle injection. Existing gimbal/manual-motion exclusion
during aircraft following remains until a dedicated combined-input mode is
specified and qualified; this plan does not weaken that current ownership rule.

Future real distance keeping needs valid range/position. Precision and moving-
platform landing need their own estimator/reference, relative-motion handling,
approach/descent/touchdown/abort behavior and native PX4 integration review.
Reuse observation, mount, session and evidence services; do not call ground
centering or Vector pursuit a qualified landing system.

## 11. References and continuation

- [PX4 VehicleAttitude](https://docs.px4.io/main/en/msg_docs/VehicleAttitude): raw quaternion/frame definition; the actual firmware source/version remains authoritative.
- [PX4 external control](https://docs.px4.io/v1.17/en/ros2/px4_ros2_control_interface): distinct MC/FW setpoints and transition requirements; capabilities depend on the pinned runtime/firmware.
- [PX4 precision landing](https://docs.px4.io/main/en/advanced_features/precland): separate landing estimation/controller workflow, not a property of image centering.
- [MAVLink manual control](https://mavlink.io/en/services/manual_control.html) and [gimbal control](https://mavlink.io/en/services/gimbal_v2.html): separate vehicle-stick and camera-pointing interfaces; the proposed manual-designation input is an application design, not an already supported standard flight mode.
- [Shared FW guidance policy](../04-configuration/fixed-wing-guidance-policy.md) and [session controls](../04-configuration/session-speed.md).
- [Agent guide](../../../AGENTS.md) and [API blueprint](../../apis/api-modernization-blueprint.md).

The two clarification questions are resolved. Continue at the checkpoint's next
open slice; request hardware only at S11. Actual revisions, changed defaults,
tests and qualification scope belong in that checkpoint. Update this plan rather
than creating parallel competing architecture plans.
