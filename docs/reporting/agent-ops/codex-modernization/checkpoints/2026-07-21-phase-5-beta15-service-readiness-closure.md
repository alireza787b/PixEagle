# Phase 5 Checkpoint: Beta.15 Service Readiness Closure

**Date:** 2026-07-21 UTC
**Slice:** PXE-0118
**Status:** beta.15 published; real Ubuntu service/update and final CI gates passed

## Scope

This slice closes the service failure reported during the maintainer's Full AI
installation on a disposable Ubuntu host. It extends PXE-0117 with real-host
evidence and fixes found only after exercising update, systemd, tmux, and a
no-PX4 lab runtime together.

It does not claim Raspberry Pi, Jetson, PX4/SIH/SITL/HIL, QGC, remote WebRTC,
field, or aircraft acceptance.

## Findings

The first repaired service run exposed four independent issues:

1. `scripts/service/install.sh` changed the executable bit of tracked launcher
   files. The updater correctly saw a dirty checkout and refused automatic
   rollback, but the mutation came from PixEagle itself.
2. MAVSDK Server does not open its gRPC listener until it discovers a vehicle.
   Requiring port `50051` during generic service startup therefore rejected a
   valid no-PX4 lab runtime.
3. Update/repair offered immediate service start and reboot while the updater
   still owned lifecycle, source, and environment resources.
4. Repeated failures could produce a systemd restart storm. After a bounded
   start limit was added, deliberate operator starts could remain blocked by
   the consumed rate-limit budget.

The final status audit also found two presentation defects: the exact tmux
session was displayed as `unknown windows`, and an absent optional legacy
telemetry WebSocket was shown as a red failure.

## Implementation

- Service installation now validates tracked launchers instead of chmodding
  them. Only generated command files receive executable permissions.
- Startup readiness requires the dashboard, backend, MAVLink2REST, and the
  exact healthy tmux component contract. MAVSDK Server remains process-
  supervised; PX4 discovery is a separate fail-closed application state.
- Update/repair may install or enable service management, but defers immediate
  runtime start and reboot until reconciliation has released its resources.
- Generated units bound automatic restart attempts with
  `StartLimitIntervalSec=300` and `StartLimitBurst=3`.
- Explicit `pixeagle-service start` and `restart` reset a prior systemd failure
  budget before making the new operator request. Automatic restart behavior
  remains bounded.
- Service status now reads an exact session window count from tmux inventory
  and identifies port `5551` as optional when absent. A foreign listener on
  that port is still reported as a conflict.
- Maintained workflows now pin `checkout`, `setup-python`, `setup-node`,
  `upload-artifact`, and Codecov to reviewed immutable commits. Dependabot
  tracks GitHub Action updates monthly, and the gimbal simulator example no
  longer teaches obsolete action tags or Python 3.8.

## Repository Validation

The code changes through `ea725c76c4355d3241010c422134a94d70d27eb3`
passed:

- runtime ownership and service CLI suite: `53 passed`;
- installer/setup/update/config lifecycle group: `271 passed` before the final
  status-only change;
- required API inventory and parameter reload gate: `72 passed`;
- infrastructure documentation suite: `26 passed`;
- schema gate: passed (`40` sections, `535` parameters);
- workflow YAML parsing, immutable-action pin guard, Bash syntax, and
  `git diff --check`: passed;
- SITL workflow contract suite: `100 passed` after replacing two stale
  `upload-artifact@v4` assertions with the immutable-pin contract;
- warning-level ShellCheck: only the documented dynamic-source `SC1090`
  warnings remain.

The pre-cleanup candidate run `29807370257` is retained as runtime-candidate
evidence. The first post-pin run `29808404016` correctly caught two stale test
assertions; those assertions were updated to the durable pin contract. The
corrected release-gate run `29809434623` passed all required jobs, including
the full backend suite (`3417 passed, 49 skipped, 1 deselected`), dashboard
tests/lint/build, Windows setup contracts, schema/infrastructure checks, and
coverage. Its logs contain no Node 20 action-runtime deprecation warning. The
annotated prerelease `v7.0.0-beta.15` is published at the tested commit
`c34c8165a22ab142c60103247926403e8d2701b4`.

## Disposable Ubuntu Evidence

Host class: Ubuntu 24.04.4 LTS, x86_64, Full AI profile, source-built OpenCV
4.13.0 with GStreamer preserved. No local model and no PX4 vehicle were
configured.

The host fast-forwarded from `91ce6efb` to exact commit `ea725c76` through the
maintained update command. Reconciliation reused and verified the existing
virtual environment, dashboard dependency tree, OpenCV provider, PyTorch CPU
profile, Ultralytics runtime, MAVSDK Server binary, and MAVLink2REST binary.
The checkout remained clean.

After an explicit restart and a 10-second settle period:

- systemd: `active/running`, `Result=success`, `ExecMainStatus=0`,
  `NRestarts=0`, auto-start enabled;
- exact run: `pixeagle_service_d7ea0227-657e-4c45-a334-1159b6df007b`;
- tmux contract: one healthy window with live `MainApp`, `Dashboard`,
  `MAVLink2REST`, and `MAVSDKServer` panes;
- owned listeners: loopback `3040`, `5077`, and `8088`;
- dashboard: HTTP `200`, 658 bytes;
- typed About route: HTTP `200`, 1,262 bytes;
- MJPEG: continuous multipart response, 1,548,288 bytes observed in six
  seconds;
- maintained GStreamer capability check: OpenCV 4.13.0 reports GStreamer,
  `appsrc`, `videoconvert`, `x264enc`, `rtph264pay`, and `udpsink` are present,
  and the effective software encoder path resolves to `x264enc`;
- optional tracker providers: OpenCV CSRT present and dlib 20.0.1 imports;
- active component JSONL logs: zero error-like records across backend,
  dashboard, main app, MAVLink2REST, and MAVSDK Server.

Port `50051` was absent because MAVSDK was waiting for vehicle discovery. Port
`5551` was absent because the legacy telemetry WebSocket is optional. Media
health reported a fresh frame publisher, no issues, no connected media clients,
and GStreamer UDP output disabled by the current default configuration. These
states are expected and do not prove remote receipt.

## Review Gate

The bounded release review returned **GO for beta.15 Ubuntu service/runtime
publication after CI**, with these explicit boundaries:

- Linux/systemd: lifecycle ownership, bounded restart policy, update deferral,
  clean source state, and explicit recovery behavior are evidenced.
- MAVSDK/PX4: no-PX4 service startup is valid, but vehicle discovery, telemetry,
  Offboard commands, and flight behavior are not evidenced.
- Media/API: process-local dashboard, About, and MJPEG paths pass; remote
  browser/QGC/WebRTC receipt is not inferred.
- Code hygiene: the final fix is narrow, behavioral tests cover the two status
  regressions, and no compatibility alias or hidden configuration was added.

## Next Gates

1. Run the documented one-line Core/default flow on a fresh Ubuntu host as a
   first-time user, then test update/repair after interruption.
2. Run Core first on Raspberry Pi 5 using the exact tagged commit. Add Full AI,
   model, dlib, GStreamer, and managed service one capability at a time.
3. Keep QGC, PX4/SIH/SITL/HIL, production TLS/WebRTC, and field acceptance in
   their own evidence-bearing slices.
