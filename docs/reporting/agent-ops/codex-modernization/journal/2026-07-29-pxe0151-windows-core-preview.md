# PXE-0151: Native Windows x64 Core Preview

Date: 2026-07-29
Status: local candidate gates passed; native evidence pending

## Decision

Native Windows will not be described as equivalent to the maintained Linux
runtime. The bounded candidate is Windows 11 x64 with CPython 3.11/3.12,
Node 24, Core dependencies, bundled video, classic CSRT/KCF tracking, and a
loopback-only dashboard/backend.

The candidate media surface includes HTTP JPEG, WebSocket JPEG, and WebRTC
signaling/transport. No native success is claimed until Windows CI and a
clean-host operator run retain decoded-frame evidence.

## Documented Contract

- `scripts\init.bat` owns idempotent Core setup and reuses only validated
  Python, npm, and dashboard-build contracts.
- `dashboard\package-lock.json` remains authoritative and setup uses `npm ci`;
  stale advice to delete the lockfile is retired.
- `scripts\run.bat`, `status.bat`, `stop.bat`, and `restart.bat` use one
  per-checkout process receipt and never kill an unknown port owner.
- Optional `--with-sidecars` acquisition is limited to manifest-pinned MAVSDK
  Server and MAVLink2REST binaries. The preview does not start them because
  MAVSDK Server cannot scope its unauthenticated gRPC listener to loopback.
- Model management remains explicitly unavailable while the POSIX artifact
  trust policy has no Windows equivalent. That capability must not prevent the
  Core control plane from starting.

## Excluded

AI/model management, NCNN/dlib, custom GStreamer, Windows services/auto-start,
ARM64, camera hardware, public exposure, PX4/SITL/X-Plane/Offboard/HIL, field,
and aircraft operation remain unsupported or unvalidated.

## Next Evidence

Run the exact candidate in native Windows CI, then perform a clean Windows 11
x64 operator walkthrough. Preserve setup versions, lifecycle receipts, logs,
port-conflict behavior, and decoded local media evidence before changing the
preview status.

Local contract evidence on the candidate includes `295 passed, 9 skipped`
across Windows/setup/profile/config contracts, `106 passed` for the model
policy/API surface, `73 passed` for required API/parameter gates, `31 passed`
for documentation consistency, and `17 passed` for the focused dashboard
capability UI. Schema, compile, lint, production build, workflow YAML, diff,
and CRLF checks also passed. None of those results substitutes for native
Windows execution.
