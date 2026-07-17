# Phase 4 Optional Setup Runtime Readiness Checkpoint

- Date: 2026-07-05
- Phase: 4
- Issue: PXE-0080
- Slice: optional setup helper venv resolution and runtime capability diagnostic
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

The user feedback intake raised eight product/setup questions. This checkpoint
closes the immediate setup/runtime-readiness defect found during that intake:
optional setup helpers had not fully followed the repo's newer `.venv` support,
and the AI runtime diagnostic did not clearly answer whether AI, dlib, OpenCV
tracker APIs, or OpenCV GStreamer were available.

## What Changed

- Added shared shell venv helpers to `scripts/lib/common.sh`:
  - `resolve_pixeagle_venv_dir`;
  - `resolve_pixeagle_venv_python`;
  - `resolve_pixeagle_venv_pip`.
- The resolver uses:
  1. explicit `PIXEAGLE_VENV_DIR`;
  2. `.venv/` when it has `bin/python`;
  3. `venv/` when it has `bin/python`;
  4. `venv/` as the expected missing path.
- Updated optional setup helpers to use the resolver:
  - `scripts/setup/check-ai-runtime.sh`;
  - `scripts/setup/install-ai-deps.sh`;
  - `scripts/setup/setup-pytorch.sh`;
  - `scripts/setup/build-opencv.sh`;
  - `scripts/setup/install-dlib.sh`;
  - `scripts/lib/reset-config.sh`.
- Extended `check-ai-runtime.sh` to report:
  - torch, torchvision, torchaudio;
  - Ultralytics, lap, ncnn, pnnx;
  - dlib;
  - OpenCV version;
  - OpenCV GStreamer and FFMPEG build flags;
  - CSRT/KCF tracker API availability.
- Updated `install-ai-deps.sh` constraints so AI installs also protect
  `opencv-python-headless` and `opencv-contrib-python-headless`.
- Added focused tests in `tests/test_setup_venv_resolution.py`.
- Updated:
  - `docs/INSTALLATION.md`;
  - `docs/OPENCV_GSTREAMER.md`;
  - `docs/TROUBLESHOOTING.md`;
  - issue register, phase map, and journal.

## VPS Runtime Capability Result

`bash scripts/setup/check-ai-runtime.sh` now runs against the active public demo
venv:

- Python: `/home/alireza/PixEagle/.venv/bin/python`
- OpenCV: `4.13.0`
- OpenCV FFMPEG: `YES`
- OpenCV GStreamer: `NO`
- CSRT tracker API: available
- KCF tracker API: available
- torch/torchvision/torchaudio: not installed
- Ultralytics/lap/ncnn/pnnx: not installed
- dlib: not installed
- SmartTracker model paths in current config: missing

This is enough for the current quick public browser demo and OpenCV tracker
paths. It is not a YOLO/AI, dlib, or OpenCV-GStreamer-ready environment.

## User Feedback Intake Disposition

- User add/change/remove/edit users: tracked as PXE-0081. Recommended first
  gate is an offline browser-user management CLI plus reset runbook, before a
  web-admin UI.
- Forgotten admin password: tracked as PXE-0081. Current recovery requires
  shell access and hashed user-file replacement/restart; docs/CLI are missing.
- `CLASSIC` overlay: dashboard reviewer found this is the tracker-mode label,
  not an OSD preset. OSD stale/empty preset display and overlay chip evidence
  remain PXE-0082.
- Log bundle download: export exists, but dashboard does not yet show filename,
  size, SHA-256, or claim-boundary after download; import/replay is not a
  current feature. Tracked as PXE-0083.
- About/version/update: version exists only in legacy drawer/footer paths.
  Typed read-only About/System/update-status is PXE-0084.
- Bootstrap/setup workflow: docs now explain the venv resolver and runtime
  diagnostic. Full clean beginner/senior walkthrough remains PXE-0074.
- Optional SIH simulator/training: existing SIH harness is suitable for L2
  validation, but not as casual operator controls. A Dev/Training surface around
  the harness/manifest, not raw injection routes, is PXE-0085.
- Safe demo cleanup/update workflow: tracked as PXE-0086.

## Evidence Boundary

This slice changes setup diagnostics and docs only. It does not claim PX4,
MAVSDK, SITL, HIL, QGC receiver, deployment, follower response, or real-aircraft
success.

## Validation

Validation run during this checkpoint:

```bash
bash -n scripts/lib/common.sh scripts/lib/reset-config.sh \
  scripts/setup/check-ai-runtime.sh scripts/setup/install-ai-deps.sh \
  scripts/setup/setup-pytorch.sh scripts/setup/build-opencv.sh \
  scripts/setup/install-dlib.sh

bash scripts/setup/check-ai-runtime.sh

.venv/bin/python -m pytest tests/test_setup_venv_resolution.py

.venv/bin/python -m pytest tests/test_setup_profiles.py \
  -k 'quick_browser_demo or setup_choice_matrix or init_optional'
```

Results:

- shell syntax: passed;
- runtime check: passed and inspected `.venv`;
- venv resolver tests: 9 passed;
- quick-browser demo dry-run focused regression: 1 passed.
- full setup profile suite with venv resolver tests: 147 passed;
- docs infrastructure consistency: 23 passed;
- schema check: up to date;
- whitespace diff check: passed.

Full validation commands:

```bash
.venv/bin/python -m pytest tests/test_setup_venv_resolution.py tests/test_setup_profiles.py
.venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py
bash scripts/check_schema.sh
git diff --check
```

## Remaining Slices

- PXE-0079: final clean setup walkthrough evidence.
- PXE-0081: browser user-management CLI and reset runbook.
- PXE-0082: OSD/video overlay polish.
- PXE-0083: log evidence bundle UX/import design.
- PXE-0084: typed About/System/update-status.
- PXE-0085: SIH Dev/Training validation surface.
- PXE-0086: safe demo cleanup/rotation and safe update workflow.
