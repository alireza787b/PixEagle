# QGC native configuration checkpoint — 4b.1

Implemented `GET /api/v1/integration/config`, `POST /api/v1/actions/osd-set` and
`POST /api/v1/actions/config-apply` with typed versioned snapshots, process-bound
configuration generations, scoped authentication, CSRF, confirmation, actor/key
idempotency and audit. Native snapshots show only pending paths/tiers and saved
versus observed OSD state; they do not expose settings values or secret URLs.

OSD now persists through the shared ConfigService transaction with renderer
rollback and overlay cache invalidation. The existing dashboard toggle delegates
to the same owner and retains its response. Normal tracker apply is guarded by
follower/tracker lifecycle barriers and runtime activity; failure restores
runtime configuration and recreates the previous tracker when possible. Smart
model changes retain their existing native model-selection workflow.

Native process restart is not available without supervisor proof. Camera owner
configuration and cached/unverified immediate settings conservatively report a
system restart requirement. No config keys were renamed. No hardware, simulator
flight, deployment or service changes were performed for this backend work.

Changed implementation groups: native config module and contracts/routes;
security and route/tool inventories; OSD compatibility delegate; focused native
config/legacy OSD tests; API/operator lifecycle documentation.

Validation commands (backend worktree, existing Core environment):

```bash
PYTHONPATH=src /home/alireza/PixEagle/.venv/bin/python -m pytest \
  tests/unit/core_app/test_native_config.py \
  tests/unit/core_app/test_api_legacy_osd_routes.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_api_security_policy.py tests/test_api_tool_candidates.py -q
bash scripts/check_schema.sh
```

Evidence boundary: automated filesystem-isolated config/audit/rollback and
control-state mocks. These do not establish supervisor restart, real camera
behavior, firmware interaction or flight qualification. Native QGC behavior and
4b.2 camera mocks are recorded in the companion QGC checkpoint.

Validation result: 19 native config/OSD tests and 26 security-policy tests passed
together (45 passed, 49.17 seconds). The additional explicit legacy/native OSD
permission-parity regression passed separately. Route inventory, Parameters
reload and legacy OSD gates passed. The 13 tool-candidate tests passed after adding
the three new explicit route entries; generated source hashes must be regenerated
after concurrent 4b.2 shared-source edits. Schema check, touched-module bytecode
compilation and `git diff --check` passed. Operator OSD authority remains `control:write` (plus `config:read` for the native
snapshot); general Apply requires `config:write`. Operator-only OSD and denied
general apply/viewer cases are covered. The only warning was the existing
Starlette HTTP 422 constant deprecation.

Authoritative camera reload-tier correction: schema generation now classifies the
provider's eight startup settings (`ENABLED`, `CONTROL_ENABLED`, `PROVIDER`,
`UDP_HOST`, `UDP_PORT`, `LISTEN_PORT`, `CONNECTION_TIMEOUT`, and
`TRACKING_STATUS_TIMEOUT`) as `system_restart`. Dashboard and QGC therefore share
one classification; the native blanket GimbalTracker remapping was removed.
Coordinate, estimator and recovery adapter settings remain `tracker_restart`.
No key names or default values changed. A regression verifies that the dashboard
tracker-tier publication cannot publish pending provider changes.

The schema generator/reload-tier suites passed **82 tests** (9.50 seconds), then
the strengthened provider-publication regression plus required route/Parameters
gates passed **75 tests** (6.88 seconds; overlapping suites, not an additive count).
Schema drift check, generated API source inventory check, bytecode compilation,
and whitespace checks passed after the final edits.

Actual SIH smoke investigation found a stale prepared backend snapshot: its copied
security policy predated the native config routes and the native config module
was absent. Product route policy was correct; no authorization relaxation was
made. Added `tools/refresh_native_demo_sources.py` to refresh a stopped prepared
demo with staged source replacement, backup/rollback, updated definition files
and source provenance, preserving config/secrets/models/media. Three isolated
refresh tests plus a real ASGI HTTP middleware operator-session regression passed
**4 tests** in 7.52 seconds using the existing Full AI Python environment. The
HTTP test exercises config GET, CSRF refusal, successful desired-state OSD and
operator refusal for general config Apply.

A subsequent live OSD action exposed a missing required `status_code` argument
in the native configuration audit helper. Fixed the shared helper for OSD and
config Apply. The HTTP integration regression now invokes the real
`FastAPIHandler._record_security_audit_event` and JSONL writer, with no permissive
audit stub; both native action audit signatures are also covered. **Three focused
tests passed** in 10.30 seconds, including successful HTTP OSD mutation and recorded
validated/success events. Generated source provenance and syntax checks passed.
