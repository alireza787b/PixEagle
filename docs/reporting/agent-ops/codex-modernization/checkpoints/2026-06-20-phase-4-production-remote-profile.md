# 2026-06-20 Phase 4 Production Remote Profile

## Phase / Slice

- Phase 4 API/security and bootstrap modernization
- Issues: PXE-0064 and PXE-0068
- Scope: guarded PixEagle-side production remote-browser profile, exact
  reverse-proxy authority policy, credential transaction safety, dashboard
  subpath support, and operator runbook.

## Summary

- Implemented the guarded `production_remote` setup profile:
  - backend remains on `127.0.0.1`;
  - exact HTTPS CORS origin;
  - exact public Host authority, including `:443` or a configured custom port;
  - `browser_session`, Secure cookie, and security audit enabled;
  - external PBKDF2-SHA256 user file;
  - generated one-time credential handoff without plaintext in normal
    non-interactive stdout.
- Made profile output transactional:
  - config, hashed users, and handoff use atomic sibling-file replacement;
  - output collisions, symlink aliases, and hardlink aliases are rejected;
  - credential artifacts roll back if config commit fails;
  - rollback failures are reported rather than hidden;
  - rotation backs up config and hashed users but does not archive plaintext
    handoff files.
- Hardened public host/origin validation for wildcard, loopback, unspecified,
  multicast, link-local, documentation, benchmarking, reserved/Class E,
  malformed URL, credential, path, query, fragment, port, and IPv6-zone cases.
- Kept Linux and Windows launchers from auto-exposing the dashboard when the
  browser-session backend remains loopback behind a proxy.
- Production credential generation fails closed on Windows until owner-only ACL
  automation has evidence; dry-run remains available.
- Added the maintained nginx/TLS/firewall/evidence/rollback runbook.
- Made the dashboard production build use relative assets and replaced two
  root-absolute navigation escapes with basename-aware router links, so the
  documented `/pixeagle` path is internally consistent.

## Files Changed

- Runtime/setup:
  - `scripts/setup/apply-setup-profile.py`
  - `src/classes/api_exposure_policy.py`
  - `scripts/run.sh`
  - `scripts/run.bat`
  - `Makefile`
- Dashboard:
  - `dashboard/package.json`
  - `dashboard/src/components/FollowerStatusCard.js`
  - `dashboard/src/components/SafetyConfigCard.js`
- Config/schema/provenance:
  - `configs/config_default.yaml`
  - `configs/config_schema.yaml`
  - `scripts/generate_schema.py`
  - `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- Tests:
  - `tests/test_setup_profiles.py`
  - `tests/unit/core_app/test_api_exposure_policy.py`
  - `tests/test_docs_infrastructure_consistency.py`
- Active docs/reporting:
  - `README.md`
  - `docs/README.md`
  - `docs/CONFIGURATION.md`
  - `docs/INSTALLATION.md`
  - `docs/TROUBLESHOOTING.md`
  - `docs/WINDOWS_SETUP.md`
  - `docs/setup/setup-profiles.md`
  - `docs/setup/production-remote-reverse-proxy.md`
  - `docs/apis/api-exposure-boundary.md`
  - `docs/apis/api-security-policy.md`
  - `docs/apis/api-modernization-blueprint.md`
  - `docs/video/04-streaming/remote-media-security.md`
  - `docs/video/04-streaming/websocket.md`
  - `docs/video/04-streaming/webrtc.md`
  - `docs/drone-interface/04-infrastructure/port-configuration.md`
  - issue register, phase map, and June journal.

## Validation

- Focused setup/exposure/docs gate:
  - `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py tests/unit/core_app/test_api_exposure_policy.py tests/test_docs_infrastructure_consistency.py -q`
  - Result: 213 passed with the existing Starlette/httpx warning.
- Dashboard:
  - `CI=true npm test -- --watchAll=false`
  - Result: 96 passed.
  - `npm run build`
  - Result: compiled successfully; CRA reports hosting at `./`.
  - Built `index.html` and asset manifest use `./static/...`, `./favicon.ico`,
    and `./manifest.json`.
- Schema and generated contract:
  - `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - Result: current, 41 sections and 549 parameters.
  - `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: current.
- Static checks:
  - Python compile for touched Python modules/tests: passed.
  - `bash -n scripts/run.sh`: passed.
  - `git diff --check`: passed with the existing `scripts/run.bat` line-ending
    warning.
- Phase gate:
  - `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`
  - Result: schema and candidate inventory current; 335 passed with the existing
    Starlette/httpx warning.

## Independent Review

- Security/runtime reviewer initially found:
  - credential/config path collision and partial-write corruption;
  - arbitrary non-loopback Host ports;
  - stdout password/logging and Windows file-mode weaknesses;
  - plaintext handoff backups during rotation.
- Docs/product reviewer initially found:
  - unwritable `/etc` examples and missing transactional behavior;
  - raw `3040` firewall contradictions;
  - no actionable proxy/evidence runbook;
  - stale credential-rotation wording;
  - root-relative CRA assets and two navigation paths escaping `/pixeagle`.
- All findings were fixed. Both final reviewer passes reported no remaining
  security/runtime or docs/product findings. The checkpoint records only
  test/build evidence, not deployment success.

## Evidence Boundary

- This slice proves static policy, unit/integration contracts, setup CLI failure
  behavior, dashboard tests, and dashboard production build shape.
- It does not prove an installed nginx/Caddy deployment, certificate trust,
  firewall enforcement, service-user ownership on a target host, browser E2E
  login/media behavior through TLS, Windows ACL behavior, QGC integration,
  Docker/PX4/SITL/HIL, field operation, or real-aircraft behavior.
- `production_remote` output is guarded configuration, not production approval.

## Risks / Open Questions

- Actual reverse-proxy and browser E2E evidence remains required on a reviewed
  deployment host.
- Windows production credential generation remains intentionally blocked until
  ACL handling is implemented and tested on Windows.
- Credential rollback is best-effort across filesystems and reports incomplete
  rollback; the supported configuration keeps outputs on normal local
  filesystems.

## Next Planned Slice

- Continue PXE-0064 with a repeatable local HTTPS reverse-proxy/browser E2E
  evidence harness where feasible, without claiming target deployment success.
- Continue PXE-0070 by rebasing and testing QGroundControl PR #13594 with generic
  Authorization/Origin/TLS support and PixEagle `media:read` compatibility.
- Continue PXE-0008/PXE-0021 typed API and dashboard toolchain modernization
  after the production-browser evidence boundary is stable.
