# October 22 — session speed override

Implemented capability-driven follow-session controls, initially GM Velocity
Vector, through the shared authenticated action/status contracts. Dashboard and
QGC keep one acknowledged session value and optimistic revision; stale gestures
and reconnections cannot replay adjustments. Public beginner defaults and the
custom profile's gains, geometry and saved speed ceilings remain unchanged.

The operator explicitly revised the initial bounded-request contract during
implementation: adjustments now replace saved total/per-axis PixEagle velocity
caps for that session. A restore action removes that override while keeping or
lowering the request. SafetyManager owns limit resolution through a weak live
provider; it does not save a duplicate speed. Altitude/rate/acceleration,
circuit-breaker and authority guards remain. Other followers opt in only with a
tested implementation.

The operator's screenshot review rejected the narrow panel's truncated speed
label. Both clients now use a speedometer, prominent acknowledged value and
touch-sized step/restore buttons. The value opens an inline exact-entry editor;
session/revision changes invalidate Apply and Stop remains reachable. QGC's
scaled Options content now contributes real font/control dimensions to its
layout and scrolling. The renewed Dashboard gate passes 512 tests and QGC
passes all 476 standard Unit/Integration suites. Captured UI states are
explicitly simulated observations, separate from the instrumented SIH evidence.

Delayed teardown observes actual authority exit and waits for MAVSDK's local
sender to stop without invoking its Stop RPC, which would request another Hold.
Read-only local shutdown must be proven; failures remain unknown/retryable.
The existing vertical guard now respects the canonical altitude-enable flag.
Full-vector dispatch also applies the existing overall magnitude limit, including
immediately after restore; no new limit setting is added.

See the [checkpoint](../checkpoints/2026-10-22-session-speed.md) for exact
verification, evidence, private configuration diff and open acceptance work.
