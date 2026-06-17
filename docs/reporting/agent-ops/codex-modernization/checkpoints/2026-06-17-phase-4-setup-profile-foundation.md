# Phase 4 Setup Profile Foundation

Date: 2026-06-17  
Slice: PXE-0068 foundation  
Status: completed foundation; PXE-0068 remains in progress  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice implemented the first PXE-0068 setup/bootstrap foundation after the
QGC source-profile and demo-policy decisions:

- keep clean clones running from `configs/config_default.yaml`;
- stop init/install from creating `configs/config.yaml` by default;
- provide an explicit setup-profile tool and Make targets;
- make beginner QGroundControl video easy through GStreamer H.264/RTP/UDP while
  keeping PixEagle backend loopback-only;
- keep full remote browser and remote QGC HTTP/WebSocket profiles fail-closed
  until credential/TLS/evidence gates are implemented;
- move Linux service onboarding behind an explicit deployment opt-in;
- remove stale setup, troubleshooting, and port-label guidance.

## Decisions

- `configs/config_default.yaml` remains the checked-in runtime source of truth.
  `configs/config.yaml` is optional and created only by an explicit profile,
  manual override, or reset command.
- `field_qgc_video` is the beginner companion-to-GCS path. It enables only
  GStreamer UDP/RTP output and preserves:
  - `Streaming.API_EXPOSURE_MODE: local_only`;
  - `Streaming.HTTP_STREAM_HOST: 127.0.0.1`;
  - `Streaming.API_AUTH_MODE: local_compat`;
  - empty `Streaming.API_ALLOWED_HOSTS`.
- QGC H.264/RTP/UDP defaults are now aligned on port `5600` across default
  config, generated schema, setup profile, docs, and runtime fallback hints.
- `demo_lan_browser`, `production_remote`, and
  `unsafe_demo_lan_media_only` are defined in the profile contract but refuse to
  write config until their security/evidence requirements are implemented.
- Normal `make init` skips service setup. Deployment prompts require
  `PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init`, or operators can run
  `sudo bash scripts/service/install.sh` directly.
- Port `5551` is now labeled as the legacy telemetry WebSocket. Backend media
  WebSocket routes remain on backend port `5077`.

## Files Changed

- `scripts/setup/apply-setup-profile.py`
- `docs/setup/setup-profiles.md`
- `tests/test_setup_profiles.py`
- `Makefile`
- `configs/config_default.yaml`
- `configs/config_schema.yaml`
- `src/classes/fastapi_handler.py`
- `scripts/init.sh`
- `scripts/init.bat`
- `scripts/lib/ports.bat`
- `scripts/run.sh`
- `scripts/service/utils.sh`
- `scripts/setup/build-opencv.sh`
- `scripts/setup/install-dlib.sh`
- `scripts/setup/setup-pytorch.sh`
- `install.sh`
- `install.ps1`
- `README.md`
- `docs/README.md`
- `docs/INSTALLATION.md`
- `docs/CONFIGURATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/TROUBLESHOOTING.md`
- `docs/SERVICE_MANAGEMENT.md`
- `docs/KNOWN_ISSUES.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/drone-interface/04-infrastructure/companion-computer.md`
- `docs/drone-interface/07-troubleshooting/connection-issues.md`
- `docs/video/04-streaming/qgc-http-websocket-source-plan.md`
- `docs/video/04-streaming/remote-media-security.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `tests/test_docs_infrastructure_consistency.py`

## Review

Independent read-only reviewers checked the slice from two angles:

- setup/bootstrap reviewer: found service setup was still wired into first-run
  init, companion docs still normalized backend exposure checks, Windows port
  discovery lacked `config_default.yaml` fallback, and `5551` labels were still
  ambiguous;
- QGC/security reviewer: found the QGC `2000` versus `5600` split, confirmed
  `field_qgc_video` is the correct beginner path, and recommended fail-closed
  tests for deferred remote profiles.

All actionable findings above were addressed in this slice. Remaining larger
work is recorded below rather than hidden.

## Validation

Passed:

```bash
.venv/bin/python -m py_compile \
  scripts/setup/apply-setup-profile.py \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py
```

```bash
.venv/bin/python -m pytest \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/unit/core_app/test_config_clean_clone.py \
  -ra --tb=short --strict-config
```

Result: 34 passed.

```bash
bash -n \
  scripts/init.sh scripts/run.sh \
  scripts/setup/build-opencv.sh scripts/setup/install-dlib.sh \
  scripts/setup/setup-pytorch.sh scripts/service/utils.sh
```

Result: passed.

```bash
PYTHON=.venv/bin/python bash scripts/check_schema.sh
```

Result: schema current; 41 sections, 549 parameters.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
```

Result: candidate inventory regenerated for changed provenance.

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -ra --tb=short --strict-config
```

Result: 36 passed.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, candidate inventory current, 211 passed with the
existing Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: passed. Git reported expected CRLF normalization warnings for edited
Windows batch/PowerShell files, with exit code 0.

## Not Performed

- No service install/start/enable.
- No sidecar mutation/update.
- No QGC branch mutation or build.
- No PX4/SITL/HIL/field run.
- No deployment.
- No runtime MCP endpoint or callable tool exposure.
- No real-aircraft control.

## Remaining PXE-0068 Work

- Reconcile binary download pin, override, checksum, and provenance policy for
  MAVSDK Server and MAVLink2REST download scripts.
- Decide whether to automate `demo_lan_browser` credential generation in a
  later slice; it must generate external hashed users, exact Host/CORS, and
  lab-only warnings before it can write config.
- Keep `production_remote` deferred until TLS/operator hardening, credential
  rollout, adversarial auth/media tests, and evidence gates are ready.
- Add a dedicated backend media WebSocket health probe so service status can
  report telemetry socket health and media WebSocket health separately.
- Continue setup/update cleanup for any remaining binary/service/download docs
  found during the binary-policy slice.
