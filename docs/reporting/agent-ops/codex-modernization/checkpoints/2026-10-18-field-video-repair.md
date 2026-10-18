# Field video repair checkpoint — 2026-10-18

## Scope

This checkpoint covers the first field-repair slice: QGC media recovery,
camera-status demand ownership, movable PixEagle panels, and continuity-policy
diagnostics. Flight gains, speed limits, mount geometry, altitude settings, and
the circuit breaker were not changed.

## Changes

- QGC keeps media identity separate from aircraft/status context during transient
  context failures. Receiver attempts use a generation and retire old callbacks;
  retry and presentation watchdogs do not replay tracking or camera actions.
- Camera status polling is owner-scoped. Closing Options cannot stop polling
  required by the camera-control panel. Status retries distinguish refreshing,
  permission, following, and actual disconnection.
- PixEagle panels can be dragged from their title or unused background/footer,
  stay within the current Fly View bounds, avoid known widget obstacles, and
  retain independent sizes and positions.
- A video stall no longer fabricates loss for a tracker that explicitly declares
  independent camera evidence. That tracker is refreshed under the existing
  model-state barrier; vision trackers remain fail-closed until a fresh frame.
- Target-continuity diagnostics expose the effective frozen policy and its source
  (`configured_global`, `follower_override:*`, or `compatibility_defaults`). A
  missing legacy policy is reported for Config Sync migration rather than being
  silently widened.
- RTSP GStreamer defaults now keep RTCP and RTSP keep-alive enabled. The two
  advanced settings are explicit and validated through the generated schema.

## Validation

- QGC build: `build/pixeagle-custom-debug-latest2` completed successfully.
- QGC focused suites: `PixEagleClientTest`, `PixEagleVideoControllerTest`, and
  `PixEagleCameraClientTest` passed (100%).
- PixEagle targeted backend/video/continuity suites: 105 passed; schema check
  passed.
- Broader PixEagle safety/configuration/API selection: 383 passed; one existing
  deprecation warning remains in `api_v1_errors.py`.
- QGC pre-commit checks passed for C++, QML structural checks, safety checks,
  vehicle null checks, and diff hygiene. The local `qmllint` hook cannot run
  because this Qt SDK does not include the `qmllint` executable; the QGC build
  still compiles the changed QML resources.

## Open evidence

The Pi was reachable at `192.168.1.160` and the camera ports `554` and `80`
were reachable once. The Pi then became unreachable during the read-only RTSP
comparison and was at 61.5°C immediately before that loss. No Pi service or
configuration was changed. The RTSP comparison and the required 30-minute soak
must be rerun after the Pi is powered with active cooling. Operator acceptance,
SIH loss/reacquisition, and Windows-first handoff remain open.
