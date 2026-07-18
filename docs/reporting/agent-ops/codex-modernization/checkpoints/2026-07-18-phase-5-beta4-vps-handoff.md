# Phase 5 Checkpoint: Beta.4 VPS Handoff

**Date:** 2026-07-18  
**Slice:** PXE-0106 / PXE-0074  
**Status:** Ready for maintainer VPS retest; fresh Ubuntu remains the next gate

## Scope

This checkpoint closes the bounded beta.4 release and handoff preparation
slice. It does not claim PX4, SIH, SITL, HIL, follower, QGC receiver, WebRTC,
field, or real-aircraft readiness. The public process is a browser/media bench
only and is intentionally kept running for maintainer acceptance.

## Source And Runtime

- Release: `v7.0.0-beta.4`
- Exact code commit: `f16133de76b5aa490046f2650b570ea92052d48b`
- `origin/main` points to the same commit; the annotated tag dereferences to the
  same commit.
- GitHub release: <https://github.com/alireza787b/PixEagle/releases/tag/v7.0.0-beta.4>
- Public dashboard: `http://204.168.181.45:3040/`
- Backend/media authority: `http://204.168.181.45:5077`
- Runtime run ID: `pixeagle_manual_f6549d79-e917-454c-86ee-d12a2dfb9230`
- `make status`: healthy; Dashboard and MainApp are alive.

The active operator configuration is the explicit browser lab profile:

- video source: looping `resources/test4.mp4`;
- default tracker: CSRT with TemplateMatching detector;
- browser-session API authentication remains enabled;
- anonymous media is enabled only for `/video_feed` and `/ws/video_feed`;
- MAVSDK Server and MAVLink2REST sidecars are intentionally not started in this
  browser-only launch;
- WebRTC is not the default public-IP transport; Auto uses WebSocket here;
- the existing owner-only browser credential file was preserved byte-for-byte
  and is not copied into this report.

The runtime log therefore correctly reports MAVLink/PX4 as disconnected. That
is an expected profile boundary, not evidence of a PX4 failure or success.

## Live Probes

The following bounded probes were run against the public address:

| Probe | Result |
| --- | --- |
| Dashboard `GET /` | HTTP 200 |
| Unauthenticated `GET /api/v1/system/about` | HTTP 401 |
| `GET /video_feed` | HTTP 200, multipart MJPEG, JPEG marker received |
| `WS /ws/video_feed` | metadata text followed by binary JPEG frame |
| Runtime streaming stats | frames sent, zero drops in sampled intervals |
| Schema/config sync status | schema `1.4.0`, no actionable sync operations |

The controlled config migration removed exactly the four registered retired
detector keys while the runtime was stopped. It created the owner-only backup
`configs/backups/config_20260718_140651_636243_de92m9zh.yaml`; no credentials
were rotated or printed.

## Clean Setup Handoff

The no-touch clean-checkout walkthrough passed **23/23** checks at the exact
beta.4 commit. It covered required files, shell syntax, schema generation,
binary download planning, local/QGC/demo/production profile dry-runs, quick
demo cleanup dry-run, minimum API tests, and clean initial/final checkout
state. Evidence is retained at:

`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-18-pxe0074-beta4-clean-handoff-no-update/manifest.json`

The updater check was intentionally omitted from that run because the public
runtime was live. A separate attempt correctly refused with the documented
"PixEagle must be stopped" guard after detecting the active ports. This is a
lifecycle safety result, not a failed update implementation.

The VPS has the optional CPU AI stack and verified local `yolo26n.pt` model:
PyTorch, Ultralytics, LAP, and OpenCV CSRT/KCF are available; CUDA, GStreamer,
dlib, NCNN, and PNNX are not available on this host. The current demo does not
claim SmartTracker execution merely because the model is installed. A Smart
tracker acceptance run must be selected explicitly and recorded separately.

## Maintainer VPS Retest

Use the dashboard URL above and the existing private demo credentials. Do not
paste the password into an issue, report, URL, or chat log.

1. Confirm the video is visible on the Live Feed page. Test Auto, then the
   WebSocket/MJPEG choices where the UI exposes them. VLC can test HTTP MJPEG;
   raw `ws://` is a frame protocol and requires the QGC draft receiver or a
   WebSocket JPEG client.
2. Click a visible target with the default point-selection behavior. Confirm
   the seed rectangle is visibly larger than the old beta behavior and the
   tracker starts.
3. While tracking or retrying, click a different target twice. The latest
   selection should replace the pending/previous target instead of producing an
   `already active` rejection. Record the target, tracker mode, and any error
   text if this fails.
4. Exercise SmartTracker only after selecting it in the tracker control. Record
   whether model readiness, detection, click selection, loss, and retry are
   distinct states.
5. Check tracker switching, settings save/restart warning, full-screen media,
   mobile layout, dark stream controls, numeric formatting, and the Logs export
   metadata. These are operator acceptance checks, not automated release proof.
6. Do not start a follower from replay video unless the UI explicitly shows the
   reviewed safety override and its reason. This VPS run has no PX4/MAVLink
   vehicle and cannot validate autonomous following.

Report the exact action sequence and approximate UTC time for any failure. The
runtime session logs are retained under the run ID above for correlation.

## Remaining Gates

- User acceptance of the public beta4 browser/tracker behavior.
- Fresh Ubuntu installation using the maintained installation guide.
- Raspberry Pi 5 Core, optional Full/AI, and board-specific video/GStreamer
  evidence.
- Recorded-video tracker robustness benchmark (acquisition, retarget, loss,
  redetection, false reacquisition, and latency).
- PX4/SIH/SITL/HIL and follower-in-loop evidence.
- QGroundControl draft PR manual receiver evidence and PR maintainer review.
- Authenticated production HTTPS/WSS and WebRTC ICE/TURN evidence.

These are explicit next gates, not hidden legacy work. Minor nonblocking
toolchain debt remains tracked as PXE-0021; no new debt was introduced by this
handoff slice.

