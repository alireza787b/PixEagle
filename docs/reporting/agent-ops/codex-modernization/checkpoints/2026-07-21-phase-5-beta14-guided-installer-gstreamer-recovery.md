# Phase 5 Checkpoint: Beta.14 Guided Installer And GStreamer Recovery

**Date:** 2026-07-21
**Slice:** PXE-0115, with PXE-0116 deferred
**Status:** release candidate verified locally; target-host GStreamer rerun remains

## Problem

The maintainer's beta.13 Full AI run completed the dependency path and the
optional OpenCV/GStreamer compilation, but exposed two real installer defects.
Explicit yes/no answers were lost through Bash dynamic-scope variable
shadowing, so a visible `y` could still take the default `No` branch. The
OpenCV builder then rejected its own successful out-of-tree compile because a
Python helper import wrote `__pycache__` into the pinned source export before
the final source-integrity digest.

The same run also showed that manually padded profile presentation and
ambiguous optional-component defaults made the guided path harder to scan than
necessary.

## Decision

- Both the outer bootstrap and shared initializer input helpers now use
  collision-resistant internal variable names. Explicit `y`, explicit `n`,
  Enter defaults, input closure, and the outer existing-checkout prompt are
  exercised through real pseudo-terminal tests.
- Terminal input closure aborts the guided setup instead of silently accepting
  a default. Unattended sudo validation is nonblocking.
- The guided Enter path is one stable contract: Core plus the `pixeagle` shell
  shortcut. dlib, OpenCV/GStreamer, standalone service, and service auto-start
  remain explicit opt-ins. `none` is exclusive and ambiguous combinations are
  rejected.
- Profile and optional-component output uses normal section/list formatting;
  it no longer depends on manually padded colored boxes.
- The OpenCV builder exports `PYTHONDONTWRITEBYTECODE=1`. The complete pinned
  source-tree digest, private staging, prior-provider preservation, and atomic
  replacement ordering remain unchanged; a real source mutation still fails.
- Full AI continues to install the reviewed dependency profile without
  silently downloading an executable model checkpoint. The current manual lab
  example remains digest-pinned. A future default-No model installer is tracked
  as PXE-0116 and must be manifest-pinned, license-aware, conflict-safe, and
  atomically registered.

## Validation

- Installer pseudo-terminal regressions: `tests/test_init_installer_ux.py`,
  **28 passed**.
- Environment/setup resolution: `tests/test_setup_venv_resolution.py`,
  **34 passed**.
- Focused initializer, OpenCV, and docs gate: **87 passed**.
- Broader installer/setup profiles gate: **217 passed**.
- Update/config lifecycle gate: **34 passed**.
- Documentation consistency gate: **25 passed**.
- Required Phase 0 API/reload command: **72 passed**.
- `bash scripts/check_schema.sh`: passed with no unintended schema change.
- Bash syntax, changed-file ShellCheck, and `git diff --check`: passed;
  ShellCheck reported only its expected dynamic-source `SC1091` limitation.
- Dashboard lint, all **53 suites / 348 tests**, and production build: passed.
- Exact committed candidate `a1bce29698f658f9f8c2a54c19cf2893cc8c2c72`
  passed the maintained dashboard-inclusive clean-checkout handoff **26/26**
  with clean initial and final state. Its temporary checkout was removed.
- A bounded independent release-blocker review returned **GO** with no material
  code finding.

## Evidence

Exact clean-checkout manifest:

`../evidence/2026-07-21-pxe0115-a1bce296-exact-clean-handoff/manifest.json`

The manifest records command lines, return codes, durations, output digests,
required-file checks, source commit, clean-state assertions, and the explicit
claim boundary. It does not retain a disposable dependency checkout.

## Release Gate

The source is ready for the `v7.0.0-beta.14` prerelease. After publication, the
maintainer must rerun the optional OpenCV/GStreamer build on the disposable
Ubuntu host. That run must reach installation and
`make check-gstreamer-runtime`; completing compilation alone is not acceptance.
The prior OpenCV provider must remain usable if the optional build fails.

## Risks And Bounded Follow-Up

- The bytecode false-positive has unit/regression coverage, but the complete
  target-host source build is intentionally not claimed until the maintainer's
  fresh rerun completes.
- A model is code-bearing third-party input. Automatic acquisition remains
  outside this beta instead of using a mutable `latest` download.
- Raspberry Pi/Jetson performance and provider support require target-specific
  evidence. The normal Enter path deliberately avoids long optional builds.
- QGC receipt, WebRTC across public networks, PX4/SIH/SITL/HIL, hardware,
  field, and aircraft validation remain separate gates.

## Claim Boundary

This checkpoint proves the corrected guided-input contract, optional-selection
defaults, OpenCV source-integrity false-positive prevention, local regression
gates, and an exact clean-checkout handoff. It does not prove GStreamer on the
maintainer host, configured-model inference there, QGC playback, PX4 behavior,
target-board performance, field readiness, or aircraft safety.
