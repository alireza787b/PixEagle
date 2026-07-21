# Phase 5 Checkpoint: Beta.18 Operator Handoff Controls

- Date: 2026-07-21
- Issue: PXE-0126
- Status: local candidate complete; CI/publication and physical acceptance pending
- Scope: bounded operator-handoff corrections; no physical or aircraft claim

## Decisions

1. Keep beginner setup sequential and reversible. Optional heavyweight features
   are independent questions with visible Enter defaults. Installing service
   controls does not silently enable boot startup, SSH hints, or a runtime.
2. Discover browser addresses from the host interfaces instead of assuming one
   public or private topology. One helper owns classification for both installer
   and lab launcher; explicit loopback and custom-address paths remain available.
3. Treat model labels as presentation metadata only. Validated artifact path and
   digest remain authoritative, and configured selection remains distinct from
   runtime-proven Smart activation.
4. Reuse the existing `COMMAND_PREVIEW` execution mode for the compact follower
   test control. It requires the circuit breaker and never creates a PX4 command
   publisher; no new bypass, profile, or hidden setting was introduced.
5. Keep the gimbal integration provider-based. The only maintained provider is
   `topotek_sip_udp` for Topotek SIP-series UDP GAC/GIC/TRC/OFT messages. Tracker
   and follower code remain provider-agnostic and fail closed on stale data.

## Changes

- Added `scripts/setup/browser_hosts.py` and contract tests; removed duplicated
  host classification from the browser demo wrapper.
- Split dlib, GStreamer, shortcut, service-control, boot, and SSH-hint setup
  choices and synchronized setup docs/tests.
- Added validated optional model display names through the provenance-backed
  upload path, fixed selected-row controls, and exposed active Smart model state.
- Extended the safety status with explicit follower-test state and added the
  compact canonical setting toggle beside the circuit breaker.
- Replaced stale `gm_velocity_vector` tuning instructions with current shared
  configuration, lifecycle, telemetry, and fail-closed bring-up guidance.
- Prepared `/home/alireza/PixEagle_topotek_rtsp_gimbal_client_merge.yaml` as a
  merge-only client template. It leaves PX4 commands blocked and calls out the
  unresolved `.108`/`.109`/historical `.110` address decision.

## Validation

- Focused installer/model/safety backend slice: `125 passed`.
- Focused dashboard component/hook/page slice: `83 passed`.
- RTSP/GStreamer/gimbal/follower contract slice: `229 passed`.
- Installer lifecycle/docs/setup slice: `209 passed`.
- Documentation/installer/browser follow-up: `67 passed`.
- Required API inventory/parameter reload: `72 passed`.
- Dashboard full suite: `54 suites`, `358 tests`, all passed.
- Dashboard ESLint and production build: passed.
- Schema: `40` sections / `535` parameters, synchronized.
- Python compile, Bash syntax, and `git diff --check`: passed.
- Final clean backend suite: `3,444 passed`, `48` expected skips, and one
  non-blocking Starlette/httpx test-toolchain warning tracked as PXE-0127.
- Independent review found three bounded correctness/UX issues. All were fixed
  with regression tests, and the independent re-review returned `GO`.
- GitHub CI, annotated tag, and prerelease publication remain post-commit gates.

## Residual Acceptance Gates

1. Confirm the physical Topotek camera/gimbal address before importing the
   client profile; update both RTSP and UDP host values together.
2. On the isolated client LAN, prove RTSP receipt, real-time pacing, reconnect,
   GStreamer fallback, gimbal status freshness, angle signs, mount geometry,
   packet-loss behavior, and operator abort before enabling PX4 dispatch.
3. Run the documented clean Raspberry Pi Core-first bootstrap, then opt in to
   GStreamer/AI only when target-host capability and thermal evidence pass.
4. Keep QGC receipt, PX4/SIH/SITL/HIL, follower vehicle response, field, and
   aircraft acceptance as separate evidence-backed gates.
