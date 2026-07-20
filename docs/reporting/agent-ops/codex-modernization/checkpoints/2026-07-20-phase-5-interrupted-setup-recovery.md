# Phase 5 Checkpoint: Interrupted Setup Recovery

**Date:** 2026-07-20
**Slice:** PXE-0113
**Status:** candidate gates passed; exact handoff, publication, and maintainer rerun pending

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

## Remaining Gates

1. Commit this candidate and run the maintained exact clean-checkout handoff.
2. Publish beta.12 and refresh the existing public browser-only lab bench
   without changing config or credentials.
3. After any currently running beta.11 installer exits, rerun the public
   one-line command on the real Ubuntu host and retain its complete summary.
4. Keep physical Raspberry Pi, Full AI/model, dlib/GStreamer target builds,
   PX4/SIH/SITL/HIL, QGC, production networking, field, and aircraft claims
   outside this checkpoint.

## Claim Boundary

This checkpoint proves local recovery contracts and repository gates. It does
not prove host package-manager rollback, arbitrary compiler-state resume,
physical hardware, PX4, simulation, QGC, production deployment, or flight.
