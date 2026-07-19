# Phase 5 Checkpoint: Beta.6 Beginner Lab And Local Follower Test

**Date:** 2026-07-19
**Slice:** PXE-0108
**Status:** Release-candidate validation and live no-PX4 smoke complete; release/push, public refresh, and maintainer Ubuntu acceptance pending

## Decision

The beginner workflow has one clear boundary:

```text
mutable-main one-liner -> Core setup -> make demo -> recorded-video local follower test
```

The one-liner prepares a Core host and leaves the runtime stopped. `make demo`
applies the canonical `beginner_lab` profile and starts only the main app and
dashboard. It does not silently install AI/GStreamer/dlib/models, enable a
system service, open firewall ports, start PX4 sidecars, or enable boot
auto-start.

The checked-in runtime default remains `Follower.FOLLOWER_EXECUTION_MODE: PX4`.
Recorded video is never an autonomous PX4 Following source. The explicit
`COMMAND_PREVIEW` mode runs the shared tracker-to-follower calculation and
records bounded `CommandIntent` values locally. The circuit breaker must remain
active. Diagnostic safety-bypass flags are default-off; when an operator
explicitly enables one, the local test remains available with a visible warning,
but no PX4/MAVSDK publication becomes possible.

## Implementation

- `scripts/setup/apply-setup-profile.py`
  - added `beginner_lab` while keeping `demo_lan_browser` network-only so its
    cleanup preserves independently selected runtime choices;
  - reads the bundled video path and Core classic tracker from checked-in
    defaults so stale local video/tracker choices cannot break `make demo`;
  - validates profile serialization before atomic write;
  - falls back to normalized builtin scalars and safe YAML when ruamel's
    comment-preserving output is invalid.
- `scripts/setup/run-beginner-demo.sh` and `Makefile` provide the short launch
  command.
- `src/classes/following_readiness.py`, API contracts/snapshots, and dashboard
  readiness/status surfaces carry explicit bypass state and warnings.
- README, installation/setup/follower docs, schema descriptions, changelog,
  issue register, and phase map now describe the same profile and claim
  boundary.
- The root README is now a 200-line-class beginner-first entry page instead of
  a duplicated operations runbook. Detailed networking, service, binary, AI,
  GStreamer, QGC, and deployment procedures remain in linked maintained docs.
- Dashboard local-test readiness no longer inherits the live-PX4 replay
  rejection field. Typed backend warnings now distinguish the local follower
  calculation bypass from the dangerous live safety-module failure bypass.

## Evidence

### Automated

- Final setup/docs gate: **186 passed**, including the transition that
  shrinks `API_ALLOWED_HOSTS` and previously generated malformed YAML.
- Final affected backend/API/docs gate: **285 passed**. It includes confirmed
  typed-action tests for both bypass flags with PX4 connection, Offboard,
  command-dispatch, and MAVSDK setter tripwires. The final independent setup
  and safety reviews both returned **GO**.
- The earlier broad beta6 gate before the serializer repair remains useful:
  clean-default
  backend **3362 passed, 48 skipped, 1 existing warning**; dashboard **53
  suites / 343 tests passed**. The final post-review dashboard rerun also passed
  **53 suites / 343 tests**, lint, and production build. Schema, API inventory,
  syntax, dry-run demo, and diff checks passed.

Evidence manifest:
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-19-pxe0108-beta6-beginner-lab/manifest.json`

### Real local runtime smoke

Runtime run ID:
`pixeagle_manual_748af2f4-11f8-496a-b183-af661b34878f`

- `make demo` reached backend `5077` and dashboard `3040` readiness.
- Video-file replay reported fresh frames and looped normally.
- Typed tracking start returned `202/success`.
- Typed circuit-breaker bypass enable returned `202/success` and an explicit
  warning-bearing state.
- Typed `offboard-start` with `reason=start_command_preview` returned
  `202/success`, `following_active=true`, and `execution_mode=COMMAND_PREVIEW`.
- Following telemetry recorded 61 accepted local preview intents.
- `commands_sent_to_px4=false`, `sends_mavsdk_commands=false`, and the
  publication source was `command_preview`.
- Typed stop actions completed successfully; the safety bypass was disabled
  before cleanup.

This is process-local evidence only. It does not prove PX4, MAVLink, MAVSDK,
SIH/SITL/HIL, QGC receiver, WebRTC ICE/TURN, tracker accuracy, vehicle
response, Raspberry Pi compatibility, or field safety.

## Risks And Remaining Gates

- The Core one-liner uses mutable `main` and is for lab/development only. The
  Raspberry Pi handoff must use the exact reviewed 40-hex commit installer.
- Full AI remains architecture/device/model dependent. Init reports degraded
  or manual states; it does not silently claim YOLO/SmartTracker readiness.
- GStreamer/OpenCV replacement, dlib, QGC networking, service ownership, and
  auto-start remain explicit follow-up workflows.
- WebRTC over public plain HTTP remains intentionally disabled/fallback-only
  until a reviewed ICE/TURN deployment exists.
- Two nonblocking release-tooling debts remain recorded rather than expanded:
  semantic YAML round-trip comparison beyond parseability, and consolidation of
  manually duplicated version metadata.
- The next acceptance gate is a fresh Ubuntu Core install following the short
  guide, followed separately by optional Full/AI, GStreamer, Raspberry Pi, and
  PX4-in-loop testing.

## Next Planned Slice

Complete the final clean validation and release `v7.0.0-beta.6`, refresh the
public lab VPS from that commit, publish the exact test URL/build metadata, and
hand the maintainer the Ubuntu Core test procedure. Do not begin Raspberry Pi
or vehicle testing until the fresh Ubuntu handoff is accepted.
