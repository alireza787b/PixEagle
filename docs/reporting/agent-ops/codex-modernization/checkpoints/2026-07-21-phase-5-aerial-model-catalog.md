# Phase 5 Aerial Detector Model Catalog

**Date:** 2026-07-21 UTC
**Issues:** PXE-0122, PXE-0123
**Status:** catalog complete; alternate backend implementation deferred

## Question

Which currently supported detector is the best starting point for drone-view,
maritime, aircraft, and small-object video, and should PixEagle add a DETR or
tiled-inference backend now?

## Decision

There is no public checkpoint that can honestly be labeled military-grade,
flight-certified, or universally best for aerial video. The practical current
choices are:

- VisDrone YOLOv9e for the highest publisher-reported score in the reviewed
  same-pipeline community collection, with a desktop-GPU and independent-test
  warning due to its 117 MB / 58.2M parameter / 193 GFLOP footprint.
- VisDrone YOLO26n or YOLO26s as the first edge candidates for drone-view
  people and road vehicles.
- Official YOLO26 OBB checkpoints as the reproducible oriented-aerial baseline;
  `x` has the highest official family DOTA metric, while `n`/`s` are the
  practical first hardware trials.
- A project fine-tune of a supported YOLO detect/OBB model for a specific
  camera, altitude, coast, vessel, or airframe taxonomy.

PixEagle does not currently support RT-DETR, RF-DETR, YOLOX P2, or SAHI. The
current registry has only the Ultralytics backend, loads through `YOLO(...)`,
and admits `detect`/`obb`. Alternate backends are deferred under PXE-0123 until
a representative-video and target-hardware benchmark shows a material benefit
over supported baselines.

## Changes

- Added `docs/MODEL_CATALOG.md` with official pinned baseline links, immutable
  community artifact links, publisher metrics, hardware direction, license and
  dataset cautions, selection workflow, safe registration handoff, and a model
  contribution template.
- Linked model selection from the README, docs index, setup guide, and AI
  tracker guide while retaining `MODEL_SETUP.md` as registration authority.
- Replaced stale RT-DETR/ONNX code sketches and unqualified FPS/effort claims
  with the actual complete backend acceptance contract.
- Added a docs test that preserves unsupported-backend and non-certification
  boundaries.

## Source Review

Primary sources reviewed on 2026-07-21 include Ultralytics YOLO26, OBB,
RT-DETR, and SAHI documentation; the official DOTA, VisDrone, and SeaDronesSee
projects; the RF-DETR repository; and the linked model publishers' cards and
immutable repository revisions. Metrics in the catalog remain explicitly
publisher-reported rather than reproduced PixEagle results.

## Claim Boundary

No complete external checkpoint was acquired or executed. No model was trusted,
registered, configured, or made a default. No Raspberry Pi, Jetson,
live-camera, tracking-quality, follower, PX4, field, or aircraft result is
claimed.

## Validation

- Documentation contract and local-link gate: 27 passed.
- Existing Ultralytics backend, model registration, and AI readiness tests:
  66 passed.
- All 15 listed direct artifact URLs returned HTTP partial-content success from
  a one-byte availability probe; no checkpoint was retained.
- `git diff --check` passed.

## Next Gate

Keep backend expansion out of the current VPS/bootstrap acceptance path. When
representative aerial videos and target hardware are selected, benchmark
supported YOLO baselines first. Only a material measured gap should open
PXE-0123 implementation.
