# Phase 4 Dashboard Operator UX Cleanup

Date: 2026-07-04  
Issue: PXE-0076  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice addressed the user-observed dashboard UX defects on the public quick
browser demo:

- public plain-HTTP WebRTC behavior was already clarified in PXE-0075: Auto
  mode intentionally uses WebSocket JPEG for non-local HTTP demos, while manual
  WebRTC remains available for reviewed localhost/HTTPS/TURN-capable paths.
- Settings mobile navigation no longer uses a floating menu button and now uses
  a normal inline `Sections` control plus bounded sidebar scrolling.
- Tracker and Follower data pages were rebuilt as operator telemetry pages
  instead of developer raw-data dumps.
- Missing numeric data now renders as `--`, not `0`.
- High-precision telemetry values now use shared operator formatting with
  compact precision, labels, units, timestamps, percentages, and vectors.
- Raw JSON payloads are now behind Diagnostics accordions with bounded history.
- Header/footer/layout/profile selector responsive faults were fixed after
  authenticated mobile Playwright checks exposed horizontal overflow.

## Files Changed

- `dashboard/src/pages/SettingsPage.js`
- `dashboard/src/pages/TrackerPage.js`
- `dashboard/src/pages/FollowerPage.js`
- `dashboard/src/components/Layout.js`
- `dashboard/src/components/Header.js`
- `dashboard/src/components/Footer.js`
- `dashboard/src/components/AuthStatusMenu.js`
- `dashboard/src/components/BackendStatusIndicator.js`
- `dashboard/src/components/ThemeToggle.js`
- `dashboard/src/components/FollowerProfileSelector.js`
- `dashboard/src/components/DynamicFieldDisplay.js`
- `dashboard/src/components/TrackerDataDisplay.js`
- `dashboard/src/components/ScopePlot.js`
- `dashboard/src/components/StaticPlot.js`
- `dashboard/src/components/RawDataLog.js`
- `dashboard/src/utils/operatorFormat.js`
- `dashboard/src/utils/operatorFormat.test.js`
- `dashboard/src/components/TrackerDataDisplay.test.js`

Evidence artifacts:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-dashboard-operator-ux/responsive-results.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-dashboard-operator-ux/mobile-settings.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-dashboard-operator-ux/mobile-tracker.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-dashboard-operator-ux/mobile-follower.png`
- matching tablet and desktop screenshots in the same folder

## Validation

Passed:

- `git diff --check`
- `bash scripts/check_schema.sh`
  - schema is up-to-date
- `PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py`
  - 50 tests passed
- `PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py`
  - 23 tests passed
- `CI=true npm test -- --watchAll=false src/utils/operatorFormat.test.js src/components/TrackerDataDisplay.test.js src/pages/FollowerPage.test.js src/components/VideoStream.test.js`
  - 4 suites passed
  - 20 tests passed
- `npm run build`
  - final production build compiled successfully
  - final bundle observed as `main.2f7202b0.js`
- `bash scripts/run.sh --no-attach --rebuild -m -k`
  - restarted minimal public browser demo
  - MAVLink2REST and MAVSDK Server intentionally skipped
- Authenticated Playwright/Chrome public-demo responsive check against
  `http://204.168.181.45:3040`
  - routes: `/settings`, `/tracker`, `/follower`
  - viewports: `390x844`, `768x1024`, `1366x768`
  - 9 route/viewport cases checked
  - 0 horizontal overflow failures
  - 0 sign-in-screen false positives

## Claim Boundary

This slice proves only the dashboard/browser-demo UX behavior listed above.
It does not prove PX4, SITL, HIL, MAVSDK, MAVLink2REST runtime routing, QGC
playback, field operation, or real-aircraft behavior.

The public demo is still the temporary HTTP/IP bench path. It is appropriate
for quick browser review only. It sends credentials over HTTP and remains
outside production remote-access policy.

## Risks And Open Questions

- The dashboard still uses Create React App/react-scripts; PXE-0021 remains
  open for supported frontend toolchain migration.
- The pages were validated against current no-target demo telemetry. A later
  tracker/follower-in-loop validation should capture screenshots with active
  target, follower setpoint, target-loss, and stale-data states.
- Public HTTP Auto streaming correctly selects WebSocket JPEG by policy. Full
  WebRTC over remote networks still needs reviewed HTTPS/ICE/TURN deployment
  support and richer media-health reporting.
- The public demo credential was intentionally kept stable for the current user
  test session. It still needs stop/cleanup/rotation after the user confirms
  testing is complete.

## Next Planned Slice

Recommended next order:

1. Record user browser retest result for the public demo and stop/cleanup or
   rotate the temporary HTTP credential when the user is done.
2. Continue PXE-0074 senior-dev setup/update walkthrough and final clean
   temp-directory handoff evidence.
3. Continue PXE-0064/PXE-0068 production remote HTTPS/WSS target evidence when
   a target domain/proxy/firewall plan is selected.
4. Continue PXE-0008 API cleanup on the next selected legacy family or broader
   typed tracker configuration mutation design.
5. Keep PXE-0021 dashboard toolchain migration as a separate planned slice.
