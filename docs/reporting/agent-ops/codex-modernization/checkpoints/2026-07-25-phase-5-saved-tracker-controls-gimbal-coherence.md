# Phase 5 Checkpoint: Saved Tracker Controls And Gimbal Coherence

Date: 2026-07-25
Issue: PXE-0145 (extends PXE-0139)
Status: implementation complete; real camera/gimbal retest pending

## Problem

Dashboard tracker and follower choices were runtime-only, and the Smart model
control was not contextual to Smart mode. The tracker handoff message also
used restart/error language even though replacing a live tracker only requires
selecting a new target.

The external gimbal protocol can send angle and target-lock responses in
different UDP packets. Treating each packet as a complete sample made status
reads and the update loop disagree, which could make the follower control appear
to flap while angle diagnostics were still useful.

## Changes

- Added an explicit `persist` field to the typed tracker-switch contract.
  Dashboard tracker selection saves the canonical
  `Tracking.DEFAULT_TRACKING_ALGORITHM` only after the runtime switch succeeds;
  persistence failure rolls the runtime switch back.
- Kept follower profile persistence on its canonical configuration path and
  made the Dashboard action read as `Save Follower`.
- Rendered the tracker selector only in Classic mode and the installed model
  selector only in Smart mode. Model changes remain live/standby operations and
  do not require a process reboot.
- Separated tracker-switch notices from errors so a required target reselection
  is informational.
- Added independent gimbal angle/status timestamps and one coherent provider
  snapshot. A fresh angle packet does not refresh a stale target-lock status,
  and a fresh status packet does not refresh stale angles.
- Made `GimbalTracker.get_output()` side-effect-free. It reports the last
  published sample and marks it stale when the provider snapshot is no longer
  current; it does not run another provider update or mutate counters.
- Kept stale angle output visible for diagnostics while requiring fresh,
  active, explicitly usable output for follower start.
- Added the schema-owned `GimbalTracker.TRACKING_STATUS_TIMEOUT` setting and
  aligned tracker/follower documentation with the runtime contract.

## Validation

- Backend focused contract suite: `341 passed`.
- Dashboard full suite: `56 suites, 375 tests passed`.
- Dashboard production build: passed.
- Schema check: 39 sections, 518 parameters, up to date.
- Python compile and `git diff --check`: passed.
- Real camera/gimbal packet, follower, PX4, Raspberry Pi, and field evidence:
  pending operator acceptance.

## Evidence Boundary

Software tests prove persistence transaction ordering, rollback handling,
packet composition, freshness separation, and side-effect-free status reads.
They do not prove camera firmware packet cadence, gimbal axis conventions,
network routing, follower response, PX4 behavior, or physical flight.

## Next Gate

Update the test host to the exact beta.30 commit. In Classic mode select and
save the external gimbal tracker, confirm angle/status widgets remain stable
through normal packet cadence, then verify that a genuinely stale target-lock
status blocks follower start while angle diagnostics remain visible. Test the
Smart model selector separately. Record the exact config, logs, and host
versions before considering PXE-0145 or PXE-0139 closed.
