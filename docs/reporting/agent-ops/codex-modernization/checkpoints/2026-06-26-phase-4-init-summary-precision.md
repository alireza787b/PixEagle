# 2026-06-26 Phase 4 Init Summary Precision

## Phase / Slice

- Phase 4 setup, bootstrap, and handoff readiness
- Issue: PXE-0068 partial; PXE-0074 preparation
- Scope: make init/bootstrap summaries truthful for partial setup outcomes
  without performing install, service, deployment, binary download, SITL/HIL,
  field, or real-aircraft actions.

## Summary

- `scripts/init.sh` now records explicit component state for:
  - Node.js setup;
  - dashboard dependencies;
  - configuration defaults;
  - dashboard `.env`;
  - MAVSDK Server binary;
  - MAVLink2REST binary.
- The final init screen is now a setup summary, not a blanket completion claim.
- Dashboard setup distinguishes:
  - `ready`: npm dependencies installed;
  - `skipped`: dashboard directory absent;
  - `degraded`: npm install failed or dashboard directory could not be entered;
  - `manual follow-up`: npm is unavailable.
- MAVSDK Server and MAVLink2REST setup distinguish:
  - `ready`: existing binary verified or binary downloaded and checksum
    verified;
  - `skipped`: operator deferred the download;
  - `degraded`: download/checksum verification failed or an existing binary
    failed manifest verification;
  - `manual follow-up`: downloader script missing.
- Dashboard `.env` generation now returns the actual YAML-to-dotenv conversion
  status so conversion failures appear as degraded setup instead of being hidden
  by virtualenv deactivation.
- `install.sh` now reports "Bootstrap Finished" and tells users to review
  degraded/manual-follow-up summary items before running services.
- README, installation docs, and setup-profile docs now document the setup
  summary state vocabulary.
- Static regressions guard the summary-state contract and wrapper wording.

## Files Changed

- `scripts/init.sh`
- `install.sh`
- `README.md`
- `docs/INSTALLATION.md`
- `docs/setup/setup-profiles.md`
- `tests/test_setup_profiles.py`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-25-setup-bootstrap-clean-walkthrough-preflight.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-26-phase-4-init-summary-precision.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

Run before this checkpoint was finalized:

- `bash -n scripts/init.sh install.sh`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py::test_manual_setup_docs_preserve_core_ai_split_and_dashboard_env_conversion tests/test_setup_profiles.py::test_init_summary_uses_explicit_component_states tests/test_setup_profiles.py::test_init_summary_tracks_dashboard_and_binary_followup_states tests/test_setup_profiles.py::test_one_line_installer_does_not_overstate_partial_init_success`
  - 4 passed
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py tests/test_docs_infrastructure_consistency.py`
  - 153 passed
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current
  - API/MCP candidate inventory current
  - 379 passed with the existing Starlette/httpx warning

## Evidence Boundary

- This slice proves shell syntax, static setup-summary contracts, and docs
  guardrails only.
- It does not claim a clean temporary checkout walkthrough, successful install
  on a fresh host, binary download/install, dashboard runtime, service
  installation, target proxy/firewall/TLS deployment, QGC playback, PX4/SITL/
  HIL, field, or real-aircraft behavior.
- PXE-0074 still requires a full clean temp-directory walkthrough using only
  public docs before any tag/release/handoff.

## Remaining Setup/Handoff Gates

1. Run the PXE-0074 clean temp-directory walkthrough for beginner demo and
   senior-dev override paths after the planned slices are otherwise complete.
2. Capture exact commands, generated files, ports, credential handoff behavior,
   validation output, and environment assumptions.
3. Capture target trusted TLS/reverse-proxy/firewall/service-account evidence,
   credential handoff evidence, target-host adversarial browser/session/media
   validation, and operator acceptance before production handoff.
4. Remove or rewrite any stale/noisy/confusing setup docs discovered by that
   walkthrough before tag/release/handoff.
