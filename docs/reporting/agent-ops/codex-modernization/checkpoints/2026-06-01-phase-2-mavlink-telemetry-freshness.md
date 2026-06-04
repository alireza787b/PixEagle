# Phase 2 MAVLink Telemetry Freshness Checkpoint

Date: 2026-06-01  
Slice: Phase 2 MAVLink telemetry freshness  
Issue: PXE-0014  
Status: Complete at config/unit/mock/docs level; no PX4-in-loop evidence claimed.

## Summary

PixEagle now exposes MAVLink2REST timeout, retry, and telemetry staleness as
typed configuration and API-visible runtime status. Aggregate polling and
per-message fetches use the same request timeout/retry path, and `/status`
reports `mavlink_telemetry` freshness. Late independent-review blockers found
after the initial checkpoint were fixed before this slice was re-closed.

This checkpoint does not claim SITL, HIL, real-aircraft, deployment, or field
success.

## Files Changed

- Runtime/API:
  - `src/classes/mavlink_data_manager.py`
  - `src/classes/fastapi_handler.py`
- Config/schema:
  - `configs/config_default.yaml`
  - `configs/config_schema.yaml`
  - `scripts/generate_schema.py`
- Tests:
  - `tests/unit/drone_interface/test_mavlink_data_manager.py`
  - `tests/test_config_service.py`
  - `tests/unit/test_generate_schema.py`
  - `tests/unit/core_app/test_app_controller_offboard_safety.py`
  - `tests/test_docs_infrastructure_consistency.py`
- Docs/reporting:
  - `docs/core-app/03-api/README.md`
  - `docs/drone-interface/02-components/mavlink-data-manager.md`
  - `docs/drone-interface/05-configuration/mavlink-config.md`
  - `docs/drone-interface/07-troubleshooting/telemetry-gaps.md`
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
  - `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Behavioral Changes

- Added MAVLink config keys:
  - `MAVLINK_REQUEST_TIMEOUT_S`
  - `MAVLINK_REQUEST_RETRIES`
  - `MAVLINK_STALE_TIMEOUT_S`
- `MavlinkDataManager` validates those settings with bounded defaults.
- Aggregate `/v1/mavlink` polling uses the configured request timeout and retry
  count instead of a hard-coded timeout.
- Per-message async fetches use the same request helper via
  `asyncio.to_thread(...)`, avoiding direct blocking HTTP calls in the event loop.
- Successful aggregate polls and per-message fetches update
  `last_successful_fetch_monotonic_s`, clear last error, reset connection error
  count, and therefore drive the same `/status.mavlink_telemetry` freshness
  truth.
- `get_connection_status()` reports enabled state, fresh/stale/error status,
  success age, stale timeout, request timeout, retry count, error count, last
  error, and endpoint.
- `/status` now includes `mavlink_telemetry`.
- `MAVLINK_REQUEST_RETRIES` is generated as schema type `integer`, so
  ConfigService and the dashboard numeric editors validate type and bounds.

## Validation

Commands run:

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/test_config_service.py \
  tests/unit/test_generate_schema.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 158 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/unit/drone_interface/test_px4_interface_manager.py \
  tests/unit/drone_interface/test_telemetry_handler.py \
  tests/integration/drone_interface/test_telemetry_flow.py \
  tests/integration/drone_interface/test_safety_integration.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/test_generate_schema.py \
  tests/test_config_service.py -q
```

Result: 289 passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest \
  tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py
```

Result: 13 passed.

```bash
PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh
```

Result: schema is up to date.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m py_compile \
  src/classes/mavlink_data_manager.py \
  src/classes/fastapi_handler.py \
  tests/unit/drone_interface/test_mavlink_data_manager.py \
  tests/test_config_service.py \
  tests/unit/test_generate_schema.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/test_docs_infrastructure_consistency.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

```bash
PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest -q tests
```

Result: 1751 passed, 40 skipped.

## Review Gate

Telemetry-focused reviewers returned after the first checkpoint and blocked
closure on two concrete issues:

- `MAVLINK_REQUEST_RETRIES` was generated as schema type `int`, which
  ConfigService and dashboard numeric editors do not validate as an integer.
- Successful per-message MAVLink2REST fetches used by follower telemetry did
  not update `last_successful_fetch_monotonic_s`, `connection_state`, or
  `last_error`; only aggregate polling updated `/status` freshness truth.

Both blockers were fixed and covered by regression tests. Post-repair
independent review found no PXE-0014 blockers and cleared the slice to proceed
to PXE-0035. Reviewers recorded residual, non-blocking debt around legacy
untyped `/status` exposure, request-level rather than payload-level freshness,
and future consumers needing to read the full `mavlink_telemetry` status object
instead of `fresh` alone.

## Evidence Limits

- Current evidence is unit/mock/integration Python evidence only.
- No live MAVLink2REST, PX4 SITL, HIL, real-aircraft, deployment, or field
  validation was run.
- Telemetry freshness status proves only PixEagle's local MAVLink2REST request
  bookkeeping and mocked request handling. It does not prove MAVLink payload
  timestamps, PX4 estimator quality, follower correctness, or live transport
  timing.

## Risks And Follow-Ups

- `MavlinkDataManager` still polls in a background thread and exposes cached
  values through `get_data(...)`; this slice adds freshness visibility but does
  not change all consumers to refuse stale telemetry.
- Freshness remains request-level MAVLink2REST transport freshness, not
  message-level freshness derived from MAVLink payload timestamps/frequencies.
- After a failed request with a recent previous success, `fresh` can still mean
  a recent successful request exists while `status` and `last_error` describe
  the latest failure. Future typed API consumers must use the full status object.
- PXE-0018 must prove live MAVLink2REST behavior, transport timing, and PX4
  interaction in a headless SITL evidence harness.
- PXE-0036 tracks typed telemetry-health semantics and payload-level freshness
  before API/MCP consumers or dashboard UI depend on `fresh` alone.
- PXE-0035 is next: repeated OffboardCommander publish failures need a local
  failure policy and operator-visible degraded/abort behavior.

## Next Slice

Continue Phase 2 with PXE-0035: OffboardCommander publish-failure policy.
