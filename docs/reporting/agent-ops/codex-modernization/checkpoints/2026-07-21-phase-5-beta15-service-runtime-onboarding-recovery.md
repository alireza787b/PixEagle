# Phase 5 Checkpoint: Beta.15 Service, Dependency, And Onboarding Recovery

**Date:** 2026-07-21 UTC  
**Slice:** PXE-0117  
**Status:** repository candidate and clean handoff complete; target-host repair and publication pending

## Trigger

The maintainer reran the Full AI bootstrap on a disposable Ubuntu 24.04
x86_64 VPS at commit `0c55eb9` and supplied the complete transcript and
service journal. The Python installation completed, but pip reported two
misleading intermediate conditions:

- an unconstrained `setuptools` upgrade reached `83.0.0` before the selected
  Torch metadata pulled it back below `82`;
- Ultralytics reported that its metadata names `opencv-python`, while PixEagle
  intentionally owns the single `cv2` provider through
  `opencv-contrib-python-headless`.

The optional standalone service was enabled and the host rebooted. The login
hint showed an activating/enabled state, but `pixeagle-service status` found no
runtime. Starting the service failed after the ownership scanner observed the
supervisor/launcher process as a marked service process. The same attempt also
emitted harmless `/proc/<pid>/environ: No such process` messages while
processes exited during inspection. The optional Bash helper was used as
`pixeagle start` and produced `cd: too many arguments`, and the summary did
not make the manual runtime command prominent enough. No dashboard account
prompt appeared, which is correct for the default local-only profile but was
not explained clearly.

## Root Cause And Boundary

The service failure is not a VPS-only or Python-version-only condition. The
runtime ownership contract uses exact environment markers so cleanup can never
signal an unrelated process. Before this slice, those markers were exported by
the long-lived systemd supervisor and by the outer launcher that waits on the
lifecycle lock. The fail-closed scanner consequently saw an ancestor as an
owned runtime process even though only the tmux component processes should be
owned. A process can also disappear between `/proc` readability and the file
read, so the diagnostic path must treat that as an absent candidate rather than
print a shell error.

The corrected boundary is:

```text
systemd supervisor                 no canonical runtime markers
  -> outer launcher/lock wrapper   private launch handoff only
    -> lifecycle child             canonical shell-local identity
      -> tmux + component panes    canonical exported identity
```

The scanner remains fail-closed. The change narrows where identity is
published; it does not weaken project-root, UID, mode, run-id, tmux, or
start-token checks.

## Implementation

- `scripts/service/run.sh` now keeps service identity in `SERVICE_*` locals,
  removes inherited canonical markers, and passes only private
  `PIXEAGLE_LAUNCH_RUNTIME_MODE`/`PIXEAGLE_LAUNCH_RUN_ID` handoff values to
  the launcher child.
- `scripts/run.sh` consumes and clears the private handoff, keeps canonical
  identity shell-local in orchestration layers, and passes it explicitly to
  the lifecycle child and component panes.
- `scripts/service/utils.sh` generates units without a canonical runtime
  `Environment=` seed, adds `UnsetEnvironment=...`, and prints one stable
  service state plus explicit start/stop/status inspection commands.
- `scripts/run.sh` now requires the tmux capability needed for atomic
  `new-session -e` environment publication and creates the ownership markers
  with the session; the service supervisor checks the complete pane/component
  health contract before sending systemd readiness.
- `scripts/lib/runtime_ownership.sh` suppresses expected TOCTOU diagnostics
  while preserving a failed ownership read as a failed ownership check.
- `scripts/setup/setup-pytorch.sh`, `scripts/init.sh`, and
  `scripts/setup/install-ai-deps.sh` no longer upgrade `setuptools`
  independently of the selected Torch metadata. Explicit pip
  `--no-warn-conflicts` flags avoid misleading intermediate resolver chatter
  while the completed environment is checked by the existing
  `pip_check_policy.py`. That policy now checks managed OpenCV distribution
  versions (and separately labels source-built module versions); the exact
  one-provider exception is not replaced by a second `opencv-python`
  distribution.
- `scripts/setup/install-shell-shortcut.sh` now installs a Bash function with
  `pixeagle help` and actionable rejection for ambiguous runtime arguments.
  It remains a directory helper; lifecycle selection stays explicit.
- `pixeagle-service disable` now disables boot auto-start while retaining the
  unit/runtime; `pixeagle-service uninstall` is the explicit removal path.
  A missing managed unit no longer silently falls back to an unmanaged start.
- Installer summaries, the login hint, README, installation/service/
  troubleshooting docs, changelog, version files, and focused regressions now
  state the manual/service commands and the local-only/no-account default.

## Authentication Decision

Fresh Core/Full setup remains local-only and does not create a dashboard user or
the unsafe shared `admin/admin` credential. This is intentional: loopback
access is the beginner same-host path. A guarded browser-session/LAN demo
profile is the explicit path that creates a credential handoff; existing
configuration and hashed user files are preserved during update/repair. The
dashboard account chip and the documented shell user-management command remain
the password-management paths.

## Repository Validation

Exact candidate `f991a4c13664b204241ccca5e301cad7b4487ac0` passed:

- focused dependency, installer UX, and runtime ownership suites: `121 passed`;
- required API inventory and parameter reload suites: `72 passed`;
- schema drift check: passed (`40` sections, `535` parameters);
- Phase 0 gate: `477 passed, 1 warning`;
- shell syntax, warning-level ShellCheck, and `git diff --check`: passed;
- dashboard: `53` suites / `348` tests, lint, and production build passed;
- Python `3.14.4` compatibility-policy probes for Core and supported Full AI
  profiles: passed; the intentionally excluded `3.14.1` CPU profile remained
  rejected.

The dashboard-inclusive clean-checkout handoff passed all `27/27` commands,
including setup-profile dry runs, stopped-runtime updater dry run, schema/API
checks, `npm ci`, dashboard tests/build, and final clean-worktree verification:

`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-21-pxe0117-f991a4c1-beta15-clean-handoff-venv-stopped/manifest.json`

The handoff used the project venv as its check interpreter. A preliminary
system-Python invocation stopped because that interpreter lacked Pydantic, and
a second invocation correctly refused while this checkout's manual runtime
owned ports `3040` and `5077`. After the exact owned runtime was stopped with
`make stop`, the unchanged candidate passed. These were harness/precondition
failures, not hidden product passes.

## Target-Host Repair Acceptance

The maintainer's existing VPS must not be wiped for this defect. After the
beta15 commit is published, the bounded in-place repair is:

```bash
cd /root/PixEagle
pixeagle-service update
sudo pixeagle-service enable
pixeagle-service start
pixeagle-service status
```

This re-generates the unit and reuses the existing verified virtual environment,
configuration, credentials, models, logs, and binaries. If startup still fails,
collect only:

```bash
systemctl status pixeagle.service --no-pager -l
journalctl -u pixeagle.service -b --no-pager -n 200
pixeagle-service status
```

Do not run a reset or delete lock/data directories as a first response. A
manual runtime remains available without the service:

```bash
cd /root/PixEagle
make demo
# or, after reviewing the live/PX4 configuration:
make run
```

The target-host run must record the exact commit, OS/Python versions, selected
profile, service unit state, tmux ownership/readiness, dashboard health, and
the bounded claim that it is a Linux runtime smoke only. It does not prove
GStreamer on the target, model quality, PX4/SIH/SITL/HIL, QGC, WebRTC across a
public network, hardware performance, or flight safety.

## Open Follow-Up

PXE-0115 remains open for the maintainer's optional GStreamer rerun and
`make check-gstreamer-runtime`. PXE-0116 remains deferred for a provenance-
and-license-aware opt-in model installer. Service lifecycle semantics,
Raspberry Pi/Jetson evidence, PX4/SIH/SITL/HIL, QGC, and field validation remain
separate gates rather than being folded into this installer repair.

## Next Slice

Apply exact candidate `f991a4c1` to the disposable VPS through the canonical
updater and capture the real systemd/tmux startup, health, restart, and shutdown
transcript. The previously supplied VPS password was rejected and the local
SSH key is not authorized, so no target mutation or success claim was made.
Tag and publish `v7.0.0-beta.15` only after that target-host gate. Then prepare
the beginner Ubuntu handoff; do not begin Raspberry Pi acceptance until the
Ubuntu path reaches a clean ready summary.
