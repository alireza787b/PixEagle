# Phase 5 Checkpoint: Profile-Driven Python 3.14 And Full AI Compatibility

**Date:** 2026-07-20  
**Slice:** PXE-0114  
**Status:** complete for the installer/policy slice; maintainer host acceptance remains separate

## Problem

The previous initializer used one global PyTorch/Python range and a dedicated
checker whose message became stale as the dependency matrix moved forward. A
fresh Ubuntu host with Python 3.14 could run Core, but Full AI was rejected even
when the current CPU wheels were available. The old path also gave no clean,
intent-preserving fallback when an accelerator profile did not match the active
interpreter.

## Decision

`scripts/setup/pytorch_matrix.json` is now the single compatibility authority.
It records the required Python language family, Core runtime policy, each AI
profile's Python range/exclusions, maintenance track, package pair, and evidence
basis. `check-python-compatibility.py` validates the policy and is shared by
`scripts/init.sh` and `scripts/setup/setup-pytorch.sh`; interpreter-specific
branches are not added to the shell installers.

The operator behavior is:

- compatible Core and Full paths proceed normally;
- automatic accelerator selection may fall back to the reviewed CPU profile
  when the accelerator profile cannot use the active interpreter;
- interactive incompatible Full setup offers Core and installs no unsupported
  AI packages if accepted;
- unattended incompatible Full setup fails closed and prints the explicit
  profile/interpreter choices;
- a valid existing PixEagle venv remains authoritative during repair;
- profiles without torchaudio remove stale torchaudio metadata before install.

The current Linux CPU profile is reviewed for Python 3.10-3.14, excluding
3.14.1, with `torch 2.12.1` and `torchvision 0.27.1`. CUDA compatibility and
Jetson operator-wheel profiles retain their narrower contracts.

## Validation

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_init_installer_ux.py tests/test_pytorch_setup_policy.py`: **53 passed**.
- Setup/docs regression suite (`tests/test_setup_profiles.py`,
  `tests/test_docs_infrastructure_consistency.py`, initializer, and PyTorch
  policy tests): **233 passed**.
- `bash -n scripts/init.sh scripts/setup/setup-pytorch.sh` and Python syntax
  checks: **passed**.
- `bash scripts/check_schema.sh`: run at the phase gate; no schema changes were
  introduced by this slice.
- Clean official `ubuntu:26.04` image (`sha256:3131b4cc82a783df6c9df078f86e01819a13594b865c2cad47bd1bca2b7063bb`) with Python 3.14.4:
  - Core requirements installed successfully;
  - compatibility checks passed for Core, Linux CPU, and any supported Full
    profile;
  - PyTorch setup report passed with `torch 2.12.1+cpu` and
    `torchvision 0.27.1+cpu`;
  - AI dependency report passed with `ultralytics 8.4.95`, `lap`, and imports;
  - CSRT/KCF/OpenCV provider preservation passed.
- The raw `pip check` command reports only the known upstream metadata name
  mismatch (`ultralytics` requests `opencv-python`; PixEagle intentionally owns
  `cv2` through `opencv-contrib-python-headless`). The shared
  `scripts/setup/pip_check_policy.py` accepted exactly that line after checking
  the actual OpenCV version/contract; unrelated pip failures remain fatal.
- Existing host `.venv` Python 3.12.3 passed `check-ai-runtime.sh`, including a
  verified local YOLO first inference with CPU fallback and CSRT/KCF. This is
  host evidence, not a claim about the clean container's configured model.

## Evidence

See `../evidence/2026-07-20-pxe0114-python314-full-ai/` for the installer
reports, isolated run log, policy matrix copy, and existing-host runtime report.
The isolated container's heavier model-readiness probe was not counted: the
small test container was killed by its memory limit after dependency/import
validation. No model or flight claim depends on that probe.

## Risks And Bounded Follow-Up

- The current CPU profile is validated on the exact clean Python 3.14.4 host;
  Raspberry Pi/Jetson wheels and target-board performance still require their
  own evidence.
- The native Windows batch installer remains an explicitly experimental,
  non-parity path; this slice does not expand or claim it.
- The next bounded gate is the maintainer's fresh Ubuntu run from the published
  beta, followed by Raspberry Pi Core acceptance. QGC, PX4/SIH/SITL/HIL,
  GStreamer-enabled OpenCV, and field tests remain separate slices.

## Claim Boundary

This checkpoint proves installer policy and dependency resolution on the
recorded Linux test image. It does not prove tracker quality, autonomous
following, PX4 interaction, simulation, QGC playback, production networking,
hardware performance, or aircraft behavior.
