# Phase 0 Checkpoint - Dashboard Debt And Resume

Date: 2026-05-07  
Slice: Phase 0 dashboard dependency/lint debt after pause  
Primary issues: PXE-0009, PXE-0010  
New follow-up issues: PXE-0021, PXE-0022

## Resume Reconciliation

Before changing files, the current plan and issue state were reconciled against:

- `docs/reporting/agent-ops/codex-modernization/audits/2026-04-29-proposed-improvement-plan.md`
- `docs/architecture/pixeagle-modernization-blueprint.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- current `git status -sb`

The resume point was Phase 0 dashboard debt. Earlier Phase 0 slices remain part
of the active worktree and were not reverted.

## Companion Tool Check

- `/home/alireza/mavlink-anywhere` fetched cleanly and remains aligned with
  `origin/main` at `fd80c48`, tag `v3.0.8`.
- `/home/alireza/mavsdk_drone_show` fetched cleanly but local `main` is behind
  `origin/main` by 26 commits. Remote `origin/main` is
  `3c42c7b2`, tag `v5.3.56-connectivity-profile-altitude`.
- `git ls-remote` for `alireza787b/smart-wifi-manager` shows latest visible tag
  `v2.1.8`.
- No local Smart Wi-Fi Manager clone was found at
  `/home/alireza/smart-wifi-manager`.

Important drift from `mavsdk_drone_show` remote `origin/main`:

- Fleet/runtime environment registry and node-local override conventions have
  advanced.
- Smart Wi-Fi Manager is treated as an optional node-local sidecar with backend
  values `none` or `smart-wifi-manager`.
- Current fleet default pins Smart Wi-Fi Manager to `v2.1.8` and
  MavlinkAnywhere to `v3.0.8`.
- Connectivity docs distinguish Wi-Fi, Ethernet, USB modem/HiLink 4G,
  cellular/GSM, VPN/NetBird, primary link display, and NetworkManager route
  metric policy.
- Fleet Ops is the primary operator surface for connectivity posture; direct
  Smart Wi-Fi dashboard access is secondary and should use a known-good
  management path before changing profiles.
- Public repos must not store real Wi-Fi SSIDs/passwords.

Decision: no PixEagle runtime code was changed for this drift in this slice.
PXE-0022 tracks reconciliation before the API/MCP/devops phases.

## Files Changed

Dashboard:

- `dashboard/package.json`
- `dashboard/package-lock.json`
- `dashboard/src/App.js`
- `dashboard/src/App.test.js`
- `dashboard/src/components/FollowerStatusCard.js`
- `dashboard/src/components/Header.js`
- `dashboard/src/components/ScopePlot.js`
- `dashboard/src/components/TrackerSelector.js`
- `dashboard/src/components/config/ArrayEditor.js`
- `dashboard/src/components/config/BackupHistoryDialog.js`
- `dashboard/src/components/config/ExportDialog.js`
- `dashboard/src/components/config/ImportDialog.js`
- `dashboard/src/components/config/MobileBottomBar.js`
- `dashboard/src/components/config/ObjectEditor.js`
- `dashboard/src/utils/valueComparison.js`

CI/reporting:

- `.github/workflows/tests.yml`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-05.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-05-07-phase-0-dashboard-debt-resume.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-05-07-resume-companion-dashboard-audit.md`

## Work Completed

- Removed unused dashboard imports, variables, and anonymous default export
  warnings that were caught by direct ESLint.
- Added `npm run lint` as a first-class dashboard script.
- Added a dashboard lint step to GitHub Actions.
- Updated direct/runtime dependencies:
  - `axios` to `^1.15.2`
  - `react-router-dom` to `^6.30.3`
  - `socket.io-client` to `^4.8.3`
- Removed unused/vulnerable `styled-components`.
- Moved testing/build/serve tooling to `devDependencies`.
- Pinned `react-scripts` exactly at `5.0.1` while it remains a temporary
  legacy dev tool.
- Added Jest transform handling for axios.
- Replaced the CRA placeholder test with a PixEagle dashboard shell test.
- Mocked `BackendStatusIndicator` in the shell test so tests do not call a live
  backend on `localhost:5077`.
- Added React Router future flags to silence current v7 migration warnings.

## Validation

Dashboard validation:

- `npm ci` passed.
- `npm run lint -- --format unix` passed.
- `CI=true npm test -- --watchAll=false` passed: 1 test, no backend connection
  noise.
- `npm run build` passed and compiled successfully.
- `npm audit --omit=dev --json` reported zero vulnerabilities.
- full `npm audit --json` reported 26 vulnerabilities, all dev dependency
  scope, with the only direct finding rooted in `react-scripts`.

Repository validation:

- `make phase0-check PYTHON=/tmp/pixeagle-audit-venv/bin/python` passed:
  schema check plus 22 Phase 0 guardrail tests.
- `git diff --check` passed.

## Risk And Open Debt

- CRA/react-scripts remains deprecated and carries dev-only audit findings. It
  is not safe to use `npm audit fix --force` because npm proposes
  `react-scripts@0.0.0`. PXE-0021 tracks migration to a supported build/test
  stack.
- Companion repo drift is important for later PixEagle API/MCP/devops design
  but did not block this dashboard slice. PXE-0022 tracks it.
- No SITL, HIL, or real-aircraft validation was run in this slice.

## Next Slice

The next modernization slice should leave Phase 0 dashboard cleanup and move to
Phase 1 gimbal provider abstraction (PXE-0016), unless the maintainer chooses
to prioritize the Offboard commander/safety slice first. The current Topotek
SIP-over-UDP implementation should become one provider behind a typed gimbal
input contract, not the architecture itself.
