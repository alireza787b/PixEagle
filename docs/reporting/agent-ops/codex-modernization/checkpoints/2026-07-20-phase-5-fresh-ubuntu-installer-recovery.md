# Phase 5 Checkpoint: Fresh Ubuntu Installer Recovery

**Date:** 2026-07-20  
**Slice:** PXE-0110  
**Status:** beta.10 published and public browser smoke accepted; complete maintainer rerun pending

## Failure Classification

The supplied Ubuntu 26.04 transcript proves that Core Python dependency
resolution, OpenCV, MAVSDK Server, and MAVLink2REST completed. It does not prove
the installation was ready because Node setup failed and dashboard dependencies
were skipped.

Two concrete defects caused the failure:

1. `/dev/tty` existed as a path but could not be opened as a controlling
   terminal, so profile input produced an error.
2. PixEagle passed an absent private staging `NVM_DIR` to the pinned nvm
   installer, which rejects that state.

The clean Ubuntu rehearsal then caught a third defect before release: spinner
shutdown could propagate its expected killed-child status under an errexit
caller and stop setup after successful nvm staging.

## Implemented Contract

- The one-line bootstrap is the beginner install-consent boundary. With a real
  terminal it offers Core or Full AI. Without one, it explicitly selects Core,
  skips optional host mutations, and reports Full/optional override syntax.
- Direct noninteractive `make init` requires
  `PIXEAGLE_NONINTERACTIVE=1 PIXEAGLE_INSTALL_PROFILE=core|full`.
- Core is the complete product runtime without local AI packages. Full AI adds
  the guarded PyTorch/Ultralytics path; a trusted model remains separate.
- Python setup commits before Node. Required component failures return nonzero
  and remain visible without deleting verified earlier work.
- Node.js 24 is defined once in `.nvmrc` and enforced by init, dashboard runtime,
  package metadata, and CI.
- Full AI with the current PyTorch 2.6 policy is rejected on Python 3.14 before
  apt/venv mutation. Core remains independently host-validated.
- dlib, OpenCV/GStreamer, the Bash directory shortcut, and standalone service
  setup are explicit optional choices and each has a later command.

## Files Changed

- `install.sh`
- `.nvmrc`
- `scripts/init.sh`
- `scripts/lib/common.sh`
- `scripts/components/dashboard.sh`
- `scripts/setup/check-pytorch-python-compat.py`
- `scripts/setup/pytorch_matrix.json`
- `scripts/setup/setup-pytorch.sh`
- `scripts/setup/install-shell-shortcut.sh`
- `dashboard/package.json`, `dashboard/package-lock.json`
- CI Node setup workflows
- `README.md`, `docs/INSTALLATION.md`, `docs/TROUBLESHOOTING.md`
- focused installer/setup policy tests and this modernization record

## Validation

- Installer/setup/profile/venv/PyTorch/dlib suite: **252 passed**.
- Minimum Phase 0 API/reload gate: **72 passed**.
- Schema check: **40 sections / 535 parameters; current**.
- Clean dashboard copy: `npm ci`, **53 suites / 348 tests**, ESLint, and
  optimized production build passed.
- Bash syntax, Python helper compile, `git diff --check`, and bounded ShellCheck
  passed. Existing unrelated `dashboard.sh` assignment/exit-code style warnings
  were excluded rather than expanding this release.
- Official Ubuntu 26.04 isolated nvm/Node rehearsal passed with image digest
  `sha256:3131b4cc82a783df6c9df078f86e01819a13594b865c2cad47bd1bca2b7063bb`,
  nvm commit `977563e97ddc66facf3a8e31c6cff01d236f09bd`, Node `v24.18.0`, and npm
  `11.16.0`.
- The initial independent review's concrete unattended/profile, Python matrix,
  apt, Node authority, service-state, and ownership findings were addressed.
  A fresh final reviewer exceeded the bounded review window and was stopped
  without a verdict; this checkpoint does not claim an independent final GO.
- Exact candidate `72ccbec13569d519647262d0e092484a4bbd7bd4` passed the
  maintained clean-checkout handoff **26/26** with clean initial/final state,
  Phase 0, schema, fresh dashboard install/tests/build, and setup/profile
  contracts. The updater dry-run stayed skipped because the public runtime is
  active and the updater requires stopped-runtime ownership.
- Annotated tag `v7.0.0-beta.10` resolves to
  `f16875f043b3e18137ae02855e63cf7cfbe3c972`, and the GitHub prerelease is
  published. The first full-component VPS launch correctly failed closed when
  that pre-existing checkout lacked `bin/mavlink2rest`; no partial runtime was
  left ready. The explicitly browser-only follow-up is healthy with exactly
  MainApp and Dashboard, preserved config and credential hashes, HTTP 200 for
  the dashboard, valid MJPEG and WebSocket JPEG delivery, and no runtime ERROR
  records. Its sole CRITICAL record is the expected public plain-HTTP lab
  exposure warning.

## Claim Boundaries

The container rehearsal intentionally repeated only the failed nvm/Node policy
section. The supplied maintainer transcript already proved Core dependency
resolution on Python 3.14, but the complete updated one-line install has not yet
been rerun by the maintainer. This checkpoint does not claim Raspberry Pi,
Full AI on Python 3.14, model inference, GStreamer/dlib target builds,
PX4/SIH/SITL/HIL, QGC, production TLS/WebRTC, field, or aircraft readiness.

## Remaining Gates

1. Give the maintainer the one-line fresh Ubuntu rerun. If it passes, proceed to
   the separately documented Raspberry Pi Core/Full/model acceptance lane.

## Evidence

- Ubuntu 26.04 repaired-section rehearsal:
  `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0110-ubuntu2604-node-rehearsal/manifest.json`
- Exact clean candidate handoff:
  `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0110-72ccbec1-exact-clean-handoff/manifest.json`
- Published beta.10 public browser smoke:
  `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0110-beta10-vps-browser-smoke/manifest.json`
