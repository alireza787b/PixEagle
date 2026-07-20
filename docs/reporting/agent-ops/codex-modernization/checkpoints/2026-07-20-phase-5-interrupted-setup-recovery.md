# Phase 5 Checkpoint: Interrupted Setup Recovery

**Date:** 2026-07-20
**Slice:** PXE-0113
**Status:** beta.12 published and public browser smoke passed; maintainer rerun pending

## Failure And Decision

The beta.11 real Ubuntu rerun fixed guided input and progressed into setup, but
SSH disconnected during a long build. Rerunning was safe, yet its intent and
reuse behavior were not clear enough. Routine init also executed `npm ci`; npm
defines that operation as a clean install that removes an existing
`node_modules`, so a repair could look like an unnecessary reinstall.

The maintained recovery model is now:

| Intent | Entry point | Contract |
| --- | --- | --- |
| Fresh setup or resume | `make init` | Verify actual state and reconcile missing/invalid components |
| Repair current source | `make repair` | Preserve source revision and operator data |
| Update and repair | one-line installer on an existing checkout, or `make update` | Stopped runtime, clean checkout, fast-forward only, then repair |
| Generated cleanup | `make clean` | Remove generated build/cache output only |
| Config reset | `make reset-config` | Back up and reset config only |
| Clean replacement | new `PIXEAGLE_HOME` | Leave the prior installation intact until explicit cutover |

A destructive full reset is intentionally absent from the beginner flow.

## Implementation

- Setup reports whether state is fresh or existing/interrupted and states the
  preservation boundary before mutation.
- One shared helper owns dashboard manifest fingerprints and readiness checks.
  Reuse requires regular non-symlink manifests/cache, matching SHA-256 values,
  an existing dependency tree, and a successful offline `npm ls --all`.
- Missing, stale, interrupted, or invalid state falls back to strict
  lockfile-enforced `npm ci`. The runtime's mutable `npm install` fallback was
  removed.
- Existing system packages, venv, matching Node/npm, manifest-verified
  binaries, config, credentials, models, recordings, logs, and evidence remain
  reusable/preserved. Source builds do not trust partial compiler work trees;
  an interrupted optional build restarts from private staging with rollback
  protection for the prior verified environment.

## Candidate Validation

- Installer/setup/profile/venv/lock/AI/dlib/model matrix:
  **304 passed, 1 skipped**.
- API route, parameter reload, docs infrastructure, and version/About:
  **101 passed**.
- Dashboard: **53 suites / 348 tests** and optimized production build passed.
- Schema: **40 sections / 535 parameters; current**.
- Bash syntax, bounded ShellCheck, and `git diff --check` passed.
- Real dashboard dependency rehearsal: stale version state triggered one clean
  `npm ci`; an immediate second run validated and reused the tree without
  reinstalling.
- Exact candidate `9df16150e9720257cbc3e2ced246d95103441c0d`
  passed the dashboard-inclusive clean-checkout handoff **26/26**, including
  clean initial/final source state. The updater dry-run was intentionally
  omitted from the passing run because the public bench owns ports `3040` and
  `5077`; a separate attempt proved the required stopped-runtime refusal.

## Remaining Gates

1. After any currently running beta.11 installer exits, rerun the public
   one-line command on the real Ubuntu host and retain its complete summary.
2. Keep physical Raspberry Pi, Full AI/model, dlib/GStreamer target builds,
   PX4/SIH/SITL/HIL, QGC, production networking, field, and aircraft claims
   outside this checkpoint.

## Claim Boundary

This checkpoint proves local recovery contracts and repository gates. It does
not prove host package-manager rollback, arbitrary compiler-state resume,
physical hardware, PX4, simulation, QGC, production deployment, or flight.

## Evidence

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0113-9df16150-exact-clean-handoff-no-update/manifest.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0113-beta12-vps-browser-smoke/manifest.json`

## Publication And Public Bench

- Annotated prerelease `v7.0.0-beta.12` targets
  `503addd06b4b21131ab52d22474f53155070b400`.
- Browser-only public run
  `pixeagle_manual_c0ca4b47-85d8-48a3-bbc5-d306448c40d5` is healthy with only
  MainApp and Dashboard expected.
- Dashboard HTTP returned `200`; served and local build indexes matched.
  Protected About returned structured `401`; configured lab-only anonymous
  MJPEG and WebSocket paths delivered frame data.
- Runtime logs contained no error record and only the expected critical
  public-HTTP lab warning. Config, browser-user store, and QGC token-store
  hashes were unchanged.
