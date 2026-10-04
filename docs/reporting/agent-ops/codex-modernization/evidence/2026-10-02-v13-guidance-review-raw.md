# V13 guidance implementation review — raw AI engineering feedback

Reviewer: `/root/v13_guidance`, AI engineering review, 2026-10-02.
This is software review feedback, not an external pilot review or physical acceptance.

The original Vector control interval used wall time recorded at construction, so
connection and Offboard startup delay could become first-step acceleration. The
repair uses the existing one-period bounded monotonic interval and resets session
history. This deliberately becomes conservative if processing runs slower than
the configured reference rate; it does not catch up missed time in a single step.

Raw Euler interpolation could hide an inadmissible rearward observation or take
the long path across wrapping. The repair validates the camera-to-aircraft body
ray first, then filters that ray along its shortest spherical path. Both raw and
filtered front-hemisphere validity remain required. Actual provider geometry and
horizontal-mount physical acceptance still need evidence separate from this math.

Command filtering previously depended on calls per second, and Chase normal
atomic output bypassed its command smoothing option. Time-normalized coefficients
retain their new-sample weighting at the configured reference rate. Chase smooths
velocity once; its dedicated yaw pipeline remains the sole yaw EMA.

The final authorized guidance limiter uses each follower's existing acceleration
and yaw-change limits after continuity blending. It references accepted submitted
commands, including ordinary-loss commands, rather than candidate calculations.
Current safety limits are reapplied after shaping. Ordinary loss and Stop must
bypass guidance slew, while invalid geometry, stale altitude and genuine safety
refusals must be immediate handoff reasons instead of ordinary recoverable loss.

The provider composed snapshots with a current timestamp while preserving old
angle objects; the tracker then assigned a fresh processing timestamp to those
angles. Processing and status packets now preserve the body-angle sample receipt,
monotonic time and sequence. Cached output cannot become fresh by video updates.
This supports post-selection freshness but cannot establish firmware target
identity without request-associated camera telemetry.

No gain, velocity envelope or acceleration setting was increased. The v12 logs
do not justify flight tuning: the real camera image is not coupled to SIH pose.
Independent command signs, slew, altitude restrictions and simulated PX4 response
are the evidence to collect before another operator retarget handoff.

Final independent continuity review: sparse overrides validate all configured
branches and known follower identities; legacy flat settings remain global.
The provisional authority cap now applies to new guidance, while final shaping
records actual submitted speed for recovery-distance integration. Repeated taps
retain the original loss budget. The ordinary-loss safety guard must preserve
body-right inertial-course compensation; lateral owner zeroing is restricted to
normal/retarget guidance. A missing-current-provider fallback in retarget sample
admission was flagged to the application owner for fail-closed correction.

Second final read-only safety review, after application teardown shielding:

- Follow teardown creates one shielded owner task, marks stopping before its
  first await, and captures the original session/aircraft/reason. A cancelled
  request waiter cannot cancel that task; subsequent startup joins completion
  before replacing runtime components. The code supports cancellation safety;
  a dedicated first-waiter-cancellation test was requested to supplement the
  existing concurrent-join test.
- The retarget sample guard now requires a live matching provider, real angle
  receipt timestamps/sequence, post-LOC receipt and <=350 ms monotonic age.
  Native commit rechecks frame/source/runtime and camera ownership after the
  handshake. A missing final shutdown-flag check was flagged: shutdown starts
  before acquiring the selection-held lifecycle lock, so an already admitted
  handshake otherwise could still send LOC during shutdown. The selection
  owner was asked to add refusal at final commit.
- Invalid edge coordinates are adapter-validated before manual cancellation,
  target generation changes or continuity entry. Do not interpret that refusal
  as an interrupted active target.
- QGC handoff presentation requires fresh native status, backend runtime
  identity, matching aircraft owner and an inactive/non-pending follow session.
  Cross-aircraft and command-preview cases have explicit tests. Retained Hold
  is historical follow-session evidence, not an independent current-flight-mode
  sensor; operator wording must continue to preserve that distinction.
- The SIH driver uses an isolated loopback-only namespace and fresh synthetic
  observation metadata. It explicitly excludes native camera selections,
  physical mounts and camera-video convergence. Its current pose-direction and
  all-publication-success checks should be supplemented with phase-correlated
  actual published-command signs and successful ACTIVE reacquisition before a
  complete retarget/loss evidence claim. Stop/pilot takeover and constrained
  networks are not covered by this driver merely because it passes.

Independent read-only diagnosis of `v13-evidence-chase-vertical-7`:

- Retargeting restored ACTIVE at approximately 1.53 seconds. The deliberate
  loss/reacquisition phase also restored ACTIVE. The final
  `maximum_coast_time_reached` occurred in the intentionally exhausted recovery
  phase and produced confirmed Hold; it is not evidence of failed reacquisition.
- Net descent over the entire left/down phase was approximately 0.0293 m,
  narrowly below the driver's 0.03 m assertion. The confirmed ACTIVE interval
  descended approximately 0.188 m. Earlier upward vehicle motion affects the
  full-phase net result; published downward intent and sustained confirmed
  response must be correlated separately from that initial transient.
- Chase's PID histories persist across deliberate target replacement. Prior
  upward-target integral could contribute to a conservative vertical reversal,
  but this run lacks PID component traces and does not prove that mechanism.
  The captured configuration disables proportional-on-measurement. Do not
  increase gains or weaken acceptance thresholds based on this observation.
- The evidence owner is using a stronger independent down-target fixture and
  longer confirmed observation interval, with unchanged gains, safety envelope
  and response thresholds. This is a fixture correction, not flight tuning.

Strict SIH slew checks subsequently exposed a real loss-to-guidance defect:
clearing coordinated-turn lateral velocity after the three-axis limiter added
an unbudgeted change. The limiter now reserves lateral zeroing within the same
acceleration budget. A larger retained inertial-coast lateral component unwinds
at the bounded rate with zero yaw before turn guidance resumes; forward/down
remain unchanged while that component consumes the entire budget. Immediate
safety restrictions retain precedence. Four regressions cover small and large
residual components at both follower accelerations. The 251 follower/continuity
tests passed after this correction. SIH source snapshots must be refreshed; the
earlier full backend results describe the preceding source revision.
