# Phase 4 API Security Policy Foundation Checkpoint

Date: 2026-06-13
Slice: PXE-0064 declarative security policy foundation
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Outcome

This slice adds the declarative API security classification layer that PXE-0064
will consume in later enforcement slices. It does not enable authentication,
create sessions, issue tokens, or change runtime access behavior.

Implemented:

- `src/classes/api_security_types.py` for typed principals, scopes, access
  modes, audit policy, and authorization decisions;
- `src/classes/api_security_policy.py` for a default-deny route classification
  covering all 132 declared custom routes plus FastAPI's implicit docs/OpenAPI
  routes;
- exact route coverage tests proving every declared route matches one and only
  one rule, and the policy surface is neither narrower nor broader than the
  actual route surface;
- least-privilege scope separation for viewer/operator/admin plus exact bearer
  scopes and loopback-only local-compat handling;
- session CSRF semantics for mutating routes;
- local-only treatment for legacy mutations, docs/OpenAPI, debug, and SITL
  injection surfaces;
- API/MCP candidate provenance updated to include the new security-policy
  modules;
- API and docs references updated to describe the policy foundation without
  implying runtime auth exists yet.

## Files Changed

Core policy and tests:

- `src/classes/api_security_types.py`
- `src/classes/api_security_policy.py`
- `tests/test_api_security_policy.py`

Provenance and docs:

- `tools/generate_api_tool_candidates.py`
- `tests/test_api_tool_candidates.py`
- `docs/apis/api-security-policy.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/03-api/README.md`
- `docs/agent-context/README.md`
- `docs/README.md`

Validation and governance:

- `Makefile`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_security_policy.py -q`:
  17 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_docs_infrastructure_consistency.py -q`:
  62 passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema current, candidate inventory current, and 77 tests passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py`:
  regenerated the non-callable candidate inventory after the policy file hash change.

## Risks And Open Work

- This slice is policy-only. It does not authenticate requests, create
  sessions, validate bearer credentials, or enforce the policy at runtime.
- PXE-0064 still needs browser/operator sessions, machine tokens, middleware,
  CSRF enforcement, authenticated media/WebSocket paths, durable audit events,
  and legacy mutation retirement.
- Independent subagent review was attempted, but the subagent service could not
  refresh its access token. The slice therefore used local finished-diff review
  and repository-level tests instead.

## Next Slice

Continue PXE-0064 with runtime enforcement:

- credential/session middleware;
- hashed revocable machine tokens;
- browser login/logout/session and CSRF handling;
- route enforcement for HTTP, MJPEG, WebSocket, and WebRTC signaling;
- security audit events;
- dashboard client migration;
- legacy mutation retirement gates.
