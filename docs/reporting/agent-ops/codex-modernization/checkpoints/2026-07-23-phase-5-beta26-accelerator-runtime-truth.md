# Phase 5 Checkpoint: Beta.26 Accelerator Runtime Truth

Date: 2026-07-23
Issue: PXE-0138
Status: local gates passed; RTX 5080 target proof pending

## Problem

An Ubuntu Full AI installation on an RTX 5080 showed no active runtime device
and slow SmartTracker behavior. The prior policy mapped every detected CUDA
12+ x86 NVIDIA host to PyTorch 2.6/CUDA 12.4. Its verification allocated a CUDA
tensor but did not force a kernel, so an architecture-incompatible build could
appear available. The Models page also read the wrong fallback-policy key.

Zero NCNN exports was not the GPU defect: CUDA uses the trusted `.pt` model;
NCNN is an optional CPU/edge export.

## Changes

- Added ordered, matrix-owned Linux NVIDIA selectors using driver CUDA level
  and compute capability.
- Added current PyTorch 2.12.1/CUDA 13 and PyTorch 2.11.0/CUDA 12.8 profiles
  while retaining compatibility profiles for older NVIDIA architectures.
- Setup, readiness diagnostics, and model loading now execute and synchronize a
  CUDA matrix kernel before claiming accelerator readiness.
- A failed model-load probe uses the existing CPU fallback and publishes the
  reason, effective device, device name, capability, and compiled architectures.
- The operational dashboard shows `CUDA`, `CPU`, `CPU fallback`, or `Loading`
  from the active SmartTracker runtime.
- Strict GPU mode no longer silently selects CPU on Linux ARM.
- Unknown/new JetPack releases can use only complete digest-verified torch and
  torchvision wheel overrides; otherwise setup fails with guidance.
- Removed the unimplemented SmartTracker MPS claim.
- Added one concise accelerator support guide linked from README, docs index,
  model setup, and troubleshooting.

## Validation

- `bash -n scripts/setup/setup-pytorch.sh scripts/setup/check-ai-runtime.sh`
- `shellcheck -x scripts/setup/setup-pytorch.sh scripts/setup/check-ai-runtime.sh`
- PyTorch policy and backend focused suite: 86 passed
- Installer UX and AI diagnostic suite: 55 passed
- Phase API/config gate: 73 passed
- Docs infrastructure suite: 31 passed
- Schema check: current, 38 sections and 513 parameters
- Dashboard focused suite: 78 passed
- Dashboard full suite: 366 passed
- Dashboard lint: passed
- Dashboard production build: passed
- CPU-host dry-run report selected `linux_cpu` and recorded unknown compute
  capability without claiming GPU evidence.

One independent focused review found strict ARM GPU fallback, unknown JetPack
override reachability, malformed selector bounds, an unimplemented MPS claim,
and missing end-to-end CPU fallback coverage. All five findings were corrected
and covered before this checkpoint.

## Evidence Boundary

This host has no NVIDIA GPU. Local tests prove selection, validation, fallback,
API state, and UI contracts; they do not prove RTX 5080, Raspberry Pi, Jetson,
thermal, throughput, camera, PX4, or field behavior.

## Next Gate

On the RTX 5080 Ubuntu host, update to the exact pushed beta.26 candidate, stop
the runtime, run strict GPU setup plus AI readiness, then start SmartTracker and
confirm the dashboard shows `Compute: CUDA`. Preserve the command output if it
fails. Tag/release promotion waits for that target-host result.
