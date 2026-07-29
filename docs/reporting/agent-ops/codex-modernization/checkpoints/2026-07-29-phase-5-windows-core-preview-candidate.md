# Phase 5 Checkpoint: Native Windows x64 Core Preview Candidate

Date: 2026-07-29
Issue: PXE-0151
Status: native baseline passed; authenticated candidate local gates passed;
native authenticated CI and clean-host operator evidence pending

## Scope

This slice defines one deliberately narrow native Windows candidate:

- Windows 11 x64;
- CPython 3.11 or 3.12 x64;
- Node.js 24 with npm 10 or 11;
- Core dependencies only;
- bundled looping video and classic CSRT/KCF tracking;
- loopback-only dashboard and backend with one `browser_session` account;
- guided credentials with Enter defaults of `admin/admin`, preserving an
  existing valid account on repair;
- owner-only current-SID credential directory/file ACL, revalidated at startup;
- authenticated HTTP JPEG, WebSocket JPEG, and WebRTC signaling/transport;
- exact receipt-owned start, status, restart, and stop.

Optional manifest-pinned MAVSDK Server and MAVLink2REST sidecars are limited to
binary acquisition. The preview does not start them because MAVSDK Server
cannot scope its unauthenticated gRPC listener to loopback. Their presence does
not establish process readiness, MAVLink routing, PX4 discovery, simulator
behavior, or vehicle control.

## Documentation Changes

- Unified guided Linux loopback, guided Linux network, and Windows preview
  onboarding on the same `demo_lan_browser` credential contract. Raw
  `make demo`/`local_dev` remains an explicit loopback developer compatibility
  path rather than a beginner installer path.
- Replaced the broad experimental Windows page with an exact preview matrix,
  prerequisites, setup/lifecycle commands, sidecar boundary, and acceptance
  gates.
- Kept the main README concise and retained WSL/Linux as the maintained
  recommendation.
- Linked the preview from the documentation and installation indexes.
- Replaced unsafe port-kill, venv-deletion, and package-lock deletion advice
  with receipt-owned lifecycle and lockfile-enforced repair guidance.
- Removed the stale implication that native Windows supports the Linux
  `field_qgc_video` custom-GStreamer profile.
- Recorded PXE-0151 as `in_progress`.

## Explicit Exclusions

AI/model management, NCNN, dlib, custom GStreamer, Windows service/auto-start,
ARM64, camera hardware, LAN/public exposure, PX4, SIH/SITL, X-Plane, Offboard,
HIL, field use, and aircraft operation are unsupported or unvalidated.

## Validation

- The pre-auth Windows baseline at `090744f5` passed native GitHub Actions run
  `30442509410`, including idempotent setup, exact lifecycle ownership, and
  decoded HTTP JPEG, WebSocket JPEG, and WebRTC before and after restart.
- Current authenticated setup/profile/Windows/auth/exposure/docs contracts:
  `465 passed, 9 skipped`. The skips are native-Windows-only execution tests
  on the Linux development host.
- Focused Windows credential/runtime/media contracts: `36 passed, 5 skipped`.
- Model-policy, model-upload, and model-API regressions: `106 passed`.
- Required API inventory and parameter-reload guardrails: `73 passed`.
- Schema drift, shell syntax, Python compile, scoped undefined-name, workflow
  YAML, `git diff --check`, and Windows CRLF checks passed.

The earlier native run did not exercise browser-session media. No native
authenticated Windows result is claimed until the candidate workflow passes.

## Next Gates

1. Pass the exact authenticated Windows CI setup/runtime contract.
2. Preserve the credential hash across repeated setup and retain decoded
   authenticated HTTP JPEG, WebSocket JPEG, and WebRTC evidence.
3. Complete a clean Windows 11 x64 operator setup and lifecycle walkthrough.
4. Keep every excluded capability outside the support statement until it has
   a separate implementation and evidence gate.
