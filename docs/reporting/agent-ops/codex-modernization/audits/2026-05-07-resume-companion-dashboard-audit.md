# Resume Companion And Dashboard Audit

Date: 2026-05-07  
Repository: `/home/alireza/PixEagle`  
Purpose: resume safely after pause, verify companion tool drift, close the
Phase 0 dashboard dependency/lint slice, and preserve next actions.

## Where We Resumed

The active modernization plan still points to the same target architecture:

- split vision, tracking, following, telemetry, flight control, API, streaming,
  config, and UI concerns;
- keep PX4 Offboard command publishing independent of camera/frame processing;
- move new public JSON APIs to typed `/api/v1/...` contracts;
- make MCP/AI-agent support come from the same typed API/state surface;
- use one source of truth for config, schemas, docs, tests, dashboard clients,
  and companion-service setup;
- remove legacy docs, configs, aliases, and duplicated behavior through tracked
  deprecation gates.

Completed Phase 0 work before this resume:

- clean-clone config fallback;
- current route inventory guard;
- schema drift guard;
- dashboard CI install/test/build guard;
- detector/estimator contract tests replacing placeholders;
- stale MavlinkAnywhere/MAVLink2REST docs cleanup;
- secondary infrastructure docs cleanup;
- pytest warning and boolean-return hygiene;
- stale gimbal-vector docs/config alias cleanup;
- Topotek SIP gimbal protocol clarification;
- PX4/SITL validation ladder scout and issue expansion.

The active resume target was PXE-0009/PXE-0010:

- dashboard npm audit debt;
- dashboard ESLint warnings.

## Companion Tool Status

### MavlinkAnywhere

Local repo: `/home/alireza/mavlink-anywhere`

Status after fetch:

- local `main` is aligned with `origin/main`;
- current commit is `fd80c48`;
- current tag is `v3.0.8`.

Impact on PixEagle:

- no new MavlinkAnywhere drift was found during this resume;
- existing PixEagle docs that were updated to `v3.0.8` routing remain aligned.

### MAVSDK Drone Show

Local repo: `/home/alireza/mavsdk_drone_show`

Status after fetch:

- local `main` is behind `origin/main` by 26 commits;
- remote `origin/main` is `3c42c7b2`;
- remote tag is `v5.3.56-connectivity-profile-altitude`.

Relevant remote changes since local HEAD:

- environment registry and control plane;
- fleet environment and presence workflows;
- runtime and Fleet Ops environment UX hardening;
- SITL dispatch/map fallback improvements;
- RTK MAVLink routing notes;
- network transport status and primary link display;
- USB modem/HiLink 4G classification;
- Smart Wi-Fi Manager workflow and UI updates;
- connectivity profile and altitude fallback clarification.

Remote `origin/main` default pins:

- `MDS_DEFAULT_SMART_WIFI_MANAGER_REF=v2.1.8`
- `MDS_DEFAULT_MAVLINK_ANYWHERE_REF=v3.0.8`
- Smart Wi-Fi dashboard default listen: `127.0.0.1:9080`
- MavlinkAnywhere dashboard default listen: `127.0.0.1:9070`

### Smart Wi-Fi Manager

Remote checked:

- `https://github.com/alireza787b/smart-wifi-manager.git`

Observed tags:

- latest visible tag: `v2.1.8`

Local clone:

- no local clone found at `/home/alireza/smart-wifi-manager`.

Design implications for PixEagle:

- PixEagle should treat connectivity management as an optional companion-node
  capability, not as a hidden dashboard detail.
- PixEagle API/MCP planning should adopt the same pattern as MDS: fleet or
  deployment defaults, node-local overrides, safe secret boundaries, status
  resources, and explicit operator actions.
- Smart Wi-Fi dashboard exposure must be explicit; public defaults should stay
  loopback-only unless a trusted network, VPN, or operator-approved field mode
  requires broader binding.
- PixEagle docs should never suggest storing real customer SSIDs/passwords in a
  public repository.

This drift is now tracked as PXE-0022.

## Dashboard Findings

### Before Cleanup

The dashboard had three distinct problems:

- direct ESLint produced unused-import and unused-variable warnings that were
  not covered by an explicit CI lint step;
- direct/runtime dependency audit included vulnerable packages;
- the app remained on Create React App/react-scripts, which is deprecated and
  carries dev-toolchain audit debt.

### Cleanup Completed

Code cleanup:

- removed unused imports/locals from dashboard components;
- replaced an anonymous default export in `valueComparison`;
- added React Router future flags;
- replaced the default CRA app test with a PixEagle dashboard shell test;
- mocked the backend status component in that shell test to avoid live backend
  requests.

Dependency cleanup:

- upgraded direct runtime dependencies with available safe replacements;
- removed unused `styled-components`;
- moved testing/build/serve tooling to `devDependencies`;
- pinned `react-scripts` exactly at `5.0.1` while deferred.

CI cleanup:

- added `npm run lint`;
- added the dashboard lint step to `.github/workflows/tests.yml`.

### Audit Outcome

Production/runtime dependency audit:

- `npm audit --omit=dev --json` reports zero vulnerabilities.

Full dependency audit:

- full `npm audit --json` reports 26 vulnerabilities:
  - 9 low;
  - 3 moderate;
  - 14 high;
  - 0 critical.

The only direct residual finding is `react-scripts`. npm proposes
`react-scripts@0.0.0` for forced remediation, which is not an acceptable fix.
The correct remediation is a planned migration to a supported dashboard
toolchain such as Vite plus Vitest/Testing Library. This is now PXE-0021.

## Current Issue State

Closed in this resume:

- PXE-0009: dashboard runtime dependency audit is clean; residual dev toolchain
  debt split to PXE-0021.
- PXE-0010: dashboard lint/build warnings are cleared and lint is now a CI
  gate.

Added in this resume:

- PXE-0021: replace CRA/react-scripts with a supported dashboard build/test
  stack.
- PXE-0022: reconcile PixEagle API/MCP/devops plans with newer MDS environment,
  fleet, connectivity, and Smart Wi-Fi standards.

Still open from earlier phases:

- PXE-0007: Offboard command heartbeat coupled to frame/follower path.
- PXE-0008: mixed unversioned API surface.
- PXE-0013: docs overstate independent Offboard/fail-closed behavior.
- PXE-0014: MAVLink polling timeout/retry/staleness config not typed.
- PXE-0016: gimbal provider abstraction.
- PXE-0018: executable PX4-in-loop validation ladder.
- PXE-0019: deterministic tracker-in-loop validation.
- PXE-0020: Windows/X-Plane SITL guidance decision.
- PXE-0021: dashboard toolchain migration.
- PXE-0022: companion environment/connectivity reconciliation.

## Recommended Continuation

Continue without restarting the plan:

1. Phase 1: implement PXE-0016 gimbal provider abstraction.
2. Phase 2: implement PXE-0007/PXE-0013 dedicated Offboard commander and
   safety supervisor contracts.
3. Phase 2/3: build the PXE-0018/PXE-0019 validation ladder so claims are
   backed by repeatable artifacts.
4. Phase 4: migrate APIs to `/api/v1` with typed schemas, structured errors,
   route inventory tests, idempotent command resources, and MCP-friendly state.
5. Phase 4/5: migrate dashboard toolchain and reconcile companion
   environment/connectivity standards.

No real-aircraft, HIL, or SITL success is claimed by this resume report.
