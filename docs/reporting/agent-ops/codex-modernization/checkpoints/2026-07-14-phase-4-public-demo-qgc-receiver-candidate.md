# 2026-07-14 Phase 4 Public Demo And QGC Receiver Candidate

## Phase / Slice

- Phase 4 runtime/configuration evidence and QGC interoperability handoff
- Issue: PXE-0095 in progress pending manual Windows receiver acceptance
- PixEagle branch: `codex/modernization-pxe0040-runtime-20260604`
- PixEagle runtime commit: `cf16411a54e5570fa2eaabb343d544c492de6ae0`
- QGroundControl candidate commit: `ab5213f4f69c5b07494f101226db384b48af1e4f`
- QGroundControl PR: <https://github.com/mavlink/qgroundcontrol/pull/13594>

## Outcome

The transactional configuration slice is now deployed to the temporary public
lab bench, the exact QGroundControl candidate passed its critical pre-promotion
CI gates, PR #13594 points to that candidate, and a checksummed Windows AMD64
installer is available for manual receiver testing. This is a lab candidate,
not a release, production deployment, or flight-readiness claim.

## PixEagle Source And Live Configuration

The completed PixEagle changes were committed and pushed as:

- `dfe1e6e7` - transactional, versioned configuration authority;
- `8bc87e61` - accurate public-lab authentication startup diagnostic;
- `753d49c3` - accurate optional dlib readiness diagnostic;
- `cf16411a` - current QGC actual-feed lab guidance.

Before migration, the ignored live config was copied to the owner-only file
`/home/alireza/PIXEAGLE_LIVE_CONFIG_PRE_PXE0094_2026-07-14.yaml` with SHA-256
`88c3fc36e07b3942a41858f1bc227b708c72b7a964ba9f043052a18cb286ea9d`.
The existing browser user file and password were not replaced or printed.

The real authenticated config API produced a contract-v2 preview and applied
the exact seven-operation plan:

- added `GStreamer.GSTREAMER_INCLUDE_OSD`;
- added `VideoSource.VIDEO_FILE_EOF_POLICY`;
- removed registered retirements `GStreamer.GSTREAMER_CONTRAST`,
  `GStreamer.GSTREAMER_BRIGHTNESS`, `GStreamer.GSTREAMER_SATURATION`,
  `Tracking.APPEARANCE_CONFIDENCE_THRESHOLD`, and
  `BOUNDARY_MARGIN_PIXELS`.

The preview reported zero changed defaults and zero unknown extensions. The
apply created managed backup
`configs/backups/config_20260714_131213_316460_9ynyq18y.yaml`. A post-apply
report has zero actionable operations. The resulting ignored config is mode
`0600`, owner `alireza:alireza`, and has SHA-256
`44bab2b07ef7e557bc21573d1640ff3705d9fd29b706bed09ecf4da0325d072c`.

The active lab-specific settings intentionally retain:

- browser-session authentication for dashboard/API users;
- anonymous access only to the two actual-feed media endpoints;
- exact public Host authority and browser Origin policy;
- `VIDEO_FILE` with `VIDEO_FILE_EOF_POLICY: LOOP`;
- no production TLS claim.

## Public Runtime Evidence

The current tmux run is
`pixeagle_20260714T132818Z_558897`, started from clean commit `cf16411a`.
The temporary public lab endpoints are:

- dashboard: `http://204.168.181.45:3040`;
- backend: `http://204.168.181.45:5077`;
- HTTP MJPEG: `http://204.168.181.45:5077/video_feed`;
- WebSocket JPEG: `ws://204.168.181.45:5077/ws/video_feed`.

Exact public probes verified:

- dashboard returned HTTP 200;
- unauthenticated `/status` returned HTTP 401;
- the preserved admin browser login returned HTTP 200;
- anonymous MJPEG returned a complete 22668-byte JPEG;
- anonymous WebSocket returned JSON frame metadata followed by the same
  complete JPEG;
- a WebSocket request with `Origin: http://evil.example` was rejected with
  HTTP 403;
- the video-file source crossed at least 16 loop boundaries without a frame
  read failure, consecutive-failure escalation, or recovery attempt.

Authenticated Playwright navigation at 1440x900 and 390x844 covered Dashboard,
Tracker, Follower, Settings, and Logs. The SPA run had zero horizontal
overflow, console errors, page errors, failed requests, or HTTP 5xx responses.
Screenshots are retained under `/tmp/pixeagle-live-ui-20260714` for this VPS
session. The one aborted OSD request observed in an earlier full-document reload
harness did not reproduce with normal SPA navigation or a steady 12-second
session.

The runtime intentionally reports degraded external dependencies:
MAVLink2REST/PX4 are disconnected, MAVSDK Server is waiting for UDP 14540, and
optional PyTorch/Ultralytics/dlib plus OpenCV-GStreamer are not installed on
this VPS. The lab exposure diagnostic is deliberately high severity. One input
dimension mismatch and one adaptive OSD downgrade warning were observed; no
unhandled traceback, frame failure, or recovery loop was observed.

## QGroundControl Candidate

The QGC candidate is generic and contains no PixEagle-specific behavior. It
adds multipart MJPEG over HTTP/HTTPS and one-complete-JPEG-per-binary-message
WebSocket video over WS/WSS. Its reviewed boundary includes:

- None, Basic, and Bearer authentication;
- session-only secrets and an owner-only file option on supported Unix desktop
  systems;
- optional exact Origin and custom CA settings;
- rejection/redaction of URL credentials and common token query parameters;
- strict TLS, redirect restrictions, JPEG/frame/image bounds;
- MKV/MOV recording and early rejection of unsupported JPEG-to-MP4 recording;
- camera-free synthetic HTTP/WebSocket sources and receiver/security/lifecycle
  tests;
- source-disconnect recording finalization before pipeline teardown.

Before promotion, the branch was exactly zero commits behind and nine commits
ahead of upstream `master`. The old PR head `b98848b2c` was replaced only with
an explicit force-with-lease, and PR #13594 is mergeable but remains draft.
Its stale description/title were replaced with the current generic scope,
accurate test claims, and QGC's current PR template. A maintainer-facing update
comment is at
<https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4969812708>.

Exact pre-promotion CI on `ab5213f4f` includes:

- Linux run `29334848451`: 183 unit tests and 49 integration tests passed;
  `GStreamerTest` passed, including source-EOS recording finalization;
- Windows run `29334848113`: AMD64, ARM64, and cross-compiled ARM64 builds
  passed; the AMD64 installer was created, installed, and its installed
  executable verified after removing the build GStreamer SDK from `PATH`;
- macOS run `29334848317` passed;
- pre-commit, CodeQL, docs, Doxygen, links, CI scripts, custom build, and iOS
  passed on the same candidate;
- the fork-only dependency-review failure was an unavailable repository
  dependency graph, while the promoted upstream dependency review passed.

The upstream full matrix was still running when this checkpoint was written.
The exact critical pre-promotion gates above are green; this document does not
convert pending upstream jobs into pass claims.

## Windows Artifact

The retained exact-head artifact is:

- file: `QGroundControl-PR13594-ab5213f4f-AMD64.exe`;
- size: 144790567 bytes;
- SHA-256:
  `c84467e514c4db696e3431248471d912d3933ab40de69fd778445a618e6de6e2`;
- public temporary URL:
  `http://204.168.181.45:3040/downloads/QGroundControl-PR13594-ab5213f4f-AMD64.exe`;
- checksum URL:
  `http://204.168.181.45:3040/downloads/SHA256SUMS.txt`.

The server reports the expected byte count and PE/NSIS content type. A complete
download through the public URL reproduced the artifact SHA-256. The July 9
installer was removed only after the replacement was downloaded and verified.
The public transport is plaintext HTTP, so the tester must verify the SHA-256
before execution and use a test Windows environment.

## Review And Evidence Boundary

Earlier independent/adversarial reviews drove the config write-receipt,
external-writer, URL-secret, tracker/model barrier, GStreamer lifecycle, and
QGC recording-finalization fixes. The final delegated re-review quota was not
available for this resumed checkpoint, so no new independent-agent GO is
claimed. The recorded basis is line-level review, focused and full suites,
exact CI artifacts, public protocol probes, and browser evidence.

This checkpoint does not claim:

- manual Windows HTTP/WebSocket playback, reconnect, source switching, or
  MKV/MOV recording acceptance;
- WebRTC over public HTTP;
- production HTTPS/WSS, reverse-proxy, firewall, or credential handling;
- OpenCV-GStreamer target output or QGC H.264/RTP/UDP receipt;
- PX4, SIH, SITL, Gazebo, X-Plane, HIL, hardware, field, or aircraft success;
- Raspberry Pi clean installation or release/tag readiness.

## Next Gate

1. Test the exact Windows installer against both public actual-feed endpoints,
   including HTTP/WS switching, reconnect behavior, and playable MKV/MOV files.
2. Keep PR #13594 draft until that evidence and the promoted-head critical CI
   checks are accepted; attach concise results to the PR afterward.
3. Continue monitoring the PixEagle run and export the runtime log bundle if a
   tester observes a failure.
4. After tester acceptance, stop the public bench, disable anonymous media,
   rotate/delete the temporary browser credential, and remove the temporary
   installer exposure.
5. Rerun the clean setup/update walkthrough on a fresh Raspberry Pi or matching
   companion target before any tag or release.
