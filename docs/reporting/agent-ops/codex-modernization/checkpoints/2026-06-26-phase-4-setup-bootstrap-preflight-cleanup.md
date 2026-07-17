# 2026-06-26 Phase 4 Setup Bootstrap Preflight Cleanup

## Phase / Slice

- Phase 4 setup, bootstrap, and handoff readiness
- Issue: PXE-0068 partial; PXE-0074 preparation
- Scope: fix the first local setup/bootstrap issues found by the 2026-06-25
  clean-walkthrough preflight without performing install, service, deployment,
  SITL/HIL, field, or real-aircraft actions.

## Summary

- Removed macOS from the guided one-command install path because the maintained
  bootstrap still uses Debian/Ubuntu apt packages.
- Added explicit macOS fail-fast behavior in `install.sh` so users see the
  support boundary before `scripts/init.sh` reaches apt-only package logic.
- Aligned the Makefile with the environment created by `scripts/init.sh`:
  Make now prefers `.venv/bin/python`, then `venv/bin/python`, then system
  `python3`.
- Added `make` to the Linux init package set and public manual prerequisites,
  because the next documented beginner command is `make init`.
- Rewrote the manual Python dependency path to preserve the same core-first
  split used by init instead of installing AI-heavy packages from the full
  `requirements.txt` immediately.
- Replaced the manual dashboard `.env` copy instruction with the same
  YAML-to-dotenv conversion semantics used by init.
- Hardened `scripts/run.sh` startup cleanup:
  - existing PixEagle tmux sessions are still stopped;
  - only PixEagle-owned listener PIDs on required ports are terminated;
  - non-PixEagle port occupants now block startup with a clear error instead of
    being killed;
  - readiness checks use `nc` when available and fall back to a Python socket
    probe, so netcat is no longer a hidden prerequisite.
- Added static regression tests for the Python environment fallback, foreign
  port-owner guard, macOS guided-bootstrap boundary, core/AI manual dependency
  split, and dashboard dotenv conversion.

## Files Changed

- `Makefile`
- `README.md`
- `docs/INSTALLATION.md`
- `install.sh`
- `scripts/init.sh`
- `scripts/run.sh`
- `tests/test_setup_profiles.py`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-25-setup-bootstrap-clean-walkthrough-preflight.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-26-phase-4-setup-bootstrap-preflight-cleanup.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

Run before this checkpoint was finalized:

- `bash -n scripts/run.sh scripts/init.sh install.sh`
- `git diff --check`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py tests/test_docs_infrastructure_consistency.py`
  - 150 passed
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py::test_makefile_uses_bootstrap_created_venv_before_system_python tests/test_setup_profiles.py::test_run_script_blocks_foreign_port_owners_and_has_no_netcat_dependency tests/test_setup_profiles.py::test_guided_install_docs_do_not_advertise_macos_bootstrap tests/test_setup_profiles.py::test_manual_setup_docs_preserve_core_ai_split_and_dashboard_env_conversion`
  - 4 passed
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current
  - API/MCP candidate inventory current
  - 376 passed with the existing Starlette/httpx warning

## Evidence Boundary

- This slice proves static contracts, shell syntax, and focused pytest coverage
  only.
- It does not claim a clean temporary checkout walkthrough, successful install
  on a fresh host, dashboard runtime, binary download, service installation,
  target proxy/firewall/TLS deployment, QGC playback, PX4/SITL/HIL, field, or
  real-aircraft behavior.
- PXE-0074 still requires a full clean temp-directory walkthrough using only
  public docs before any tag/release/handoff.

## Remaining Setup/Handoff Gates

1. Make init summaries distinguish ready, skipped, degraded, and manual-follow-up
   states for dashboard dependencies and binary downloads.
2. Run the PXE-0074 clean temp-directory walkthrough for beginner demo and
   senior-dev override paths after the planned slices are otherwise complete.
3. Capture exact commands, generated files, ports, credential handoff behavior,
   validation output, and environment assumptions.
4. Remove or rewrite any stale/noisy/confusing setup docs discovered by that
   walkthrough before tag/release/handoff.
