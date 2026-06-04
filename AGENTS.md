# PixEagle Agent Operating Guide

This file is the canonical operating guide for terminal AI agents working in
this repository. It applies to the full repository unless a deeper-scoped
`AGENTS.md` is added later for a subtree.

## Start Here

Before making changes, read:

- `README.md`
- `docs/README.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-04-29-proposed-improvement-plan.md`
- `docs/architecture/pixeagle-modernization-blueprint.md`
- `docs/apis/api-modernization-blueprint.md`
- the domain docs for the files being changed

Always check the current branch and worktree status before editing. The user may
have local changes; do not revert or overwrite changes you did not make.

## Safety Boundaries

PixEagle is flight-control-adjacent software. Treat safety claims as requiring
evidence, not intent.

- Do not run real-aircraft control, deployment, field tests, destructive cleanup,
  or service installation without explicit operator approval.
- Do not claim SITL, HIL, or real-world success without logs, exact commands,
  versions, configs, and evidence artifacts.
- Prefer fail-closed behavior for PX4/MAVSDK command paths.
- Keep Offboard, telemetry, target freshness, and operator abort paths visible in
  code, tests, docs, and reports.

## Validation Expectations

Use the narrowest useful verification during development, then broaden at phase
checkpoints.

Minimum Phase 0 gates:

- `PYTHONPATH=src pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py`
- `bash scripts/check_schema.sh`
- Python syntax/import checks for touched modules
- dashboard install/test/build in CI

When changing frontend code, run the dashboard tests/build. When changing config
schema or defaults, run `bash scripts/check_schema.sh` and commit generated
schema changes only when intentional.

## API And MCP Rules

- New public JSON APIs belong under `/api/v1/...`.
- API routes must use typed request/response models, structured errors,
  operation IDs, and route inventory tests.
- Legacy routes may exist only as compatibility aliases with deprecation notes
  and removal tracking.
- MCP/AI-agent support must come from the same typed API/state contracts, not a
  separate ad hoc automation surface.
- Dangerous actions need idempotency, dry-run or preview where possible, explicit
  confirmation, and audit/event records.

## Documentation And Reports

Behavior changes must update docs in the same slice. Keep modernization records
under:

- `docs/reporting/agent-ops/codex-modernization/journal/`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`

Checkpoint reports should include:

- phase/slice
- files changed
- validations run
- evidence paths
- risks and open questions
- next planned slice

Vendor-specific agent files, if added later, should be thin pointers to this
file rather than duplicate operating specs.
