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
