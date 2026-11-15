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

Backend validation:

- Schema regeneration and verification passed.
- Focused configuration/API/default gates: 220 passed.
- First full unit/configuration pass: 7,672 passed, 11 skipped, 31 failed.
  The failures assumed the old fallback floor or implicitly used 20 m world
  fixtures. Tests now explicitly declare their saved low-floor scenario, or
  place the aircraft above the public floor when testing another failure.
- Affected regression suites after those corrections: 356 passed.
- Full rerun: **7,703 passed, 11 skipped**, recorded under
  `reports/sitl/follower-consolidation-20261111/public-defaults30-full-unit-r2.log`.

Official upstreams were checked with `git ls-remote`:

| Repository | Revision |
|---|---|
| QGC master | `19e4246b244d3946fa6f2ea65d349a7fa30f11d0` |
| PX4 main | `c4b8f107ae97d643fc784a394e3874f34caec563` |

The QGC merge ports authenticated sources, frame provenance and custom views to
the new worker/session receiver API. The local build, six focused media suites,
and H.264/VP8 exact displayed-frame association tests pass, including three
repeated native runs. The upstream MAVLink pin is refreshed to
`87da370c02e40f6f9a2eacf1b162d7f07e640467`. All 559 Unit/Integration suites pass with the standard Flaky/Network
exclusions; 52 tool/workflow contracts and scoped lint pass. Full-tree lint was
run: inherited formatting, archived prose, example QML and production assertion
failures remain. It is not a green full-tree lint result. The customized repository is private; no new custom changes
are pushed to the old public fork, and no public QGC PR/release is authorized.

The allocator-only PX4 candidate was rebuilt on current main separately: all
11 real functional cases pass; the negative control fails exactly the two
coefficient-invariance regressions. Cases run in separate processes. Native
`make check_format` passes. Evidence, XML results and the reviewable patch are
under `reports/native-guidance/px4-allocator-current-main-20261115-r1/`.
The pinned simulator firmware and hardware are unchanged. No PX4 draft PR,
QGC PR/release, public PixEagle release or new hardware qualification is claimed
by this checkpoint.

## PX4 upstream disposition

| Change | Decision and remaining evidence |
| --- | --- |
| Sparse roll/pitch allocator normalization (0008–0009) | Recommend an isolated upstream draft: current-main functional positive/negative controls and format pass. Human patch review/DCO sign-off is pending. Related #18984, #24199, merged #28589 and open #27083 were inspected; no exact duplicate found in the targeted search. |
| Transition acceleration (0003–0004) | Requalify against current main and its #29783 changes. Earlier altitude evidence does not establish improvement. |
| Transition heading (0006–0007) | Coordinate with merged #28656 and open #29509; do not submit an overlapping bundled flight claim. |
| Transitive flight-task build dependencies (0005) | Need an isolated current-main reproducer before proposing a patch. |
| Owned-mode API, phase history and physical attitude source (0001–0002, 0010–0013) | Keep experimental. Upstream design needs lifecycle/failsafe, versioned-message translation and publication-cost review. |
| ROS SDK shutdown behavior | No as-is proposal: preserve unregister/ownership cleanup; first isolate the lifecycle requirement against current SDK. |

The complete native firmware extension remains pinned to
`155f415168cef08dca2f5d85d2bc258b44a589ec` in `native/px4/extension.json`.
Only the allocator-only proposal has been renewed and tested on current PX4
main. This checkpoint does not claim that the complete experimental firmware
is rebased or qualified on current main. No archived result or firmware pin is
rewritten to imply that it is.

## Source candidate identity

Backend, Dashboard package/lock and installer fallback version agree on
`7.6.0-rc.1`. Release-identity/documentation/setup gates pass (209 cases);
Dashboard passes 69 suites / 591 cases and its production build. This is a
prerelease software checkpoint, not renewed hardware acceptance.

Evidence root: `reports/sitl/follower-consolidation-20261111/`. Logs include
`qgc-upstream-full-unit-integration-r3.log`,
`qgc-upstream-native-presentation-r4.log`, `qgc-upstream-native-repeat-r1.log`,
`qgc-upstream-tool-contracts-r2.log`, `qgc-upstream-full-lint-r2.log`,
`qgc-upstream-final-scoped-lint-r2.log`, `public-dashboard-final-tests-r1.log`
and `public-dashboard-final-build-r1.log`. Older failed runs remain retained.
