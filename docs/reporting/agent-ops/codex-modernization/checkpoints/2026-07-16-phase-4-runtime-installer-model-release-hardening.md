# Phase 4 Runtime, Installer, And Model Release Hardening

Date: 2026-07-16

## Status

PXE-0096 is complete on pushed exact candidate
`b64d6c2817f21068073f63c66131258561f90125`. Local review and broad gates plus
the isolated clean-checkout handoff passed. This checkpoint is not a release,
deployment, Raspberry Pi, PX4, QGC receiver, HIL, or field claim. Controlled VPS
and RPi evidence follow under PXE-0068/PXE-0074.

## Scope

- Preserve the operator-owned ignored config, credentials, models, evidence,
  and currently running public demo while consolidating the candidate.
- Keep one maintained stopped-runtime update surface with deterministic
  lifecycle, source, and virtual-environment ownership.
- Make service installation/removal and runtime state queries fail closed.
- Complete the OpenCV provider and model artifact transaction review without
  broadening into target-only claims.
- Reconcile active setup/config/model/runtime docs and tests in the same slice.
- Stop review when concrete release blockers are closed; record nonblocking
  cleanup for a later version.

## Implemented Contracts

### Runtime And Update Ownership

- `make update` and `pixeagle-service update` now delegate to the same
  `scripts/update.sh` transaction. The retired public sync/restart aliases are
  absent and guarded by tests.
- Update requires a stopped runtime and owns lifecycle, source checkout, and
  selected venv resources. It does not stop or restart PixEagle.
- Runtime components retain shared source/venv locks for their lifetime.
  Start and stop own exclusive lifecycle transactions. Acquisition order puts
  lifecycle before resources acquired by startup, preventing the reproduced
  update/start inversion.
- The exact candidate branch is fetched without tags or submodules, checked as
  a fast-forward descendant, checked for stable management entrypoints, and
  published only from a clean tracked/untracked worktree.
- Candidate publication and guarded rollback reject target-tree paths that
  would overwrite ignored or untracked operator data. Rollback remains limited
  to the updater's exact candidate HEAD and an unchanged tracked checkout.
- A partial fast-forward that changes HEAD or tracked state is now reported as
  changed and requiring inspection; it cannot emit the former contradictory
  "source HEAD was not changed" result.
- Runtime listener inspection distinguishes a normal empty `lsof` query from
  nonzero/error-output failures. Unknown listener ownership blocks update.

### Service Lifecycle

- Generated system units use a private temporary file, pass
  `systemd-analyze verify`, publish atomically, and include `Delegate=yes` for
  bounded model worker cgroups.
- Service removal verifies load, active, stopped, enabled/disabled, unit path,
  deletion, and daemon reload. The public uninstall path uses this same helper;
  query failure preserves both unit and wrapper.

### Config Runtime State

- A runtime config containing a declared legacy value alias is validated in its
  normalized form and now retains that same normalized candidate in memory.
  Unrelated valid writes no longer fail against the pre-normalized legacy value.
- Schema/default/retirement authority remains generated and checked from the
  existing single-source contracts. Current result: 40 sections, 540 parameters.

### OpenCV And Model Transactions

- OpenCV provider replacement uses exact source/archive/tree evidence, private
  publication, stale-metadata rejection, hostile-Git-environment coverage, and
  cleanup/finalizer checks. The VPS still has no accepted OpenCV-GStreamer
  target result.
- Model loading uses a private lease-owned canonical-name binding so Ultralytics
  and NCNN format discovery sees the expected suffix while the admitted
  artifact identity remains pinned.
- A narrow same-artifact legacy evidence upgrade is supported; arbitrary legacy
  re-registration is not.
- AI runtime probes return structured results over a private descriptor, so
  dependency stdout/stderr cannot corrupt the result document.
- Target Full/RPi evidence is still required for trusted `.pt` load/inference,
  NCNN export/load, and delegated service execution.

## Independent Review

The bounded reviewer initially returned NO-GO with six reproducible blockers:

1. ignored paths could collide with newly tracked candidate/rollback paths;
2. a failed merge could move HEAD while reporting `changed=false`;
3. update/start lock ordering could invert;
4. `lsof` errors could be read as no listeners;
5. the public uninstall path bypassed fail-closed removal;
6. candidate validation did not preserve stable runtime/update entrypoints.

All six received production fixes and adversarial regressions. A follow-up
found one remaining `lsof` status-1 ambiguity; private stderr capture closed it.
The final bounded verdict was `GO`.

## Validation Evidence

- Adversarial runtime/update/config gate: `102 passed, 1 skipped`.
- Minimum API/reload gate: `72 passed`.
- Schema check: `40 sections, 540 parameters`, current.
- API/MCP candidate inventory: current.
- Docs/inventory gate: `36 passed`.
- Maintained non-hardware/non-SITL suite:
  `3275 passed, 48 skipped, 1 deselected`, zero failures, 369.34 seconds.
- Earlier candidate gates retained in this worktree:
  - combined installer/runtime/model: `509 passed, 3 skipped`;
  - model focused: `207 passed, 1 skipped`;
  - dashboard: 49 suites/296 tests, lint, production build;
  - Phase 0 broad checkpoint: 457 tests with one dependency deprecation warning.
- Python compile, Bash syntax, ShellCheck, generated schema drift, API candidate
  drift, docs links/terms, and `git diff --check`: passed.
- Expected local skips include native Windows ACL/launcher checks, root-only
  cross-UID lock execution, absent optional dlib, and absent Ultralytics on the
  Core VPS. These are not silently counted as target evidence.
- Exact-commit clean-checkout handoff:
  - source `b64d6c2817f21068073f63c66131258561f90125`;
  - 26/26 required commands passed;
  - initial and final temporary checkout state clean;
  - dashboard `npm ci`, 49 suites/296 tests, and production build passed;
  - updater dry-run explicitly skipped because the old public demo remained
    active and this gate was not authorized to stop it;
  - manifest:
    `../evidence/2026-07-16-pxe0096-release-candidate/manifest.json`.

## Deferred Debt

PXE-0097 records only nonblocking cleanup for the next version:

- consolidate duplicated probe/publisher evidence plumbing;
- remove or replace two unused weaker NCNN helpers;
- consolidate duplicate post-admission process cleanup after cgroup cleanup;
- split `ModelManager` only if it preserves the proven artifact lifecycle.

These items do not justify delaying clean-checkout and operator feedback.

## Remaining Gates

1. Back up/hash ignored live config, browser credentials, model registry, and
   service/runtime state; stop only the verified old runtime.
2. Run the full stopped-runtime updater preflight, migrate config through the
   typed preview/apply contract, launch the exact candidate, and probe public
   login, APIs, MJPEG, WebSocket, WebRTC policy, responsive UI, actions, logs,
   About, and managed-SIH status while monitoring logs.
3. After maintainer VPS acceptance, execute the fresh Raspberry Pi 5 Core/Full
   walkthrough and collect OpenCV-GStreamer plus trusted model evidence.
4. Resume manual QGC Windows playback/recording work only after PixEagle is
   accepted. Keep PR #13594 draft until its separate acceptance gate passes.

## Claim Boundary

No real aircraft was commanded. No PX4/SITL/SIH runtime, HIL, field flight,
production TLS/firewall deployment, Raspberry Pi Full install, target
OpenCV-GStreamer build, trusted YOLO/NCNN inference, or manual QGC Windows
receiver result is claimed by this checkpoint.
