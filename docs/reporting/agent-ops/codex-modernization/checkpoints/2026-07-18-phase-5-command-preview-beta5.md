# Phase 5 Checkpoint: Follower Command Preview Beta.5

**Date:** 2026-07-18
**Slice:** PXE-0107
**Status:** Release candidate and public VPS automated acceptance validated; maintainer Ubuntu acceptance pending

## Decision

Recorded-video follower testing is now supported through one explicit
`COMMAND_PREVIEW` execution mode. It runs the maintained tracker-to-follower
calculation and `CommandIntent` validation path, then records a bounded local
intent history. It has no PX4, MAVSDK, MAVLink, Offboard, or network command
publisher and is not a simulator or vehicle-response test.

The default `PX4` execution mode is unchanged and continues to reject
video-file replay for autonomous Following. A circuit-breaker safety bypass is
not used as a replay authorization mechanism.

## Safety Contract

Preview can start only when all of these are true:

- `Follower.FOLLOWER_EXECUTION_MODE=COMMAND_PREVIEW` is explicitly selected;
- the source is `VideoSource.VIDEO_SOURCE_TYPE=VIDEO_FILE` with an open, fresh
  replay frame;
- a tracker target is active and usable for follower math;
- the follower circuit breaker is available and active;
- `CIRCUIT_BREAKER_DISABLE_SAFETY=false`;
- `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES=false`.

The profile is default-off and applies the complete set of related settings:

```bash
make setup-profile PROFILE=follower_command_preview
```

The mode selector chooses the next session. It does not mutate an active PX4
or preview session in place.

## Implementation Surface

- `src/classes/command_preview.py` owns the local controller and bounded intent
  recorder. Its command-send method is a defensive tripwire.
- `src/classes/following_readiness.py` owns the separate preview readiness
  contract; live PX4 readiness remains replay-rejecting.
- `src/classes/app_controller.py` routes preview lifecycle and tracker output
  through the same follower and setpoint-handler ownership checks, while
  explicitly skipping PX4 connect/Offboard stop operations.
- Typed following status/telemetry expose `execution_mode`,
  `commands_sent_to_px4`, preview readiness, last intent, and a bounded recent
  intent window.
- Dashboard actions say `Start Command Preview`, and status cards label the
  result `Previewing` / `Local only` rather than presenting it as live
  setpoint control.
- The checked-in schema/defaults and `follower_command_preview` profile are the
  only configuration authority; no preview-specific hidden config file exists.

## Validation

- `bash scripts/check_schema.sh` passed; 40 sections / 535 parameters.
- Backend/API/config/safety gate: 396 passed.
- Dashboard: 53 suites / 342 tests passed.
- Dashboard ESLint passed.
- Dashboard production build passed.
- Python compile checks passed for touched modules.
- `git diff --check` passed.
- The first full-suite run exposed stale generated API/MCP provenance and a
  partial-controller shutdown fixture assumption; both were repaired. The
  post-fix maintained suite passed **3,361 tests**, with 48 expected skips and
  one existing Starlette/httpx deprecation warning.
- The API/MCP candidate inventory was regenerated and its current-inventory
  tests passed. The shutdown regression tests and the complete preview suite
  passed after the repair.

No PX4, SIH, SITL, HIL, QGC, Raspberry Pi, GStreamer, WebRTC ICE/TURN,
field, or real-aircraft result is claimed by these checks.

## Release And Handoff Gates

1. Commit and push the candidate, then publish `v7.0.0-beta.5` as a
   prerelease. **Done:** commit `026f7a07dc42a4090cf32ae48964b153d2a8e908`,
   `origin/main`, and the GitHub prerelease are aligned.
2. Stop/reconfigure the existing VPS only after the pushed source is verified;
   preserve the existing owner credential and do not enable vehicle sidecars
   for the browser-only bench. **Done:** the previous beta4 run was stopped,
   the tagged beta5 source was verified, and the browser-only runtime was
   restarted with the explicit preview profile.
3. Validate the public dashboard, preview readiness, one local intent, stop
   behavior, and fresh runtime logs. Retain exact run IDs and timestamps.
   **Done:** see the evidence section below.
4. Provide the fresh Ubuntu Core/Full test handoff. The user must run that on a
   clean host before Raspberry Pi execution. **Ready:**
   `/home/alireza/PIXEAGLE_BETA5_UBUNTU_TEST_HANDOFF.md` and the maintained
   `docs/INSTALLATION.md` are the starting points.

## VPS Beta.5 Acceptance Evidence

The public browser-only bench was started from the tagged source with run ID
`pixeagle_manual_cd168876-0700-4686-aefe-9690b158e254`.

Unauthenticated media probes returned a dashboard `200`, an MJPEG multipart
response with a JPEG marker, and a video WebSocket metadata message followed by
JPEG bytes. The dashboard/API remained authenticated under the browser-session
profile.

One authenticated, reversible command-preview probe then:

- started a normalized tracking ROI and received typed action `202/success`;
- started `COMMAND_PREVIEW` and received typed action `202/success`;
- observed `following_active=true`, `execution_mode=COMMAND_PREVIEW`, and a
  `last_command_intent` from `MCVelocityPositionFollower` with four finite
  fields;
- verified `commands_sent_to_px4=false` and `command_publication.source=command_preview`;
- stopped preview and tracking through typed actions, both `202/success`, and
  finished inactive.

The exact authenticated probe used owner-only credentials from the private VPS
handoff file; no credential, cookie, or token is recorded here. The runtime
log has 450 INFO, 5 expected WARNING, and no backend ERROR entries. The one
CRITICAL entry is the intentional lab warning for public `trusted_lan_legacy`
exposure. Expected browser-only warnings include MAVLink2REST/PX4 being absent,
the source file's 1280x720 frame differing from the conservative 640x480
capture setting, and OSD auto-degrading on the VPS CPU. These are recorded
boundaries, not hidden failures.

Evidence manifest:
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-18-pxe0107-beta5-vps-command-preview/manifest.json`

## Remaining Boundaries

Maintainer acceptance, clean Ubuntu installation, Raspberry Pi Core/Full and optional
AI/GStreamer evidence, tracker robustness benchmarks, PX4/SIH/SITL/HIL
integration, QGC receiver acceptance, production TLS/WebRTC ICE/TURN, and
field/aircraft tests remain separate gates. They are not silently covered by
Command Preview.
