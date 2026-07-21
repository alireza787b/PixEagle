# Phase 5 Setup Lock Observability

**Date:** 2026-07-21 UTC
**Issue:** PXE-0121
**Status:** implementation complete; maintainer VPS retry pending

## Trigger

A fresh VPS lost its SSH transport when the optional OpenCV build had reported
100%. Re-running the one-line installer correctly refused the setup resource,
but the timeout exposed only its internal lock path.

## Decision

Keep setup serialization fail-closed. A second installer must not delete or
bypass an active lease. Instead, expose only verified process metadata and make
long compilation visibly alive. A heartbeat helps diagnose a quiet terminal;
`tmux` remains the documented option when the SSH transport itself is unstable.

## Changes

- Exclusive setup leases record a UTC start time.
- Lock timeouts identify the verified operation and supervisor PID and explain
  that work may continue after an SSH disconnect.
- `make setup-status` reports active/idle state and can find a multi-resource
  updater lease from any resource it covers.
- The OpenCV compilation step prints elapsed time and observed progress every
  30 seconds and points reconnecting operators to `make setup-status`.
- README and troubleshooting recovery guidance use the same command and retain
  the no-concurrent-installer/no-lock-deletion boundary.

## Validation

- `python3 -m py_compile scripts/lib/setup_lock_supervisor.py`
- `bash -n scripts/lib/setup_lock.sh scripts/setup/build-opencv.sh`
- `PYTHONPATH=src .venv/bin/pytest -q tests/test_setup_lock.py tests/test_setup_venv_resolution.py tests/test_init_installer_ux.py`
  - `93 passed, 1 skipped`
- `make setup-status` on an idle local environment
- `git diff --check`

No full OpenCV source build or remote VPS mutation is claimed by this local
slice. The maintainer's fresh-VPS retry is the remaining acceptance evidence.

## Next

Push the bounded fix to `main`. On the VPS, run `make setup-status` after a
disconnect and retry the one-line installer only after it reports `Active: no`.
Then resume the researched aerial-model catalog slice.
