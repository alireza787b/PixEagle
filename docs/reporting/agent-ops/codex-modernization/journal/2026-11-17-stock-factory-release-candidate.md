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

Private operator startup exposed a simulator-only mismatch: the reviewed no-pitot
resource variant removed the sensor, but the airframe still required one through
`SYS_HAS_NUM_ASPD=1`. Setting the declared sensor count to zero while disarmed
produced PX4's `Preflight check: OK`; the operator then took off and engaged
Offboard. Future launcher runs derive no-pitot preparation from the verified
resource variant and affected model, with `ASPD_FALLBACK=1` for qualified
groundspeed-minus-wind estimation. Disarm and parameter acknowledgement are
required; normal sensor-equipped scenarios and hardware are untouched. The
current operator run was not restarted or retuned after it became armed.

The operator accepted private tailsitter guidance and reported a rendered-camera
rest-view problem across transitions. The run is closed and retained as
`reports/sitl/private-tailsitter-coast-20261117-r1/`; its original source is not
relabelled. The simulator now reads native PX4 phase without sending aircraft
actions and recenters once after a settled phase change. It clears only the
synthetic camera lock and invalidates prepared selections; it never starts
following. Home shares the same forward-horizon calculation and canonical FW
tailsitter transform. SIP angles still come from measured attached-camera pose.
Unknown/stale phase cannot reframe the view. A fresh public MC/2D operator review
is the next acceptance checkpoint; no Pi or real camera was contacted.

Public final run r2 recorded `telemetry_generation` changing at `before_offboard`.
The shared identity owner incorrectly treated heartbeat freshness expiry as
connection replacement, even when new packets continued the same UID, kind,
counter and boot clock. Replay of 899 captured simulator samples at a one-second
poll schedule produced 19 identity generations before the repair and one after,
with the same 89/90 fresh samples. The original poll's exact expiry interval was
not logged, so this replay demonstrates the defect rather than reconstructing
an unrecorded timing measurement.

Freshness now expires independently at the unchanged two-second deadline;
advancing same-aircraft evidence can restore it without rotating identity.
Explicit disconnect, UID/kind change, reboot/counter rollback and ambiguity still
retire bindings. No client retries or flight-command replay were added. The
520-case identity/API/phase/Start/session/commander selection passes, including
stale Start rejection and true reconnect fencing. The requested next MC review
enables altitude only in a disposable test profile, leaving factory altitude
guidance off. Retained evidence: `public-mc-final-20261117-r2/identity-freshness-replay.json`.

Earlier candidate CI found three tests still coupled to the previous public
velocity defaults. The public policy assertion now checks the agreed 4 m/s
ceiling and 0.5 m/s startup; the override-validation fixture explicitly owns
its 0.5 m/s test limit. Emergency missing-config velocity fallbacks remain
stricter than the factory cruise ceiling instead of being raised to satisfy a
test. All 137 affected schema/safety/policy cases pass. Fresh altitude-enabled
operator session: `public-mc-altitude-final-20261117-r1/`; its 20 read-only
observations retained one telemetry generation, all fresh and associated.

Final public operator review was accepted. Logs record two successful Start/Stop
pairs, three speed adjustments, 1,222 successful publications and no context-change
refusal. Follow-up coverage CI at `523f0ed87` passed 10,573 tests but found one
remaining configuration-service fixture coupled to the previous speed ceiling.
The fixture now derives a violating override from its actual saved envelope,
so future default changes cannot silently make its invalid case valid.

Hardware deployment is paused at storage preflight: active ext4 bitmap and inode
checksum errors were observed before any update. Readable private configuration
and health evidence were retained outside Git. PixEagle was stopped and the Pi
cleanly shut down for offline storage repair. No aircraft parameter, camera
command or firmware change was sent.
