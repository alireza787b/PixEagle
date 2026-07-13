# 2026-07-13 Phase 4 Video-File EOF And Replay Safety

## Phase / Slice

- Phase 4 runtime, video, and flight-adjacent safety modernization
- Issue: PXE-0092 done
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Scope: deterministic `VIDEO_FILE` EOF behavior, replay provenance, pacing,
  and Offboard-start safety

## Outcome

- `VideoSource.VIDEO_FILE_EOF_POLICY` is the single source of truth for file
  boundaries. `LOOP` is the checked-in demo default; `STOP` holds the final
  cached frame without reconnection.
- The initialization probe frame is retained and returned in capture order.
- EOF is an explicit state transition. A loop returns a cached,
  command-unusable boundary frame before the first frame of the next playback
  epoch, so a rewind cannot create a fresh command measurement in the same
  call.
- Known frame count/position distinguishes EOF from mid-stream decode failure.
  Unknown-length backends use a bounded three-empty-read ambiguity window;
  any successful read resets it.
- OpenCV seeks are verified. A rejected or non-productive seek receives one
  atomic reopen fallback. Active GStreamer file captures reopen directly
  rather than trusting unsupported random seek. A replacement must be open
  before the previous capture is released.
- Playback status exposes replay provenance, policy, state, epoch, loop count,
  expected frame count, and the bounded ambiguity counter through frame/video
  health diagnostics.
- `DETERMINISTIC_REPLAY` resets PTS pacing when playback epoch changes.
- Video-file replay remains available for tracker UI, OSD, media output, and
  validation, but is never command-fresh for a vision tracker. Offboard-start
  readiness explicitly rejects replay while preserving an external tracker
  contract that declares `requires_video: false`.

## Files Changed

- Runtime/safety: `src/classes/video_handler.py`,
  `src/classes/flow_controller.py`, `src/classes/api_v1_snapshots.py`, and
  `src/classes/config_validator.py`.
- Config/schema: `configs/config_default.yaml`,
  `configs/config_schema.yaml`, and `scripts/generate_schema.py`.
- Tests: `tests/unit/video/test_video_handler.py`,
  `tests/unit/core_app/test_flow_controller_frame_freshness.py`,
  `tests/unit/core_app/test_app_controller_offboard_safety.py`, and
  `tests/unit/test_generate_schema.py`.
- Docs/provenance: active video-file/configuration guides and generated API
  tool-candidate source provenance.

## Validation

- Focused runtime/safety/schema/hygiene selection: **225 passed**.
- Exact Phase 0 gate, `make phase0-check PYTHON=.venv/bin/python`:
  **430 passed**, with one existing Starlette/httpx deprecation warning.
- Generated schema: current at 41 sections / 549 parameters.
- Generated API tool candidate inventory: current; no new callable MCP surface.
- Python compile checks and `git diff --check`: passed.
- Real OpenCV/MP4 probe against `resources/test4.mp4`:
  - frame count: 1613;
  - epoch 0 frames reached verified EOF;
  - one `video_file_eof_loop_boundary` frame was returned at epoch 1;
  - the next call returned frame 0 as `video_file_replay_frame` in epoch 1.
- Broader non-hardware/non-SITL discovery run: **2606 passed**, 40 optional
  dlib skips, one explicit deselection, and two unrelated harness failures.
  Those failures are retained as PXE-0093, not represented as a clean full-suite
  gate for this checkpoint.

## Independent Review

The first review returned NO-GO for three issues: unverified seek, treating all
file read failures as EOF, and recovery reordering the prefetched probe. All
three were fixed with explicit regressions. Follow-up review returned GO and
identified unknown-length metadata as a non-blocking portability concern. The
bounded ambiguity contract and two additional tests closed that concern; final
review returned GO with no blocking finding. The reviewer agent was closed.

## Evidence Boundary

This checkpoint proves deterministic local file handling and process-local
safety contracts only. It does not prove OpenCV-GStreamer target operation,
QGC playback, PX4/SITL/SIH/HIL response, follower performance, field behavior,
or real-aircraft safety.

## Next Slice

1. Stabilize the two full-suite test debts tracked by PXE-0093 and rerun the
   complete non-hardware/non-SITL suite.
2. Replace destructive unknown-key config sync with an explicit, versioned,
   exact-key migration registry; preserve extension/plugin keys and remove the
   retired local GStreamer adjustment keys.
3. Apply the reviewed migration to the ignored VPS config, restart the public
   demo with `VIDEO_FILE_EOF_POLICY: LOOP`, and verify CPU/media/auth behavior.
4. Continue exact QGC CI, official PR, and Windows artifact handoff separately.
