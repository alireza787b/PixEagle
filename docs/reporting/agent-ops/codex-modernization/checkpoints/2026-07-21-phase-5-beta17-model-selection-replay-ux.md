# Phase 5 Checkpoint: Beta.17 Model Selection And Replay UX

- Date: 2026-07-21
- Issue: PXE-0125
- Status: candidate validation in progress
- Scope: evidence-backed VPS feedback only; no PX4, SIH/SITL, QGC, field, or aircraft claim

## Findings

1. The model-selection route durably wrote the chosen trusted artifact, but its
   generic immediate-tier publication skipped model paths classified as
   restart-tier. SmartTracker therefore read stale process defaults on its next
   activation.
2. Device-specific model selection updated only one artifact slot and could
   revert to the previous model on the next Smart Mode lifecycle.
3. The Models UI called both configured standby state and loaded runtime state
   "active", and the compact control discarded the backend action/error result.
4. GStreamer file input used an unsynchronized dropping sink while
   `FlowController` also paced replay. Decode could race to EOF on fast hosts,
   while a simple lossless replacement would make overloaded real-time replay
   lag rather than skip stale frames.
5. The one-line bootstrap prompt and quick-browser wrapper repeated profile,
   credential-path, transport, and cleanup internals before a beginner could
   reach the dashboard.

## Changes

- Model selection now persists and atomically publishes both validated
  SmartTracker artifact variants plus an explicit GPU/CPU preference inside the
  existing rollback transaction. The specialized lifecycle action makes the
  next activation ready immediately.
- Generic Settings-page model-path edits honestly remain `system_restart`;
  they do not claim a SmartTracker restart implementation that does not exist.
- Dashboard state and feedback distinguish **selected** from runtime-proven
  **active**, preserve the backend action, normalize structured errors, and
  refresh both model summaries after a compact-control action.
- Smart Mode activation exposes a bounded operator-facing failure while raw
  loader detail remains in runtime logs.
- GStreamer `VIDEO_FILE` is timing-mode aware: `REALTIME` uses media-clock sync
  with a bounded stale-frame-dropping queue; `DETERMINISTIC_REPLAY` and
  `MAX_THROUGHPUT` use bounded non-dropping decode. `FlowController` subtracts
  capture/decode and processing from one frame budget.
- Bootstrap now asks one access question: Enter starts the detected network lab,
  `2` starts loopback-only, and `3` replaces an unsuitable detected address.
  The compact handoff reports the actual username/password mode and exact UFW/
  credential cleanup command; `VERBOSE=1` retains maintainer diagnostics.

## Validation

- Model, controller, flow, GStreamer, installer, and setup slice: `432 passed`.
- Required API inventory and parameter-reload gate: `72 passed`.
- Exact CI Phase 0 guardrail, including generated API-tool inventory: `145 passed`.
- Documentation infrastructure consistency: `27 passed`.
- Dashboard model hook/page/compact-control tests: `9 passed`.
- Dashboard ESLint gate: passed.
- `bash scripts/check_schema.sh`: 40 sections / 535 parameters, synchronized.
- Python compile, Bash syntax, and `git diff --check`: passed.
- Dashboard production build: passed.
- Two independent focused reviews found nine concrete lifecycle, timing,
  cleanup, error-surface, accessibility, and coverage issues; all blocking and
  bounded findings were repaired before publication.
- The first GitHub run caught test-only ESLint style and stale generated source
  digests. Assertions were split, the canonical tool inventory was regenerated,
  and the exact failed commands passed locally before the corrective push.

## Remaining Gate

Publish the exact candidate, update the disposable VPS without deleting its
credential store or uploaded models, then prove:

1. the uploaded VisDrone and YOLO26-OBB rows report selected state correctly;
2. Smart Mode loads the selected trusted model and reports runtime-active state;
3. GStreamer file replay does not reach EOF early or burst through the media;
4. dashboard login, browser media, and compact installer handoff remain healthy.

The maintainer's separate browser acceptance and later clean Raspberry Pi
walkthrough remain required before the stable release.
