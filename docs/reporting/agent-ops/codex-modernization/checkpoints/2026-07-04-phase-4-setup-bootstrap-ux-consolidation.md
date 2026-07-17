# Phase 4 Checkpoint: Setup Bootstrap UX Consolidation

Date: 2026-07-04

Slice: PXE-0078

## Summary

Closed the setup/bootstrap UX cleanup found during the WebRTC, quick-demo, and
logging planning review. The Python dependency surface is now role-based, the
quick browser demo wrapper explains its side effects before applying anything,
and dry-run mode no longer writes or chmods filesystem paths.

## Files Changed

- `requirements.txt`
- `requirements-core.txt`
- `requirements-ai.txt`
- `requirements-dev.txt`
- `scripts/init.sh`
- `scripts/setup/install-ai-deps.sh`
- `scripts/setup/quick-browser-demo.sh`
- `README.md`
- `docs/INSTALLATION.md`
- `docs/setup/setup-profiles.md`
- `tests/test_setup_profiles.py`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Behavior

- `requirements-core.txt` is the Core runtime contract.
- `requirements-ai.txt` is the required AI/YOLO contract.
- `requirements-dev.txt` is optional contributor/CI tooling.
- `requirements.txt` remains an aggregate developer convenience, not the
  bootstrap source of truth.
- `scripts/init.sh` installs Core from `requirements-core.txt` directly and
  uses legacy grep filtering only as a fallback for damaged/partial checkouts.
- `scripts/setup/install-ai-deps.sh` installs required AI packages from
  `requirements-ai.txt`; `pnnx` remains best-effort for NCNN export.
- Optional dlib guidance now points to `scripts/setup/install-dlib.sh`.
- `make quick-browser-demo ... DRY_RUN=1` is no-touch: it does not create
  credential directories, write credential/config files, open firewall ports, or
  start services.
- The quick browser demo wrapper no longer chmods existing parent directories
  such as `/tmp` when custom credential paths are supplied.
- The wrapper prints mode, host scope, dashboard/API URLs, credential paths,
  skipped MAVSDK/MAVLink2REST sidecars, browser video transport expectation,
  and cleanup before applying the profile.
- Docs now state that public HTTP/IP demos intentionally use dashboard
  Auto/WebSocket rather than WebRTC until HTTPS/WSS plus a reviewed ICE/TURN
  path is available.

## Validation

Passed:

```bash
bash -n scripts/setup/quick-browser-demo.sh scripts/init.sh scripts/setup/install-ai-deps.sh
git diff --check
PYTHONPATH=src .venv/bin/pytest \
  tests/test_setup_profiles.py::test_make_quick_browser_demo_wrapper_supports_dry_run_handoff \
  tests/test_setup_profiles.py::test_manual_setup_docs_preserve_core_ai_split_and_dashboard_env_conversion \
  tests/test_setup_profiles.py::test_python_requirements_are_role_based_and_stale_paths_removed \
  -q
PYTHONPATH=src .venv/bin/pytest \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py \
  -q
PYTHONPATH=src .venv/bin/pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -q
bash scripts/check_schema.sh
```

Result: 160 setup/docs tests passed in the wider run; 50 minimum backend tests
passed; schema check reported `Schema is up-to-date`.

## Evidence

- The focused dry-run regression uses explicit `/tmp/...` credential paths and
  verifies no files are created.
- The docs consistency run passed after the requirement role-file and quick-demo
  documentation changes.
- No PX4/SITL/HIL, QGC receiver, production deployment, or real-aircraft
  behavior was run or claimed in this slice.

## Risks And Open Questions

- `install.sh` versus `make sync` behavior is documented enough for this slice,
  but the final PXE-0074 clean walkthrough still needs to exercise beginner and
  senior-dev update paths from a clean temporary checkout.
- The public demo is still a temporary HTTP/IP lab path. It must be stopped and
  credentials/firewall exposure cleaned up after user testing.
- Unified runtime logs are still missing; PXE-0079 is the next implementation
  slice.

## Next Slice

PXE-0079 unified runtime logging and evidence:

- runtime log sessions and manifests;
- component JSONL logs with retention/redaction;
- launcher capture for backend/dashboard/sidecars;
- typed `/api/v1/logs/*` read/export/stream contracts;
- dashboard Logs page and frontend error reporting;
- exportable demo evidence bundle;
- security audit remains separate from runtime logs.
