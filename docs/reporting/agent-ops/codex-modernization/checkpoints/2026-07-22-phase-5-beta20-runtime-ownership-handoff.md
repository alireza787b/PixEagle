# Phase 5 Checkpoint: Beta.20 Runtime Ownership Handoff

- Date: 2026-07-22
- Issue: PXE-0129
- Status: local release candidate; fresh-host acceptance pending
- Scope: manual browser-lab versus managed-service lifecycle, setup reporting,
  ownership detection, and operator guidance

## Trigger

The beta.19 maintainer run exposed a lifecycle collision. The guided installer
started a manual browser-lab runtime, then the operator installed or enabled
service controls and attempted `pixeagle-service start`. The managed launcher
treated the already-running manual PixEagle processes as an unrelated process,
reported misleading port ownership, and could enter a systemd retry loop. Repair
summaries could also describe a default disabled policy rather than the state
actually observed on the host.

## Decisions

1. Manual/browser-lab and managed/systemd are two mutually exclusive runtime
   ownership modes. PixEagle never kills the other mode implicitly.
2. `pixeagle-service install` installs or refreshes the validated service unit
   and CLI controls only. It does not start a runtime and does not change boot
   enablement.
3. `pixeagle-service start` and `restart` control the managed runtime only.
   They refuse clearly when a manual runtime is active and print the exact stop
   command. `enable` and `disable` change boot policy only; they are not aliases
   for start or stop.
4. The initializer keeps service installation, boot auto-start, and SSH login
   hints as separate choices. Defaults remain conservative and their summaries
   report observed state on reruns instead of assuming the default.
5. The installed unit's declared service user is authoritative. User-level
   systemd conflicts are checked fail-closed across standard and dynamically
   reported `systemd-analyze --user unit-paths` locations; an unknown user bus
   state is never treated as absence.
6. Launcher preflight recognizes both PixEagle ownership modes. An unowned
   process still blocks startup and receives actionable diagnostics.

## Changes

- Added a validated, policy-preserving service-unit install path and a separate
  `install` CLI command.
- Separated current-runtime commands from boot-policy and SSH-hint commands in
  CLI help and setup handoff text.
- Added cross-mode runtime ownership identification and exact manual-to-managed
  handoff guidance without broad process termination.
- Made service-user resolution follow the canonical unit instead of whichever
  user happened to invoke the CLI.
- Added fail-closed user-service conflict detection and complete local user-unit
  search-path discovery.
- Corrected initializer repair summaries and installer handoff wording.
- Updated README, installation, service, troubleshooting, model, and companion
  computer docs and added regression coverage for the lifecycle contract.

## Validation

- Focused lifecycle/setup/docs suite: `294 passed`.
- Full backend suite: `3461 passed, 48 skipped`; one existing Starlette/httpx
  test-toolchain deprecation warning remains tracked as PXE-0127.
- Required Phase 0 gate: `72 passed`.
- `bash scripts/check_schema.sh`: 40 sections, 535 parameters, no drift.
- Dashboard: 54 suites / 358 tests passed; production build completed.
- Bash syntax, ShellCheck, Python compilation, and `git diff --check` passed.
- Independent UX/docs review returned `GO` after its bounded wording findings.
- Independent systemd/shell review returned `GO` after the bounded user-unit
  search-path finding was addressed.
- CI, tag, release, fresh Ubuntu/systemd execution, Raspberry Pi execution,
  PX4/SIH/SITL/HIL, QGC, camera/gimbal, and field evidence are not included in
  this local checkpoint.

## Maintainer Retest

On the target host, stop any existing beta.19 manual runtime before updating:

```bash
cd /root/PixEagle
make stop
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

Accept the default browser-lab path and keep boot auto-start disabled for the
first check. Verify the printed dashboard URL and run:

```bash
cd /root/PixEagle
pixeagle-service status
pixeagle-service start
```

While the manual lab is active, `start` must refuse with a clear handoff note;
it must not kill the lab or create a systemd retry storm. Then switch modes:

```bash
make stop
pixeagle-service start
pixeagle-service status
```

This should start the managed runtime while boot auto-start remains disabled.
Use `sudo pixeagle-service enable` only when the next-boot policy is wanted;
use `sudo pixeagle-service disable` to remove that policy. Use
`sudo pixeagle-service login-hint enable --system` independently if the SSH
startup hint is wanted. The installer and `pixeagle-service help` are the
authoritative concise command references.

## Claim Boundary

This checkpoint proves repository behavior and local automated contracts. It
does not prove a fresh target system, systemd permissions under a non-root
companion account, Raspberry Pi performance, optional GStreamer/AI runtime,
PX4/MAVLink discovery or command response, SIH/SITL/HIL, QGC receipt,
camera/gimbal behavior, production TLS/WebRTC, field operation, or aircraft
safety.

## Next Gate

1. Publish beta.20 only after the release commit and required GitHub Actions
   run are green.
2. Run the exact published revision on a clean Ubuntu host and capture setup,
   service, dashboard, and log evidence.
3. Repeat Core-first installation on the Raspberry Pi, then add optional AI or
   GStreamer only with corresponding capability evidence.
4. Keep PX4/router, real RTSP/gimbal, QGC, and field acceptance as separate
   evidence slices; do not collapse them into a green installer result.
