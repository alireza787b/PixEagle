# 17 November 2026 — factory policy and release candidate

Finished the stock application checkpoint with explicit public/expert velocity
permission, safe factory 5–100 m limits, Config Sync compatibility and rc.4 version
metadata. Private configuration stays outside Git. Rebuilt unmodified latest PX4
and renewed actual tailsitter MC/FW application scenarios. The existing report
viewer separates request, command intent and actual observed motion.

Backend full unit/API, Dashboard and QGC local gates pass. One private all-platform
QGC build is running; hardware remains unchanged and pending separate acceptance.
See the [checkpoint](../checkpoints/2026-11-17-stock-factory-release-candidate.md)
for exact evidence, counts and boundaries.

Final expectation audit found and repaired stock-Gazebo launcher admission and
independent telemetry-route discovery. New scene bindings retain their template
provenance and original historical evidence. A disarmed, command-blocked stock
full-stack startup now verifies video and aircraft association without a native
adapter or GCS-supplied identity request. Operator flight acceptance is pending.

The operator accepted the public MC Position/Chase workflow in the coastal world.
The following follow-up changes remain a new checkpoint, not retroactive claims
about that run:

- One versioned coastal scene recipe now supplies all five training combinations;
  aircraft, camera and source bindings remain independently validated. Native
  Gazebo spectator follow changes only the GUI camera. All 295 scene/launcher
  checks pass.
- Public MC Chase starts at a configured 0.5 m/s and permits requests up to the
  saved 4 m/s total/forward envelope. Lateral/vertical caps stay 0.5 m/s, optional
  altitude guidance stays off, and legacy missing/null startup settings keep
  their previous behavior. Clients use the existing advertised control contract.
- Start acquisition now retains its structured precondition and logs only changed
  guard field names. QGC preserves a confirmed action failure across a same-runtime
  status refresh; replacement runtimes, sessions and attempts remain excluded.
  The broader backend API/configuration checks pass all 414 cases.

Evidence: `reports/sitl/public-mc-coast-20261117-r1/`. The retained run is closed;
its original source and configuration receipts are unchanged. It also recorded
telemetry connection-generation changes during healthy HTTP polling. Their cause
is not established: the short raw-input replay did not reproduce them. The new
stage/field diagnostics support a fresh reproduction; freshness/authority guards
were not relaxed. Private tailsitter acceptance and exact-head CI remain separate.
