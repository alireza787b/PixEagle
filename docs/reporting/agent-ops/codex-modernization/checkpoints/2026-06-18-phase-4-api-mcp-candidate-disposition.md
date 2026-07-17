# Phase 4 API/MCP Candidate Disposition Governance

Date: 2026-06-18  
Slice: PXE-0066 API/MCP candidate disposition governance  
Status: completed  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice made the generated API/MCP candidate inventory review-complete by
assigning an explicit disposition to every generated `/api/v1` candidate.

It did not add a runtime MCP endpoint, executor, `tools/list`, `tools/call`, or
callable automation surface.

## Decisions

- `review_disposition` is a nested object, separate from `review_status` and
  `promotion_status`.
- Valid states are:
  - `approved_for_review_only`: docs-stage approval only; never callable by
    itself.
  - `blocked`: not eligible for agent/MCP promotion without a separate design,
    tests, policy update, and independent review.
  - `deferred`: postponed to a later validation or safety slice; still
    non-callable and unpromoted.
- Every disposition records owner, review date, rationale, evidence, next gate,
  `does_not_imply_mcp_exposure: true`, and
  `runtime_promotion: not_promoted`.
- Sensitive action/auth/SITL/audit paths are defensively excluded from
  approved-for-review-only classification even if the initial read-only
  allowlist is misconfigured later.
- `agent_policy.yaml` owns the disposition vocabulary and fail-closed defaults.
- `agent_tools.yaml` mirrors only the six approved-for-review-only
  process-local GET candidates and remains docs-stage only.

## Candidate Split

Generated candidate inventory now contains:

- 24 total `/api/v1` candidates.
- 6 `approved_for_review_only` process-local GET candidates:
  - `/api/v1/runtime/status`
  - `/api/v1/following/status`
  - `/api/v1/following/telemetry`
  - `/api/v1/telemetry/health`
  - `/api/v1/tracking/runtime-status`
  - `/api/v1/tracking/telemetry`
- 13 `blocked` auth/action/action-audit candidates.
- 5 `deferred` SITL validation-stimulus candidates.

All candidates remain:

- `callable: false`
- `mcp_exposure: none`
- `default_registry_exposure: exclude`
- `promotion_status: unpromoted`

## Files Changed

- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/agent_tools.yaml`
- `docs/agent-context/agent_policy.yaml`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Review

Two read-only reviewers inspected the generator, registry, policy, and tests.

Findings fixed in this slice:

- Generated inventory was stale after the generator change.
- Tests needed explicit disposition counts and route-class-to-state checks.
- Approved-for-review-only candidates needed tests proving they are still
  non-callable, unpromoted, and outside runtime exposure.
- Sensitive GET/action/auth/SITL paths needed a defensive guard so future
  read-only allowlist mistakes cannot approve them.
- Registry entries needed disposition mirroring without becoming `tools/list`
  entries.

## Validation

Passed:

```bash
python3 tools/generate_api_tool_candidates.py --check
```

```bash
python3 -m py_compile \
  tools/generate_api_tool_candidates.py \
  tests/test_api_tool_candidates.py
```

```bash
.venv/bin/python -m pytest tests/test_api_tool_candidates.py -q
```

Result: 9 passed.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_tool_candidates.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -q
```

Result: 45 passed.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current, 41 sections, 549 parameters.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_docs_infrastructure_consistency.py \
  -q
```

Result: 20 passed.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 217 passed with the
existing Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: passed.

Note: plain `bash scripts/check_schema.sh` uses system `python3` on this host
and failed because that interpreter lacks `ruamel.yaml`. The authoritative
schema gate passed with the repo virtualenv via `PYTHON=.venv/bin/python`.

## Not Performed

- No runtime MCP endpoint, executor, `tools/list`, or `tools/call`.
- No callable tool exposure.
- No service install/start/enable.
- No sidecar mutation/update.
- No QGC branch mutation or build.
- No PX4/SITL/HIL/field run.
- No deployment.
- No real-aircraft control.

## Remaining Work

- PXE-0065: SITL sidecar evidence hardening.
- PXE-0068: remote/demo setup profile automation and media/service follow-ups.
- PXE-0070: QGC authenticated remote HTTP/WebSocket media support.
- PXE-0064: operator credential/TLS hardening, remaining legacy alias
  retirement, and broader adversarial auth/media tests.
- PXE-0008/PXE-0021: continue broader `/api/v1` migration and dashboard
  toolchain modernization.

## Next Planned Slice

Continue with PXE-0065 SITL sidecar evidence hardening unless maintainer
priority shifts to PXE-0068 setup-profile automation or PXE-0070 QGC remote
media support.
