# Phase 5 Checkpoint: Beta.15 Service, Dependency, And Onboarding Recovery

**Date:** 2026-07-21 UTC  
**Slice:** PXE-0117  
**Status:** implementation complete; repository gates, publication, and target-host repair pending

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

## Validation Contract

Already passed before this checkpoint was recorded:

- Bash syntax checks for all touched shell scripts;
- Python compilation checks for touched tests;
- `git diff --check` (with the existing CRLF normalization notice for
  `scripts/init.bat`);
- focused runtime ownership, installer UX, PyTorch policy, and setup-lock
  suites: `131 passed, 1 skipped`.

Required before publication:

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py
bash scripts/check_schema.sh
```

The broader installer/config/docs/service suites and dashboard test/lint/build
must also pass. A clean-checkout handoff must run from the committed candidate;
the existing beta14 evidence is not silently reused as beta15 evidence.

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

Run the complete repository gates, obtain an independent practical/safety
review of the diff, apply the exact candidate to the disposable VPS through
the canonical updater, and capture the real systemd/tmux startup and shutdown
transcript. Tag and publish `v7.0.0-beta.15` only after that target-host gate.
Then prepare the beginner Ubuntu handoff; do not begin Raspberry Pi acceptance
until the Ubuntu path reaches a clean ready summary.
