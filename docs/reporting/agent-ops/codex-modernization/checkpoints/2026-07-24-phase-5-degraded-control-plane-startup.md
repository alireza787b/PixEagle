# Phase 5 Checkpoint: Degraded Control-Plane Startup

Date: 2026-07-24
Issue: PXE-0141
Status: local implementation complete; Ubuntu unavailable-source acceptance pending

## Problem

External video acquisition ran during synchronous AppController construction.
An unreachable RTSP endpoint could therefore exhaust nested GStreamer and
OpenCV attempts before Uvicorn accepted requests. Launcher readiness treated
the missing backend as a total startup failure and removed the dashboard,
preventing the operator from correcting the source in Settings or inspecting
Logs and health.

The launcher also treated MAVLink2REST and MAVSDK panes as control-plane
requirements, and manual video reconnect could report a stale cached frame as
successful recovery.

## Changes

- Start and verify the backend API before one bounded external video-source
  activation.
- Serialize capture reads separately from source lifecycle transitions, so
  reconnect/release can retire a capture blocked in backend I/O; discard late
  frames from retired captures and keep retry/backoff ownership at the caller.
- Publish explicit unavailable/degraded media state while preserving Settings,
  Logs, typed status, and reconnect.
- Run the reconnect action outside the API event loop and require a real source
  reopen before reporting success.
- Expose sanitized component startup state through typed runtime/about status.
- Require backend and dashboard runtime panes while allowing absent or failed
  MAVLink2REST/MAVSDK sidecars to degrade in combined and separate tmux
  layouts.
- Keep runtime launch noninteractive: setup and repair own dependency
  installation.
- Reuse an already verified GStreamer-enabled OpenCV provider during guided
  repair instead of rebuilding it.

## Validation

- Video lifecycle, FlowController, media reconnect, and typed status:
  `100 passed`.
- Runtime process ownership and required/optional component policy:
  `69 passed`.
- Installer UX and setup profiles: `203 passed`.
- AppController safety and capability lifecycle: `163 passed`.
- Required API inventory and parameter reload: `73 passed`.
- Complete Phase 0 guardrail: `490 passed` with one tracked third-party
  deprecation warning.
- Generated schema: current, `38` sections and `513` parameters.
- Process-level source-failure smoke: the API returned its expected
  unauthenticated `401` response while source activation was blocked, proving
  the listener was reachable; final startup state was `degraded` and video
  state was `unavailable`.
- Python compile, Bash syntax, ShellCheck, docs consistency, and diff checks:
  passed.

A bounded independent review found two blockers not covered by the first test
round: a synchronous read owned the lifecycle lock needed by reconnect, and a
separate tmux window could disappear after optional-sidecar exit. Both findings
are closed by real blocking-read and separate-window tmux regressions.

## Evidence Boundary

The local evidence proves process ordering, bounded failure, runtime ownership,
status reporting, and recovery contracts. It does not prove a physical RTSP
camera, GStreamer decoder compatibility, Raspberry Pi/Jetson performance,
MAVLink/PX4 connectivity, browser behavior on the operator host, QGC, field
operation, or aircraft control.

## Next Gate

Update a stopped Ubuntu checkout through `make update` (or run `make repair`
only if source was already changed with `git pull`). Start with an unreachable
RTSP URL and verify that the dashboard, Settings, Logs, runtime status, and
reconnect action remain available. Then correct the source and confirm recovery
without restarting the process. Keep PX4 command output disabled for this gate.
