# Phase 0 Checkpoint - PX4/SITL Validation Scout

Date: 2026-04-30  
Status: completed for planning scout

## Scope

This slice researched how PixEagle should validate followers, trackers, gimbal
providers, and PX4 Offboard behavior during development and CI. It did not add a
runtime SITL runner yet.

## Work Completed

- Audited current PixEagle PX4/SITL/X-Plane docs, CI, Makefile, follower tests,
  tracker tests, MAVSDK mocks, MAVLink2REST mocks, and gimbal tests.
- Compared PixEagle with `/home/alireza/mavsdk_drone_show` SITL scenario-plan
  and evidence-reporting practice.
- Rechecked `/home/alireza/mavlink-anywhere` current headless routing defaults
  for MAVSDK and MAVLink2REST fanout.
- Researched official PX4 container/SITL guidance, official PX4 MAVSDK
  integration testing, PX4 Offboard requirements, MAVSDK Offboard behavior,
  MAVLink Gimbal Protocol v2, Topotek SIP protocol, and the user-suggested
  unofficial PX4/Gazebo headless image.
- Added a target validation ladder to
  `docs/architecture/pixeagle-modernization-blueprint.md`.
- Added PXE-0018, PXE-0019, and PXE-0020 to the issue register.
- Expanded PXE-0016 to include gimbal provider conformance and stale-data
  fail-closed behavior.
- Corrected the gimbal tracker reference so it no longer claims old flat gimbal
  keys remain compatibility fallbacks.
- Wrote the full strategy scout:
  `docs/reporting/agent-ops/codex-modernization/audits/2026-04-30-px4-sitl-validation-strategy-scout.md`.

## Decisions

- Use a layered validation ladder rather than one huge full visual simulation for
  every change.
- Make follower-only headless PX4 SITL the first live PX4 validation target
  after the dedicated Offboard commander lands.
- Use official PX4 images or internally pinned images as the default container
  path; keep `jonasvautherin/px4-gazebo-headless` as an optional pinned
  reference/evaluation path because it is unofficial.
- Keep tracker tests deterministic with synthetic/recorded fixtures; reserve
  X-Plane/Gazebo/scene-stream visual SITL for nightly, release, or manual
  evidence runs.
- Treat current gimbal support as `topotek_sip_udp` provider instance. Do not
  put vendor protocol logic in followers.

## Validation

- `git diff --check`
  - Result: passed.

No runtime tests were needed because this was a documentation/planning scout,
but the next implementation slice should run the relevant docs and schema gates
if active docs or config contracts are changed.

## Evidence Paths

- Strategy scout:
  `docs/reporting/agent-ops/codex-modernization/audits/2026-04-30-px4-sitl-validation-strategy-scout.md`
- Blueprint:
  `docs/architecture/pixeagle-modernization-blueprint.md`
- Issue register:
  `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- Journal:
  `docs/reporting/agent-ops/codex-modernization/journal/2026-04.md`
- Gimbal tracker reference:
  `docs/trackers/02-reference/gimbal-tracker.md`

## Risks And Open Items

- PXE-0007/PXE-0013 remain blockers before live SITL can honestly prove
  Offboard heartbeat robustness.
- PXE-0018 is the planned SITL harness/scenario/artifact work.
- PXE-0019 is the planned deterministic tracker-in-loop evidence work.
- PXE-0020 is the planned X-Plane/Windows cleanup decision.
- PXE-0016 remains the gimbal provider extraction work.

## Plan Reconciliation

This slice strengthens the original plan rather than changing direction. The
main adjustment is scheduling PX4-in-loop validation earlier: it should start
right after the Offboard commander work, not wait until final release hardening.
