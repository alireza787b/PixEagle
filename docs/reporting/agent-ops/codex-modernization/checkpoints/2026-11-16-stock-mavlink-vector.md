# Stock MAVLink vector component — 16 November 2026

## Boundary

The ordinary integration direction is the existing UART/MAVLink link and stock
PX4. DDS and the experimental native firmware extension are not requirements
for this replacement. Hardware is paused; the Pi, aircraft parameters, private
saved profile and QGC source were not changed in this slice.

The FW component is **not admitted to application following**. These results
must not be called a complete VTOL, QGC, camera or hardware qualification.
The existing VTOL gate remains closed until its ownership replacement passes.

## Implemented

- The existing telemetry identity owner observes fresh aircraft kind and VTOL
  phase from standard heartbeat/extended-state messages. Phase and connection
  generations remain distinct. Cached, reordered and mutated samples cannot
  renew phase freshness or grant command ownership.
- The canonical simulator builder supports an explicitly selected, exactly
  pinned stock SIH policy. It requires no native patch tree, refuses a dirty or
  patched stock source, and verifies source, submodules, binary and runtime image.
- MC qualification scenarios start at 40 m above the public 30 m floor. Target
  geometry translates with the scenario except ground targets, which remain on
  the ground. An invalid initial altitude is refused before simulator launch.
  Unit fixtures derive height from the scenario rather than a second 20 m value.
- `FixedWingMavlinkVectorControl` reuses the existing world-ray course classifier,
  speed-envelope resolver, session binding and altitude guard. It converts the
  direction and request into coordinated bank, pitch and normalized thrust.
  PX4 retains attitude/rate control; this contract does not retain native TECS.
- Normal requests retain resolved speed, pitch and climb/sink limits. The isolated
  expert fixture removes the upper-speed and pitch/sink soft limits, retaining
  the shared floor, bank/actuator limits and climb-speed priority. This does not
  change the existing native policy's advertised semantics or saved configuration.
- Fresh selected airspeed is preferred. Missing/stale airspeed falls back to an
  explicitly named ground-speed proxy, not an invented airspeed measurement or
  claim of known stall margin. Repeated VFR_HUD cache reads retain the original
  advancing packet's receipt clock.
- Tailsitter measurement conversion is canonical. Physical camera rays still
  use physical body FRD; outgoing FW virtual attitude is not rotated twice.

One target direction and requested speed remain the guidance model. FW cannot
instantaneously follow an arbitrary 3D velocity: bank, lift, thrust and energy
constrain the observed path. Climb demand is reduced as speed approaches the
configured minimum; this is not a guarantee of stall protection, especially with
no qualified airspeed. A request above the normal maximum does not guarantee
that speed will be achieved.

## Actual stock SIH evidence

Firmware: `99a3048735caa5a2c277d6aa8e17a12a6133db5d`, unmodified.
No aircraft parameter writes. Each run has its original source checksums,
configuration, isolated-runtime manifest, JSONL and PX4 ULog.

Evidence root: `reports/sitl/stock-px4-qualification-20261116/`.

| Run | Observed result | Scope |
| --- | --- | --- |
| `mc-position-stock-r2` | 0.204 m maximum altitude error; Hold and publication release confirmed | Production follower/publisher component |
| `gm-vector-vertical-on-stock-r1` | Range 18.00 → 14.27 m; vertical response 1.076 m; Hold/release confirmed | Production gimbal follower, simulated angle input |
| `fw-vector-normal-r3` | Range 169.37 → 49.96 m; observed speed 12.59–17.37 m/s; post-Stop minimum 14.29 m/s | Stock attitude/thrust vector component |
| `fw-vector-unconstrained-r2` | 30 m/s request accepted; range 175.92 → 68.76 m; observed speed 12.47–20.17 m/s | Stock attitude/thrust vector component |
| `fw-vector-steep-descent-r2` | −65.09° minimum request, −62.27° observed pitch; peak speed 21.24 m/s; post-Stop ULog minimum CAS 14.41 m/s | Expert descent component, 3 m floor retained |
| `fw-vector-climb-r1` | Climb-speed priority exercised; range 187.82 → 51.43 m; minimum speed 12.45 m/s | Expert climb component |

`vector-review/index.html` includes plots and a 3D animation of actual aircraft
pose and independent moving target truth. Commands are never integrated to create
aircraft motion. Target passage/overshoot is visible; a range reduction is not a
claim of sustained target capture. Original failed runs remain retained.
Post-Stop observation is explicit in the newer normal/steep-descent runs; earlier
runs confirm Hold but do not qualify that observation window.
Runs were staged during implementation: their manifests record the base commit,
dirty-worktree status and exact staged source checksums. They are not pristine
published-revision or release qualification.

The original three interface-only dive probes and their speed-undershoot finding
remain separate evidence. A passing moving-target component run does not erase
their failure mode or qualify every handoff condition.

## Verification

- Full unit gate: 7,591 passed, 11 optional GI cases skipped, 14 subtests passed.
- API/parameters/integration gate: 270 passed.
- Builder/native-runner/docs gate: 412 passed; final fixture/CLI gate: 97 passed.
  These overlap the full suite and must not be added as unique test counts.
- Schema drift, API candidate inventory, CI-selected fatal Python lint and
  whitespace checks passed. Dashboard and QGC source are unchanged.
- The first full run retained 11 failed unit fixtures at the obsolete 20 m
  height. Fixtures now use the scenario height and explicit relative deltas;
  the altitude/response assertions and runtime safety limits were not weakened.
- Earlier cloud CI at `f36de70eb` passed. New component commits need their own
  exact-head CI; that older result is not a claim of current-head success.

## Remaining integration and acceptance

1. Connect fresh standard observations and resolved PX4 parameters to the
   existing aircraft-state owner without another polling/identity service.
2. Add the stock attitude command contract to the existing publisher and session
   lifecycle, with phase/connection fencing, Stop, takeover and source expiry.
   A transition ends following and requires a new Start; no automatic resumption.
3. Reuse the FW continuity supervisor for bounded loss, level recovery and Hold.
   Exercise target loss, retargeting, process/link failure, stale edits and phase
   changes through actual application actions and both client interfaces.
4. Qualify stock native FW and VTOL/tailsitter simulations, then request cooled
   hardware and confirm the physical camera conventions. Keep public defaults
   conservative and the owner test envelope separate.
5. Remove the superseded ordinary-path native dependency after parity. Do not
   retain permanently competing publishers or duplicate recovery mechanisms.

See the [stock integration guide](../../../../followers/07-integration/stock-px4-gimbal-vtol.md)
for commands and configuration. No firmware patch, live capability bypass,
deployment, final tag or public release is authorized by these component results.
