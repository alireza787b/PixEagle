# Raspberry Pi CSI Automatic Capture

Date: 2026-09-19
Slice: Phase 5 / PXE-0171 / issue #19

## Behavior

`GStreamerPipelines.CSI_RPI: auto` is the new default. It opens a direct BGR
pipeline first, then NV12 plus conversion if needed. Each candidate has an
open/read timeout taken from the existing live-source connection setting and
one first-frame probe. Only a nonempty uint8 three-channel frame is accepted.
Failed sources are released before fallback. Both failures are retained in the
error reported through existing degraded startup/recovery. Selection is made
per open/reconnect and recorded in existing media diagnostics.

An explicit pipeline string remains authoritative. Older saved defaults are
also explicit strings; updates preserve them. Adopt auto in Settings or Config
Sync, then restart. No automatic config rewrite or OpenCV rebuild is required.
No source-version or sensor-name list is used.

The [benchmark assessment](2026-09-17-csi-bgr-benchmark-assessment.md) records the
operator-supplied evidence. Implementation was authorized after that assessment;
the additional harness request is not a prerequisite to this code change.

## Files And Validation

- Capture selector: `src/classes/video_handler.py`.
- Default/schema: `configs/config_default.yaml`, generated schema and generator
  description. Existing string field supports both auto and custom pipelines.
- Regression tests: `tests/unit/video/test_gstreamer_pipelines.py` read the real
  default and exercise first-frame success/failure, open/read exceptions,
  release ordering, invalid frame layout, both-fail diagnostics, reconnect,
  custom pipelines and Jetson isolation.
- CSI guides, changelog, journal and issue register aligned.

Validation: `PYTHONPATH=src .venv/bin/pytest -q tests/unit/video
tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py
tests/unit/test_generate_schema.py tests/test_docs_infrastructure_consistency.py`
passed (429 tests). `bash scripts/check_schema.sh`, Python compilation of the
touched modules and `git diff --check` passed. No dashboard code changed.

## Remaining Evidence

No local physical CSI camera is available. Tester CSVs demonstrate direct-BGR
benefit, but automatic native timeout/fallback behavior still needs a target
camera test. OpenCV/GStreamer must honor their native timeout properties;
these are not process-isolation guarantees against a broken driver. First-frame
shape validation cannot establish color accuracy or sustained stability.
Next: Nils updates, selects auto, restarts, and confirms frames and selected
strategy. Jetson optimization and unsupported 60 FPS modes remain separate.
