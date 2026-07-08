# Phase 5 Checkpoint: Dashboard Clean Handoff Walkthrough

Date: 2026-07-08
Slice: PXE-0074 partial
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice exercises the optional dashboard release-candidate lane in the
repeatable clean-checkout setup/update walkthrough.

The checkpoint proves that a temporary clean checkout of the current branch can
run the documented setup/update dry-run checks plus dashboard `npm ci`,
dashboard tests, and dashboard production build. It does not claim service
installation, firewall mutation, MAVSDK/MAVLink2REST binary download success,
PX4/SITL/HIL, QGC playback, field behavior, tracker/follower response, target
deployment readiness, or real-aircraft readiness.

## Evidence

Manifest:

```text
docs/reporting/agent-ops/codex-modernization/evidence/2026-07-08-pxe0074-dashboard-clean-handoff-walkthrough/manifest.json
```

Source commit under test:

```text
2027e779841d13b00dc564fa5849dc7586888812
```

The manifest reports:

- source worktree clean at start: `true`;
- source git status at start: empty;
- temporary checkout preserved: `false`;
- required files: pass;
- command count: 25;
- passed commands: 25;
- failed commands: none;
- temporary checkout `git_status_initial.git_worktree_clean`: `true`;
- temporary checkout `git_status_final.git_worktree_clean`: `true`.

## Commands Proved

The dashboard-inclusive run includes the prior default clean-handoff gates:

- `make help`;
- shell syntax checks for setup/launch/demo/sync scripts;
- pinned MAVSDK/MAVLink2REST binary download plan with `--dry-run`;
- setup-profile dry-runs for local, QGC field video, browser demo, QGC direct
  media, and production remote;
- quick browser demo dry-run and cleanup dry-run;
- clean-worktree fast-forward sync check;
- `bash scripts/check_schema.sh`;
- minimum backend/API tests.

It additionally proves the dashboard lane from the temporary checkout:

```bash
npm ci --no-audit --fund=false
npm test -- --runInBand --watchAll=false
npm run build
```

Dashboard evidence summary:

- `npm ci`: passed, added 1607 packages in 27 seconds;
- dashboard tests: 28 suites passed, 161 tests passed;
- dashboard build: compiled successfully with `main.fe82c183.js`.

## Review Notes

- `--include-dashboard` intentionally runs `npm ci`, so it may fetch npm
  package artifacts from the configured npm registry.
- React Router v7 future-flag warnings appeared in test stderr. They are
  existing non-blocking frontend-toolchain warnings and remain relevant to the
  future CRA/toolchain modernization work.
- Node emitted an `fs.F_OK` deprecation warning during build. The build still
  completed successfully; this is toolchain warning evidence, not release
  failure.
- Evidence hygiene scan found only credential/token option names and inert local
  placeholder file paths in the manifest, not plaintext passwords or bearer
  tokens.
- Read-only DevOps/safety and operator-doc reviewer passes found no blocking
  findings. Their cleanup findings were folded into the resume map and report
  wording.

## Residual Risk

- This still is not production target evidence. Target deployment requires
  selected TLS/proxy/firewall/service-account configuration, credential handoff,
  adversarial browser/media tests, and operator acceptance.
- The active public HTTP demo credential was not rotated in this slice.
- QGC PR #13594 remains draft until authenticated generic/PixEagle media is
  tested end to end.

## Next Slice

Continue the remaining PXE-0074 planned gates:

1. public-demo cleanup/credential rotation after the active tester session;
2. production target evidence when a target host/proxy/firewall plan is
   selected;
3. final tag/release dry run on the exact release branch.

Related open work remains tracked separately: QGC authenticated media validation
under PXE-0070.
