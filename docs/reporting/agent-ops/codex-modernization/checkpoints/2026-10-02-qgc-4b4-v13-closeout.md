# QGC 4b.4 — v13 closeout

Status: repair implemented; backend/Dashboard/QGC and isolated SIH gates passed;
fresh blocked v13 ready, physical operator acceptance pending. Neither source publication nor real-flight
qualification is claimed.

## V12 findings

Evidence: private `camera-sih-operator-v12/logs/` under the 2026-10-01 baseline
cache. All 1,046 recorded publications succeeded. Vector retarget generations
2 and 3 restored authority in about 1.5 and 1.8 seconds with simulated yaw
response. Chase sessions changed simulated yaw/altitude but contained no active
retarget. Around 07:21:17 Tehran time an edge selection was refused after
continuity entry; error handling stopped following. An intentional publisher
shutdown then produced a misleading secondary unhealthy-publisher report.

Static review identified abrupt provisional caps, Vector connection-time ramp
catch-up, frame-rate-dependent filtering and processing timestamps that could
make older camera measurements appear fresh. Raw AI engineering feedback is
kept in the evidence directory, separate from operator observations.

## Repair contract

Selection is prepared before target generation, manual cancellation or follow
transition. Invalid input retains existing operation. The validated adapter
region is reused at dispatch with final ownership checks. Shutdown is one
session-owned operation; its first cause and observed result are retained.

Followers use monotonic bounded timing, raw-validated body-line-of-sight
filtering and existing acceleration/rate limits after continuity blending.
Submitted commands own the next slew baseline and integrated recovery budget.
Ordinary loss stays horizontal-only; safety restrictions and Stop bypass slew.
Camera angles/status retain actual receipt stamps and current-provider identity;
selection evidence must be newer than actual LOC dispatch. Firmware without
target request IDs retains a physical identity-evidence limitation.

Fresh defaults add sparse gimbal recovery overrides: 8 seconds/4 metres,
0.5-second confirmation/restoration, 70% angle blend and half-authority new
provisional guidance. Other followers and explicit saved configurations retain
their policy. Fresh Vector defaults select coordinated turn; existing gains,
speed limits and accelerations are unchanged. Config Sync remains explicit.

## Validation record

Final backend Unit: **3,304 passed, 41 optional-dependency skips, 14 subtests
passed**; Integration: **185 passed**. Schema generation/check, API candidate
inventory, route contracts and hygiene pass. Focused coverage includes
117 continuity/schema/profile checks, 133 camera/native checks and 86
video/hygiene checks. Dashboard: **489 tests / 64 suites**, build and lint pass.
QGC build and focused client pass; corrected canonical-tool-PATH full
Unit/Integration suite: **413/413 passed**, Flaky/Network excluded.
CI route/docs/config/binary/remote-browser contract gate: **154 passed**.
Additional security/config/Dashboard contracts: **47 passed, 1 optional skip**.
API inventory/route/hygiene gate: **64 passed**.

Software Stop gates renewed under blocked capture and inference: operator Stop
2.75/2.80 ms; expiry Stop 369.70/367.51 ms after last accepted renewal. These
measure software dispatch, not network or motor stopping. Four timing tests pass.

Logs are under the 2026-10-01 slice-4b4 private baseline cache; final Unit log is
`v13-backend-unit-qualified.log`, Integration `v13-backend-integration-qualified.log`,
schema `v13-schema-final.log`, inventory `v13-api-inventory-current.log`, timing
`v13-camera-stop-timing.log`. The initial failed/interrupted runs remain retained.

The source checksum manifest in private `camera-sih-operator-v13` pins 190 copied
files including dirty integration source, rather than treating unchanged git
HEAD as release provenance. Instance: `gimbal-sih-8731fee94510e2e1`.
QGC debug binary SHA-256:
`0c968d8ed28f8f685c9a3f4dbc2d2f46ba4379c2c268946d3b41df9cfae68dd2`.
Preparation is private, command-blocked, starts no services and does not move
the camera. The later camera-free check found no live v12 stack; only the
unrelated Portainer container remained. No operator services were stopped.

Camera-free continuation and newly exposed normal-follower release blockers
are recorded in [the later checkpoint](2026-10-02-qgc-camera-free-qualification.md).

The checked-in QGC validation runner snapshots source/configuration and uses
an isolated loopback-only PX4 namespace. Both followers/mounts passed
with independent world-target observations through production dispatch,
continuity, shaping and publication, including actual command signs/slew and
independent simulated yaw/altitude response. This does not qualify native camera
transactions or physical image/aircraft closed-loop convergence. Native
transactions have separate focused tests and pending camera acceptance.

All **2,210 recorded publications succeeded**. Each case restored confirmed
ACTIVE authority after retarget/loss, respected submitted/published slew limits,
kept ordinary loss yaw/down zero and confirmed one Hold after budget exhaustion.

| Follower / synthetic mount | Sends | Initial right/up yaw/altitude | Retarget left/down yaw/altitude |
| --- | ---: | --- | --- |
| Chase / vertical | 552 | +11.36° / +0.940 m | −2.13° / −2.361 m |
| Chase / horizontal | 553 | +13.74° / +0.930 m | −1.85° / −2.364 m |
| Vector / vertical | 552 | +22.12° / +0.365 m | −14.18° / −2.005 m |
| Vector / horizontal | 553 | +23.41° / +0.521 m | −11.09° / −2.444 m |

Artifacts: 2026-10-02 slice-4b4 cache
`v13-final-{chase,vector}-{vertical,horizontal}/`, each with source/configuration/
driver/image/binary/package provenance, observations, actual publication and
hover precondition traces, and `result.json`. All four source maps match.
Driver SHA-256:
`d479ba65f447c13e21845aae9a030a02ccda3484d70638996088d71093ea8f7d`.
Evidence-owned containers were cleaned; unrelated/live v12 containers preserved.

Strict SIH checking found a small Vector slew overshoot when clearing inertial
coast lateral compensation after the limiter. The correction reserves that
component in the same acceleration budget; large residuals unwind with zero yaw
before turning resumes. Four new regressions pass; full backend/SIH evidence was
renewed after the fix. Earlier fixture failures remain saved, including response
windows contaminated by startup heading drift/prior climbing; final observation
preconditions were strengthened without relaxing thresholds or production tuning.

Harness bring-up exposed the existing MAVSDK-only telemetry manager calling
`velocity_body`, absent from the installed SDK. SIH evidence uses production
MAVLink2REST, matching v12; unsupported SDK-only mode remains explicit release
compatibility debt. No gains/limits were changed to accommodate fixture failures.

Raw AI reviews: `../evidence/2026-10-02-v13-selection-shutdown-review-raw.md`
and `../evidence/2026-10-02-v13-guidance-review-raw.md`; QGC operator review is
retained in `custom-pixeagle/reviews/slice-4b4-v13-operator-raw.md`.

## Remaining gates

The fresh blocked v13 profile and QGC operator guide are ready. Camera startup
will be checked by the launcher without interfering with live v12. The operator
tests both followers during
retarget, edge refusal, loss/reacquisition, vertical guidance and Stop. The real
camera image is not coupled to SIH pose. Network/load is 4b.4d; reproducible
Linux/Windows/Android releases, PR review and rollback are slice 5; Pi/router/
camera/PX4 ground acceptance with CB active is slice 6. Real-flight scope is later.
