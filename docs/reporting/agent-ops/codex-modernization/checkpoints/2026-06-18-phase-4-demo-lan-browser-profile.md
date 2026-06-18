# 2026-06-18 Phase 4 Demo LAN Browser Profile

## Slice

- Phase: 4 API/setup/runtime modernization
- Issue: PXE-0068
- Scope: automate the `demo_lan_browser` setup profile without creating an
  anonymous remote backend/control surface.

## Summary

This slice promotes `demo_lan_browser` from a documented-but-deferred profile to
a supported lab-LAN profile. The profile is intentionally for isolated
operator-approved LAN demos over HTTP. It does not claim production remote
operator readiness.

Implemented behavior:

- `scripts/setup/apply-setup-profile.py` now applies `demo_lan_browser`;
- requires `--lan-host` for the PixEagle companion address/hostname used by
  browser clients;
- rejects wildcard, loopback, URL, credential-bearing, public-IP, and public-DNS
  host values;
- allows private/link-local IPs and local-scope hostnames only: single-label,
  `.local`, or `.lan`;
- sets backend exposure to `trusted_lan_legacy` with exact
  `API_ALLOWED_HOSTS` and exact `API_CORS_ALLOWED_ORIGINS`;
- sets `API_AUTH_MODE: browser_session`;
- writes an external PBKDF2-SHA256 hashed user file under a gitignored
  `configs/secrets/` default path;
- generates a random demo password, prints it once, and never writes plaintext;
- sets the generated credential file mode to `0600`;
- refuses to overwrite an existing credential file unless
  `--rotate-demo-credentials` is explicit;
- keeps `production_remote` and `unsafe_demo_lan_media_only` fail-closed;
- teaches `make run` to bind the static dashboard on LAN only when the config is
  both `trusted_lan_legacy` and `browser_session`.

## Files Changed

- `.gitignore`
- `Makefile`
- `README.md`
- `docs/setup/setup-profiles.md`
- `docs/video/04-streaming/remote-media-security.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `scripts/run.sh`
- `scripts/setup/apply-setup-profile.py`
- `tests/test_docs_infrastructure_consistency.py`
- `tests/test_setup_profiles.py`

## Security Boundary

The checked-in default remains local-only and no-password same-host compatible.
The new LAN browser profile is not anonymous:

- remote browser clients must log in through browser-session auth;
- browser mutations still require CSRF;
- backend Host and Origin checks remain exact;
- credentials live outside checked-in config;
- generated credential files are gitignored;
- production HTTPS/TLS, durable credential management, adversarial browser
  tests, and deployment evidence remain outside this lab profile.

The QGC field-video recommendation remains unchanged: use GStreamer
H.264/RTP/UDP for simple remote QGC video. Direct remote PixEagle HTTP/WS media
for QGC remains PXE-0070 and still needs generic QGC Authorization/Origin/TLS
support.

## Independent Review

Two independent read-only reviewers inspected the slice.

Findings fixed before this checkpoint:

- public DNS hostnames were initially allowed while public IP literals were
  rejected; hostname validation now limits the lab profile to local-scope names;
- a generated credential file could be written before a later config write
  failure showed the password; config writes now happen before credential
  generation, and invalid username input is preflighted before writing config;
- tests now assert generated credential mode `0600`;
- tests now cover public IP and public DNS rejection;
- tests now cover the `make demo-lan-browser-profile` wrapper;
- tests now cover the `make run` dashboard LAN-bind handoff;
- README now tells beginners to restart/run `make run` and open
  `http://<LAN_HOST>:3040`;
- the checkpoint file referenced from the issue register now exists.

Residual reviewer notes:

- The launcher handoff test is text-level, not a live tmux/service start. That
  is intentional for this slice because service startup/deployment actions are
  operator-gated.
- If writing the credential file fails after config is written, browser-session
  startup fails closed because the user file is missing. No plaintext password
  is written in that path.

## Validation

Passed:

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py`
  - 27 passed
- `PYTHONPATH=src .venv/bin/python -m py_compile scripts/setup/apply-setup-profile.py`
- `bash -n scripts/run.sh scripts/components/dashboard.sh`
- `git diff --check`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py::test_setup_profiles_are_documented_and_linked_from_onboarding_docs tests/test_docs_infrastructure_consistency.py::test_qgc_http_ws_source_plan_preserves_generic_and_pixeagle_boundaries`
  - 2 passed
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema current: 41 sections, 549 parameters
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py`
  - 36 passed
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current
  - API tool candidate inventory current
  - 233 passed
  - existing Starlette/httpx `TestClient` deprecation warning remains

Notes:

- Plain `bash scripts/check_schema.sh` still depends on the host `python3`; on
  this machine that interpreter lacks `ruamel.yaml`. The repo venv-backed gate
  passed with `PYTHON=.venv/bin/python`.
- No service install/start, deployment, sidecar mutation, Docker/PX4/SITL/HIL,
  QGC branch mutation/build, or real-aircraft control was performed.

## Risks And Open Questions

- `production_remote` remains gated on TLS/operator hardening, durable
  credentials, adversarial auth/media tests, and deployment evidence.
- Backend media WebSocket health reporting remains a PXE-0068 follow-up.
- A live browser-session smoke test on an actual Pi/GCS LAN should be part of
  operator acceptance, with logs and exact network topology recorded before any
  field claim.

## Next Planned Slice

Continue Phase 4 cleanup with the next PXE-0068 follow-up:

1. Add backend media WebSocket health/probe reporting without weakening auth.
2. Keep production remote profile defined-but-not-automated until TLS,
   credential rollout, and adversarial browser/media evidence exist.
3. Continue scanning setup/update/service docs for stale contradictions during
   later slices.
