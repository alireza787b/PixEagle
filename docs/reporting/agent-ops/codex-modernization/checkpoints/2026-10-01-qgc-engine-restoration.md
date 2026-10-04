# QGC camera bench: engine restoration and follower compatibility

Slice 4b.3 software follow-up, 2026-10-01. Physical camera acceptance remains open.

## Changes

- Native tracker switch accepts optional `restore_engine_selection:true` with
  native context and `persist:false`. Runtime memory restores the local Classic
  implementation/Smart intent or camera selection-mode intent. It never restores
  a previous target or writes saved tracker configuration. Local model selection
  continues using its existing canonical configuration.
- Explicit tracker choices remain exact. Unavailable remembered choices return
  an error instead of silently selecting a replacement. Local Smart cannot be
  enabled on the camera engine; camera Smart remains provider-owned.
- Tracker schemas declare canonical `data_type`. Native follower compatibility
  uses the same schema matrix as the follower runtime. Derived image coordinates
  from a camera tracker do not advertise image followers.
- Native target/model operations and shared dashboard tracker/model transitions
  reserve camera lifecycle. Accepted transitions cancel a manual gesture before
  changing ownership. Dry-run, stale native requests and idempotent replay do not
  stop current camera input. A failed Stop blocks mutation with an actionable
  conflict. Following start reserves the same lifecycle and refuses active
  manual control before aircraft commands.
- Companion-only follower reads retain identity, compatible profiles and start
  reasons. Profile selection and Start retain verified-aircraft requirements;
  `camera_control_active` adds a readiness reason. Bench preview remains inhibited.

Implementation touches AppController, native target/model/follower helpers,
the shared dashboard model executor, a small tracking-engine selection helper,
tracker schema metadata, and their tests. Camera executor/contracts are the
coordinated control-worker change, documented separately.

## Validation

**357 passed**, two existing dependency deprecation warnings, 6.78 seconds:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/unit/core_app/test_tracking_engine_selection.py \
  tests/unit/core_app/test_native_following.py \
  tests/unit/core_app/test_native_target_operations.py \
  tests/unit/core_app/test_native_models.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py -q
```

Log: `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b3-2026-10-01/backend-engine-restoration-tests.log`.
`bash scripts/check_schema.sh` passes with 606 parameters. Touched Python modules
compile and whitespace checks pass. Tests exercise real AppController switching
and native guards with model constructors and camera transport replaced by fakes.
They do not establish camera motor behavior, inference performance or flight safety.

The final shared synchronous Smart-toggle entry point received the same lifecycle
reservation as its async API wrapper. The focused engine/target/model/Offboard
regression then passed **263 tests**, 2.38 seconds; log
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b3-2026-10-01/backend-engine-lifecycle-final-tests.log`.

## Next gate

Refresh only the isolated camera profile to saved `Gimbal` tracking and a chosen
compatible angle follower, keeping command preview/inhibit. Ordinary shipped
profiles stay local. Complete QGC/control-worker gates, then operator camera
Classic/Smart, local tracking round trips, joystick/roll/release and telemetry
checks. The 90-degree mounting transform and angle following remain unqualified.
