# 2026-06-19 Phase 4 LAN/Private-Overlay Browser Profile Hardening

## Phase / Slice

- Phase 4 API/setup/runtime modernization
- Issues: PXE-0068, PXE-0064, PXE-0072
- Scope: clarify TLS/LAN/private-overlay policy, harden
  `demo_lan_browser` host validation, align Windows launcher behavior, and keep
  beginner demos simple without weakening production remote gates.

## Summary

- Confirmed and documented the policy split:
  - TLS is not only for domain names; it is an application-layer trust boundary
    that can use DNS certificates, internal PKI, or another reviewed trust
    anchor.
  - HTTP over an isolated LAN or operator-approved private overlay/VPN is
    allowed only through the explicit `demo_lan_browser` lab profile.
  - Production remote browser access still requires TLS or an equivalent
    reviewed trust boundary, durable credentials, adversarial auth/media tests,
    audit/evidence, and operator deployment hardening.
- Hardened `demo_lan_browser` host validation:
  - allowed RFC1918 private LAN, shared private-overlay/CGNAT `100.64.0.0/10`,
    IPv4 link-local, IPv6 ULA, plain IPv6 link-local, bracketed IPv6, and
    local-scope hostnames;
  - rejected public, documentation, multicast, loopback, unspecified, wildcard,
    scheme/path/credential, query/fragment, port-bearing, malformed bracketed
    IPv6, and IPv6 zone-identifier inputs.
- Documented that the standalone browser demo needs two scoped ports:
  dashboard `3040` for static assets and authenticated backend/API media `5077`
  for API/media calls.
- Updated `scripts/run.bat` so Windows mirrors Linux `make run`: generated
  `trusted_lan_legacy` plus `browser_session` config automatically binds the
  dashboard on the lab LAN/private overlay.

## Files Changed

- `scripts/setup/apply-setup-profile.py`
- `scripts/run.bat`
- `tests/test_setup_profiles.py`
- `tests/test_docs_infrastructure_consistency.py`
- `README.md`
- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/WINDOWS_SETUP.md`
- `docs/apis/api-exposure-boundary.md`
- `docs/setup/setup-profiles.md`
- `docs/video/04-streaming/qgc-http-websocket-source-plan.md`
- `docs/video/04-streaming/remote-media-security.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Independent Review

- Security/setup reviewer findings fixed:
  - query/fragment suffixes were silently normalized to the bare host;
  - malformed bracketed IPv6 could raise raw `ValueError` instead of
    controlled `ProfileError`;
  - IPv6 zone identifiers created browser Host/CORS ambiguity;
  - address validation tests did not cover enough accepted/rejected ranges.
- Docs/reporting reviewer findings fixed:
  - dashboard-only firewall guidance would not work because the standalone
    dashboard calls backend/API media on `5077`;
  - Windows docs advertised `demo_lan_browser` before `scripts/run.bat` mirrored
    Linux dashboard LAN binding;
  - API docs said "Public LAN/private-overlay" instead of private
    LAN/private-overlay;
  - setup CLI output still said LAN-only rather than LAN/private-overlay.

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py -q`
  - Result: 58 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -q`
  - Result: 22 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py tests/test_docs_infrastructure_consistency.py tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q`
  - Result: 118 passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - Result: schema current, 41 sections, 549 parameters.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: candidate inventory current.
- `PYTHONPATH=src .venv/bin/python -m py_compile scripts/setup/apply-setup-profile.py tests/test_setup_profiles.py tests/test_docs_infrastructure_consistency.py`
  - Result: passed.
- `git diff --check`
  - Result: passed, with the existing Git line-ending warning for
    `scripts/run.bat`.
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`
  - Result: schema current, API tool candidate inventory current, 282 passed
    with the existing Starlette/httpx `TestClient` deprecation warning.

## Evidence Boundary

- This is setup-profile, launcher, docs, and unit/docs regression evidence only.
- No browser automation, service install/start, deployment, Docker/PX4/SITL/HIL,
  sidecar mutation, QGC branch mutation/build, runtime MCP endpoint, callable
  tool exposure, field test, or real-aircraft control was performed or claimed.
- No production remote-browser approval is claimed. `production_remote` remains
  gated.

## Risks / Open Questions

- Live LAN/private-overlay smoke should still be run by an operator on a real
  Pi/GCS or Windows host before any field/demo claim, with topology, commands,
  logs, and screenshots captured as evidence.
- Browser automation for login/session expiry and media playback remains a
  useful PXE-0064 follow-up.
- QGC authenticated remote HTTP/WebSocket media remains PXE-0070 and was not
  changed in this slice.

## Next Planned Slice

- Continue Phase 4 with either dashboard-side adversarial browser/session/media
  tests, production remote-profile credential/TLS hardening, or the next typed
  API/router extraction slice, depending on risk ordering.
