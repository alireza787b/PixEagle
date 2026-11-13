# Stable-flight evidence with native sensorless feedback

The isolated native harness keeps its default qualified-EAS readiness gate.
An explicit per-sample native airspeed-control flag now permits fresh unavailable
airspeed only when native airspeed control is disabled. Valid low or stale
qualified EAS cannot fall through to this path. Unknown values, ambiguous
sources, missing feedback and stale unavailable reports remain unqualified.
Groundspeed is never converted into airspeed or stall margin.

The same predicate rejects nonprogressing sequences, large observation gaps,
aircraft/source changes and altitude-reference changes across the stable window.
It retains the existing altitude, hover and phase requirements. Receipt
association is bounded in either direction because the native aggregate state
time is the oldest constituent receipt; it is not an absolute freshness check.
Callers must still check fresh raw packets and retain feedback paired with each
sample. An independent source review caught the initial ordering assumption;
the corrected test covers newer independent airspeed receipts in both paths.

Validation: 232 native-harness tests pass, including existing transition-release
and actual-world-target fixture contracts, plus the new measured/sensorless,
low-speed, skew and context-change cases. CI-selected fatal lint and diff checks
pass. The minimum API/configuration and docs/hygiene gate passes 109 checks;
generated schema remains current (45 sections, 612 parameters). These tests use
fixtures, not an actual sensorless flight. No production
following admission, aircraft configuration, service or command authority is
changed. The separate Gazebo model/parameter/no-pitot evidence gate remains open.
