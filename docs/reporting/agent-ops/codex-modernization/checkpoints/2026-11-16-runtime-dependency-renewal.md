# Runtime and dependency renewal — 16 November 2026

## Scope

Hardware deployment resumes only after operator authorization. No firmware was flashed,
no PX4 parameters changed, and no following/movement action was issued to the
physical aircraft. Resume hardware deployment and physical camera-axis checks
only after the renewed simulator workflow is reviewed. The operator has now
requested the Pi update and final bench check; its results belong to the private
deployment evidence, not a general hardware qualification claim.

| Dependency | Previous pin | Reviewed replacement |
| --- | --- | --- |
| Python gRPC wrapper | `mavsdk==3.15.3` | `mavsdk-grpc==4.0.5` |
| MAVSDK Server | `v3.12.0` | `v4.2.0` |
| MAVLink2REST | `1.0.0` | `1.1.1` |

Upstream reused the `mavsdk` Python distribution name for a different native API.
Runtime, tools and examples now import `mavsdk_grpc` explicitly; no shadow alias
or second runtime client path is retained. The shared managed-setup policy
checks the maintained client before removing a retired `mavsdk<4` distribution.
Windows preview and Linux setup use the same migration. Linux retains exact
venv rollback and the existing OpenCV/GStreamer provider.

The binary manifest remains the single source for platform assets and upstream
SHA-256 pins. Linux x86-64 replacements were downloaded and verified. ARM64
execution, Pi deployment and physical acceptance remain pending. The renewed actual Gazebo session verifies that the maintained wrapper imports
`mavsdk_grpc.system`, starts with Server v4.2.0, and observes the same PX4 UID as
MAVLink2REST 1.1.1. Association is verified through the authenticated API. An
earlier probe without an autopilot timed out awaiting discovery; it is retained
as an incomplete probe, not compatibility evidence. Operator following acceptance
and hardware deployment remain separate.

## Demonstrated repairs

- Unavailable per-message MAVLink2REST responses (`None`, JSON null, 404) and
  malformed message payloads no longer invalidate fresh aircraft identity.
  Missing measurements remain unavailable and cannot authorize following.
  Aggregate corruption and transport failures still invalidate the link.
- Runtime retention protects each live writer through a per-process marker.
  Linux tokens contain boot identity and process start ticks, independent of
  wall-clock corrections and PID reuse. The original manifest creator may exit
  without making its active component writers disposable. Bootstrap capture
  does not require third-party imports on Linux.
- Installer tests copy the configuration implementation as one complete package;
  native sensorless test packets now carry the canonical phase-specific Start
  context instead of failing before the boundary they intended to exercise.

## Verification

Evidence: `reports/sitl/follower-consolidation-20261111/`.

- Initial client migration/drone-interface checks: 1,075 passed.
- Integration/setup/API/guide checks: 428 passed.
- Logging and bootstrap-pipe regressions: 19 passed.
- Complete renewed unit run: 7,493 passed, 11 skipped, 14 subtests passed.
  The skipped optional GI cases are not claimed as exercised. Earlier failed and
  interrupted runs remain retained alongside the final passing evidence.
- Schema drift, API candidate inventory, syntax lint and whitespace checks pass.
- QGC incremental build passed. The private matched Windows/Linux/Android build
  run `43797652116` passed all three platforms at `e4f626a9c`.
- Launcher/provider/joint regressions: 290 passed.
- Controlled rendering comparison reproduced a black QGC window with private
  IPC (596 Mesa shared-memory errors), then a rendered interface with desktop IPC
  and zero such errors. Only display containers now share desktop IPC; backend
  workers and every network boundary retain their existing isolation.
- Fresh operator session: `tailsitter-gimbal-dependency-renewal-20261116-r3`,
  source `de2f51f08`; starts ground/disarmed and command-blocked. Video and gimbal
  telemetry are healthy. The operator confirmed the rendered interface/video
  and reported that nearly all functions worked. The trace records MC and FW
  ownership, two operator Stops, and a later Return-mode authority loss. Whether
  that Return was operator-commanded remains unconfirmed; no flawless flight
  acceptance is claimed. Training used conservative limits, not a private
  unrestricted envelope.
- Hardware, physical camera geometry and flight qualification are not passed.

## ARM64 setup follow-up

The authorized Pi bench update exposed a downloader prompt despite the managed
unattended flag. It was stopped without restarting a partially reconciled
runtime. One shared confirmation helper now honors that flag for both pinned
binaries and verified legacy moves, retaining checksum-before-publication and
interactive refusal on EOF. Six offline executable regressions cover both
helpers, successful replacement, bad checksums and closed interactive input.
The unpublished rc.2 tag is retained; rc.3 includes this repair. Hardware
qualification remains separate from successful dependency installation.

## Reproduce

Use the [training launcher](../../../../followers/05-development/ubuntu-training-platform.md)
with the prepared workstation dependency file and explicitly select the advanced
`tailsitter-gimbal` profile. Its `--bin-dir` must name the newly verified pinned
helpers. The independent simulator network, disposable credentials and safety
barrier remain unchanged. Preserve each new run rather than replacing evidence.
