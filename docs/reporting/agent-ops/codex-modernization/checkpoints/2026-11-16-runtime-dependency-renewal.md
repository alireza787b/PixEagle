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

## Stock firmware and installation review

The operator selected no private PX4 firmware for the ordinary MC/VTOL/FW
workflow. The current native experiment still gates VTOL; neither documentation
nor an operator layout label opens that gate. The canonical consolidation plan
and stock integration guide distinguish implemented MC support, pending stock
VTOL/FW transports, DDS communication requirements and bounded failure handling.
One vertical gimbal installation is retained across transition; a new phase
requires a fresh Start.

The private saved profile was aligned through the existing guarded config API:
only its unsupported upper-speed request changed to `px4_configured_max`.
The exact single-leaf diff and previous experimental overlay are retained
privately. Gains, MC speed/rate limits, altitude choices and provider/mount data
were not changed; no PX4 parameter or firmware write occurred. Reading aircraft
parameters is evidence of configuration, not a measured flight envelope.

Public defaults and generated schema are unchanged. Documentation/API/config
checks passed 105 cases; the renewed documentation check passed 31. Schema and
whitespace gates passed. Stock PX4 simulation, transport implementation and
physical following admission remain open. Do not publish this candidate as
plug-and-play VTOL following merely because the earlier patched simulator passed.

## Stock-firmware software checkpoint

Hardware updates are paused at the operator's request. Official PX4 main
`99a3048735caa5a2c277d6aa8e17a12a6133db5d` builds as `px4_sitl_sih`, with
no PixEagle patches or PX4 parameter writes. The new upstream CDR and Zenoh
submodules are included; original preparation failures remain retained.

Three isolated stock-airplane attitude/thrust probes observed −39.90°, −44.98°
and −59.92° pitch against the configured −30° normal TECS limit. The last probe
observed 22.02 m/s calibrated airspeed against `FW_AIRSPD_MAX=20`. All three
observed Hold after Offboard Stop. This proves an interface response, not target
guidance, requested-airspeed control or TECS underspeed protection. Post-Stop CAS
briefly reached 8.99, 8.68 and 7.88 m/s, below the configured normal minimum of
10 m/s; the saved stall parameter is 7 m/s. This is not proof of a stall or a
qualified handoff envelope. Stock VTOL/FW application, recovery and takeover
qualification remain open. No physical-aircraft following admission changes.

Evidence: `reports/sitl/stock-px4-qualification-20261116/`, including exact build
inputs, binary hash, network-isolated runtime manifests, original ULogs and
JSONL, result JSON and the offline `index.html`/PNG review. Aircraft movement is
observed PX4 telemetry. The probes have no moving target and must not be presented
as complete follower tests.

The docs-head cloud failure was a concurrent model-upload test that assumed a
100 ms mutation lease always serialized both requests. Production intentionally
returns busy under contention. The serialization test now uses its own longer
test budget, and an event-synchronized regression separately verifies immediate
busy refusal, intact staging, explicit retry and no overwrite. Runtime lock
semantics are unchanged. Renewed gates: 81 model-store tests, 236 guidance/frame/
API tests, 7,494 full unit cases (11 optional GI skips, 14 subtests), schema and
CI-selected flake8 checks passed. No duplicate QGC build is needed.
