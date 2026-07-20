# PXE-0109: Safe Active Retarget And Intent Clarity

## 2026-07-20

- Recovered the interrupted beta8 candidate without changing the running beta7
  public bench or its ignored configuration and credentials.
- Correlated the operator's zero-setpoint report with runtime evidence. The
  selected `mc_velocity_position` follower intentionally commands zero forward
  and lateral velocity; with altitude control disabled and a centered target,
  a valid accepted intent can contain only zeros. No preview dispatch failure
  was present.
- Kept execution-mode authority separate from safety permission. The dashboard
  says **Start Follower Test** only for `COMMAND_PREVIEW` and **Start
  Following** only for `PX4`; circuit-breaker state can permit or inhibit an
  action but cannot rename or reroute it.
- Added a fail-closed target-transition contract. During an active session,
  classic or Smart target replacement first invalidates the follower intent and
  activates commander defaults under the existing lifecycle barriers. A failed
  transition rejects target mutation. The session remains active and resumes
  only after a fresh target update produces another accepted intent.
- Live PX4 tracker-implementation replacement remains blocked. Local command
  preview may replace the implementation while held at defaults and then
  requires a new target.
- Made the follower telemetry card distinguish an accepted all-zero intent,
  fail-closed hold output, and absence of an accepted intent. It also displays
  the selected follower profile description and normalized intent reason.
- Made only the explicit `beginner_lab` profile select
  `mc_velocity_chase`, which gives a first-time replay user visibly changing
  forward/steering intents. Checked-in PX4 defaults, standalone command preview,
  and existing deployments retain their configured follower.
- Focused backend/setup tests passed 340. The affected API/docs gate passed 127;
  Phase 0 passed 477. Dashboard passed 53 suites and 348 tests plus lint and a
  production build. The maintained non-hardware/non-SITL suite passed 3,371,
  with 47 expected skips, one deliberate deselection, and the existing
  Starlette/httpx deprecation warning. Schema, API inventory, Python compile,
  selected fatal lint, and diff-hygiene checks passed.
- Two bounded delegated reviewers exhausted their separate usage quota without
  a verdict. No independent-review claim is made. A bounded local
  safety/API/UI/setup review found no release-blocking defect; minor broader
  follower-controller-history and repeated inactive-warning improvements stay
  out of this operator-feedback release unless concrete testing demonstrates a
  regression.

## Next

Candidate `54271ceecddc06cb17765a3f8c575d1c006e629c` passed the maintained
clean-checkout setup/handoff harness 26/26, including fresh dashboard
install/test/build. Beta.8 was published and then superseded by the narrow
typed-response correction described below. Publish beta.9, preserve the
existing demo credential while redeploying, and repeat public media plus
authenticated command-preview/active-retarget probes. Fresh Ubuntu is the next
maintainer gate; Raspberry Pi, optional AI/GStreamer, PX4/SIH/SITL/HIL, QGC,
production TLS/WebRTC, and field evidence remain separate.

## Public Beta.8 Probe And Beta.9 Correction

- Published immutable beta.8 head
  `385ae4a017de45cfbce4877e747a836ead87d345` and started public run
  `pixeagle_manual_f80299ac-a72a-4c70-baf9-bf70a5038d73` without rotating the
  existing browser credential. Anonymous MJPEG/WebSocket JPEG, authentication,
  runtime/media health, version, and exact-commit checks passed.
- The authenticated probe observed a finite nonzero `mc_velocity_chase`
  command-preview intent and `commands_sent_to_px4=false`. Active classic
  retargeting succeeded and the runtime log confirmed commander defaults were
  activated first.
- The same probe caught that `_execute_tracking_start_action` reconstructed the
  classic result and omitted the `target_transition` evidence. Smart click
  already preserved its complete result. Probe cleanup left Following inactive.
- Added the missing classic result field and executor-level regression. The
  correction passed 397 affected behavior tests, 85 API/inventory/Phase 0
  tests, 4 version-consistency tests, schema, compile, and diff checks. It is
  versioned beta.9 rather than rewriting the published beta.8 tag.
