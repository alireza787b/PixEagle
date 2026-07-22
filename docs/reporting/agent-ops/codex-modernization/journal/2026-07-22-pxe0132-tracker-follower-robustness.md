# PXE-0132 Tracker And Follower Robustness

- Date: 2026-07-22
- Phase: 5
- Status: local implementation complete; publication/VPS acceptance pending

## Trigger

Maintainer preview tests reported fragile CSRT retention, reversed-looking yaw,
zero forward velocity, and uncertainty about how tracker recovery should relate
to follower safety. The resumed audit covered candidate state, estimator
mutation, command eligibility, PID direction, units, target aim ownership,
follower profile intent, stale config, and unsupported capability claims.

## Decision

Recovery and control remain separate. Trackers may keep private tentative or
predicted state for bounded reacquisition, but only a current measured output
may authorize normal follower math. Classic validation now evaluates explicit
candidate geometry without replacing the last confirmed target or advancing
the estimator. After rejection, CSRT requires configured consecutive valid
proposals before reacquisition becomes measured again.

Follower signs are normalized once in `BaseFollower`. A positive image-X error
means body-right or clockwise yaw; a positive image-Y error means body-down.
The helper mirrors the measurement around the PID setpoint because
`simple_pid` computes `setpoint - measurement`. Mount transforms remain provider
responsibility and occur before this mapping.

The profiles keep distinct behavior: `mc_velocity_chase` ramps forward toward
its configured limit, while position and historical distance profiles publish
zero forward velocity because no maintained range signal exists. No fake range
controller was added to make preview numbers look active.

Both maintained chase ramps now use monotonic time and bound one state
transition to the configured nominal period. Delayed scheduling therefore slows
the ramp instead of applying accumulated catch-up in one command. Gimbal chase
advertises only its implemented `CONSTANT` and `PITCH_BASED` forward-speed
modes; the inactive `PROPORTIONAL_NAV` selection and obsolete research guide
were removed rather than preserved as a silent fallback.

## Cleanup And Compatibility

Dead Particle Filter, dlib, KCF, estimator-following, and distance-hold settings
were removed through the retirement registry. Runtime/catalog/docs no longer
promise universal FPS, accuracy, occlusion recovery, or production readiness.

Two `PF_CANNY_THRESHOLD*` paths remain active because the detector consumes
them. A test against an old full config proved that renaming them through the
current retirement metadata would remove the old values before canonical
fields exist. The rename is therefore deferred under PXE-0133 until one generic
value-preserving path migration is implemented and tested; deployed tuning is
more important than cosmetic schema purity.

## Evidence

- Upgrade/config/detector: 91 passed.
- Followers: 110 passed.
- Tracker/detector/runtime: 469 passed, 40 optional skips.
- AppController Offboard safety: 160 passed.
- Required API/reload: 72 passed.
- Docs/schema generator: 85 passed.
- Smart capability regression: 9 passed.
- Schema: 38 sections / 513 parameters; compile/diff checks pass.
- OpenCV 4.13 deterministic CSRT smoke: 59/59 accepted, mean IoU 0.724,
  minimum IoU 0.601.

- Complete backend regression: 3518 passed, 48 skipped, 1 known PXE-0127
  Starlette/httpx warning in 417.09 seconds. Dashboard: 54 suites / 358 tests
  and the beta.21 production build passed. The generated API tool-candidate
  inventory was refreshed and its 13 tests passed.
- Final focused review added monotonic ramp, supported-mode, and tentative CSRT
  reference regressions: 82 focused tests; 49 config migration tests; 114
  follower tests; 372 tracker/detector/Smart/static tests with 40 optional
  skips; 232 required API/reload and Offboard-safety tests; and 89
  docs/schema/static tests passed. These groups overlap the complete suite.

Exact-source CI and the authorized VPS preview remain the next gates. No real
camera, gimbal, PX4, Raspberry Pi, aerial benchmark, SITL/HIL, field, or
aircraft claim is made.
