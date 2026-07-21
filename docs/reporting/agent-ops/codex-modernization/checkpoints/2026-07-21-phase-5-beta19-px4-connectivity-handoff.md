# Phase 5 Checkpoint: Beta.19 PX4 Connectivity Handoff

- Date: 2026-07-21
- Issue: PXE-0128
- Status: local release gates complete; publication and target execution pending
- Scope: setup handoff, MAVLink ownership, port truth, and active documentation

## Decisions

1. PixEagle installs and launches its local MAVSDK Server and MAVLink2REST
   consumers. It does not choose or own the PX4 UART, radio, Ethernet, SITL
   source, or deployment MAVLink router.
2. The maintained router contract fans one vehicle MAVLink network to
   `127.0.0.1:14540/udp` for MAVSDK and `127.0.0.1:14569/udp` for
   MAVLink2REST. Ports `50051` and `8088` are application protocols, not
   vehicle ingress.
3. MavlinkAnywhere is the beginner router path but remains a separate pinned
   deployment component. Its dashboard-only installer and headless router
   configurator are separate commands.
4. UDP `14550` is mode-dependent. A router can use it as PX4/SITL input or as
   an ad-hoc QGC listener on the same address, not both concurrently.
5. The pinned upstream MAVSDK Server has no gRPC host-bind option and listens on
   `0.0.0.0:50051`. PixEagle connects through loopback; operators must block
   TCP `50051` on untrusted interfaces. The beginner browser workflow neither
   opens nor starts this server.
6. In beginner setup, Enter selects network browser access. Services bind to
   `0.0.0.0`, while the installer prints the requested host when supplied or
   otherwise the primary-route device address as the navigable URL.

## Changes

- Replaced conflicting PX4/MAVLink port and ownership guidance with one
  canonical active guide and linked onboarding to it.
- Removed instructions that started standalone MAVLink2REST beside the full
  PixEagle launcher.
- Corrected MAVSDK external/embedded connection documentation and runtime
  exposure wording.
- Separated MavlinkAnywhere dashboard installation from router configuration
  in SITL examples.
- Corrected retired UDP `14570` and ambiguous `14550` diagrams/examples.
- Made launcher output label wildcard endpoints as binds, never browser URLs.
- Added regression guards for port defaults, mode separation, retired ingress,
  installer handoff, and wildcard presentation.
- Aligned backend, setup, and dashboard package version metadata to
  `7.0.0-beta.19`.

## Validation

- `281 passed`: setup profiles, runtime ownership, installer UX, and
  infrastructure documentation.
- `72 passed`: required API route inventory and parameter reload gate.
- `bash scripts/check_schema.sh`: 40 sections, 535 parameters, no drift.
- `3,448 passed, 48 skipped`: final complete backend suite. One known
  Starlette/httpx deprecation warning remains tracked as PXE-0127.
- Dashboard: 54 suites / 358 tests passed; ESLint passed; production build
  completed.
- Bash syntax, ShellCheck, Python compilation, and `git diff --check` passed.
- Independent port/setup/safety re-review returned `GO` after two initial
  presentation/test-contract blockers were fixed.

## Claim Boundary

This checkpoint proves local code, setup, documentation, and test contracts.
It does not prove PX4 vehicle discovery, Offboard response, SIH/SITL/HIL,
MavlinkAnywhere installation on the target, Raspberry Pi performance, QGC
receipt, camera/gimbal hardware, field behavior, or aircraft safety.

## Next Gate

1. Commit and push the exact candidate.
2. Require green GitHub CI, then publish annotated prerelease
   `v7.0.0-beta.19`.
3. Run the documented one-line install on a fresh Ubuntu host.
4. On Raspberry Pi, configure the real PX4 source in MavlinkAnywhere with
   outputs `127.0.0.1:14540,127.0.0.1:14569` before expecting vehicle data.
5. Record exact router revision/config, firewall state, PixEagle config,
   telemetry freshness, command-path evidence, and operator observations.
