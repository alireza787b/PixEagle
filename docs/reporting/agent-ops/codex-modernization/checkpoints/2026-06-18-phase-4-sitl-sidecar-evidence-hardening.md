# Phase 4 SITL Sidecar Evidence Hardening

Date: 2026-06-18
Slice: PXE-0065 SITL sidecar evidence hardening
Status: completed
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice hardened the checked-in SITL evidence contract for companion
sidecar compatibility and credential handling. It did not run PX4, Gazebo,
MavlinkAnywhere mutation flows, MAVLink2REST, PixEagle runtime control actions,
HIL, field validation, deployment, or real-aircraft control.

## Decisions

- Maintained SITL plans must declare a MavlinkAnywhere sidecar compatibility
  policy instead of relying on implicit docs.
- Accepted evidence must capture the installed MavlinkAnywhere dashboard
  version in `versions/mavlink_anywhere_dashboard.json`.
- MavlinkAnywhere probe results are classified as one of:
  - `unavailable`;
  - `unexpected_auth`;
  - `unsupported_contract_version`;
  - `unprepared_config`;
  - `prepared_routing`.
- Only `prepared_routing` can support accepted SITL evidence.
- Diagnostics, config, endpoints, profile-summary, and status reads are all
  core MavlinkAnywhere evidence.
- Accepted evidence requires `security/secret_scan.json` with `status: pass`.
- The secret scan blocks high-confidence credential-bearing text artifacts
  without storing matched secret values or context lines. Binary flight
  artifacts are skipped with metadata instead of decoded.

## Files Changed

- `tools/run_sitl_validation_suite.py`
- `tools/sitl_plans/phase2_follower_validation.json`
- `tools/sitl_plans/gazebo_visual_validation.json`
- `tests/test_sitl_validation_contract.py`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/architecture/companion-runtime-contract.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Implemented

- Added plan validation for `stack.routing.compatibility_policy` when the
  routing provider is `mavlink-anywhere`.
- Added the checked-in policy to both maintained plans:
  - reviewed ref:
    `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`;
  - reviewed version: `v3.0.14-2-g7643d4d`;
  - minimum dashboard semver: `3.0.14`;
  - auth expectation: `loopback_read_without_credentials`;
  - required API reads: status, diagnostics, endpoints, profile summary, and
    config.
- Added required evidence artifacts:
  - `versions/mavlink_anywhere_dashboard.json`;
  - `security/secret_scan.json`.
- Added version evidence extraction from `/api/v1/status`.
- Added semantic MavlinkAnywhere compatibility classification with auth
  precedence over transport failures.
- Added high-confidence secret scanning for:
  - private key blocks;
  - URL userinfo credentials;
  - Authorization bearer/basic values;
  - query-string secrets;
  - sensitive assignment keys;
  - sensitive structured JSON keys.
- Added safe suppressions for empty values, redacted placeholders,
  idempotency keys, hash/digest metadata, token IDs, CSRF/header names, and
  `_FILE`/path fields.
- Added binary skip metadata for flight logs and NUL-containing artifacts.
- Updated SITL and companion-runtime docs so operators understand the new
  classification and secret evidence gates.

## Review

Two read-only reviewers inspected the intended SITL sidecar contract and
evidence-security design.

Findings fixed in this slice:

- plan-level MavlinkAnywhere version/capability policy was missing;
- installed dashboard version/ref evidence was missing;
- sidecar failures were collapsed into generic probe failures;
- auth failure needed classification precedence;
- diagnostics/config/profile-summary probes needed to participate in the core
  evidence decision;
- secret scanning needed high-confidence detectors, placeholder/path
  suppressions, binary skips, and no raw secret echo in reports.

## Validation

Passed:

```bash
.venv/bin/python -m py_compile \
  tools/run_sitl_validation_suite.py \
  tests/test_sitl_validation_contract.py
```

```bash
PYTHONPATH=src .venv/bin/python tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run \
  --json
```

Result: dry-run summary exposed the MavlinkAnywhere policy and included
`versions/mavlink_anywhere_dashboard.json` plus `security/secret_scan.json`.

```bash
PYTHONPATH=src .venv/bin/python tools/run_sitl_validation_suite.py \
  --plan-name gazebo_visual_validation \
  --dry-run \
  --json
```

Result: dry-run summary exposed the MavlinkAnywhere policy and included
`versions/mavlink_anywhere_dashboard.json` plus `security/secret_scan.json`.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_sitl_validation_contract.py
```

Result: 69 passed.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 20 passed.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, API candidate inventory current, 217 passed with the
existing Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: passed.

## Not Performed

- No PX4, Gazebo, X-Plane, SITL runtime pass, HIL, or field validation.
- No Docker/PX4 container start.
- No MavlinkAnywhere install, update, restart, profile apply, or route
  mutation.
- No MAVLink2REST or PixEagle service start.
- No deployment or service installation.
- No QGC branch mutation or build.
- No runtime MCP endpoint, `tools/list`, `tools/call`, or callable tool
  exposure.
- No real-aircraft control.

## Remaining Work

- PXE-0068: continue setup/bootstrap cleanup with credential-generating
  `demo_lan_browser` only after external hashed users, exact Host/CORS,
  warning/evidence UX, and tests exist.
- PXE-0070: repair/rebase the QGC PR for authenticated remote HTTP/WebSocket
  media while preserving generic anonymous non-PixEagle sources.
- PXE-0064: complete operator credential/TLS hardening, remaining legacy alias
  retirement, and broader adversarial browser/session/media tests.
- PXE-0040: execute full visual Gazebo runtime proof only on a suitable
  operator-approved host and keep the result incomplete unless every artifact
  and content gate passes.

## Next Planned Slice

Continue with PXE-0068 setup/bootstrap cleanup follow-up or PXE-0070 QGC
authenticated remote HTTP/WebSocket media, depending on maintainer priority.
