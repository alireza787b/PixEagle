# Phase 5 Checkpoint: Guided Update Recovery And Version Policy

Date: 2026-07-25
Issue: PXE-0144
Status: local gates passed; Ubuntu one-line acceptance pending

## Problem

The installer correctly refused to mutate a running checkout, but made a
beginner stop PixEagle manually and rerun the same command. Transactional
dashboard settings backups were not ignored and could block the next update.
Source fetch and native builds could appear idle, settings-reset validation
printed a harmless but misleading missing-config fallback, and the binary
upgrade policy was not clear at the setup handoff.

## Changes

- Interactive update offers to stop an exactly owned manual or managed runtime
  after one confirmation. It does not restart after reconciliation.
- Unattended auto-stop requires `PIXEAGLE_UPDATE_STOP_RUNTIME=1`; dry-run,
  unknown listeners, conflicting sessions, and other checkouts remain no-touch.
- The public bootstrap contains a narrow compatibility handoff for the beta.28
  manual runtime before delegating all future behavior to `scripts/update.sh`.
- Added the missing ignore rule for transactional dashboard settings backups.
  An affected checkout can confirm preservation/local exclusion of only that
  known generated directory; arbitrary local changes still block.
- Source fetch, dlib compilation, and OpenCV compilation emit cancellable
  30-second progress heartbeats that retire if the parent shell is interrupted.
- Settings-reset validation stages current defaults as the temporary runtime
  config, retaining its backup/validation/rollback transaction without the
  false warning.
- MAVSDK Server and MAVLink2REST remain exact versions, assets, and SHA-256
  values in `scripts/setup/binary-manifest.env`. Matching binaries are reused;
  a reviewed manifest change triggers verified replacement.
- Python MAVSDK is a separate exact package contract pinned to tested `3.15.3`.
  Client/server upgrades require an intentional source change and compatibility
  evidence, so no future minor or major can enter silently.

## Validation

- Focused update/setup/reset suite: 120 passed
- Broader installer/lifecycle suite: 348 passed
- Config/docs integration suite: 192 passed
- Required API inventory and parameter reload: 73 passed
- Schema: current, 39 sections and 517 parameters
- Dashboard lint and production build: passed
- Maintained pip-check policy: passed; raw pip reports only the documented
  Ultralytics/OpenCV distribution-name mismatch
- Bash syntax, ShellCheck warning gate, updater dry-run, heartbeat cancellation,
  manifest readback, and `git diff --check`: passed

## Review

One bounded independent review identified the broad Python MAVSDK range,
dispatch-level stop coverage, and parent-interruption heartbeat cleanup. The
client is now exactly pinned, manual/managed stop dispatch and post-stop gates
have behavioral tests, and the shared heartbeat monitors parent liveness. No
review finding remains open in this slice.

## Evidence Boundary

These gates prove local ownership classification, stop policy, rollback
boundaries, liveness output, config-reset validation, and dependency policy.
They do not prove a fresh or upgraded Ubuntu host, Raspberry Pi, physical
camera/gimbal, PX4, QGC, field, or aircraft behavior.

## Next Gate

Publish beta.29, rerun the public one-line installer against the active Ubuntu
checkout, accept the stop prompt, and verify that setup reaches its final
dashboard handoff without rebuilding components whose contracts still pass.
