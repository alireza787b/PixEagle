# 2026-07-12 Phase 4 GStreamer Output Runtime Closure

## Phase / Slice

- Phase 4 streaming, setup, and operator-observability modernization
- Issues: PXE-0091 done; PXE-0040 remains partial
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Scope: optional OpenCV/GStreamer H.264/RTP/UDP output to QGC/GCS, independent
  output OSD, encoder lifecycle, typed health, runtime diagnostics, and safe
  OpenCV-GStreamer installation

## Outcome

- `GStreamerHandler` validates its immutable output contract, including host,
  port, dimensions, frame rate, bitrate, encoder options, queue bounds, and
  total pixel budget before constructing a pipeline.
- Output frames use bounded cadence and queueing, aspect-preserving
  letterboxing, and a detached frame when output OSD could otherwise mutate
  browser/shared frame memory.
- Browser and QGC/GCS OSD composition now use independent pipeline state.
  `OSDRenderer.sync_frame_size()` also makes alternating output dimensions
  deterministic before cached geometry and sprites are composed.
- Encoder lifecycle transitions are serialized. A timed-out writer release
  retains ownership in a retiring generation, blocks overlapping writers,
  remains retryable, and exposes cleanup state instead of reporting a false
  stop/start success.
- Legacy toggle actions and typed `/api/v1/streams/media-health` now propagate
  start/stop failures and expose typed `cleanup_pending` and `last_error`
  fields.
- `scripts/setup/check-gstreamer-runtime.sh` checks the selected PixEagle venv,
  OpenCV GStreamer capability, and the effective encoder/RTP/UDP plugin set.
- `scripts/setup/build-opencv.sh` now:
  - keeps the active OpenCV runtime until compilation and full staging finish;
  - derives replacement targets from the install manifest;
  - backs up Python and native headers, libraries, CMake/pkg-config metadata,
    share data, tools, and pre-existing manifest targets;
  - rejects symlink escapes, venv-root aliases, `.`/`..` path components,
    empty components, and paths outside the selected canonical venv;
  - fails closed if wheel uninstall or any obsolete artifact removal fails,
    and does not copy staged files after incomplete cleanup;
  - rolls back an incomplete replacement and preserves the backup if rollback
    itself is incomplete;
  - verifies the exact OpenCV version and venv path, GStreamer and FFmpeg build
    flags, instantiated CSRT/KCF trackers, and a non-empty local GStreamer
    `filesink` result before committing the replacement.
- Config defaults, generated schema, setup profiles, installation guidance,
  and video docs now describe one output contract and distinguish browser
  media, GStreamer input, and optional GStreamer UDP output.

## Files Changed

- Runtime/API: `src/classes/gstreamer_handler.py`,
  `src/classes/app_controller.py`, `src/classes/osd_pipeline.py`,
  `src/classes/osd_renderer.py`,
  `src/classes/api_legacy_gstreamer_routes.py`,
  `src/classes/api_v1_streams.py`, and `src/classes/api_v1_contracts.py`.
- Config/setup: `configs/config_default.yaml`, `configs/config_schema.yaml`,
  `scripts/generate_schema.py`, `scripts/init.sh`,
  `scripts/setup/apply-setup-profile.py`,
  `scripts/setup/build-opencv.sh`,
  `scripts/setup/check-gstreamer-runtime.sh`, and `Makefile`.
- Tests: `tests/test_setup_profiles.py`,
  `tests/test_setup_venv_resolution.py`,
  `tests/unit/video/test_gstreamer_handler.py`,
  `tests/unit/core_app/test_app_controller_gstreamer_output.py`,
  `tests/unit/core_app/test_osd_pipeline_multi_output.py`,
  `tests/unit/core_app/test_api_legacy_gstreamer_routes.py`,
  `tests/unit/core_app/test_api_v1_streams.py`, and
  `tests/unit/streaming/test_streaming_lifecycle.py`.
- Documentation: `docs/INSTALLATION.md`, `docs/OPENCV_GSTREAMER.md`,
  `docs/setup/setup-profiles.md`, the active `docs/video/` input,
  GStreamer, streaming, and configuration guides, generated API candidate
  provenance, and modernization reporting records.

## Validation

- Focused runtime/setup/API selection: **228 passed** in 60.24 seconds.
- Exact Phase 0 gate, `make phase0-check PYTHON=.venv/bin/python`:
  **430 passed**, one existing Starlette/httpx deprecation warning, in 68.15
  seconds. This includes shell syntax, schema drift, generated API candidate
  drift, route/security/tool inventory, docs, setup, browser-security, and
  typed stream-health guards.
- Minimum API/reload gate: **54 passed** in 6.39 seconds.
- `tests/test_setup_venv_resolution.py`: **19 passed**, including forced
  artifact-removal failure, symlink escape, and venv-root/component aliases.
- `bash scripts/check_schema.sh`: current, 41 sections and 548 parameters.
- `tools/generate_api_tool_candidates.py --check`: current.
- `bash -n` and ShellCheck for the touched GStreamer setup scripts: passed.
- `git diff --check`: passed.
- Dashboard: 28 suites / 161 tests passed; production build completed. The
  final follow-up only changed shell/setup tests and documentation, not
  dashboard source.

## Independent Review

The review gate iterated on five findings before closure:

1. browser and output OSD pipelines shared renderer dimensions;
2. installer containment did not fully cover symlink escape;
3. a successful cleanup retry retained a stale cleanup error;
4. the build script rewrote a tracked shared helper during startup;
5. host/tune documentation had drift.

Follow-up review then found two additional medium installer integrity gaps:
ignored native cleanup failures and venv-root aliases in manifest paths. Both
were fixed with fail-closed removal checks, strict component validation, and
executable regressions. The final read-only review reported no blocker, high,
medium, or low findings. No subagent remains active.

## Evidence Boundary

On this VPS, the active `.venv` OpenCV 4.13.0 build still reports GStreamer
`NO`. System GStreamer and the software H.264/RTP/UDP elements are present,
but that does not make OpenCV `VideoWriter` output available. Therefore this
checkpoint does **not** claim:

- a live PixEagle GStreamer UDP frame;
- QGC/GCS receipt or playback of UDP/RTP/H.264 output;
- target Raspberry Pi/Jetson build or deployment success;
- Gazebo visual-camera success;
- PX4, SITL, SIH, HIL, follower-response, field, or real-aircraft success.

Those claims require exact target versions/configs, receiver or simulator
artifacts, logs, and operator evidence.

## Next Slice

1. Commit and push this PixEagle checkpoint branch.
2. Commit/push the reviewed generic QGC receiver branch and run exact QGC CI.
3. Verify a replacement Windows installer before deleting the prior artifact;
   keep PR #13594 draft until Windows receiver tests pass.
4. Restart the public PixEagle lab demo from pinned source, preserving the
   current test credential, then verify and monitor HTTP/WebSocket media and
   authorization boundaries.
5. Run target OpenCV-GStreamer build and UDP receiver evidence later on a
   suitable Raspberry Pi/Jetson or reviewed native Linux target.
