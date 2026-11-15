# Public defaults and upstream renewal — 15 November 2026

Public startup uses MC Position, optional target-altitude guidance disabled,
altitude protection and the circuit breaker enabled. One existing SafetyManager
global floor is now 30 m relative altitude for MC/FW; the existing 2 m warning
buffer requires at least 32 m for Start. The 120 m ceiling and conservative
velocity/rate values are unchanged. Native FW minimum/trim/envelope handling
remains PX4-owned. These are conservative evaluation defaults, not a physical
safety guarantee or terrain clearance.

The beginner lab setup profile previously replaced Position with Chase. It now
retains Position. Explicit saved values remain unchanged until Config Sync
preview/apply adopts a new default; a regression exercises a saved 3 m floor.
Private owner overlays remain outside the public repository.

Validation so far:

- Schema regeneration and verification passed.
- Focused configuration/API/default gates: 220 passed.
- First full unit/configuration pass: 7,672 passed, 11 skipped, 31 failed.
  The failures assumed the old fallback floor or implicitly used 20 m world
  fixtures. Tests now explicitly declare their saved low-floor scenario, or
  place the aircraft above the public floor when testing another failure.
- Affected regression suites after those corrections: 356 passed.
- Full rerun is recorded under
  `reports/sitl/follower-consolidation-20261111/public-defaults30-full-unit-r2.log`;
  its final verdict remains a release gate.

Official upstreams were checked with `git ls-remote`:

| Repository | Revision |
|---|---|
| QGC master | `19e4246b244d3946fa6f2ea65d349a7fa30f11d0` |
| PX4 main | `c4b8f107ae97d643fc784a394e3874f34caec563` |

The QGC merge ports authenticated sources, frame provenance and custom views to
the new worker/session receiver API; it is not yet a qualified binary. Its
dependency cache must also adopt upstream's MAVLink pin rather than retain the
old configured value. Build, media recovery, Unit/Integration and lint remain
gates before the single final platform-artifact dispatch.

The allocator-only PX4 candidate is being rebuilt on current main separately.
The pinned simulator firmware and hardware are unchanged. No PX4 draft PR,
QGC PR/release, public PixEagle release or new hardware qualification is claimed
by this checkpoint.
