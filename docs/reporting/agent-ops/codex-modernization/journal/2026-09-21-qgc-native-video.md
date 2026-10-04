# 2026-09-21 — PXE-0175 native JPEG provenance and no-aircraft preview

- Completed the backend slice-2 gate: immutable frame provenance, capture and
  publication freshness, source/output invalidation, encoded-cache isolation,
  serialized frame pairs, exact-ACK delivery challenge, and advertised read-only
  media/status capabilities. Authentication and following boundaries remain.
- Added explicit fixture `--no-aircraft`: live authenticated numbered video
  works while both identity channels stay disconnected before and after
  observational verification. No aircraft, camera, MAVSDK or service starts.
- Final focused backend selection: 948 passed, including 36 provenance cases;
  schema 43/606, candidate, compile, fatal Python lint and diff checks passed.
- Read-only real-startup audit confirms aircraft connection is separate from
  capture; 26 existing no-PX4 lifecycle/preview contracts passed. After the
  operator chose recorded video, prepared a private actual Core source/config
  snapshot with bundled `test4.mp4`, viewer auth and inhibited routing. Seven
  preparation/schema/isolation tests passed; the paired owner will start it in
  the chosen harness. Preparation did not open video or start the application.
- First actual Core launch exposed a runner configuration error: field schema
  accepted host:port, but the runtime local-only Host policy rejected it. Kept
  the failed snapshot/log, fixed the Host entry without loosening policy and
  added runtime exposure validation. V2 preparation has eight passing tests.
- Authorized v2 Core launch in the existing Docker `none` network succeeded.
  Authenticated context/status and two decoded real-file JPEGs passed; frame
  provenance/challenge matched, both aircraft channels remained disconnected
  and following stayed inactive. Actual file-loop processing continued. The
  runtime stays available for the paired QGC owner's GUI/operator acceptance;
  no aircraft, camera, control action, sidecar or service was started.
- Preserved exact commands, source/artifact hashes, raw logs/JUnit, package
  versions and baseline CI qualifiers in the
  [backend checkpoint](../checkpoints/2026-09-21-qgc-native-video.md).
- Combined slice 2 remains in progress until the paired QGC display, lifecycle,
  stock/custom builds, UI and raw simulated-operator feedback gates are recorded.
  No real operator, camera, aircraft, deployment or release qualification claim.
- Paired Linux technical video gates subsequently passed: all four builds,
  custom 407/407, stock 405/405, and 40 displayed-frame cases in each software
  and threaded OpenGL mode. Real Core replay reached QGC Release without PX4;
  raw simulated operator feedback is retained. Final fullscreen affordance
  checks belong to the paired checkpoint; human user feedback is pending.
- Host desktop launcher stopped its backend after QGC exited. The backend
  completed its shutdown sequence, then MAVSDK 3.15.3 emitted an interpreter
  finalization warning. Reproduced it in an unconnected dependency-only object
  lifetime probe (exit zero), confirmed matching baseline SDK version and
  unchanged construction/stop code, and recorded it without a production patch.
  Snapshot remains valid; no residual host demo server found. A current isolated
  GUI harness remains intentional and separately owned by the paired agent.
