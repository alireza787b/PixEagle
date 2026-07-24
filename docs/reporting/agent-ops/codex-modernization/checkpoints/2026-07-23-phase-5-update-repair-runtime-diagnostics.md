# Phase 5 Update/Repair And Runtime Diagnostics

Date: 2026-07-23

## Scope

Resolve the operator handoff after an external `git pull` was followed by a
generic backend readiness failure. Keep the change bounded to maintained
update/repair guidance, sidecar classification, and actionable failed-run
diagnostics.

## Decision

- `make update` and `pixeagle-service update` remain the normal update path.
  They require a stopped runtime, fast-forward source, reconcile the selected
  setup profile, preserve operator data, and do not restart PixEagle.
- If source was already changed outside that transaction, stop PixEagle and run
  `make repair`; it reconciles the current source without fetching again.
- A missing MAVLink2REST executable is classified before runtime publication.
  The optional sidecar is excluded while the backend/dashboard control plane
  remains available in a degraded state.
- A component that fails after publication must leave the exact structured-log
  directory and a copyable inspection command in launcher output.

## Changes

- Added MAVLink2REST executable classification before tmux runtime publication.
- Added failed-run log directory and `tail` handoff before bounded cleanup.
- Aligned Makefile, service CLI, updater, README, installation, and service
  management help around update versus repair.
- Added regression coverage for sidecar classification, log handoff, and help
  consistency.

## Validation

- `tests/test_runtime_process_ownership.py`: `66 passed`
- setup and infrastructure docs suites: `190 passed`
- required API route inventory and parameter reload: `73 passed`
- `make phase0-check`: `490 passed`
- schema: `38` sections / `513` parameters, no drift
- Bash syntax and ShellCheck pass; only dynamic-source `SC1091` notices were
  excluded from the final ShellCheck invocation
- Live local launch with `-m` (explicitly no MAVLink2REST): backend and
  dashboard ready, ownership contract healthy, dashboard HTTP `200`, clean
  `make stop`
- Normal launch with an intentionally absent local MAVLink2REST artifact:
  backend/dashboard became healthy, telemetry degradation and binary-only
  recovery guidance were explicit, and the runtime stopped cleanly

## Claim Boundary

The current backend/dashboard source starts locally. This does not prove the
operator's external Ubuntu dependency state, MAVLink2REST/MAVSDK connectivity,
PX4, camera/gimbal, Raspberry Pi, SITL/HIL, QGC, field, or aircraft behavior.
PXE-0140 closes only after a stopped-runtime `make repair` and full sidecar
launch pass on the Ubuntu acceptance host.
