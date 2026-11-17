# Optional mission altitude ceiling — 2026-11-13

Schema 1.10 adds explicit `Safety.GlobalLimits.MAX_ALTITUDE: null` for no application
mission ceiling. One resolver supplies both effective values and their sources;
guidance, legacy consumers, API summaries, evidence readers and dashboard
editing/import/export preserve that value. Missing settings retain the 120 m
default. Follower overrides still require finite values or omission, and can
tighten an unbounded global ceiling. Existing numeric settings and public
configuration values are unchanged.

The 3 m default relative-altitude floor and 2 m warning buffer remain active.
Invalid heights remain unavailable rather than becoming an unbounded value.
Native climb/sink, underspeed, attitude, actuator and speed policy are unchanged.
Relative home altitude is not terrain clearance. This slice makes no new
sensorless, simulator, hardware or physical performance claim and does not
modify the private profile.

Focused software validation covers finite legacy behavior, null round-tripping,
missing/default migration, finite follower tightening, floor/start/descent
guards, API provenance, native guidance bounds and dashboard editing/YAML
import/export. The schema check, fatal Python lint and dashboard tests/build
pass; full qualification gates remain a separate review step.

Independent review blocked the first candidate: replacing a positive finite
ceiling comparison with its negation allowed NaN through MC Distance, and
unbounded limits exposed invalid-height escapes in other direct legacy checks.
The repaired candidate requires finite measured height before PID/comparison
work. Positive climb permission preserves valid upward recovery below the floor;
altitude-guidance-off and explicit safety-disable authority remain separate.
The original failed candidate and red regression evidence are retained.

Root independently renews 532 combined limit, guidance, API/configuration and
native-harness checks after integration, 69 schema/documentation checks and all
560 Dashboard tests in 69 suites. The Dashboard production build, ESLint,
schema regeneration check and fatal Python lint pass. Schema generation is versioned as
1.10.0; retirement history stays at its original versions. A rollback to an
older backend requires restoring a numeric ceiling first. Saved public/private
configuration bytes remain unchanged.

The exact clean `773b1005e` full regression passes 6,562 unit, 196 integration and
155 Phase 0 checks plus inventory/schema/fatal lint, with eleven optional
GStreamer skips. Native transition and private-profile qualification remain
separate from this software receipt.
