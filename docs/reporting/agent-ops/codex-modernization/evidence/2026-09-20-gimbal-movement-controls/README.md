# Adjustable movement and hold-control evidence

Software/browser validation only, dated 2026-09-20. Camera offline; no hardware
axis mapping, continuous tracking, aircraft, SITL or HIL acceptance claim.

Commands:

```sh
.venv/bin/python tools/generate_api_tool_candidates.py
PYTHONPATH=src .venv/bin/pytest -q tests/unit/trackers/test_gimbal_control.py tests/unit/core_app/test_api_v1_gimbal_control.py tests/unit/followers/test_gimbal_mount_validation.py tests/unit/followers/test_image_axis_control_contract.py tests/unit/followers/test_gm_velocity_vector_control.py tests/test_gm_velocity_vector_smoke.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_backend_restart_lifecycle.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_tracker_follower_contract_consistency.py tests/integration/test_follower_factory.py
cd dashboard
CI=true npm test -- --watchAll=false --runInBand
npm run build
cd ..
bash scripts/check_schema.sh
.venv/bin/python -m py_compile src/classes/gimbal_motion.py src/classes/gimbal_control.py src/classes/api_v1_actions.py src/classes/api_v1_contracts.py src/classes/followers/gm_velocity_chase_follower.py src/classes/followers/gm_velocity_vector_follower.py
git diff --check
node reports/gimbal-motion-controls/browser_check.cjs
```

Results: 491 backend tests; 62 dashboard suites / 471 tests; build, schema,
compilation and whitespace checks passed. The generated candidate inventory was
regenerated before the final run; an earlier review run found stale hashes.

`browser_check.cjs` and `browser-events.json` record the offline production
browser test. It intercepts every action request and never forwards movement to
the backend. Status is read from the actual isolated runtime, then connection
state is simulated in the page. Native Chromium touch input and keyboard events
exercise the same pointer handlers as desktop movement. Local screenshots are
under `reports/gimbal-motion-controls`; hashes are recorded separately. A second
read-only browser view captured the fully settled dialog after its opening fade.

The normal runtime supervisor, preserved in the earlier Smart/restart evidence,
still validates command preview, circuit breaker, disabled MAVLink and loopback
binding. `runtime-status.json` captures the actual disconnected camera status
with new motion settings and following off.

See the [checkpoint](../../checkpoints/2026-09-20-gimbal-movement-controls.md) for
the release/tap boundaries and next horizontal/vertical hardware sequence.
