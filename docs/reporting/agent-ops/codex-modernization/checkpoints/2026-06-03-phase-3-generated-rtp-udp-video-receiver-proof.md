# Phase 3 Checkpoint: Generated RTP/UDP Video Receiver Proof

Date: 2026-06-03  
Phase/slice: Phase 3, PXE-0040 prerequisite  
Status: done for generated RTP/UDP receiver proof; official Gazebo visual SITL remains open  
Claim boundary: video-ingest evidence only. This is not tracker, follower, PX4,
Gazebo, SITL, HIL, field, deployment, service-install, or real-aircraft
validation.

## Summary

PixEagle now has an executable generated H.264 RTP/UDP receiver proof before
any Gazebo camera evidence is accepted.

This slice also fixed a real video-path hazard found during proof scouting:
OpenCV's GStreamer backend can block on UDP receiver open/read calls when no
sender is available or after the sender stops. `VideoHandler` now keeps
UDP/GStreamer open/read calls in a daemon async reader so the main frame path
can return cached/stale status as `usable_for_following=false` instead of
freezing.

Independent review found blockers after the first pass. This checkpoint records
the repaired version:

- async UDP reconnect/release now uses per-reader stop events and generation
  ownership so a still-blocked old reader cannot prevent a fresh reconnect;
- runtime proof acceptance now requires an actual `udp_async_frame_stale` status
  with `frame_age_seconds >= stale_timeout_seconds`;
- the receiver contract now includes `clock-rate=90000` and enforces caps
  ordering before `rtph264depay`;
- execute attempts write manifests for incomplete runtime prerequisites;
- the important evidence files are copied into tracked reporting evidence, not
  only the git-ignored `reports/` runtime directory.

## Files Changed

- `src/classes/video_handler.py`
  - Added asynchronous UDP/GStreamer reader ownership.
  - `get_frame()` no longer calls blocking OpenCV reads directly for
    `UDP_STREAM` + `USE_GSTREAMER=true`.
  - Post-stop/no-new-frame statuses distinguish fresh, awaiting new frame, and
    stale cached frames.
- `tools/run_udp_video_receiver_proof.py`
  - Added dry-run default contract validation.
  - Added guarded execute mode requiring `--execute --allow-process-start`.
  - Runtime execute starts only a local `gst-launch-1.0 videotestsrc` H.264 RTP
    sender and writes evidence artifacts under `reports/video/`.
  - Execute attempts write a `manifest.json` even when runtime prerequisites are
    incomplete.
- `configs/config_default.yaml`
  - Upgraded the checked-in UDP receiver template to explicit H.264 RTP caps,
    `clock-rate=90000`, `h264parse`, and
    `appsink drop=true max-buffers=1 sync=false`.
- `configs/config_schema.yaml`
  - Regenerated from checked-in defaults.
- `Makefile`
  - Added `video-udp-proof-dry-run` and `video-udp-proof-execute`.
- `tests/test_udp_video_receiver_proof.py`
  - Added proof-tool dry-run, guarded execute, side-effect boundary, and weak
    pipeline rejection tests.
  - Added default-template parsing, caps-ordering, strict stale-gate, and
    incomplete-manifest tests.
- `tests/unit/video/test_gstreamer_pipelines.py`
  - Added a real UDP pipeline contract test using `VideoHandler`.
- `tests/unit/video/test_video_handler.py`
  - Added async UDP initialization, reconnect-generation, and stale/unusable
    status tests.
- `docs/video/02-input-sources/udp-stream.md`
- `docs/video/03-gstreamer/input-pipelines.md`
- `docs/video/03-gstreamer/pipeline-reference.md`
- `docs/video/01-architecture/video-handler.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
  - Updated UDP/GStreamer contract, async loss behavior, proof commands, and
    no-overclaim boundaries.
- `src/tools/gstreamer_tests/receive_from_rdp.sh`
- `src/tools/gstreamer_tests/gstreamdl_receiver_rtp.bat`
  - Updated helper receive pipelines to the same H.264 RTP caps/depay/parse
    shape.

## Runtime Evidence

Guarded local command run:

```bash
python3 tools/run_udp_video_receiver_proof.py \
  --execute \
  --allow-process-start \
  --artifact-root reports/video \
  --run-id 20260603T-pxe0040-generated-rtp-udp-proof-v2 \
  --port 5636 \
  --json
```

Result: `passed`

Evidence directory:

```text
reports/video/20260603T-pxe0040-generated-rtp-udp-proof-v2/
```

Portable tracked evidence copy:

```text
docs/reporting/agent-ops/codex-modernization/evidence/2026-06-03-pxe0040-generated-rtp-udp-video-receiver-proof/
```

Important artifacts:

- `manifest.json`
- `source_config.json`
- `receiver_pipeline.txt`
- `sender_pipeline.txt`
- `post_stop_frame_status_sequence.json`
- `frame_hashes.json`
- `runtime.json`

Observed evidence:

- OpenCV runtime: `4.6.0`
- OpenCV GStreamer: enabled
- `gst-launch-1.0`: `/usr/bin/gst-launch-1.0`
- GStreamer: `1.24.2`
- Git HEAD at proof time: `eac9d010c0040d9d4cd38aaaf50c27f0996c7308`
- Receiver pipeline:
  - `udpsrc`
  - explicit `application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000`
  - `rtph264depay`
  - `h264parse`
  - `avdec_h264`
  - BGR conversion
  - `videoscale`
  - `width=320,height=240`
  - `appsink drop=true max-buffers=1 sync=false`
- Fresh frames: 8 of 8 requested.
- Frame dimensions: all `[240, 320, 3]`.
- First frame hash:
  `7ea59dfc68dcea8b17deea9d980a1d7fa84ff0facae3a59862b888f52b899952`
- Last frame hash:
  `e258a7fcef6add72dd36d542a00db0ace9f87773d6d2c7888db09ac725c6d0e1`
- After sender stop, `VideoHandler.get_frame_status()` reported cached/stale
  frames with `usable_for_following=false`, including strict accepted statuses
  with `reason=udp_async_frame_stale` and `frame_age_seconds >= 0.6`.
- Sender exit code was `-15` because the proof intentionally terminates the
  local sender after capture; the manifest records `sender_stop_expected=true`.

## Validation

Passed:

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  tools/run_udp_video_receiver_proof.py \
  tools/run_sitl_validation_suite.py \
  src/classes/video_handler.py \
  tests/test_udp_video_receiver_proof.py \
  tests/unit/video/test_gstreamer_pipelines.py \
  tests/unit/video/test_video_handler.py
```

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_udp_video_receiver_proof.py \
  tests/unit/video/test_gstreamer_pipelines.py \
  tests/unit/video/test_video_handler.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py -q
```

Result after reviewer fixes: 112 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHON=/tmp/pixeagle-audit-venv/bin/python \
  make video-udp-proof-dry-run
```

Result: passed; dry-run JSON reported `would_start_processes=false` and
receiver contract valid.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
```

Result: schema up to date.

```bash
git diff --check
```

Result: passed with CRLF normalization warning for the edited Windows
GStreamer helper, no whitespace errors.

Broader focused suite:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py \
  tests/test_udp_video_receiver_proof.py \
  tests/unit/video/test_gstreamer_pipelines.py \
  tests/unit/video/test_video_handler.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py -q
```

Result after reviewer fixes: 172 passed, 1 skipped.

Additional checks after reviewer fixes:

```bash
rg --pcre2 -n "application/x-rtp(?!,media=video,encoding-name=H264,payload=96,clock-rate=90000)|encoding-name=H264,payload=96(?!,clock-rate=90000)" configs docs src tools
```

Result: no active config/docs/source/tool matches outside intentional proof
tests and archived checkpoint/evidence text.

```bash
ps -eo pid,ppid,pgid,stat,etime,cmd | rg -n "run_udp_video_receiver_proof|gst-launch-1.0|5636|pixeagle-udp-gstreamer-reader"
```

Result: no leftover proof or GStreamer sender processes.

Not run:

- Docker/PX4 runtime
- PX4 SIH or Gazebo container execution
- SITL scenario execution against a full PixEagle/PX4 stack
- GitHub Actions hosted workflow
- tracker/follower/PX4 visual SITL
- HIL, field, real aircraft, deployment, or service installation

## Risks And Open Questions

- The local venv OpenCV remains `4.13.0` without GStreamer support, so guarded
  runtime proof uses system `python3` where OpenCV `4.6.0` has GStreamer
  enabled. The Makefile exposes `VIDEO_PROOF_PYTHON` for this reason.
- The async UDP reader prevents the main frame path from blocking, but a daemon
  reader thread may remain blocked in OpenCV if the process opens a UDP receiver
  without any sender and then shuts down immediately. This is bounded at process
  level and preferable to blocking the control/frame loop, but a future native
  GStreamer appsink implementation could provide cleaner cancellation.
- This proof does not validate tracker accuracy, follower response, Offboard
  behavior, PX4 telemetry, Gazebo camera export, HIL, or field operation.

## Next Slice

Continue PXE-0040 with the official Gazebo visual SITL profile:

- checked-in visual SITL plan using official `px4io/px4-sitl-gazebo:<tag>`;
- `HEADLESS=1` where supported;
- camera-capable model such as `gz_x500_mono_cam` or `gz_x500_gimbal`;
- simulated RTP/H.264 video on UDP `5600` through the now-proven
  UDP/GStreamer path;
- tracker/follower/command traces plus PX4 params, ULog/tlog, logs, route
  profile, and config snapshots;
- no fallback to unofficial Gazebo images unless the official image is proven
  insufficient and the missing capability is documented.
